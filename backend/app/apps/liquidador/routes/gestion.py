"""Gestión humana: incapacidades (con su CIE), restricciones médicas y casos jurídicos con sus soportes adjuntos, la
consulta de cuotas pendientes y el histórico de vacaciones. Es un repositorio de consulta: no afecta la nómina.

Los diagnósticos son datos sensibles de salud (Ley 1581 de 2012): solo los ve quien tiene el permiso de salud, y la
auditoría registra el registro tocado, nunca el diagnóstico."""

import hashlib
import re
from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import Response as RespuestaCruda
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import or_, select

from app.api.deps import CurrentUser, DbSession, require
from app.core.archivos import leer_xlsx
from app.core.auditoria import auditar
from app.core.paginacion import Paginacion, paginar_consulta, paginar_lista
from app.core.rate_limit import limitar
from app.core.respuestas import ApiError, ApiResponse, ok
from app.models import Usuario
from app.apps.liquidador.models import (
    DOCUMENTOS_DE, LiqCaso, LiqCasoActuacion, LiqCie, LiqDescuento, LiqDocumento, LiqEmpleado, LiqIncapacidad, LiqRestriccion,
    LiqVacacionSalida,
)
from app.apps.liquidador.services import gestion, personal
from app.apps.liquidador.services.nomina import descontado

router = APIRouter(tags=["liquidador: gestión humana"])
SALUD_VER, SALUD = "liquidador.salud.ver", "liquidador.salud.gestionar"
JURIDICO_VER, JURIDICO = "liquidador.juridico.ver", "liquidador.juridico.gestionar"
PERSONAL_VER = "liquidador.personal.ver"
# Permiso de cada módulo con soportes: (ver, gestionar)
PERMISOS_MODULO = {"incapacidad": (SALUD_VER, SALUD), "restriccion": (SALUD_VER, SALUD), "caso": (JURIDICO_VER, JURIDICO)}


def _persona(db, documento: str, nombre: str | None) -> tuple[str, LiqEmpleado | None, str]:
    """Documento, empleado (si está en la base) y nombre. Se puede registrar a alguien que no está en la base."""
    doc, _ = personal.documento(documento)
    if not doc:
        raise ApiError(422, "Escriba el documento")
    e = gestion.empleado_de(db, doc)
    nombre = (nombre or "").strip() or (e.nombre if e else "")
    if not nombre:
        raise ApiError(422, "Esa persona no está en la base de empleados: escriba su nombre")
    return (e.documento if e else doc), e, nombre[:200]


def _filtro_texto(consulta, modelo, q: str, *extra):
    if q.strip():
        patron = f"%{q.strip()}%"
        consulta = consulta.where(or_(modelo.documento.ilike(patron), modelo.nombre.ilike(patron), *(c.ilike(patron) for c in extra)))
    return consulta


def _documentos(db, modulo: str, ids: list[int]) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {i: [] for i in ids}
    if ids:
        for d in db.scalars(select(LiqDocumento).where(LiqDocumento.modulo == modulo, LiqDocumento.registro_id.in_(ids))
                            .order_by(LiqDocumento.id)):
            out[d.registro_id].append({"id": d.id, "nombre": d.nombre, "mime": d.mime, "bytes": d.bytes})
    return out


def _borrar_documentos(db, modulo: str, registro_id: int) -> None:
    for d in db.scalars(select(LiqDocumento).where(LiqDocumento.modulo == modulo, LiqDocumento.registro_id == registro_id)):
        db.delete(d)


def _texto(v: str | None, largo: int) -> str | None:
    return (v or "").strip()[:largo] or None


# --- Catálogo CIE-10 ---

@router.get("/cie", response_model=ApiResponse[list[dict]])
def buscar_cie(db: DbSession, q: str = Query("", max_length=100), _=Depends(require(SALUD_VER))):
    """Hasta 20 diagnósticos por código (prefijo) o por nombre."""
    gestion.sembrar_cie(db)
    texto = q.strip()
    if not texto:
        return ok([])
    codigo = re.sub(r"[^A-Za-z0-9]", "", texto).upper()
    consulta = select(LiqCie).order_by(LiqCie.codigo).limit(20)
    if re.fullmatch(r"[A-Z]\d{0,3}", codigo):
        consulta = consulta.where(LiqCie.codigo.startswith(codigo))
    else:
        consulta = consulta.where(LiqCie.descripcion.ilike(f"%{texto}%"))
    return ok([{"codigo": c.codigo, "descripcion": c.descripcion} for c in db.scalars(consulta)])


