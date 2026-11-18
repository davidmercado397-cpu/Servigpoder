"""Rutas de la Nómina Speed: /api/speed/…"""

import io

import xlsxwriter
from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import DbSession, require
from app.apps.speed.models import (
    ABIERTO, ADICIONAL, CERRADO, TIPOS_DESCUENTO, SpdDescuento, SpdDescuentoAplicado, SpdEmpleado, SpdLiquidacion, SpdNovedad,
    SpdParametro, SpdPeriodo,
)
from app.apps.speed.services import listado, programacion, servicio
from app.core.archivos import leer_xlsx
from app.core.auditoria import auditar
from app.core.rate_limit import limitar
from app.core.respuestas import ApiError, ApiResponse, ok
from app.models import Usuario

router = APIRouter(prefix="/speed", tags=["Nómina Speed"])
VER, LIQUIDAR, DESCUENTOS, CONFIGURAR = "speed.ver", "speed.liquidar", "speed.descuentos", "speed.configurar"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _f(v) -> float | None:
    return None if v is None else float(v)


# --- Parámetros ---------------------------------------------------------------------------------------------

@router.get("/parametros", response_model=ApiResponse[list[dict]])
def ver_parametros(db: DbSession, _=Depends(require(VER))):
    return ok([{"clave": p.clave, "valor": float(p.valor), "nombre": p.nombre, "ayuda": p.ayuda}
               for p in db.scalars(select(SpdParametro).order_by(SpdParametro.orden))])


@router.put("/parametros", response_model=ApiResponse[dict])
def guardar_parametros(data: dict[str, float], request: Request, db: DbSession, actual: Usuario = Depends(require(CONFIGURAR))):
    cambios = {}
    for p in db.scalars(select(SpdParametro)):
        if p.clave in data and abs(float(p.valor) - data[p.clave]) > 1e-9:
            if data[p.clave] < 0:
                raise ApiError(422, f"«{p.nombre}» no puede ser negativo")
            cambios[p.clave] = [float(p.valor), data[p.clave]]
            p.valor = data[p.clave]
    auditar(db, request, "spd_parametros", actual.id, cambios=cambios)
    db.commit()
    return ok({"cambios": len(cambios)})


# --- Empleados ----------------------------------------------------------------------------------------------

def _empleado_out(e: SpdEmpleado) -> dict:
    return {"id": e.id, "cedula": e.cedula, "nombre": e.nombre, "fecha_ingreso": e.fecha_ingreso.isoformat() if e.fecha_ingreso else None,
            "tipo_contrato": e.tipo_contrato, "grupo": e.grupo, "cargo": e.cargo, "area": e.area, "puesto": e.puesto, "cliente": e.cliente,
            "tipo_turno": e.tipo_turno, "salario": float(e.salario or 0), "auxilio_listado": float(e.auxilio_listado or 0),
            "horas_extras": float(e.horas_extras or 0), "comisiones": float(e.comisiones or 0), "ley_2466": float(e.ley_2466 or 0),
            "bonificaciones": float(e.bonificaciones or 0), "rodamiento": float(e.rodamiento or 0), "nota": e.nota,
            "aplica_programacion": e.aplica_programacion, "activo": e.activo}


@router.get("/empleados", response_model=ApiResponse[list[dict]])
def empleados(db: DbSession, inactivos: bool = False, _=Depends(require(VER))):
    q = select(SpdEmpleado).order_by(SpdEmpleado.nombre)
    if not inactivos:
        q = q.where(SpdEmpleado.activo.is_(True))
    return ok([_empleado_out(e) for e in db.scalars(q)])


@router.post("/empleados/importar", response_model=ApiResponse[dict], dependencies=[Depends(limitar("spd_importar", 10, 60))])
async def importar(request: Request, db: DbSession, archivo: UploadFile = File(...), actual: Usuario = Depends(require(LIQUIDAR))):
    """Importa el Excel de colaboradores (hoja LISTADO). El archivo se lee y se descarta."""
    nombre = (archivo.filename or "")[:200]
    contenido = await leer_xlsx(archivo)
    try:
        filas, advertencias = listado.leer_listado(contenido)
    except listado.ListadoInvalido as e:
        raise ApiError(422, str(e), "ARCHIVO_INVALIDO") from e
    del contenido
    r = servicio.importar_listado(db, filas)
    auditar(db, request, "spd_listado_importado", actual.id, archivo=nombre, filas=len(filas), nuevos=r["nuevos"],
            actualizados=r["actualizados"], inactivados=len(r["inactivados"]))
    db.commit()
    return ok({**r, "filas": len(filas), "advertencias": advertencias})


