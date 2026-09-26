from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DbSession, require
from app.core.auditoria import auditar
from app.core.rate_limit import limitar
from app.core.respuestas import ApiError, ApiResponse, ok
from app.apps.capacidad.models import Analisis, Cubrimiento, CubrimientoDecision, ProgramacionCarga, Puesto, Turno, Ubicacion, Usuario
from app.apps.capacidad.models.cubrimientos import APROBADO, JUSTIFICADO, PENDIENTE, RECHAZADO
from app.apps.capacidad.models.maestros import TRABAJO
from app.apps.capacidad.schemas.f1 import PuestoOut
from app.apps.capacidad.services import cubrimientos as svc

router = APIRouter(prefix="/cubrimientos", tags=["cubrimientos (nómina)"])


class CubrimientoOut(BaseModel):
    id: int
    puesto: PuestoOut
    fecha: date
    cedula: str
    nombre: str
    codigo_turno: str
    horas: Decimal
    puesto_titular: str | None
    motivo: str
    referencia: list[dict]
    genera_exceso: bool
    doble_turno: bool
    estado_auto: str
    estado: str  # estado final: decisión de nómina si existe, si no el automático
    comentario: str | None = None
    decidido_por: str | None = None
    decidido_en: datetime | None = None


class DecisionIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)
    estado: str = Field(pattern="^(aprobado|rechazado|pendiente)$")  # pendiente = deshacer la decisión
    comentario: str = Field(default="", max_length=1000)


class PersonaBolsaOut(BaseModel):
    cedula: str
    nombre: str
    bolsas: list[str]
    dias_sin_puesto: list[str]
    horas_sin_puesto: float
    dias_en_puesto: int


def _analisis(db: DbSession, analisis_id: int) -> tuple[Analisis, ProgramacionCarga]:
    a = db.get(Analisis, analisis_id)
    if a is None:
        raise ApiError(404, "Análisis no encontrado")
    return a, db.get(ProgramacionCarga, a.carga_id)


def _clave(c: Cubrimiento) -> tuple[str, int, date]:
    return (c.cedula, c.puesto_id, c.fecha)


def _decisiones(db: DbSession, carga: ProgramacionCarga) -> dict[tuple[str, int, date], CubrimientoDecision]:
    return {
        (d.cedula, d.puesto_id, d.fecha): d
        for d in db.scalars(select(CubrimientoDecision).where(CubrimientoDecision.anio == carga.anio, CubrimientoDecision.mes == carga.mes))
    }


def _out(c: Cubrimiento, d: CubrimientoDecision | None, usuarios: dict[int, str]) -> CubrimientoOut:
    return CubrimientoOut(
        id=c.id, puesto=PuestoOut.model_validate(c.puesto), fecha=c.fecha, cedula=c.cedula, nombre=c.nombre,
        codigo_turno=c.codigo_turno, horas=c.horas, puesto_titular=c.puesto_titular, motivo=c.motivo,
        referencia=c.referencia, genera_exceso=c.genera_exceso, doble_turno=c.doble_turno, estado_auto=c.estado_auto,
        estado=d.estado if d else c.estado_auto, comentario=d.comentario if d else None,
        decidido_por=usuarios.get(d.usuario_id) if d and d.usuario_id else None, decidido_en=d.decidido_en if d else None,
    )


@router.get("/{analisis_id}", response_model=ApiResponse[list[CubrimientoOut]])
def listar(analisis_id: int, db: DbSession, estado: str = Query("", max_length=20), motivo: str = Query("", max_length=20),
           q: str = Query("", max_length=100), solo_doble: bool = False, solo_exceso: bool = False,
           _=Depends(require("capacidad.analisis.ver"))):
    a, carga = _analisis(db, analisis_id)
    consulta = (select(Cubrimiento).join(Cubrimiento.puesto).join(Puesto.ubicacion)
                .where(Cubrimiento.analisis_id == a.id).order_by(Cubrimiento.fecha, Puesto.codigo, Cubrimiento.nombre))
    if motivo:
        consulta = consulta.where(Cubrimiento.motivo == motivo)
    if solo_doble:
        consulta = consulta.where(Cubrimiento.doble_turno.is_(True))
    if solo_exceso:
        consulta = consulta.where(Cubrimiento.genera_exceso.is_(True))
    if q.strip():
        patron = f"%{q.strip()}%"
        consulta = consulta.where(Cubrimiento.nombre.ilike(patron) | Cubrimiento.cedula.ilike(patron)
                                  | Puesto.codigo.ilike(patron) | Ubicacion.nombre.ilike(patron))
    decisiones = _decisiones(db, carga)
    usuarios = {u.id: u.nombre for u in db.scalars(select(Usuario))}
    lista = [_out(c, decisiones.get(_clave(c)), usuarios) for c in db.scalars(consulta).unique()]
    conteo = {e: sum(1 for c in lista if c.estado == e) for e in (PENDIENTE, JUSTIFICADO, APROBADO, RECHAZADO)}
    if estado:
        lista = [c for c in lista if c.estado == estado]
    return ok(lista, total=len(lista), por_estado=conteo, horas=float(sum(c.horas for c in lista)))


@router.post("/{analisis_id}/decidir", response_model=ApiResponse[dict], dependencies=[Depends(limitar("cubrimientos", 60, 60))])
def decidir(analisis_id: int, data: DecisionIn, request: Request, db: DbSession,
            actual: Usuario = Depends(require("capacidad.cubrimientos.aprobar"))):
    a, carga = _analisis(db, analisis_id)
    if data.estado == RECHAZADO and not data.comentario.strip():
        raise ApiError(400, "Indique el motivo del rechazo en el comentario")
    cubs = list(db.scalars(select(Cubrimiento).where(Cubrimiento.analisis_id == a.id, Cubrimiento.id.in_(data.ids))))
    if len(cubs) != len(set(data.ids)):
        raise ApiError(404, "Algún cubrimiento no pertenece a este análisis")
    decisiones = _decisiones(db, carga)
    for c in cubs:
        d = decisiones.get(_clave(c))
        if data.estado == PENDIENTE:
            if d:
                db.delete(d)
            continue
        if d is None:
            d = CubrimientoDecision(anio=carga.anio, mes=carga.mes, cedula=c.cedula, puesto_id=c.puesto_id, fecha=c.fecha)
            db.add(d)
        d.estado, d.comentario, d.usuario_id = data.estado, data.comentario.strip(), actual.id
        d.decidido_en = datetime.now(timezone.utc)
    auditar(db, request, "cubrimientos_decididos", actual.id, analisis_id=a.id, estado=data.estado, cantidad=len(cubs),
            comentario=data.comentario.strip()[:200])
    db.commit()
    return ok({"actualizados": len(cubs), "estado": data.estado})


@router.get("/{analisis_id}/bolsas", response_model=ApiResponse[list[PersonaBolsaOut]])
def bolsas(analisis_id: int, db: DbSession, todas: bool = False, _=Depends(require("capacidad.analisis.ver"))):
    """Personas programadas en bolsas (disponibles, relevantes…) los días que no cubren ningún puesto."""
    a, carga = _analisis(db, analisis_id)
    franjas = {t.codigo: [(f.inicio, f.fin) for f in t.franjas] for t in db.scalars(select(Turno)) if t.clase == TRABAJO}
    lista = svc.personas_en_bolsa(db, carga.id, svc.horas_por_turno(franjas), todas)
    return ok([PersonaBolsaOut(**p.__dict__) for p in lista], total=len(lista),
              horas=round(sum(p.horas_sin_puesto for p in lista), 1))
