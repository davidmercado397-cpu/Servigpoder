import calendar
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy import case, func, select

from app.api.deps import DbSession, require
from app.core.archivos import leer_xlsx
from app.core.auditoria import auditar
from app.core.rate_limit import limitar
from app.core.respuestas import ApiError, ApiResponse, ok
from app.apps.capacidad.models import MatrizExcepcion, MatrizFranja, MatrizPeriodo, MatrizPuesto, Puesto, Ubicacion, Usuario
from app.apps.capacidad.models.matriz import CERRADO
from app.apps.capacidad.schemas.f1 import (
    DiaRequerido, EstadoIn, ExcepcionIn, ExcepcionOut, FranjaHorario, ImportacionOut, MatrizPuestoEditar,
    MatrizPuestoOut, PeriodoOut, ProyectarIn, ResumenPeriodo,
)
from app.apps.capacidad.services import matriz as svc

router = APIRouter(prefix="/matriz", tags=["matriz comercial"])

escritura = [Depends(limitar("matriz-escritura", 60, 60))]


def _periodo(db: DbSession, periodo_id: int) -> MatrizPeriodo:
    p = db.get(MatrizPeriodo, periodo_id)
    if p is None:
        raise ApiError(404, "Periodo no encontrado")
    return p


def _editable(p: MatrizPeriodo) -> None:
    if p.estado == CERRADO:
        raise ApiError(409, f"La matriz de {p.mes:02d}/{p.anio} está cerrada y no se puede modificar")
    # Toda edición marca la matriz como modificada: los análisis previos quedan desactualizados
    p.actualizado_en = datetime.now(timezone.utc)


def _matriz_puesto(db: DbSession, mp_id: int) -> MatrizPuesto:
    mp = db.get(MatrizPuesto, mp_id)
    if mp is None:
        raise ApiError(404, "Puesto de la matriz no encontrado")
    return mp


@router.get("/periodos", response_model=ApiResponse[list[ResumenPeriodo]])
def listar_periodos(db: DbSession, _=Depends(require("capacidad.matriz.ver"))):
    stats = {
        pid: (n, h or 0, r or 0)
        for pid, n, h, r in db.execute(
            select(MatrizPuesto.periodo_id, func.count(), func.sum(MatrizPuesto.hombres),
                   func.sum(case((MatrizPuesto.requiere_revision.is_(True), 1), else_=0)))
            .group_by(MatrizPuesto.periodo_id)
        )
    }
    excluidos = dict(db.execute(
        select(MatrizPuesto.periodo_id, func.count()).join(MatrizPuesto.puesto).where(Puesto.excluido.is_(True))
        .group_by(MatrizPuesto.periodo_id)
    ).all())
    periodos = db.scalars(select(MatrizPeriodo).order_by(MatrizPeriodo.anio.desc(), MatrizPeriodo.mes.desc()))
    return ok([
        ResumenPeriodo(**PeriodoOut.model_validate(p).model_dump(), puestos=stats.get(p.id, (0, 0, 0))[0],
                       hombres=stats.get(p.id, (0, 0, 0))[1], requieren_revision=stats.get(p.id, (0, 0, 0))[2],
                       excluidos=excluidos.get(p.id, 0))
        for p in periodos
    ])


@router.post("/importar", response_model=ApiResponse[ImportacionOut], status_code=201,
             dependencies=[Depends(limitar("importar", 10, 60))])
async def importar(request: Request, db: DbSession, archivo: UploadFile = File(...),
                   anio: int = Form(..., ge=2020, le=2100), mes: int = Form(..., ge=1, le=12),
                   actual: Usuario = Depends(require("capacidad.matriz.gestionar"))):
    contenido = await leer_xlsx(archivo)
    try:
        r = svc.importar_matriz(db, contenido, anio, mes)
    except svc.ErrorMatriz as e:
        raise ApiError(409, str(e)) from e
    auditar(db, request, "matriz_importada", actual.id, archivo=archivo.filename, anio=anio, mes=mes, puestos=r.puestos)
    db.commit()
    return ok(ImportacionOut(**r.__dict__))


@router.get("/periodos/{periodo_id}/puestos", response_model=ApiResponse[list[MatrizPuestoOut]])
def puestos_periodo(periodo_id: int, db: DbSession, solo_revision: bool = False, q: str = Query("", max_length=100),
                    _=Depends(require("capacidad.matriz.ver"))):
    _periodo(db, periodo_id)
    consulta = (select(MatrizPuesto).join(MatrizPuesto.puesto).join(Puesto.ubicacion)
                .where(MatrizPuesto.periodo_id == periodo_id).order_by(Ubicacion.codigo, Puesto.codigo))
    if solo_revision:
        consulta = consulta.where(MatrizPuesto.requiere_revision.is_(True))
    if q.strip():
        patron = f"%{q.strip()}%"
        consulta = consulta.where(Puesto.codigo.ilike(patron) | Puesto.descripcion.ilike(patron) | Ubicacion.nombre.ilike(patron))
    lista = list(db.scalars(consulta).unique())
    return ok(lista, total=len(lista))


