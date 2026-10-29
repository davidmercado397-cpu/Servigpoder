"""Quincenas: carga del Excel, conteo de horas, cierre y descargas."""

from datetime import date, datetime, timezone
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
    CargaOut, DetalleEmpleado, DiaOut, EmpleadoOut, NombreNominaIn, PeriodoIn, PeriodoOut, ResultadoOut, UmbralIn,
)
from app.apps.liquidador.services import calculo, exportar, importador, vacaciones

router = APIRouter(tags=["liquidador: quincenas"])
VER = "liquidador.periodos.ver"
GESTIONAR = "liquidador.periodos.gestionar"
VER_NOMINA = "liquidador.nomina.ver"


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
        raise ApiError(409, "El periodo está cerrado. Reábralo para hacer cambios.", "PERIODO_CERRADO")


def _resultado_out(r: LiqResultado, nomina: bool = False, detalle: bool = False) -> ResultadoOut:
    """Los valores de la nómina solo van a quien tiene el permiso liquidador.nomina.ver."""
    out = ResultadoOut(empleado_id=r.empleado_id, documento=r.empleado.documento, nombre=r.empleado.nombre,
                       cargo=r.empleado.cargo, horas=r.horas, dias=r.dias, total_horas=float(r.total_horas),
                       umbral_semanas=(r.umbral_semanas or []) if detalle else [],
                       otras_nominas=bool((r.nomina or {}).get("otras_nominas")))
    if nomina and r.nomina:  # vacía si el periodo se calculó antes de existir la nómina
        out.devengado, out.neto = float(r.devengado), float(r.neto)
        out.nomina = r.nomina if detalle else None
    return out


@router.get("/periodos", response_model=ApiResponse[list[PeriodoOut]])
def listar(db: DbSession, p: Paginacion, _=Depends(require(VER))):
    consulta = select(LiqPeriodo).order_by(LiqPeriodo.anio.desc(), LiqPeriodo.mes.desc(), LiqPeriodo.quincena.desc(), LiqPeriodo.id)
    periodos, meta = paginar_consulta(db, consulta, p)
    return ok([_periodo_out(db, x) for x in periodos], **meta)


