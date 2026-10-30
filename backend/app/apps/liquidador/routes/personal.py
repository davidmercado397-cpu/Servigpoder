"""Ficha del personal: datos personales, contratos e historial de vacaciones, e importación de la base de personal y
del libro de vacaciones (los archivos se procesan en memoria y se descartan)."""

import re
from datetime import date, timedelta

from fastapi import APIRouter, Depends, File, Request, UploadFile
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from sqlalchemy import select

from app.api.deps import DbSession, require
from app.core.archivos import leer_xlsx
from app.core.auditoria import auditar
from app.core.rate_limit import limitar
from app.core.respuestas import ApiError, ApiResponse, ok
from app.models import Usuario
from app.apps.liquidador.models import CARGO_DEFECTO, LiqContrato, LiqDia, LiqEmpleado, LiqTurno, LiqVacacionSalida
from app.apps.liquidador.services import festivos, personal, vacaciones as vac

router = APIRouter(tags=["liquidador: ficha del personal"])
VER = "liquidador.personal.ver"
GESTIONAR = "liquidador.personal.gestionar"

CAMPOS_TEXTO = ("puesto", "tipo_contrato", "rh", "pais_nacimiento", "depto_nacimiento", "ciudad_nacimiento", "pais_expedicion",
                "depto_expedicion", "ciudad_expedicion", "celular", "correo", "direccion", "barrio", "ciudad", "eps", "fondo_pensiones",
                "fondo_cesantias", "caja_compensacion", "plan_exequial", "numero_cuenta", "nivel_educativo", "cursos", "tipo_personal", "sexo")
CAMPOS = (*CAMPOS_TEXTO, "fecha_nacimiento", "fecha_expedicion", "estado_civil", "extranjero", "pensionado")


class DatosPersonalesIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)
    cargo: str = Field(min_length=1, max_length=80)
    tipo_personal: str | None = Field(None, pattern="^(operativo|administrativo)$")
    puesto: str | None = Field(None, max_length=200)
    tipo_contrato: str | None = Field(None, max_length=40)
    sexo: str | None = Field(None, pattern="^[MF]$")
    fecha_nacimiento: date | None = None
    rh: str | None = Field(None, max_length=5)
    pais_nacimiento: str | None = Field(None, max_length=80)
    depto_nacimiento: str | None = Field(None, max_length=80)
    ciudad_nacimiento: str | None = Field(None, max_length=80)
    fecha_expedicion: date | None = None
    pais_expedicion: str | None = Field(None, max_length=80)
    depto_expedicion: str | None = Field(None, max_length=80)
    ciudad_expedicion: str | None = Field(None, max_length=80)
    estado_civil: int | None = Field(None, ge=0, le=5)
    extranjero: bool = False
    celular: str | None = Field(None, max_length=30)
    correo: EmailStr | None = None
    direccion: str | None = Field(None, max_length=200)
    barrio: str | None = Field(None, max_length=120)
    ciudad: str | None = Field(None, max_length=80)
    eps: str | None = Field(None, max_length=80)
    fondo_pensiones: str | None = Field(None, max_length=80)
    pensionado: bool = False
    fondo_cesantias: str | None = Field(None, max_length=80)
    caja_compensacion: str | None = Field(None, max_length=80)
    plan_exequial: str | None = Field(None, max_length=80)
    numero_cuenta: str | None = Field(None, max_length=40)
    nivel_educativo: str | None = Field(None, max_length=60)
    cursos: str | None = Field(None, max_length=2000)

    @field_validator("*", mode="before")
    @classmethod
    def _vacios(cls, v):
        if isinstance(v, str):
            v = " ".join(v.split()) if "\n" not in v else v.strip()
            return v or None
        return v

    @model_validator(mode="after")
    def _fechas(self):
        hoy = date.today()
        for f in (self.fecha_nacimiento, self.fecha_expedicion):
            if f is not None and (f > hoy or f.year < 1900):
                raise ValueError("Revise las fechas de nacimiento y de expedición")
        return self