@router.patch("/puestos/{mp_id}", response_model=ApiResponse[MatrizPuestoOut], dependencies=escritura)
def editar_puesto(mp_id: int, data: MatrizPuestoEditar, request: Request, db: DbSession,
                  actual: Usuario = Depends(require("capacidad.matriz.gestionar"))):
    mp = _matriz_puesto(db, mp_id)
    _editable(mp.periodo)
    cambios = data.model_dump(exclude_unset=True)
    for campo in ("hombres", "secuencia", "incluye_festivos", "requiere_revision", "nota"):
        if campo in cambios and cambios[campo] is not None:
            setattr(mp, campo, cambios[campo])
    if data.franjas is not None:
        mp.franjas = [MatrizFranja(**f.model_dump()) for f in data.franjas]
    auditar(db, request, "matriz_puesto_editado", actual.id, periodo_id=mp.periodo_id, puesto=mp.puesto.codigo,
            campos=sorted(cambios))
    db.commit()
    db.refresh(mp)
    return ok(mp)


@router.post("/puestos/{mp_id}/excepciones", response_model=ApiResponse[ExcepcionOut], status_code=201, dependencies=escritura)
def agregar_excepcion(mp_id: int, data: ExcepcionIn, request: Request, db: DbSession,
                      actual: Usuario = Depends(require("capacidad.matriz.gestionar"))):
    mp = _matriz_puesto(db, mp_id)
    _editable(mp.periodo)
    if (data.fecha.year, data.fecha.month) != (mp.periodo.anio, mp.periodo.mes):
        raise ApiError(400, "La fecha debe estar dentro del mes de la matriz")
    exc = MatrizExcepcion(matriz_puesto_id=mp.id, **data.model_dump())
    db.add(exc)
    auditar(db, request, "matriz_excepcion_creada", actual.id, puesto=mp.puesto.codigo, fecha=str(data.fecha))
    db.commit()
    return ok(exc)


@router.delete("/excepciones/{exc_id}", response_model=ApiResponse[None], dependencies=escritura)
def eliminar_excepcion(exc_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require("capacidad.matriz.gestionar"))):
    exc = db.get(MatrizExcepcion, exc_id)
    if exc is None:
        raise ApiError(404, "Excepción no encontrada")
    mp = _matriz_puesto(db, exc.matriz_puesto_id)
    _editable(mp.periodo)
    auditar(db, request, "matriz_excepcion_eliminada", actual.id, puesto=mp.puesto.codigo, fecha=str(exc.fecha))
    db.delete(exc)
    db.commit()
    return ok()


@router.post("/periodos/{periodo_id}/proyectar", response_model=ApiResponse[PeriodoOut], status_code=201,
             dependencies=[Depends(limitar("proyectar", 5, 60))])
def proyectar(periodo_id: int, data: ProyectarIn, request: Request, db: DbSession,
              actual: Usuario = Depends(require("capacidad.matriz.gestionar"))):
    origen = _periodo(db, periodo_id)
    try:
        nuevo = svc.proyectar(db, origen, data.copiar_excepciones)
    except svc.ErrorMatriz as e:
        raise ApiError(409, str(e)) from e
    auditar(db, request, "matriz_proyectada", actual.id, desde=f"{origen.mes:02d}/{origen.anio}",
            hacia=f"{nuevo.mes:02d}/{nuevo.anio}")
    db.commit()
    return ok(nuevo)


@router.put("/periodos/{periodo_id}/estado", response_model=ApiResponse[PeriodoOut], dependencies=escritura)
def cambiar_estado(periodo_id: int, data: EstadoIn, request: Request, db: DbSession,
                   actual: Usuario = Depends(require("capacidad.matriz.gestionar"))):
    p = _periodo(db, periodo_id)
    if p.estado == CERRADO:
        raise ApiError(409, "Un periodo cerrado no cambia de estado")
    anterior, p.estado = p.estado, data.estado
    auditar(db, request, "matriz_estado", actual.id, periodo=f"{p.mes:02d}/{p.anio}", de=anterior, a=data.estado)
    db.commit()
    return ok(p)


@router.get("/puestos/{mp_id}/requerimiento", response_model=ApiResponse[list[DiaRequerido]])
def requerimiento(mp_id: int, db: DbSession, _=Depends(require("capacidad.matriz.ver"))):
    """Calendario del mes: cobertura vendida por día (aplica festivos y excepciones)."""
    mp = _matriz_puesto(db, mp_id)
    anio, mes = mp.periodo.anio, mp.periodo.mes
    fest = svc.festivos(anio, mes)
    dias = svc.requerimiento(mp, anio, mes, fest)
    return ok([
        DiaRequerido(fecha=d, festivo=fest.get(d), franjas=[FranjaHorario(inicio=f.inicio, fin=f.fin) for f in fr],
                     horas=sum(svc.horas(f.inicio, f.fin) * f.cantidad for f in fr))
        for d, fr in dias.items()
    ], dias_mes=calendar.monthrange(anio, mes)[1])


@router.get("/festivos", response_model=ApiResponse[dict[str, str]])
def festivos(anio: int = Query(..., ge=2020, le=2100), mes: int = Query(..., ge=1, le=12), _=Depends(require("capacidad.matriz.ver"))):
    return ok({d.isoformat(): n for d, n in svc.festivos(anio, mes).items()})