def _validar_cie(db, texto: str | None) -> tuple[str | None, list[str], dict[str, str]]:
    codigos = gestion.codigos_cie(texto)
    nombres = gestion.catalogo(db, set(codigos))
    return ",".join(codigos)[:60] or None, [c for c in codigos if c not in nombres], nombres


# --- Incapacidades ---

class IncapacidadIn(BaseModel):
    documento: str = Field(min_length=1, max_length=32)
    nombre: str | None = Field(None, max_length=200)
    puesto: str | None = Field(None, max_length=200)
    novedad: str = Field("incapacidad", pattern="^(" + "|".join(gestion.NOVEDADES) + ")$")
    origen: str | None = Field(None, pattern="^(" + "|".join(gestion.ORIGENES) + ")$")
    prorroga: bool = False
    desde: date
    hasta: date
    entidad: str | None = Field(None, max_length=80)
    cie: str | None = Field(None, max_length=60)
    diagnostico: str | None = Field(None, max_length=300)
    soporte: str | None = Field(None, pattern="^(" + "|".join(gestion.SOPORTES) + ")$")
    observacion: str | None = Field(None, max_length=300)

    @model_validator(mode="after")
    def _fechas(self):
        if self.hasta < self.desde:
            raise ValueError("La fecha de fin no puede ser anterior a la de inicio")
        if (self.hasta - self.desde).days > 366:
            raise ValueError("Una incapacidad no puede pasar de un año: regístrela por tramos (prórrogas)")
        return self


def _incapacidad_out(x: LiqIncapacidad, ac: dict, docs: dict, desconocidos: set[str]) -> dict:
    a = ac.get(x.id)
    hoy = date.today()
    return {
        "id": x.id, "documento": x.documento, "nombre": x.nombre, "empleado_id": x.empleado_id, "puesto": x.puesto,
        "novedad": x.novedad, "origen": x.origen, "prorroga": x.prorroga, "desde": x.desde.isoformat(), "hasta": x.hasta.isoformat(),
        "dias": x.dias, "entidad": x.entidad, "cie": x.cie, "diagnostico": x.diagnostico, "soporte": x.soporte,
        "observacion": x.observacion, "origen_registro": x.origen_registro, "vigente": x.desde <= hoy <= x.hasta,
        "acumulado": a.dias if a else None, "inicio_caso": a.inicio.isoformat() if a else None, "alerta": a.alerta if a else None,
        "cie_desconocidos": [c for c in (x.cie or "").split(",") if c in desconocidos],
        "documentos": docs.get(x.id, []),
    }


@router.get("/incapacidades", response_model=ApiResponse[list[dict]])
def listar_incapacidades(db: DbSession, p: Paginacion, q: str = Query("", max_length=100), anio: str = Query("", pattern=r"^(|\d{4})$"),
                         origen: str = Query("", max_length=30), novedad: str = Query("", max_length=30),
                         vista: str = Query("todas", pattern="^(todas|vigentes|prolongadas)$"),
                         _=Depends(require(SALUD_VER))):
    """Incapacidades con los días acumulados de cada una (inicial + prórrogas). «Prolongadas»: la última incapacidad
    de cada caso que pasa de 180 días acumulados."""
    todas = list(db.scalars(select(LiqIncapacidad)))
    ac = gestion.acumulados(todas)
    lista = list(db.scalars(_filtro_texto(select(LiqIncapacidad), LiqIncapacidad, q, LiqIncapacidad.cie, LiqIncapacidad.diagnostico)))
    if anio:  # vacío = todos los años
        lista = [x for x in lista if int(anio) in (x.desde.year, x.hasta.year)]
    if origen:
        lista = [x for x in lista if (x.origen or "") == origen]
    if novedad:
        lista = [x for x in lista if x.novedad == novedad]
    hoy = date.today()
    resumen = {"registros": len(lista), "dias": sum(x.dias for x in lista), "personas": len({x.documento for x in lista}),
               "vigentes": sum(1 for x in lista if x.desde <= hoy <= x.hasta)}
    ultimas: dict[tuple, LiqIncapacidad] = {}
    for x in lista:
        if (a := ac.get(x.id)) and a.dias > 180:
            clave = (x.documento, a.inicio)
            if clave not in ultimas or (x.hasta, x.id) > (ultimas[clave].hasta, ultimas[clave].id):
                ultimas[clave] = x
    resumen["prolongadas"] = len(ultimas)
    if vista == "vigentes":
        lista = [x for x in lista if x.desde <= hoy <= x.hasta]
    elif vista == "prolongadas":
        lista = list(ultimas.values())
    lista.sort(key=lambda x: (x.desde, x.id), reverse=True)
    pagina, meta = paginar_lista(lista, p)
    codigos = {c for x in pagina for c in (x.cie or "").split(",") if c}
    desconocidos = codigos - set(gestion.catalogo(db, codigos))
    docs = _documentos(db, "incapacidad", [x.id for x in pagina])
    return ok([_incapacidad_out(x, ac, docs, desconocidos) for x in pagina], **meta, resumen=resumen,
              anios=sorted({x.desde.year for x in todas}, reverse=True))


