"""Turnos, festivos y parámetros del liquidador."""

from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import or_, select

from app.api.deps import DbSession, require
from app.core.auditoria import auditar
from app.core.paginacion import Paginacion, paginar_consulta
from app.core.respuestas import ApiError, ApiResponse, ok
from app.models import Usuario
from app.apps.liquidador.dominio.matriz import build_shift_matrix
from app.apps.liquidador.dominio.tipos import CONCEPT_LABELS, DAY_LABELS, DAY_SHORT_LABELS
from app.apps.liquidador.models import LiqFestivoAjuste, LiqTurno
from app.apps.liquidador.schemas import (
    FestivoIn, FestivoOut, ParametrosIn, ParametrosOut, TurnoDetalle, TurnoIn, TurnoOut, VistaPreviaIn,
)
from app.apps.liquidador.services import festivos as svc_festivos
from app.apps.liquidador.services import turnos as svc_turnos
from app.apps.liquidador.services.calculo import clase_de

router = APIRouter(tags=["liquidador: configuración"])
VER = "liquidador.turnos.ver"
GESTIONAR = "liquidador.turnos.gestionar"


def _turno_out(t: LiqTurno, detalle: bool = False) -> TurnoOut:
    datos = TurnoOut.model_validate(t).model_dump() | {"clase": clase_de(t)}
    return TurnoDetalle(**datos, matriz=t.matriz or {}) if detalle else TurnoOut(**datos)


# --- Parámetros ----------------------------------------------------------------

@router.get("/parametros", response_model=ApiResponse[ParametrosOut])
def ver_parametros(db: DbSession, _=Depends(require(VER))):
    p = svc_turnos.parametros(db)
    db.commit()
    return ok(p)