class EmpleadoEditar(BaseModel):
    aplica_programacion: bool | None = None
    activo: bool | None = None


@router.patch("/empleados/{empleado_id}", response_model=ApiResponse[dict])
def editar_empleado(empleado_id: int, data: EmpleadoEditar, request: Request, db: DbSession, actual: Usuario = Depends(require(LIQUIDAR))):
    e = db.get(SpdEmpleado, empleado_id)
    if e is None:
        raise ApiError(404, "Empleado no encontrado")
    cambios = data.model_dump(exclude_none=True)
    for k, v in cambios.items():
        setattr(e, k, v)
    auditar(db, request, "spd_empleado_editado", actual.id, cedula=e.cedula, cambios=cambios)
    db.commit()
    return ok(_empleado_out(e))


# --- Quincenas ------------------------------------------------------------------------------------------------

class PeriodoIn(BaseModel):
    anio: int = Field(ge=2024, le=2100)
    mes: int = Field(ge=1, le=12)
    quincena: int = Field(ge=1, le=2)


def _periodo(db: DbSession, periodo_id: int) -> SpdPeriodo:
    p = db.get(SpdPeriodo, periodo_id)
    if p is None:
        raise ApiError(404, "Quincena no encontrada")
    return p


def _abierto(p: SpdPeriodo) -> None:
    if p.estado != ABIERTO:
        raise ApiError(409, "La quincena está cerrada: reábrala para cambiarla")


def _periodo_out(db: DbSession, p: SpdPeriodo) -> dict:
    tot = db.execute(select(func.count(), func.coalesce(func.sum(SpdLiquidacion.devengado), 0), func.coalesce(func.sum(SpdLiquidacion.deducciones), 0),
                            func.coalesce(func.sum(SpdLiquidacion.neto), 0)).where(SpdLiquidacion.periodo_id == p.id)).one()
    return {"id": p.id, "anio": p.anio, "mes": p.mes, "quincena": p.quincena, "estado": p.estado,
            "calculado_en": p.calculado_en.isoformat() if p.calculado_en else None,
            "personas": tot[0], "devengado": float(tot[1]), "deducciones": float(tot[2]), "neto": float(tot[3]),
            "novedades": db.scalar(select(func.count()).select_from(SpdNovedad).where(SpdNovedad.periodo_id == p.id)) or 0}


@router.get("/periodos", response_model=ApiResponse[list[dict]])
def periodos(db: DbSession, _=Depends(require(VER))):
    lista = db.scalars(select(SpdPeriodo).order_by(SpdPeriodo.anio.desc(), SpdPeriodo.mes.desc(), SpdPeriodo.quincena.desc()))
    return ok([_periodo_out(db, p) for p in lista])


@router.post("/periodos", response_model=ApiResponse[dict], status_code=201)
def crear_periodo(data: PeriodoIn, request: Request, db: DbSession, actual: Usuario = Depends(require(LIQUIDAR))):
    if db.scalar(select(SpdPeriodo.id).where(SpdPeriodo.anio == data.anio, SpdPeriodo.mes == data.mes, SpdPeriodo.quincena == data.quincena)):
        raise ApiError(409, "Esa quincena ya existe")
    p = SpdPeriodo(anio=data.anio, mes=data.mes, quincena=data.quincena, creado_por=actual.id)
    db.add(p)
    db.flush()
    auditar(db, request, "spd_periodo_creado", actual.id, periodo=f"Q{p.quincena} {p.mes:02d}/{p.anio}")
    db.commit()
    return ok(_periodo_out(db, p))


@router.get("/periodos/{periodo_id}", response_model=ApiResponse[dict])
def ver_periodo(periodo_id: int, db: DbSession, _=Depends(require(VER))):
    p = _periodo(db, periodo_id)
    liq = db.scalars(select(SpdLiquidacion).where(SpdLiquidacion.periodo_id == p.id))
    filas = sorted(({"empleado_id": l.empleado_id, "cedula": l.empleado.cedula, "nombre": l.empleado.nombre, "cargo": l.empleado.cargo,
                     "puesto": l.empleado.puesto, "devengado": float(l.devengado), "deducciones": float(l.deducciones), "neto": float(l.neto),
                     **(l.detalle or {})} for l in liq), key=lambda x: x["nombre"])
    return ok({**_periodo_out(db, p), "liquidaciones": filas})