class NuevoEmpleadoIn(BaseModel):
    documento: str = Field(min_length=3, max_length=32)
    nombre: str = Field(min_length=3, max_length=200)
    cargo: str = Field(CARGO_DEFECTO, min_length=1, max_length=80)
    tipo_personal: str = Field("operativo", pattern="^(operativo|administrativo)$")
    puesto: str | None = Field(None, max_length=200)
    tipo_contrato: str | None = Field(None, max_length=40)
    # Con fecha de ingreso queda registrado su contrato (historial laboral) y empieza a causar vacaciones
    fecha_ingreso: date | None = None

    @field_validator("*", mode="before")
    @classmethod
    def _vacios(cls, v):
        if isinstance(v, str):
            return " ".join(v.split()) or None
        return v

    @model_validator(mode="after")
    def _ingreso(self):
        if self.fecha_ingreso and (self.fecha_ingreso.year < 1950 or self.fecha_ingreso > date.today() + timedelta(days=60)):
            raise ValueError("Revise la fecha de ingreso")
        return self


class ContratoIn(BaseModel):
    fecha_inicio: date
    fecha_retiro: date | None = None
    tipo_contrato: str | None = Field(None, max_length=40)
    cargo: str | None = Field(None, max_length=120)
    puesto: str | None = Field(None, max_length=200)
    motivo_retiro: str | None = Field(None, max_length=200)
    observacion: str | None = Field(None, max_length=300)

    @model_validator(mode="after")
    def _fechas(self):
        if self.fecha_retiro and self.fecha_retiro < self.fecha_inicio:
            raise ValueError("La fecha de retiro no puede ser anterior a la de inicio")
        return self


class SalidaIn(BaseModel):
    tipo: str = Field("disfrutadas", pattern="^(disfrutadas|compensadas)$")
    desde: date | None = None
    hasta: date | None = None
    retorno: date | None = None
    dias_habiles: int | None = Field(None, ge=0, le=400)
    estado: str = Field("historico", pattern="^(historico|programada|cancelada)$")
    observacion: str | None = Field(None, max_length=300)

    @model_validator(mode="after")
    def _fechas(self):
        if self.tipo == "disfrutadas" and (self.desde is None or self.hasta is None):
            raise ValueError("Indique desde y hasta")
        if self.desde and self.hasta and self.hasta < self.desde:
            raise ValueError("La fecha final no puede ser anterior a la inicial")
        return self


def _empleado(db: DbSession, empleado_id: int) -> LiqEmpleado:
    e = db.get(LiqEmpleado, empleado_id)
    if e is None:
        raise ApiError(404, "Empleado no encontrado")
    return e


def datos_personales(e: LiqEmpleado) -> dict:
    datos = {c: getattr(e, c) for c in CAMPOS}
    for c in ("fecha_nacimiento", "fecha_expedicion"):
        datos[c] = datos[c].isoformat() if datos[c] else None
    hoy = date.today()
    if e.fecha_nacimiento:
        datos["edad"] = hoy.year - e.fecha_nacimiento.year - ((hoy.month, hoy.day) < (e.fecha_nacimiento.month, e.fecha_nacimiento.day))
    if e.fecha_ingreso:
        datos["antiguedad_anios"] = round((hoy - e.fecha_ingreso).days / 365.25, 1)
    return datos


def contrato_out(c: LiqContrato) -> dict:
    return {"id": c.id, "fecha_inicio": c.fecha_inicio.isoformat(), "fecha_retiro": c.fecha_retiro.isoformat() if c.fecha_retiro else None,
            "tipo_contrato": c.tipo_contrato, "cargo": c.cargo, "puesto": c.puesto, "motivo_retiro": c.motivo_retiro,
            "observacion": c.observacion}