@router.put("/parametros", response_model=ApiResponse[ParametrosOut])
def guardar_parametros(data: ParametrosIn, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    p = svc_turnos.parametros(db)
    anterior = p.hora_inicio_nocturna
    regenerados = 0
    if data.hora_inicio_nocturna != anterior:
        p.hora_inicio_nocturna = data.hora_inicio_nocturna
        db.flush()
        # Cambia el reparto diurno/nocturno de todos los turnos
        regenerados = svc_turnos.regenerar_todos(db, data.hora_inicio_nocturna)
    auditar(db, request, "liq_parametros", actual.id, antes=anterior, despues=data.hora_inicio_nocturna, turnos=regenerados)
    db.commit()
    return ok(p, turnos_regenerados=regenerados)


# --- Turnos --------------------------------------------------------------------

@router.get("/turnos/etiquetas", response_model=ApiResponse[dict])
def etiquetas(_=Depends(require(VER))):
    """Nombres de los 12 conceptos y los 8 tipos de día, en el orden de la matriz."""
    return ok({"conceptos": {c.value: n for c, n in CONCEPT_LABELS.items()},
               "tipos_dia": {d.value: n for d, n in DAY_LABELS.items()},
               "tipos_dia_corto": {d.value: n for d, n in DAY_SHORT_LABELS.items()}})


@router.get("/turnos", response_model=ApiResponse[list[TurnoOut]])
def listar_turnos(db: DbSession, p: Paginacion, q: str = Query("", max_length=80), inactivos: bool = True,
                  _=Depends(require(VER))):
    consulta = select(LiqTurno).order_by(LiqTurno.codigo)
    if q.strip():
        patron = f"%{q.strip()}%"
        consulta = consulta.where(or_(LiqTurno.codigo.ilike(patron), LiqTurno.nombre.ilike(patron)))
    if not inactivos:
        consulta = consulta.where(LiqTurno.activo.is_(True))
    turnos, meta = paginar_consulta(db, consulta, p)
    return ok([_turno_out(t) for t in turnos], **meta)


@router.get("/turnos/{turno_id}", response_model=ApiResponse[TurnoDetalle])
def ver_turno(turno_id: int, db: DbSession, _=Depends(require(VER))):
    return ok(_turno_out(_turno(db, turno_id), detalle=True))


@router.post("/turnos/vista-previa", response_model=ApiResponse[dict])
def vista_previa(data: VistaPreviaIn, db: DbSession, _=Depends(require(VER))):
    """Matriz que tendría un turno con estos datos, sin guardarlo."""
    ordinarias, extras = (0, 0) if data.incapacidad else (data.horas_ordinarias, data.horas_extras)
    return ok(build_shift_matrix(ordinarias, extras, data.hora_inicio, svc_turnos.parametros(db).hora_inicio_nocturna))


@router.post("/turnos", response_model=ApiResponse[TurnoDetalle], status_code=201)
def crear_turno(data: TurnoIn, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    _codigo_libre(db, data.codigo)
    t = svc_turnos.guardar(db, LiqTurno(), **data.model_dump())
    auditar(db, request, "liq_turno_creado", actual.id, **data.model_dump(mode="json"))
    db.commit()
    return ok(_turno_out(t, detalle=True))


@router.put("/turnos/{turno_id}", response_model=ApiResponse[TurnoDetalle])
def editar_turno(turno_id: int, data: TurnoIn, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    t = _turno(db, turno_id)
    _codigo_libre(db, data.codigo, turno_id)
    antes = TurnoOut.model_validate(t).model_dump(mode="json")
    svc_turnos.guardar(db, t, **data.model_dump())
    auditar(db, request, "liq_turno_editado", actual.id, turno=t.codigo, antes=antes, despues=data.model_dump(mode="json"))
    db.commit()
    return ok(_turno_out(t, detalle=True))


@router.post("/turnos/{turno_id}/activo", response_model=ApiResponse[TurnoOut])
def activar_turno(turno_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    t = _turno(db, turno_id)
    t.activo = not t.activo
    auditar(db, request, "liq_turno_activo", actual.id, turno=t.codigo, activo=t.activo)
    db.commit()
    return ok(_turno_out(t))


def _turno(db: DbSession, turno_id: int) -> LiqTurno:
    t = db.get(LiqTurno, turno_id)
    if t is None:
        raise ApiError(404, "Turno no encontrado")
    return t


def _codigo_libre(db: DbSession, codigo: str, excepto: int | None = None) -> None:
    otro = db.scalar(select(LiqTurno).where(LiqTurno.codigo == codigo.strip().upper()))
    if otro is not None and otro.id != excepto:
        raise ApiError(409, f"Ya existe un turno con el código '{codigo.strip().upper()}'")


# --- Festivos --------------------------------------------------------------------

@router.get("/festivos", response_model=ApiResponse[list[FestivoOut]])
def listar_festivos(db: DbSession, anio: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2100),
                    _=Depends(require(VER))):
    return ok(svc_festivos.del_anio(db, anio))


@router.post("/festivos", response_model=ApiResponse[FestivoOut], status_code=201)
def agregar_festivo(data: FestivoIn, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    if not data.descripcion.strip():
        raise ApiError(422, "Escriba la descripción del festivo")
    svc_festivos.ajustar(db, data.fecha, True, data.descripcion.strip())
    auditar(db, request, "liq_festivo_agregado", actual.id, fecha=data.fecha.isoformat(), descripcion=data.descripcion)
    db.commit()
    return ok(next(f for f in svc_festivos.del_anio(db, data.fecha.year) if f["fecha"] == data.fecha))


@router.post("/festivos/quitar", response_model=ApiResponse[FestivoOut])
def quitar_festivo(data: FestivoIn, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    """Deja de tratar como festivo una fecha del calendario nacional."""
    nombre = svc_festivos.nacionales(data.fecha.year).get(data.fecha)
    if nombre is None:
        raise ApiError(404, "Esa fecha no es un festivo nacional")
    svc_festivos.ajustar(db, data.fecha, False, nombre)
    auditar(db, request, "liq_festivo_quitado", actual.id, fecha=data.fecha.isoformat())
    db.commit()
    return ok(next(f for f in svc_festivos.del_anio(db, data.fecha.year) if f["fecha"] == data.fecha))


@router.delete("/festivos/ajustes/{ajuste_id}", response_model=ApiResponse[dict])
def eliminar_ajuste(ajuste_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    """Borra un ajuste manual: la fecha vuelve a lo que diga el calendario nacional."""
    aj = db.get(LiqFestivoAjuste, ajuste_id)
    if aj is None:
        raise ApiError(404, "Ajuste no encontrado")
    auditar(db, request, "liq_festivo_restablecido", actual.id, fecha=aj.fecha.isoformat())
    db.delete(aj)
    db.commit()
    return ok({"eliminado": ajuste_id})