@router.delete("/periodos/{periodo_id}", response_model=ApiResponse[dict])
def eliminar_periodo(periodo_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(LIQUIDAR))):
    p = _periodo(db, periodo_id)
    _abierto(p)
    db.query(SpdDescuentoAplicado).filter(SpdDescuentoAplicado.periodo_id == p.id).delete()
    db.query(SpdLiquidacion).filter(SpdLiquidacion.periodo_id == p.id).delete()
    db.query(SpdNovedad).filter(SpdNovedad.periodo_id == p.id).delete()
    auditar(db, request, "spd_periodo_eliminado", actual.id, periodo=f"Q{p.quincena} {p.mes:02d}/{p.anio}")
    db.delete(p)
    db.commit()
    return ok({"eliminado": True})


@router.post("/periodos/{periodo_id}/liquidar", response_model=ApiResponse[dict])
def liquidar(periodo_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(LIQUIDAR))):
    p = _periodo(db, periodo_id)
    _abierto(p)
    totales = servicio.liquidar_periodo(db, p)
    auditar(db, request, "spd_quincena_liquidada", actual.id, periodo=f"Q{p.quincena} {p.mes:02d}/{p.anio}",
            personas=totales["personas"], neto=round(totales["neto"]))
    db.commit()
    return ver_periodo(p.id, db)


class EstadoIn(BaseModel):
    estado: str = Field(pattern=r"^(abierto|cerrado)$")


@router.post("/periodos/{periodo_id}/estado", response_model=ApiResponse[dict])
def cambiar_estado(periodo_id: int, data: EstadoIn, request: Request, db: DbSession, actual: Usuario = Depends(require(LIQUIDAR))):
    p = _periodo(db, periodo_id)
    if data.estado == CERRADO and not p.calculado_en:
        raise ApiError(409, "Liquide la quincena antes de cerrarla")
    p.estado = data.estado
    auditar(db, request, "spd_quincena_" + ("cerrada" if data.estado == CERRADO else "reabierta"), actual.id,
            periodo=f"Q{p.quincena} {p.mes:02d}/{p.anio}")
    db.commit()
    return ok(_periodo_out(db, p))


@router.get("/periodos/{periodo_id}/excel")
def excel(periodo_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(VER))):
    p = _periodo(db, periodo_id)
    liq = sorted(db.scalars(select(SpdLiquidacion).where(SpdLiquidacion.periodo_id == p.id)), key=lambda l: l.empleado.nombre)
    contenido = servicio.excel(p, liq)
    auditar(db, request, "spd_excel_quincena", actual.id, periodo=f"Q{p.quincena} {p.mes:02d}/{p.anio}")
    db.commit()
    return StreamingResponse(io.BytesIO(contenido), media_type=XLSX,
                             headers={"Content-Disposition": f'attachment; filename="nomina_speed_{p.anio}-{p.mes:02d}_q{p.quincena}.xlsx"'})


# --- Novedades de la quincena ------------------------------------------------------------------------------------

CAMPOS_NOVEDAD = ("dias_programados", "ausencias", "licencias", "suspensiones", "desprogramados", "permisos_remunerados", "vacaciones",
                  "incapacidad", "incapacidad_previos", "turnos_tad", "turnos_tan")


def _novedades(db: DbSession, p: SpdPeriodo) -> list[dict]:
    """Todos los empleados activos con su novedad de la quincena (vacía si no tiene)."""
    nov = {n.empleado_id: n for n in db.scalars(select(SpdNovedad).where(SpdNovedad.periodo_id == p.id))}
    emp = db.scalars(select(SpdEmpleado).where((SpdEmpleado.activo.is_(True)) | (SpdEmpleado.id.in_(list(nov) or [0]))).order_by(SpdEmpleado.nombre))
    return [{"empleado_id": e.id, "cedula": e.cedula, "nombre": e.nombre, "cargo": e.cargo, "aplica_programacion": e.aplica_programacion,
                "fecha_ingreso": e.fecha_ingreso.isoformat() if e.fecha_ingreso else None,
                **{c: (_f(getattr(nov[e.id], c)) if e.id in nov else (None if c == "dias_programados" else 0)) for c in CAMPOS_NOVEDAD},
                "sin_programacion": _f(nov[e.id].sin_programacion) if e.id in nov else 0,
                "programacion": nov[e.id].programacion if e.id in nov else None,
                "observacion": nov[e.id].observacion if e.id in nov else "", "origen": nov[e.id].origen if e.id in nov else None}
               for e in emp]