def _guardar_incapacidad(db, x: LiqIncapacidad, data: IncapacidadIn) -> list[str]:
    doc, e, nombre = _persona(db, data.documento, data.nombre)
    cie, desconocidos, nombres = _validar_cie(db, data.cie)
    x.documento, x.nombre, x.empleado_id = doc, nombre, e.id if e else None
    x.puesto = _texto(data.puesto, 200) or (e.puesto if e else None)
    x.novedad, x.origen, x.prorroga, x.desde, x.hasta = data.novedad, data.origen, data.prorroga, data.desde, data.hasta
    x.dias = (data.hasta - data.desde).days + 1
    x.entidad, x.cie = _texto(data.entidad, 80), cie
    x.diagnostico = _texto(data.diagnostico, 300) or (nombres.get(cie.split(",")[0]) if cie else None)
    x.soporte, x.observacion = data.soporte, _texto(data.observacion, 300)
    return desconocidos


@router.post("/incapacidades", response_model=ApiResponse[dict], status_code=201)
def crear_incapacidad(data: IncapacidadIn, request: Request, db: DbSession, actual: Usuario = Depends(require(SALUD))):
    x = LiqIncapacidad(origen_registro="manual", creado_por=actual.id)
    desconocidos = _guardar_incapacidad(db, x, data)
    repetida = db.scalar(select(LiqIncapacidad.id).where(LiqIncapacidad.documento == x.documento, LiqIncapacidad.desde == x.desde,
                                                         LiqIncapacidad.hasta == x.hasta).limit(1))
    if repetida:
        raise ApiError(409, "Esa persona ya tiene una incapacidad registrada con las mismas fechas", "REPETIDA")
    db.add(x)
    db.flush()
    auditar(db, request, "liq_incapacidad_creada", actual.id, incapacidad_id=x.id, documento=x.documento)
    db.commit()
    return ok({"id": x.id}, aviso=f"El código {', '.join(desconocidos)} no está en el catálogo CIE-10" if desconocidos else None)


@router.put("/incapacidades/{incapacidad_id}", response_model=ApiResponse[dict])
def editar_incapacidad(incapacidad_id: int, data: IncapacidadIn, request: Request, db: DbSession, actual: Usuario = Depends(require(SALUD))):
    x = db.get(LiqIncapacidad, incapacidad_id)
    if x is None:
        raise ApiError(404, "Incapacidad no encontrada")
    desconocidos = _guardar_incapacidad(db, x, data)
    auditar(db, request, "liq_incapacidad_editada", actual.id, incapacidad_id=x.id, documento=x.documento)
    db.commit()
    return ok({"id": x.id}, aviso=f"El código {', '.join(desconocidos)} no está en el catálogo CIE-10" if desconocidos else None)


@router.delete("/incapacidades/{incapacidad_id}", response_model=ApiResponse[dict])
def eliminar_incapacidad(incapacidad_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(SALUD))):
    x = db.get(LiqIncapacidad, incapacidad_id)
    if x is None:
        raise ApiError(404, "Incapacidad no encontrada")
    _borrar_documentos(db, "incapacidad", x.id)
    auditar(db, request, "liq_incapacidad_eliminada", actual.id, incapacidad_id=x.id, documento=x.documento)
    db.delete(x)
    db.commit()
    return ok({"eliminada": incapacidad_id})