def salida_out(x: LiqVacacionSalida) -> dict:
    return {"id": x.id, "tipo": x.tipo, "desde": x.desde.isoformat() if x.desde else None, "hasta": x.hasta.isoformat() if x.hasta else None,
            "retorno": x.retorno.isoformat() if x.retorno else None, "dias_habiles": x.dias_habiles, "estado": x.estado,
            "observacion": x.observacion, "origen": x.origen}


def historial(db: DbSession, e: LiqEmpleado) -> dict:
    """Contratos, salidas de vacaciones registradas y las vacaciones (V) liquidadas en nóminas, agrupadas en tramos."""
    contratos = db.scalars(select(LiqContrato).where(LiqContrato.empleado_id == e.id).order_by(LiqContrato.fecha_inicio.desc()))
    salidas = db.scalars(select(LiqVacacionSalida).where(LiqVacacionSalida.empleado_id == e.id)
                         .order_by(LiqVacacionSalida.desde.desc().nulls_last(), LiqVacacionSalida.id.desc()))
    fechas = sorted(set(db.scalars(select(LiqDia.fecha).join(LiqTurno, LiqTurno.id == LiqDia.turno_id)
                                   .where(LiqDia.empleado_id == e.id, LiqTurno.vacaciones.is_(True)))))
    tramos: list[dict] = []
    if fechas:
        fest = festivos.conjunto(db, fechas[0], fechas[-1])
        for f in fechas:
            if tramos and date.fromisoformat(tramos[-1]["hasta"]) == f - timedelta(days=1):
                tramos[-1]["hasta"] = f.isoformat()
            else:
                tramos.append({"desde": f.isoformat(), "hasta": f.isoformat(), "dias_habiles": 0, "dias": 0})
            tramos[-1]["dias"] += 1
            tramos[-1]["dias_habiles"] += vac.es_habil(f, e.dias_habiles, fest)
        for t in tramos:
            t["antes_del_corte"] = bool(e.vacaciones_corte and date.fromisoformat(t["hasta"]) <= e.vacaciones_corte)
    return {"contratos": [contrato_out(c) for c in contratos], "salidas": [salida_out(x) for x in salidas],
            "vacaciones_liquidadas": list(reversed(tramos))}