@router.get("/periodos/{periodo_id}/novedades", response_model=ApiResponse[list[dict]])
def novedades(periodo_id: int, db: DbSession, _=Depends(require(VER))):
    return ok(_novedades(db, _periodo(db, periodo_id)))


class NovedadIn(BaseModel):
    dias_programados: float | None = Field(default=None, ge=0, le=15)
    ausencias: float = Field(default=0, ge=0, le=15)
    licencias: float = Field(default=0, ge=0, le=15)
    suspensiones: float = Field(default=0, ge=0, le=15)
    desprogramados: float = Field(default=0, ge=0, le=15)
    permisos_remunerados: float = Field(default=0, ge=0, le=15)
    vacaciones: float = Field(default=0, ge=0, le=15)
    incapacidad: float = Field(default=0, ge=0, le=15)
    incapacidad_previos: float = Field(default=0, ge=0, le=1000)
    turnos_tad: int = Field(default=0, ge=0, le=31)
    turnos_tan: int = Field(default=0, ge=0, le=31)
    observacion: str = Field(default="", max_length=300)


def _guardar_novedad(db: DbSession, p: SpdPeriodo, empleado_id: int, data: dict, origen: str) -> None:
    n = db.scalar(select(SpdNovedad).where(SpdNovedad.periodo_id == p.id, SpdNovedad.empleado_id == empleado_id))
    vacia = data.get("dias_programados") is None and not any(data.get(c) for c in CAMPOS_NOVEDAD[1:]) and not data.get("observacion")
    if vacia:
        # En pantalla, dejarla en blanco la borra; en la plantilla, una fila sin datos no cambia nada
        if n is not None and origen == "manual":
            db.delete(n)
        return
    if n is None:
        n = SpdNovedad(periodo_id=p.id, empleado_id=empleado_id, observacion="")
        db.add(n)
    for c in (*CAMPOS_NOVEDAD, "observacion"):
        if c in data:
            setattr(n, c, data[c])
    n.origen = origen


@router.put("/periodos/{periodo_id}/novedades/{empleado_id}", response_model=ApiResponse[dict])
def guardar_novedad(periodo_id: int, empleado_id: int, data: NovedadIn, request: Request, db: DbSession,
                    actual: Usuario = Depends(require(LIQUIDAR))):
    p = _periodo(db, periodo_id)
    _abierto(p)
    e = db.get(SpdEmpleado, empleado_id)
    if e is None:
        raise ApiError(404, "Empleado no encontrado")
    _guardar_novedad(db, p, e.id, data.model_dump(), "manual")
    auditar(db, request, "spd_novedad", actual.id, periodo=f"Q{p.quincena} {p.mes:02d}/{p.anio}", cedula=e.cedula, **data.model_dump())
    db.commit()
    return ok({"guardado": True})