@router.post("/periodos", response_model=ApiResponse[PeriodoOut], status_code=201)
def crear(data: PeriodoIn, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    desde, hasta = calculo.rango_quincena(data.anio, data.mes, data.quincena)
    p = LiqPeriodo(anio=data.anio, mes=data.mes, quincena=data.quincena, nombre=data.nombre, desde=desde, hasta=hasta,
                   advertencias=[])
    _nombre_libre(db, p, data.nombre)
    db.add(p)
    db.flush()
    auditar(db, request, "liq_periodo_creado", actual.id, periodo=p.etiqueta, nomina=p.nombre)
    db.commit()
    return ok(_periodo_out(db, p))


def _nombre_libre(db: DbSession, p: LiqPeriodo, nombre: str) -> None:
    otra = db.scalar(select(LiqPeriodo).where(LiqPeriodo.anio == p.anio, LiqPeriodo.mes == p.mes, LiqPeriodo.quincena == p.quincena,
                                              func.lower(LiqPeriodo.nombre) == nombre.lower()))
    if otra is not None and otra.id != p.id:
        raise ApiError(409, f"El periodo {p.etiqueta} ya tiene una nómina «{otra.nombre}»")


@router.put("/periodos/{periodo_id}/nombre", response_model=ApiResponse[PeriodoOut])
def renombrar(periodo_id: int, data: NombreNominaIn, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    p = _periodo(db, periodo_id)
    _abierto(p)
    _nombre_libre(db, p, data.nombre)
    antes, p.nombre = p.nombre, data.nombre
    auditar(db, request, "liq_nomina_renombrada", actual.id, periodo=p.etiqueta, antes=antes, despues=p.nombre)
    db.commit()
    return ok(_periodo_out(db, p))


@router.get("/periodos/{periodo_id}", response_model=ApiResponse[PeriodoOut])
def ver(periodo_id: int, db: DbSession, _=Depends(require(VER))):
    return ok(_periodo_out(db, _periodo(db, periodo_id)))


@router.delete("/periodos/{periodo_id}", response_model=ApiResponse[dict])
def eliminar(periodo_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    p = _periodo(db, periodo_id)
    _abierto(p)
    auditar(db, request, "liq_periodo_eliminado", actual.id, periodo=p.etiqueta, nomina=p.nombre)
    otras = calculo.hermanas(db, p)
    db.delete(p)
    db.flush()
    for h in otras:  # quienes estaban también en esta nómina pueden pasar a aplicar sus descuentos en otra
        if h.estado == CALCULADA and h.cargado_en is not None:
            calculo.calcular(db, h, con_hermanas=False)
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
    auditar(db, request, "liq_excel_cargado", actual.id, periodo=p.etiqueta, archivo=nombre,
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
        raise ApiError(409, "El periodo aún no tiene un Excel cargado")
    empleados = calculo.calcular(db, p)
    auditar(db, request, "liq_periodo_recalculado", actual.id, periodo=p.etiqueta, empleados=empleados)
    db.commit()
    return ok(_periodo_out(db, p))


@router.put("/periodos/{periodo_id}/umbral", response_model=ApiResponse[PeriodoOut])
def umbral_semanal(periodo_id: int, data: UmbralIn, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    """Marca o desmarca el umbral semanal del periodo. Queda guardado para la siguiente carga del Excel y, si el
    periodo ya tiene Excel, se recalcula de una vez."""
    p = _periodo(db, periodo_id)
    _abierto(p)
    antes = {"activo": p.umbral_activo, "horas": float(p.umbral_horas), "horas_novedad": float(p.umbral_horas_novedad)}
    p.umbral_activo, p.umbral_horas, p.umbral_horas_novedad = data.activo, data.horas, data.horas_novedad
    if p.cargado_en is not None:
        calculo.calcular(db, p)
    auditar(db, request, "liq_umbral_semanal", actual.id, periodo=p.etiqueta, antes=antes,
            despues={"activo": data.activo, "horas": float(data.horas), "horas_novedad": float(data.horas_novedad)},
            recalculado=p.cargado_en is not None)
    db.commit()
    return ok(_periodo_out(db, p))


@router.post("/periodos/{periodo_id}/cerrar", response_model=ApiResponse[PeriodoOut])
def cerrar(periodo_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    p = _periodo(db, periodo_id)
    if p.estado != CALCULADA:
        raise ApiError(409, "Solo se puede cerrar un periodo con el Excel cargado y las horas contadas")
    p.estado, p.cerrado_en, p.cerrado_por = CERRADA, datetime.now(timezone.utc), actual.id
    auditar(db, request, "liq_periodo_cerrado", actual.id, periodo=p.etiqueta)
    db.commit()
    return ok(_periodo_out(db, p))


@router.post("/periodos/{periodo_id}/reabrir", response_model=ApiResponse[PeriodoOut])
def reabrir(periodo_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    p = _periodo(db, periodo_id)
    if p.estado != CERRADA:
        raise ApiError(409, "El periodo no está cerrado")
    p.estado, p.cerrado_en, p.cerrado_por = CALCULADA, None, None
    auditar(db, request, "liq_periodo_reabierto", actual.id, periodo=p.etiqueta)
    db.commit()
    return ok(_periodo_out(db, p))


@router.get("/periodos/{periodo_id}/resultados", response_model=ApiResponse[list[ResultadoOut]])
def resultados(periodo_id: int, db: DbSession, p: Paginacion, q: str = Query("", max_length=100),
               orden: str = Query("documento", pattern="^(documento|nombre|horas|novedad|devengado|neto)$"),
               actual: Usuario = Depends(require(VER))):
    periodo = _periodo(db, periodo_id)
    lista = list(db.scalars(select(LiqResultado).where(LiqResultado.periodo_id == periodo.id)))
    if q.strip():
        t = q.strip().lower()
        lista = [r for r in lista if t in r.empleado.documento.lower() or t in r.empleado.nombre.lower()]
    claves = {"documento": lambda r: r.empleado.documento, "nombre": lambda r: r.empleado.nombre.lower(),
              "horas": lambda r: -float(r.total_horas), "novedad": lambda r: -int(r.dias.get("novedad", 0)),
              "devengado": lambda r: -float(r.devengado), "neto": lambda r: -float(r.neto)}
    ve_nomina = VER_NOMINA in actual.permisos
    if orden in ("devengado", "neto") and not ve_nomina:
        orden = "documento"
    lista.sort(key=claves[orden])
    pagina, meta = paginar_lista(lista, p)
    totales: dict = {"horas": {}, "dias": {}}
    for r in lista:
        for k, v in r.horas.items():
            totales["horas"][k] = round(totales["horas"].get(k, 0) + v, 2)
        for k, v in r.dias.items():
            totales["dias"][k] = totales["dias"].get(k, 0) + v
    pendiente = any(not r.nomina for r in lista)
    if ve_nomina and not pendiente:
        claves_nomina = ("basico", "incapacidad", "vacaciones_valor", "recargos", "extras", "auxilio", "devengado", "salud", "pension",
                         "embargos", "prestamos", "cuotas", "novedades_devengo", "novedades_deduccion",
                         "deducciones", "neto", "provision_ss_180")
        totales["nomina"] = {k: round(sum((r.nomina or {}).get(k, 0) for r in lista)) for k in claves_nomina}
    return ok([_resultado_out(r, ve_nomina) for r in pagina], **meta, totales=totales, nomina_pendiente=ve_nomina and pendiente,
              en_otras_nominas=sum(1 for r in lista if (r.nomina or {}).get("otras_nominas")))


@router.get("/periodos/{periodo_id}/empleados/{empleado_id}", response_model=ApiResponse[DetalleEmpleado])
def detalle_empleado(periodo_id: int, empleado_id: int, db: DbSession, actual: Usuario = Depends(require(VER))):
    """Día a día de una persona: turno, tipo de día y horas por concepto (de dónde sale cada total)."""
    r = db.scalar(select(LiqResultado).where(LiqResultado.periodo_id == periodo_id, LiqResultado.empleado_id == empleado_id))
    if r is None:
        raise ApiError(404, "La persona no tiene turnos en este periodo")
    dias = db.scalars(select(LiqDia).where(LiqDia.periodo_id == periodo_id, LiqDia.empleado_id == empleado_id).order_by(LiqDia.fecha))
    return ok(DetalleEmpleado(empleado=_resultado_out(r, VER_NOMINA in actual.permisos, detalle=True), dias=[
        DiaOut(fecha=d.fecha, codigo=d.codigo, turno=d.turno.nombre, tipo_dia=d.tipo_dia, clase=d.clase, horas=d.horas) for d in dias]))


@router.get("/periodos/{periodo_id}/liquidacion", dependencies=[Depends(limitar("exportar", 10, 60))])
def descargar_liquidacion(periodo_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(VER))):
    p = _periodo(db, periodo_id)
    contenido, tipo, nombre = exportar.liquidacion(db, p)
    auditar(db, request, "liq_liquidacion_descargada", actual.id, periodo=p.etiqueta)
    db.commit()
    return _archivo(contenido, tipo, nombre)


@router.get("/periodos/{periodo_id}/plantilla")
def descargar_plantilla(periodo_id: int, db: DbSession, _=Depends(require(VER))):
    return _archivo(*exportar.plantilla(_periodo(db, periodo_id)))


def _archivo(contenido: bytes, tipo: str, nombre: str) -> StreamingResponse:
    return StreamingResponse(BytesIO(contenido), media_type=tipo, headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.get("/empleados", response_model=ApiResponse[list[EmpleadoOut]])
def empleados(db: DbSession, p: Paginacion, q: str = Query("", max_length=100),
              estado: str = Query("todos", pattern="^(todos|activo|retirado)$"),
              tipo: str = Query("todos", pattern="^(todos|operativo|administrativo)$"), actual: Usuario = Depends(require(VER))):
    consulta = select(LiqEmpleado).order_by(LiqEmpleado.nombre)
    if estado != "todos":
        consulta = consulta.where(LiqEmpleado.estado == estado)
    if tipo != "todos":
        consulta = consulta.where(LiqEmpleado.tipo_personal == tipo)
    if q.strip():
        patron = f"%{q.strip()}%"
        consulta = consulta.where(or_(LiqEmpleado.documento.ilike(patron), LiqEmpleado.nombre.ilike(patron)))
    lista, meta = paginar_consulta(db, consulta, p)
    ids = [e.id for e in lista]
    conteo = dict(db.execute(select(LiqResultado.empleado_id, func.count()).where(LiqResultado.empleado_id.in_(ids))
                             .group_by(LiqResultado.empleado_id)).all()) if ids else {}
    ultimas: dict[int, tuple[tuple[int, int, int], str]] = {}
    if ids:
        filas = db.execute(select(LiqResultado.empleado_id, LiqPeriodo.anio, LiqPeriodo.mes, LiqPeriodo.quincena)
                           .join(LiqPeriodo, LiqPeriodo.id == LiqResultado.periodo_id).where(LiqResultado.empleado_id.in_(ids)))
        for eid, anio, mes, qn in filas:
            # La clave ordena por fecha (el mensual cuenta como el periodo más completo del mes)
            clave = (anio, mes, 3 if qn == 0 else qn)
            if eid not in ultimas or clave > ultimas[eid][0]:
                ultimas[eid] = (clave, f"{anio}-{mes:02d} {'Mensual' if qn == 0 else f'Q{qn}'}")
    disfrutados = vacaciones.habiles_disfrutados(db, {e.id: e for e in lista})
    return ok([_empleado_out(e, conteo.get(e.id, 0), ultimas[e.id][1] if e.id in ultimas else None, disfrutados.get(e.id, 0), actual)
               for e in lista], **meta)


def _empleado_out(e: LiqEmpleado, quincenas: int, ultima: str | None, disfrutados: int, actual: Usuario) -> EmpleadoOut:
    return EmpleadoOut(id=e.id, documento=e.documento, nombre=e.nombre, cargo=e.cargo, quincenas=quincenas, ultima=ultima,
                       salario=float(e.salario) if e.salario is not None and VER_NOMINA in actual.permisos else None,
                       dias_habiles=[int(c) for c in (e.dias_habiles or vacaciones.HABILES_DEFECTO)],
                       fecha_ingreso=e.fecha_ingreso, vacaciones_previas=float(e.vacaciones_previas or 0),
                       vacaciones_liquidador=disfrutados, saldo_vacaciones=vacaciones.saldo(e, disfrutados, date.today()),
                       arl_clase=e.arl_clase, estado=e.estado or "activo", fecha_retiro=e.fecha_retiro,
                       tipo_personal=e.tipo_personal, puesto=e.puesto)


@router.get("/empleados/{empleado_id}", response_model=ApiResponse[dict])
def ficha(empleado_id: int, db: DbSession, actual: Usuario = Depends(require(VER))):
    """Ficha del empleado: sus datos y las nóminas en que aparece (con valores solo para quien ve la nómina)."""
    e = db.get(LiqEmpleado, empleado_id)
    if e is None:
        raise ApiError(404, "Empleado no encontrado")
    ve_nomina = VER_NOMINA in actual.permisos
    filas = db.execute(select(LiqResultado, LiqPeriodo).join(LiqPeriodo, LiqPeriodo.id == LiqResultado.periodo_id)
                       .where(LiqResultado.empleado_id == e.id)
                       .order_by(LiqPeriodo.anio.desc(), LiqPeriodo.mes.desc(), LiqPeriodo.quincena.desc(), LiqPeriodo.id)).all()
    nominas = []
    for r, p in filas:
        n = r.nomina or {}
        x = {"periodo_id": p.id, "etiqueta": p.etiqueta, "anio": p.anio, "mes": p.mes, "quincena": p.quincena, "nombre": p.nombre,
             "estado": p.estado, "total_horas": float(r.total_horas), "dias": r.dias, "alertas": len(n.get("alertas", []))}
        if ve_nomina and n:
            x.update(devengado=float(r.devengado), neto=float(r.neto), vacaciones=n.get("vacaciones_valor", 0),
                     auxilios_no_prestacionales=n.get("auxilios_no_prestacionales", 0), prestamos=n.get("prestamos", 0),
                     embargos=n.get("embargos", 0), cuotas=n.get("cuotas", 0))
        nominas.append(x)
    ultima = nominas[0]["etiqueta"] if nominas else None
    disfrutados = vacaciones.habiles_disfrutados(db, {e.id: e}).get(e.id, 0)
    ficha = {**_empleado_out(e, len(nominas), ultima, disfrutados, actual).model_dump(mode="json"), "nominas": nominas}
    if "liquidador.personal.ver" in actual.permisos:  # datos personales e historiales: solo gestión humana y nómina
        from app.apps.liquidador.routes.personal import datos_personales, historial

        ficha.update(personal=datos_personales(e), **historial(db, e))
    return ok(ficha)
