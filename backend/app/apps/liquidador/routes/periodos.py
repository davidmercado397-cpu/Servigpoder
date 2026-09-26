"""Quincenas: carga del Excel, conteo de horas, cierre y descargas."""

from datetime import datetime, timezone
from io import BytesIO

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select

from app.api.deps import DbSession, require
from app.core.archivos import leer_xlsx
from app.core.auditoria import auditar
from app.core.paginacion import Paginacion, paginar_consulta, paginar_lista
from app.core.rate_limit import limitar
from app.core.respuestas import ApiError, ApiResponse, ok
from app.models import Usuario
from app.apps.liquidador.models import CALCULADA, CERRADA, LiqDia, LiqEmpleado, LiqPeriodo, LiqResultado
from app.apps.liquidador.schemas import (
    CargaOut, DetalleEmpleado, DiaOut, EmpleadoOut, PeriodoIn, PeriodoOut, ResultadoOut,
)
from app.apps.liquidador.services import calculo, exportar, importador

router = APIRouter(tags=["liquidador: quincenas"])
VER = "liquidador.periodos.ver"
GESTIONAR = "liquidador.periodos.gestionar"


def _periodo_out(db: DbSession, p: LiqPeriodo) -> PeriodoOut:
    empleados = db.scalar(select(func.count()).select_from(LiqResultado).where(LiqResultado.periodo_id == p.id)) or 0
    return PeriodoOut.model_validate(p).model_copy(update={"empleados": empleados})


def _periodo(db: DbSession, periodo_id: int) -> LiqPeriodo:
    p = db.get(LiqPeriodo, periodo_id)
    if p is None:
        raise ApiError(404, "Quincena no encontrada")
    return p


def _abierto(p: LiqPeriodo) -> None:
    if p.estado == CERRADA:
        raise ApiError(409, "La quincena está cerrada. Reábrala para hacer cambios.", "PERIODO_CERRADO")


def _resultado_out(r: LiqResultado) -> ResultadoOut:
    return ResultadoOut(empleado_id=r.empleado_id, documento=r.empleado.documento, nombre=r.empleado.nombre,
                        cargo=r.empleado.cargo, horas=r.horas, dias=r.dias, total_horas=float(r.total_horas))


@router.get("/periodos", response_model=ApiResponse[list[PeriodoOut]])
def listar(db: DbSession, p: Paginacion, _=Depends(require(VER))):
    consulta = select(LiqPeriodo).order_by(LiqPeriodo.anio.desc(), LiqPeriodo.mes.desc(), LiqPeriodo.quincena.desc())
    periodos, meta = paginar_consulta(db, consulta, p)
    return ok([_periodo_out(db, x) for x in periodos], **meta)