# --- Restricciones médicas ---

class RestriccionIn(BaseModel):
    documento: str = Field(min_length=1, max_length=32)
    nombre: str | None = Field(None, max_length=200)
    puesto: str | None = Field(None, max_length=200)
    tipo: str = Field("restriccion", pattern="^(" + "|".join(gestion.TIPOS_RESTRICCION) + ")$")
    desde: date | None = None
    hasta: date | None = None
    cie: str | None = Field(None, max_length=60)
    diagnostico: str | None = Field(None, max_length=300)
    detalle: str | None = Field(None, max_length=4000)
    observacion: str | None = Field(None, max_length=300)

    @model_validator(mode="after")
    def _fechas(self):
        if self.desde and self.hasta and self.hasta < self.desde:
            raise ValueError("La fecha de fin no puede ser anterior a la de inicio")
        return self


def _estado_restriccion(x: LiqRestriccion) -> str:
    if x.tipo == "oncologico":
        return "seguimiento"
    hoy = date.today()
    if x.desde and x.desde > hoy:
        return "programada"
    return "vencida" if x.hasta and x.hasta < hoy else "vigente"


@router.get("/restricciones", response_model=ApiResponse[list[dict]])
def listar_restricciones(db: DbSession, p: Paginacion, q: str = Query("", max_length=100), tipo: str = Query("", max_length=20),
                         estado: str = Query("todas", pattern="^(todas|vigente|vencida|seguimiento|programada)$"),
                         _=Depends(require(SALUD_VER))):
    consulta = _filtro_texto(select(LiqRestriccion), LiqRestriccion, q, LiqRestriccion.diagnostico, LiqRestriccion.detalle)
    if tipo:
        consulta = consulta.where(LiqRestriccion.tipo == tipo)
    lista = [x for x in db.scalars(consulta) if estado == "todas" or _estado_restriccion(x) == estado]
    lista.sort(key=lambda x: (_estado_restriccion(x) != "vigente", -(x.hasta or date.max).toordinal(), x.nombre))
    pagina, meta = paginar_lista(lista, p)
    docs = _documentos(db, "restriccion", [x.id for x in pagina])
    return ok([{"id": x.id, "documento": x.documento, "nombre": x.nombre, "empleado_id": x.empleado_id, "puesto": x.puesto,
                "tipo": x.tipo, "desde": x.desde.isoformat() if x.desde else None, "hasta": x.hasta.isoformat() if x.hasta else None,
                "cie": x.cie, "diagnostico": x.diagnostico, "detalle": x.detalle, "observacion": x.observacion,
                "estado": _estado_restriccion(x), "documentos": docs.get(x.id, [])} for x in pagina], **meta)


def _guardar_restriccion(db, x: LiqRestriccion, data: RestriccionIn) -> None:
    doc, e, nombre = _persona(db, data.documento, data.nombre)
    cie, _, nombres = _validar_cie(db, data.cie)
    x.documento, x.nombre, x.empleado_id = doc, nombre, e.id if e else None
    x.puesto = _texto(data.puesto, 200) or (e.puesto if e else None)
    x.tipo, x.desde, x.hasta, x.cie = data.tipo, data.desde, data.hasta, cie
    x.diagnostico = _texto(data.diagnostico, 300) or (nombres.get(cie.split(",")[0]) if cie else None)
    x.detalle, x.observacion = (data.detalle or "").strip() or None, _texto(data.observacion, 300)


@router.post("/restricciones", response_model=ApiResponse[dict], status_code=201)
def crear_restriccion(data: RestriccionIn, request: Request, db: DbSession, actual: Usuario = Depends(require(SALUD))):
    x = LiqRestriccion(origen_registro="manual", creado_por=actual.id)
    _guardar_restriccion(db, x, data)
    db.add(x)
    db.flush()
    auditar(db, request, "liq_restriccion_creada", actual.id, restriccion_id=x.id, documento=x.documento)
    db.commit()
    return ok({"id": x.id})