@router.get("/periodos/{periodo_id}/novedades/plantilla")
def plantilla(periodo_id: int, db: DbSession, _=Depends(require(VER))):
    """Plantilla de novedades con todos los empleados activos y lo que ya tiene la quincena."""
    filas = _novedades(db, _periodo(db, periodo_id))
    buf = io.BytesIO()
    libro = xlsxwriter.Workbook(buf, {"in_memory": True})
    negrita = libro.add_format({"bold": True, "bg_color": "#e2e8f0", "text_wrap": True})
    hoja = libro.add_worksheet("Novedades")
    hoja.write_row(0, 0, [t for _, t in listado.COLUMNAS_NOVEDAD], negrita)
    for i, f in enumerate(filas, start=1):
        hoja.write_string(i, 0, f["cedula"])
        hoja.write_string(i, 1, f["nombre"])
        for j, c in enumerate(CAMPOS_NOVEDAD, start=2):
            if f[c] not in (None, 0):
                hoja.write_number(i, j, f[c])
        hoja.write_string(i, 2 + len(CAMPOS_NOVEDAD), f["observacion"] or "")
    hoja.set_column(0, 0, 13)
    hoja.set_column(1, 1, 34)
    hoja.set_column(2, 1 + len(CAMPOS_NOVEDAD), 14)
    hoja.set_column(2 + len(CAMPOS_NOVEDAD), 2 + len(CAMPOS_NOVEDAD), 40)
    hoja.freeze_panes(1, 2)
    nota = libro.add_worksheet("Instrucciones")
    for i, t in enumerate([
        "Días programados: días de la quincena con programación (solo para quienes aplican a la regla). Vacío = toda la quincena.",
        "Ausencias, licencias no remuneradas, suspensiones, renuncia y desprogramado descuentan salario, auxilio de transporte y variables.",
        "Licencias remuneradas (PR, calamidad, luto, día de la familia, ley María) y vacaciones pagan salario, pero no auxilio ni variables.",
        "Turnos TAD y TAN: turnos adicionales; se pagan aparte con el valor por turno de Parámetros.",
        "Lo normal es cargar estos días con el archivo de programación; esta plantilla sirve para corregir o para quien no está en él.",
        "Días de incapacidad: los 2 primeros de cada incapacidad al 100 % y desde el 3.º al 66,67 %.",
        "Días previos de la misma incapacidad: los que ya llevaba antes de esta quincena (si es una prórroga).",
        "Las filas sin datos no cambian nada; para borrar una novedad déjela en blanco desde la pantalla.",
    ]):
        nota.write_string(i, 0, t)
    nota.set_column(0, 0, 120)
    libro.close()
    buf.seek(0)
    return StreamingResponse(buf, media_type=XLSX, headers={"Content-Disposition": 'attachment; filename="novedades_speed.xlsx"'})


@router.post("/periodos/{periodo_id}/novedades/importar", response_model=ApiResponse[dict], dependencies=[Depends(limitar("spd_importar", 10, 60))])
async def importar_novedades(periodo_id: int, request: Request, db: DbSession, archivo: UploadFile = File(...),
                             actual: Usuario = Depends(require(LIQUIDAR))):
    p = _periodo(db, periodo_id)
    _abierto(p)
    contenido = await leer_xlsx(archivo)
    try:
        filas, advertencias = listado.leer_novedades(contenido)
    except listado.ListadoInvalido as e:
        raise ApiError(422, str(e), "ARCHIVO_INVALIDO") from e
    del contenido
    por_cedula = {e.cedula: e for e in db.scalars(select(SpdEmpleado))}
    cargadas = 0
    for f in filas:
        e = por_cedula.get(f["cedula"])
        if e is None:
            advertencias.append(f"La cédula {f['cedula']} no está en el Listado: se ignoró")
            continue
        _guardar_novedad(db, p, e.id, f, "plantilla")
        cargadas += 1
    auditar(db, request, "spd_novedades_importadas", actual.id, periodo=f"Q{p.quincena} {p.mes:02d}/{p.anio}", filas=cargadas)
    db.commit()
    return ok({"cargadas": cargadas, "advertencias": advertencias})


@router.post("/periodos/{periodo_id}/programacion/importar", response_model=ApiResponse[dict],
             dependencies=[Depends(limitar("spd_importar", 10, 60))])
async def importar_programacion(periodo_id: int, request: Request, db: DbSession, archivo: UploadFile = File(...),
                                actual: Usuario = Depends(require(LIQUIDAR))):
    """Archivo de programación de la quincena (hojas de programación general y de la señora Sandra). Se lee y se descarta."""
    p = _periodo(db, periodo_id)
    _abierto(p)
    nombre = (archivo.filename or "")[:200]
    contenido = await leer_xlsx(archivo)
    try:
        personas, advertencias, info = programacion.leer(contenido)
    except programacion.ProgramacionInvalida as e:
        raise ApiError(422, str(e), "ARCHIVO_INVALIDO") from e
    del contenido
    r = servicio.importar_programacion(db, p, personas, info)
    auditar(db, request, "spd_programacion_importada", actual.id, periodo=f"Q{p.quincena} {p.mes:02d}/{p.anio}", archivo=nombre,
            personas=r["personas"], cargadas=r["cargadas"], no_encontrados=len(r["no_encontrados"]))
    db.commit()
    return ok({**r, "avisos": r["avisos"] + advertencias})


# --- Descuentos y pagos adicionales ----------------------------------------------------------------------------