@router.post("/periodos", response_model=ApiResponse[PeriodoOut], status_code=201)
def crear(data: PeriodoIn, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    if db.scalar(select(LiqPeriodo).where(LiqPeriodo.anio == data.anio, LiqPeriodo.mes == data.mes,
                                          LiqPeriodo.quincena == data.quincena)):
        raise ApiError(409, f"La quincena {data.anio}-{data.mes:02d} Q{data.quincena} ya existe")
    desde, hasta = calculo.rango_quincena(data.anio, data.mes, data.quincena)
    p = LiqPeriodo(anio=data.anio, mes=data.mes, quincena=data.quincena, desde=desde, hasta=hasta, advertencias=[])
    db.add(p)
    db.flush()
    auditar(db, request, "liq_periodo_creado", actual.id, periodo=f"{data.anio}-{data.mes:02d}-Q{data.quincena}")
    db.commit()
    return ok(_periodo_out(db, p))


@router.get("/periodos/{periodo_id}", response_model=ApiResponse[PeriodoOut])
def ver(periodo_id: int, db: DbSession, _=Depends(require(VER))):
    return ok(_periodo_out(db, _periodo(db, periodo_id)))


@router.delete("/periodos/{periodo_id}", response_model=ApiResponse[dict])
def eliminar(periodo_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    p = _periodo(db, periodo_id)
    _abierto(p)
    auditar(db, request, "liq_periodo_eliminado", actual.id, periodo=f"{p.anio}-{p.mes:02d}-Q{p.quincena}")
    db.delete(p)
    db.commit()
    return ok({"eliminado": periodo_id})


@router.post("/periodos/{periodo_id}/cargar", response_model=ApiResponse[CargaOut],
             dependencies=[Depends(limitar("liq_cargar", 10, 60))])
async def cargar(periodo_id: int, request: Request, db: DbSession, archivo: UploadFile = File(...),
                 actual: Usuario = Depends(require(GESTIONAR))):
    """Reemplaza los turnos cargados de la quincena y cuenta las horas de inmediato."""
    p = _periodo(db, periodo_id)
    _abierto(p)
    nombre = (archivo.filename or "")[:255]
    contenido = await leer_xlsx(archivo)
    try:
        res = importador.importar(db, p, contenido)
    except importador.ErrorImportacion as e:
        db.rollback()
        raise ApiError(422, str(e), "EXCEL_INVALIDO") from e
    p.archivo = nombre
    p.advertencias = res.advertencias[:500]
    p.cargado_en = datetime.now(timezone.utc)
    calculo.calcular(db, p)
    auditar(db, request, "liq_excel_cargado", actual.id, periodo=f"{p.anio}-{p.mes:02d}-Q{p.quincena}", archivo=nombre,
            empleados=res.empleados, dias=res.dias, advertencias=len(res.advertencias))
    db.commit()
    return ok(CargaOut(periodo=_periodo_out(db, p), empleados=res.empleados, dias=res.dias, fechas=res.fechas,
                       advertencias=res.advertencias[:500]))


@router.post("/periodos/{periodo_id}/recalcular", response_model=ApiResponse[PeriodoOut],
             dependencies=[Depends(limitar("liq_recalcular", 10, 60))])
def recalcular(periodo_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    """Vuelve a contar con los turnos y festivos vigentes (por ejemplo, tras corregir un turno)."""
    p = _periodo(db, periodo_id)
    _abierto(p)
    if p.cargado_en is None:
        raise ApiError(409, "La quincena aún no tiene un Excel cargado")
    empleados = calculo.calcular(db, p)
    auditar(db, request, "liq_periodo_recalculado", actual.id, periodo=f"{p.anio}-{p.mes:02d}-Q{p.quincena}", empleados=empleados)
    db.commit()
    return ok(_periodo_out(db, p))


@router.post("/periodos/{periodo_id}/cerrar", response_model=ApiResponse[PeriodoOut])
def cerrar(periodo_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    p = _periodo(db, periodo_id)
    if p.estado != CALCULADA:
        raise ApiError(409, "Solo se puede cerrar una quincena con el Excel cargado y las horas contadas")
    p.estado, p.cerrado_en, p.cerrado_por = CERRADA, datetime.now(timezone.utc), actual.id
    auditar(db, request, "liq_periodo_cerrado", actual.id, periodo=f"{p.anio}-{p.mes:02d}-Q{p.quincena}")
    db.commit()
    return ok(_periodo_out(db, p))


@router.post("/periodos/{periodo_id}/reabrir", response_model=ApiResponse[PeriodoOut])
def reabrir(periodo_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    p = _periodo(db, periodo_id)
    if p.estado != CERRADA:
        raise ApiError(409, "La quincena no está cerrada")
    p.estado, p.cerrado_en, p.cerrado_por = CALCULADA, None, None
    auditar(db, request, "liq_periodo_reabierto", actual.id, periodo=f"{p.anio}-{p.mes:02d}-Q{p.quincena}")
    db.commit()
    return ok(_periodo_out(db, p))


@router.get("/periodos/{periodo_id}/resultados", response_model=ApiResponse[list[ResultadoOut]])
def resultados(periodo_id: int, db: DbSession, p: Paginacion, q: str = Query("", max_length=100),
               orden: str = Query("documento", pattern="^(documento|nombre|horas|novedad)$"), _=Depends(require(VER))):
    periodo = _periodo(db, periodo_id)
    lista = list(db.scalars(select(LiqResultado).where(LiqResultado.periodo_id == periodo.id)))
    if q.strip():
        t = q.strip().lower()
        lista = [r for r in lista if t in r.empleado.documento.lower() or t in r.empleado.nombre.lower()]
    claves = {"documento": lambda r: r.empleado.documento, "nombre": lambda r: r.empleado.nombre.lower(),
              "horas": lambda r: -float(r.total_horas), "novedad": lambda r: -int(r.dias.get("novedad", 0))}
    lista.sort(key=claves[orden])
    pagina, meta = paginar_lista(lista, p)
    totales: dict = {"horas": {}, "dias": {}}
    for r in lista:
        for k, v in r.horas.items():
            totales["horas"][k] = round(totales["horas"].get(k, 0) + v, 2)
        for k, v in r.dias.items():
            totales["dias"][k] = totales["dias"].get(k, 0) + v
    return ok([_resultado_out(r) for r in pagina], **meta, totales=totales)


@router.get("/periodos/{periodo_id}/empleados/{empleado_id}", response_model=ApiResponse[DetalleEmpleado])
def detalle_empleado(periodo_id: int, empleado_id: int, db: DbSession, _=Depends(require(VER))):
    """Día a día de una persona: turno, tipo de día y horas por concepto (de dónde sale cada total)."""
    r = db.scalar(select(LiqResultado).where(LiqResultado.periodo_id == periodo_id, LiqResultado.empleado_id == empleado_id))
    if r is None:
        raise ApiError(404, "La persona no tiene turnos en esta quincena")
    dias = db.scalars(select(LiqDia).where(LiqDia.periodo_id == periodo_id, LiqDia.empleado_id == empleado_id).order_by(LiqDia.fecha))
    return ok(DetalleEmpleado(empleado=_resultado_out(r), dias=[
        DiaOut(fecha=d.fecha, codigo=d.codigo, turno=d.turno.nombre, tipo_dia=d.tipo_dia, clase=d.clase, horas=d.horas) for d in dias]))


@router.get("/periodos/{periodo_id}/liquidacion", dependencies=[Depends(limitar("exportar", 10, 60))])
def descargar_liquidacion(periodo_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(VER))):
    p = _periodo(db, periodo_id)
    contenido, tipo, nombre = exportar.liquidacion(db, p)
    auditar(db, request, "liq_liquidacion_descargada", actual.id, periodo=f"{p.anio}-{p.mes:02d}-Q{p.quincena}")
    db.commit()
    return _archivo(contenido, tipo, nombre)


@router.get("/periodos/{periodo_id}/plantilla")
def descargar_plantilla(periodo_id: int, db: DbSession, _=Depends(require(VER))):
    return _archivo(*exportar.plantilla(_periodo(db, periodo_id)))


def _archivo(contenido: bytes, tipo: str, nombre: str) -> StreamingResponse:
    return StreamingResponse(BytesIO(contenido), media_type=tipo, headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.get("/empleados", response_model=ApiResponse[list[EmpleadoOut]])
def empleados(db: DbSession, p: Paginacion, q: str = Query("", max_length=100), _=Depends(require(VER))):
    consulta = select(LiqEmpleado).order_by(LiqEmpleado.documento)
    if q.strip():
        patron = f"%{q.strip()}%"
        consulta = consulta.where(or_(LiqEmpleado.documento.ilike(patron), LiqEmpleado.nombre.ilike(patron)))
    lista, meta = paginar_consulta(db, consulta, p)
    ids = [e.id for e in lista]
    conteo = dict(db.execute(select(LiqResultado.empleado_id, func.count()).where(LiqResultado.empleado_id.in_(ids))
                             .group_by(LiqResultado.empleado_id)).all()) if ids else {}
    ultimas: dict[int, str] = {}
    if ids:
        filas = db.execute(select(LiqResultado.empleado_id, LiqPeriodo.anio, LiqPeriodo.mes, LiqPeriodo.quincena)
                           .join(LiqPeriodo, LiqPeriodo.id == LiqResultado.periodo_id).where(LiqResultado.empleado_id.in_(ids)))
        for eid, anio, mes, qn in filas:
            etiqueta = f"{anio}-{mes:02d} Q{qn}"
            if etiqueta > ultimas.get(eid, ""):
                ultimas[eid] = etiqueta
    return ok([EmpleadoOut(id=e.id, documento=e.documento, nombre=e.nombre, cargo=e.cargo,
                           quincenas=conteo.get(e.id, 0), ultima=ultimas.get(e.id)) for e in lista], **meta)