@router.put("/restricciones/{restriccion_id}", response_model=ApiResponse[dict])
def editar_restriccion(restriccion_id: int, data: RestriccionIn, request: Request, db: DbSession, actual: Usuario = Depends(require(SALUD))):
    x = db.get(LiqRestriccion, restriccion_id)
    if x is None:
        raise ApiError(404, "Restricción no encontrada")
    _guardar_restriccion(db, x, data)
    auditar(db, request, "liq_restriccion_editada", actual.id, restriccion_id=x.id, documento=x.documento)
    db.commit()
    return ok({"id": x.id})


@router.delete("/restricciones/{restriccion_id}", response_model=ApiResponse[dict])
def eliminar_restriccion(restriccion_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(SALUD))):
    x = db.get(LiqRestriccion, restriccion_id)
    if x is None:
        raise ApiError(404, "Restricción no encontrada")
    _borrar_documentos(db, "restriccion", x.id)
    auditar(db, request, "liq_restriccion_eliminada", actual.id, restriccion_id=x.id, documento=x.documento)
    db.delete(x)
    db.commit()
    return ok({"eliminada": restriccion_id})


# --- Tutelas, demandas y derechos de petición ---

class CasoIn(BaseModel):
    documento: str = Field(min_length=1, max_length=32)
    nombre: str | None = Field(None, max_length=200)
    tipo: str = Field(pattern="^(" + "|".join(gestion.TIPOS_CASO) + ")$")
    asunto: str = Field(min_length=1, max_length=300)
    recibido: date
    vence: date | None = None
    estado: str = Field("abierto", pattern="^(" + "|".join(gestion.ESTADOS_CASO) + ")$")
    contacto: str | None = Field(None, max_length=200)
    observacion: str | None = Field(None, max_length=4000)


class ActuacionIn(BaseModel):
    fecha: date
    descripcion: str = Field(min_length=1, max_length=300)
    medio: str | None = Field(None, max_length=60)
    # Cambia el estado del caso junto con la actuación (p. ej. al contestar)
    estado: str | None = Field(None, pattern="^(" + "|".join(gestion.ESTADOS_CASO) + ")$")


def _caso_out(x: LiqCaso, docs: dict) -> dict:
    hoy = date.today()
    return {"id": x.id, "documento": x.documento, "nombre": x.nombre, "empleado_id": x.empleado_id, "tipo": x.tipo, "asunto": x.asunto,
            "recibido": x.recibido.isoformat(), "vence": x.vence.isoformat() if x.vence else None, "estado": x.estado,
            "vencido": x.estado == "abierto" and x.vence is not None and x.vence < hoy,
            "dias_abierto": (hoy - x.recibido).days if x.estado == "abierto" else None,
            "contacto": x.contacto, "observacion": x.observacion, "origen_registro": x.origen_registro,
            "actuaciones": [{"id": a.id, "fecha": a.fecha.isoformat() if a.fecha else None, "descripcion": a.descripcion, "medio": a.medio}
                            for a in sorted(x.actuaciones, key=lambda a: (a.fecha or date.min, a.id))],
            "documentos": docs.get(x.id, [])}


@router.get("/casos", response_model=ApiResponse[list[dict]])
def listar_casos(db: DbSession, p: Paginacion, q: str = Query("", max_length=100), tipo: str = Query("", max_length=20),
                 estado: str = Query("", max_length=12), _=Depends(require(JURIDICO_VER))):
    consulta = _filtro_texto(select(LiqCaso), LiqCaso, q, LiqCaso.asunto).order_by(LiqCaso.recibido.desc(), LiqCaso.id.desc())
    if tipo:
        consulta = consulta.where(LiqCaso.tipo == tipo)
    if estado:
        consulta = consulta.where(LiqCaso.estado == estado)
    lista, meta = paginar_consulta(db, consulta, p)
    abiertos = db.scalars(select(LiqCaso).where(LiqCaso.estado == "abierto")).all()
    hoy = date.today()
    resumen = {"abiertos": len(abiertos), "vencidos": sum(1 for x in abiertos if x.vence and x.vence < hoy)}
    docs = _documentos(db, "caso", [x.id for x in lista])
    return ok([_caso_out(x, docs) for x in lista], **meta, resumen=resumen)