def _descuento_out(db: DbSession, d: SpdDescuento) -> dict:
    aplicado = float(db.scalar(select(func.coalesce(func.sum(SpdDescuentoAplicado.valor), 0)).where(SpdDescuentoAplicado.descuento_id == d.id)) or 0)
    return {"id": d.id, "empleado_id": d.empleado_id, "cedula": d.empleado.cedula, "nombre": d.empleado.nombre, "tipo": d.tipo,
            "tipo_nombre": TIPOS_DESCUENTO.get(d.tipo, d.tipo), "descripcion": d.descripcion, "valor_total": _f(d.valor_total),
            "cuota": float(d.cuota), "salarial": d.salarial, "activo": d.activo, "aplicado": aplicado,
            "saldo": None if d.valor_total is None else max(0.0, float(d.valor_total) - aplicado),
            "creado_en": d.creado_en.isoformat() if d.creado_en else None}


@router.get("/descuentos", response_model=ApiResponse[list[dict]])
def descuentos(db: DbSession, empleado_id: int | None = Query(default=None), _=Depends(require(VER))):
    q = select(SpdDescuento).order_by(SpdDescuento.activo.desc(), SpdDescuento.id.desc())
    if empleado_id:
        q = q.where(SpdDescuento.empleado_id == empleado_id)
    return ok([_descuento_out(db, d) for d in db.scalars(q)])


class DescuentoIn(BaseModel):
    empleado_id: int
    tipo: str = Field(pattern=r"^(embargo|prestamo|cuota|adicional)$")
    descripcion: str = Field(default="", max_length=300)
    valor_total: float | None = Field(default=None, gt=0, le=1e12)
    cuota: float = Field(gt=0, le=1e12)
    salarial: bool = True


@router.post("/descuentos", response_model=ApiResponse[dict], status_code=201)
def crear_descuento(data: DescuentoIn, request: Request, db: DbSession, actual: Usuario = Depends(require(DESCUENTOS))):
    e = db.get(SpdEmpleado, data.empleado_id)
    if e is None:
        raise ApiError(404, "Empleado no encontrado")
    if data.tipo != "embargo" and data.valor_total is None:
        raise ApiError(422, "Indique el valor total (solo un embargo puede quedar sin tope)")
    if data.valor_total is not None and data.cuota > data.valor_total:
        raise ApiError(422, "La cuota no puede ser mayor que el valor total")
    d = SpdDescuento(**data.model_dump(), creado_por=actual.id)
    if d.tipo != ADICIONAL:
        d.salarial = False
    db.add(d)
    db.flush()
    auditar(db, request, "spd_descuento_creado", actual.id, cedula=e.cedula, tipo=d.tipo, total=data.valor_total, cuota=data.cuota)
    db.commit()
    return ok(_descuento_out(db, d))


class DescuentoEditar(BaseModel):
    descripcion: str | None = Field(default=None, max_length=300)
    cuota: float | None = Field(default=None, gt=0, le=1e12)
    activo: bool | None = None


@router.patch("/descuentos/{descuento_id}", response_model=ApiResponse[dict])
def editar_descuento(descuento_id: int, data: DescuentoEditar, request: Request, db: DbSession, actual: Usuario = Depends(require(DESCUENTOS))):
    d = db.get(SpdDescuento, descuento_id)
    if d is None:
        raise ApiError(404, "Descuento no encontrado")
    cambios = data.model_dump(exclude_none=True)
    for k, v in cambios.items():
        setattr(d, k, v)
    auditar(db, request, "spd_descuento_editado", actual.id, cedula=d.empleado.cedula, cambios=cambios)
    db.commit()
    return ok(_descuento_out(db, d))


@router.delete("/descuentos/{descuento_id}", response_model=ApiResponse[dict])
def eliminar_descuento(descuento_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(DESCUENTOS))):
    d = db.get(SpdDescuento, descuento_id)
    if d is None:
        raise ApiError(404, "Descuento no encontrado")
    cerrados = db.scalar(select(func.count()).select_from(SpdDescuentoAplicado).join(SpdPeriodo, SpdPeriodo.id == SpdDescuentoAplicado.periodo_id)
                         .where(SpdDescuentoAplicado.descuento_id == d.id, SpdPeriodo.estado == CERRADO))
    if cerrados:
        raise ApiError(409, "Ya se aplicó en quincenas cerradas: desactívelo en vez de eliminarlo")
    auditar(db, request, "spd_descuento_eliminado", actual.id, cedula=d.empleado.cedula, tipo=d.tipo)
    db.query(SpdDescuentoAplicado).filter(SpdDescuentoAplicado.descuento_id == d.id).delete()
    db.delete(d)
    db.commit()
    return ok({"eliminado": True})


__all__ = ["router"]