@router.post("/empleados", response_model=ApiResponse[dict], status_code=201)
def crear_empleado(data: NuevoEmpleadoIn, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    """Crea un empleado desde la plataforma (sin esperar al Excel de turnos o a la base de personal). Lo demás se
    completa en su ficha."""
    # Cédula escrita con puntos o espacios (1.144.000.111): solo los números
    doc, _ = personal.documento(re.sub(r"[.,\s]", "", data.documento) if re.fullmatch(r"[\d.,\s]+", data.documento) else data.documento)
    existente = personal.Indice(db.scalars(select(LiqEmpleado))).buscar(doc)
    if existente is not None:
        raise ApiError(409, f"Ya existe un empleado con ese documento: {existente.nombre}", "EMPLEADO_EXISTE",
                       details=[{"id": existente.id}])
    e = LiqEmpleado(documento=doc, nombre=data.nombre.upper(), cargo=data.cargo, tipo_personal=data.tipo_personal, puesto=data.puesto,
                    tipo_contrato=data.tipo_contrato, fecha_ingreso=data.fecha_ingreso, estado=personal.ACTIVO)
    db.add(e)
    db.flush()
    if data.fecha_ingreso:
        db.add(LiqContrato(empleado_id=e.id, fecha_inicio=data.fecha_ingreso, tipo_contrato=data.tipo_contrato, cargo=data.cargo,
                           puesto=data.puesto))
        db.flush()
        personal.sincronizar_estado(db, e)
    auditar(db, request, "liq_empleado_creado", actual.id, documento=e.documento)
    db.commit()
    return ok({"id": e.id, "documento": e.documento, "nombre": e.nombre})


@router.put("/empleados/{empleado_id}/datos", response_model=ApiResponse[dict])
def guardar_datos(empleado_id: int, data: DatosPersonalesIn, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    """Datos personales de la ficha. La auditoría registra qué campos cambiaron (sin sus valores)."""
    e = _empleado(db, empleado_id)
    cambios = []
    for campo, valor in data.model_dump().items():
        if campo == "correo" and valor is not None:
            valor = str(valor).lower()
        if getattr(e, campo) != valor:
            setattr(e, campo, valor)
            cambios.append(campo)
    auditar(db, request, "liq_datos_personales", actual.id, documento=e.documento, campos=cambios)
    db.commit()
    return ok({"id": e.id, "cambios": cambios, "personal": datos_personales(e)})


@router.post("/empleados/{empleado_id}/contratos", response_model=ApiResponse[dict], status_code=201)
def crear_contrato(empleado_id: int, data: ContratoIn, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    e = _empleado(db, empleado_id)
    if db.scalar(select(LiqContrato).where(LiqContrato.empleado_id == e.id, LiqContrato.fecha_inicio == data.fecha_inicio)):
        raise ApiError(409, "Ya hay un contrato con esa fecha de inicio")
    c = LiqContrato(empleado_id=e.id, **data.model_dump())
    db.add(c)
    db.flush()
    personal.sincronizar_estado(db, e)
    auditar(db, request, "liq_contrato_creado", actual.id, documento=e.documento, inicio=data.fecha_inicio.isoformat(),
            retiro=data.fecha_retiro.isoformat() if data.fecha_retiro else None)
    db.commit()
    return ok(contrato_out(c))


@router.put("/contratos/{contrato_id}", response_model=ApiResponse[dict])
def editar_contrato(contrato_id: int, data: ContratoIn, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    c = db.get(LiqContrato, contrato_id)
    if c is None:
        raise ApiError(404, "Contrato no encontrado")
    otro = db.scalar(select(LiqContrato).where(LiqContrato.empleado_id == c.empleado_id, LiqContrato.fecha_inicio == data.fecha_inicio,
                                               LiqContrato.id != c.id))
    if otro is not None:
        raise ApiError(409, "Ya hay un contrato con esa fecha de inicio")
    for k, v in data.model_dump().items():
        setattr(c, k, v)
    db.flush()
    e = db.get(LiqEmpleado, c.empleado_id)
    personal.sincronizar_estado(db, e)
    auditar(db, request, "liq_contrato_editado", actual.id, documento=e.documento, inicio=data.fecha_inicio.isoformat(),
            retiro=data.fecha_retiro.isoformat() if data.fecha_retiro else None)
    db.commit()
    return ok(contrato_out(c))


@router.delete("/contratos/{contrato_id}", response_model=ApiResponse[dict])
def eliminar_contrato(contrato_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    c = db.get(LiqContrato, contrato_id)
    if c is None:
        raise ApiError(404, "Contrato no encontrado")
    e = db.get(LiqEmpleado, c.empleado_id)
    auditar(db, request, "liq_contrato_eliminado", actual.id, documento=e.documento, inicio=c.fecha_inicio.isoformat())
    db.delete(c)
    db.flush()
    personal.sincronizar_estado(db, e)
    db.commit()
    return ok({"eliminado": contrato_id})


def _guardar_salida(x: LiqVacacionSalida, data: SalidaIn) -> None:
    for k, v in data.model_dump().items():
        setattr(x, k, v)
    if x.tipo == "compensadas" and x.estado == "programada":
        x.estado = "historico"


@router.post("/empleados/{empleado_id}/salidas", response_model=ApiResponse[dict], status_code=201)
def crear_salida(empleado_id: int, data: SalidaIn, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    e = _empleado(db, empleado_id)
    x = LiqVacacionSalida(empleado_id=e.id, origen="manual")
    _guardar_salida(x, data)
    db.add(x)
    db.flush()
    auditar(db, request, "liq_vacacion_salida_creada", actual.id, documento=e.documento, tipo=x.tipo,
            desde=x.desde.isoformat() if x.desde else None)
    db.commit()
    return ok(salida_out(x))


@router.put("/salidas/{salida_id}", response_model=ApiResponse[dict])
def editar_salida(salida_id: int, data: SalidaIn, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    x = db.get(LiqVacacionSalida, salida_id)
    if x is None:
        raise ApiError(404, "Registro de vacaciones no encontrado")
    _guardar_salida(x, data)
    auditar(db, request, "liq_vacacion_salida_editada", actual.id, salida=x.id, estado=x.estado)
    db.commit()
    return ok(salida_out(x))


@router.delete("/salidas/{salida_id}", response_model=ApiResponse[dict])
def eliminar_salida(salida_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    x = db.get(LiqVacacionSalida, salida_id)
    if x is None:
        raise ApiError(404, "Registro de vacaciones no encontrado")
    auditar(db, request, "liq_vacacion_salida_eliminada", actual.id, salida=x.id)
    db.delete(x)
    db.commit()
    return ok({"eliminado": salida_id})


@router.get("/personal/exportar-base", dependencies=[Depends(limitar("exportar", 10, 60))])
def exportar_base(request: Request, db: DbSession, actual: Usuario = Depends(require(VER))):
    """Base de personal con el formato de la importación (para corregirla en Excel y volver a subirla). El salario solo
    va con el permiso de nómina. Se genera en memoria y no se guarda."""
    from app.apps.liquidador.routes.periodos import _archivo
    from app.apps.liquidador.services.exportar_personal import exportar_base as generar

    contenido, tipo, nombre = generar(db, con_salario="liquidador.nomina.ver" in actual.permisos)
    auditar(db, request, "liq_base_personal_exportada", actual.id)
    db.commit()
    return _archivo(contenido, tipo, nombre)


@router.post("/personal/importar-base", response_model=ApiResponse[dict], dependencies=[Depends(limitar("liq_personal", 5, 60))])
async def importar_base(request: Request, db: DbSession, archivo: UploadFile = File(...), actual: Usuario = Depends(require(GESTIONAR))):
    """Base de personal de gestión humana (OPERATIVOS, ADMINISTRATIVOS, RETIROS OP, RETIROS ADMIN)."""
    contenido = await leer_xlsx(archivo)
    try:
        res = personal.importar_base(db, contenido)
    except personal.ErrorArchivo as e:
        db.rollback()
        raise ApiError(422, str(e), "EXCEL_INVALIDO") from e
    auditar(db, request, "liq_base_personal_importada", actual.id, archivo=(archivo.filename or "")[:255],
            **{k: v for k, v in res.items() if isinstance(v, int)}, hallazgos=len(res["hallazgos"]))
    db.commit()
    return ok(res)


@router.post("/personal/importar-vacaciones", response_model=ApiResponse[dict], dependencies=[Depends(limitar("liq_personal", 5, 60))])
async def importar_vacaciones(request: Request, db: DbSession, archivo: UploadFile = File(...), actual: Usuario = Depends(require(GESTIONAR))):
    """Libro de vacaciones (PERSONAL con el saldo al corte y FECHAS VACACIONES con las salidas)."""
    contenido = await leer_xlsx(archivo)
    try:
        res = personal.importar_vacaciones(db, contenido)
    except personal.ErrorArchivo as e:
        db.rollback()
        raise ApiError(422, str(e), "EXCEL_INVALIDO") from e
    auditar(db, request, "liq_libro_vacaciones_importado", actual.id, archivo=(archivo.filename or "")[:255],
            **{k: v for k, v in res.items() if isinstance(v, int)}, hallazgos=len(res["hallazgos"]))
    db.commit()
    return ok(res)