def _guardar_caso(db, x: LiqCaso, data: CasoIn) -> None:
    doc, e, nombre = _persona(db, data.documento, data.nombre)
    x.documento, x.nombre, x.empleado_id = doc, nombre, e.id if e else None
    x.tipo, x.asunto, x.recibido, x.vence, x.estado = data.tipo, data.asunto.strip(), data.recibido, data.vence, data.estado
    x.contacto, x.observacion = _texto(data.contacto, 200), (data.observacion or "").strip() or None


@router.post("/casos", response_model=ApiResponse[dict], status_code=201)
def crear_caso(data: CasoIn, request: Request, db: DbSession, actual: Usuario = Depends(require(JURIDICO))):
    x = LiqCaso(origen_registro="manual", creado_por=actual.id)
    _guardar_caso(db, x, data)
    db.add(x)
    db.flush()
    auditar(db, request, "liq_caso_creado", actual.id, caso_id=x.id, documento=x.documento, tipo=x.tipo)
    db.commit()
    return ok({"id": x.id})


@router.put("/casos/{caso_id}", response_model=ApiResponse[dict])
def editar_caso(caso_id: int, data: CasoIn, request: Request, db: DbSession, actual: Usuario = Depends(require(JURIDICO))):
    x = db.get(LiqCaso, caso_id)
    if x is None:
        raise ApiError(404, "Caso no encontrado")
    _guardar_caso(db, x, data)
    auditar(db, request, "liq_caso_editado", actual.id, caso_id=x.id, documento=x.documento, estado=x.estado)
    db.commit()
    return ok({"id": x.id})


@router.delete("/casos/{caso_id}", response_model=ApiResponse[dict])
def eliminar_caso(caso_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(JURIDICO))):
    x = db.get(LiqCaso, caso_id)
    if x is None:
        raise ApiError(404, "Caso no encontrado")
    _borrar_documentos(db, "caso", x.id)
    auditar(db, request, "liq_caso_eliminado", actual.id, caso_id=x.id, documento=x.documento)
    db.delete(x)
    db.commit()
    return ok({"eliminado": caso_id})


@router.post("/casos/{caso_id}/actuaciones", response_model=ApiResponse[dict], status_code=201)
def agregar_actuacion(caso_id: int, data: ActuacionIn, request: Request, db: DbSession, actual: Usuario = Depends(require(JURIDICO))):
    x = db.get(LiqCaso, caso_id)
    if x is None:
        raise ApiError(404, "Caso no encontrado")
    a = LiqCasoActuacion(fecha=data.fecha, descripcion=data.descripcion.strip(), medio=_texto(data.medio, 60))
    x.actuaciones.append(a)
    if data.estado:
        x.estado = data.estado
    db.flush()
    auditar(db, request, "liq_caso_actuacion", actual.id, caso_id=x.id, estado=x.estado)
    db.commit()
    return ok({"id": a.id, "estado": x.estado})


@router.delete("/casos/actuaciones/{actuacion_id}", response_model=ApiResponse[dict])
def eliminar_actuacion(actuacion_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(JURIDICO))):
    a = db.get(LiqCasoActuacion, actuacion_id)
    if a is None:
        raise ApiError(404, "Actuación no encontrada")
    auditar(db, request, "liq_caso_actuacion_eliminada", actual.id, caso_id=a.caso_id)
    db.delete(a)
    db.commit()
    return ok({"eliminada": actuacion_id})


# --- Soportes adjuntos (excepción a "no guardar archivos": repositorio documental de gestión humana) ---

MAX_DOCUMENTO = 10 * 1024 * 1024
MAX_DOCUMENTOS = 10
FIRMAS = ((b"%PDF-", "application/pdf", ".pdf"), (b"\x89PNG\r\n\x1a\n", "image/png", ".png"), (b"\xff\xd8\xff", "image/jpeg", ".jpg"))


def _puede(actual: Usuario, modulo: str, gestionar: bool) -> None:
    if modulo not in PERMISOS_MODULO:
        raise ApiError(404, "Módulo no encontrado")
    permiso = PERMISOS_MODULO[modulo][1 if gestionar else 0]
    if permiso not in actual.permisos:
        raise ApiError(403, "No tiene permiso para realizar esta acción", details=[{"permiso": permiso}])


@router.post("/documentos/{modulo}/{registro_id}", response_model=ApiResponse[dict], status_code=201,
             dependencies=[Depends(limitar("liq_documento", 30, 60))])
async def adjuntar(modulo: str, registro_id: int, request: Request, db: DbSession, actual: CurrentUser, archivo: UploadFile = File(...)):
    """Adjunta un soporte (PDF, PNG o JPG; máx. 10 MB). Se valida por su contenido real."""
    _puede(actual, modulo, True)
    if db.get(DOCUMENTOS_DE[modulo], registro_id) is None:
        raise ApiError(404, "Registro no encontrado")
    cantidad = len(db.scalars(select(LiqDocumento.id).where(LiqDocumento.modulo == modulo, LiqDocumento.registro_id == registro_id)).all())
    if cantidad >= MAX_DOCUMENTOS:
        raise ApiError(409, f"El registro ya tiene {MAX_DOCUMENTOS} soportes")
    try:
        contenido = await archivo.read(MAX_DOCUMENTO + 1)
    finally:
        await archivo.close()
    if len(contenido) > MAX_DOCUMENTO:
        raise ApiError(413, "El soporte supera los 10 MB")
    tipo = next(((mime, ext) for firma, mime, ext in FIRMAS if contenido.startswith(firma)), None)
    if tipo is None:
        raise ApiError(415, "Solo se aceptan soportes en PDF, PNG o JPG")
    mime, ext = tipo
    base = re.sub(r"[^\w.\- ]+", "_", (archivo.filename or "soporte").rsplit(".", 1)[0]).strip()[:150] or "soporte"
    d = LiqDocumento(modulo=modulo, registro_id=registro_id, nombre=base + ext, mime=mime, bytes=len(contenido),
                     sha256=hashlib.sha256(contenido).hexdigest(), contenido=contenido, cargado_por=actual.id)
    db.add(d)
    db.flush()
    auditar(db, request, "liq_documento_cargado", actual.id, modulo=modulo, registro_id=registro_id, documento_id=d.id, bytes=d.bytes,
            sha256=d.sha256)
    db.commit()
    return ok({"id": d.id, "nombre": d.nombre, "mime": d.mime, "bytes": d.bytes})


@router.get("/documentos/{documento_id}")
def descargar(documento_id: int, request: Request, db: DbSession, actual: CurrentUser):
    d = db.get(LiqDocumento, documento_id)
    if d is None:
        raise ApiError(404, "Soporte no encontrado")
    _puede(actual, d.modulo, False)
    auditar(db, request, "liq_documento_consultado", actual.id, modulo=d.modulo, registro_id=d.registro_id, documento_id=d.id)
    db.commit()
    return RespuestaCruda(d.contenido, media_type=d.mime, headers={
        "Content-Disposition": f"inline; filename*=UTF-8''{quote(d.nombre)}",
        "Cache-Control": "private, no-store",
    })


@router.delete("/documentos/{documento_id}", response_model=ApiResponse[dict])
def quitar(documento_id: int, request: Request, db: DbSession, actual: CurrentUser):
    d = db.get(LiqDocumento, documento_id)
    if d is None:
        raise ApiError(404, "Soporte no encontrado")
    _puede(actual, d.modulo, True)
    auditar(db, request, "liq_documento_eliminado", actual.id, modulo=d.modulo, registro_id=d.registro_id, sha256=d.sha256)
    db.delete(d)
    db.commit()
    return ok({"eliminado": documento_id})


# --- Importación del formato de ausentismo ---

@router.post("/gestion/importar-ausentismo", response_model=ApiResponse[dict], dependencies=[Depends(limitar("liq_personal", 5, 60))])
async def importar_ausentismo(request: Request, db: DbSession, actual: CurrentUser, archivo: UploadFile = File(...)):
    """Formato de caracterización de ausentismo: incapacidades y restricciones (con el permiso de salud) y derechos de
    petición, tutelas y demandas (con el permiso jurídico). El archivo se procesa y se descarta."""
    salud, juridico = SALUD in actual.permisos, JURIDICO in actual.permisos
    if not salud and not juridico:
        raise ApiError(403, "No tiene permiso para realizar esta acción", details=[{"permiso": SALUD}])
    contenido = await leer_xlsx(archivo)
    try:
        res = gestion.importar_ausentismo(db, contenido, salud=salud, juridico=juridico, usuario_id=actual.id)
    except personal.ErrorArchivo as e:
        db.rollback()
        raise ApiError(422, str(e), "EXCEL_INVALIDO") from e
    auditar(db, request, "liq_ausentismo_importado", actual.id, archivo=(archivo.filename or "")[:255], hallazgos=len(res["hallazgos"]),
            **{k: v["creadas"] for k, v in res.items() if k != "hallazgos"})
    db.commit()
    return ok(res)


# --- Consultas de gestión humana ---

@router.get("/personal/cuotas-pendientes", response_model=ApiResponse[list[dict]])
def cuotas_pendientes(db: DbSession, p: Paginacion, q: str = Query("", max_length=100),
                      tipo: str = Query("", pattern="^(|prestamo|embargo|cuota)$"), _=Depends(require(PERSONAL_VER))):
    """Préstamos, embargos y cuotas activos con lo descontado y el saldo (solo consulta)."""
    consulta = select(LiqDescuento).join(LiqEmpleado).where(LiqDescuento.activo.is_(True)).order_by(LiqEmpleado.nombre, LiqDescuento.desde)
    if q.strip():
        patron = f"%{q.strip()}%"
        consulta = consulta.where(or_(LiqEmpleado.documento.ilike(patron), LiqEmpleado.nombre.ilike(patron), LiqDescuento.descripcion.ilike(patron)))
    if tipo:
        consulta = consulta.where(LiqDescuento.tipo == tipo)
    lista, meta = paginar_consulta(db, consulta, p)
    ya = descontado(db, {x.id for x in lista})
    out = []
    for x in lista:
        hecho = float(ya.get(x.id, 0))
        out.append({"id": x.id, "empleado_id": x.empleado_id, "documento": x.empleado.documento, "nombre": x.empleado.nombre,
                    "tipo": x.tipo, "descripcion": x.descripcion,
                    "valor_mensual": float(x.valor_mensual) if x.valor_mensual is not None else None,
                    "porcentaje": float(x.porcentaje) if x.porcentaje is not None else None,
                    "monto_total": float(x.monto_total) if x.monto_total is not None else None, "descontado": hecho,
                    "saldo": max(float(x.monto_total) - hecho, 0) if x.monto_total is not None else None,
                    "desde": x.desde.isoformat(), "hasta": x.hasta.isoformat() if x.hasta else None, "quincena": x.quincena or "ambas"})
    return ok(out, **meta)


@router.get("/personal/salidas", response_model=ApiResponse[list[dict]])
def salidas_vacaciones(db: DbSession, p: Paginacion, q: str = Query("", max_length=100), anio: str = Query("", pattern=r"^(|\d{4})$"),
                       estado: str = Query("", pattern="^(|historico|programada|cancelada)$"), _=Depends(require(PERSONAL_VER))):
    """Histórico de vacaciones de todo el personal (libro de vacaciones y registros manuales)."""
    consulta = select(LiqVacacionSalida, LiqEmpleado).join(LiqEmpleado, LiqEmpleado.id == LiqVacacionSalida.empleado_id) \
        .order_by(LiqVacacionSalida.desde.desc().nulls_last(), LiqVacacionSalida.id.desc())
    if q.strip():
        patron = f"%{q.strip()}%"
        consulta = consulta.where(or_(LiqEmpleado.documento.ilike(patron), LiqEmpleado.nombre.ilike(patron)))
    if estado:
        consulta = consulta.where(LiqVacacionSalida.estado == estado)
    filas = db.execute(consulta).all()
    if anio:  # vacío = todos los años
        filas = [(s, e) for s, e in filas if s.desde and s.desde.year == int(anio)]
    pagina, meta = paginar_lista(filas, p)
    return ok([{"id": s.id, "empleado_id": e.id, "documento": e.documento, "nombre": e.nombre, "puesto": e.puesto, "tipo": s.tipo,
                "desde": s.desde.isoformat() if s.desde else None, "hasta": s.hasta.isoformat() if s.hasta else None,
                "retorno": s.retorno.isoformat() if s.retorno else None, "dias_habiles": s.dias_habiles, "estado": s.estado,
                "observacion": s.observacion, "origen": s.origen} for s, e in pagina], **meta)
