"""MFP: clientes, MFP, ítems pactados, movimientos (con tope y autorización), terminación, vistas y Excel."""

import hashlib
import re
from collections import defaultdict
from datetime import date
from io import BytesIO
from urllib.parse import quote

import xlsxwriter
from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import Response as RespuestaCruda
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, require
from app.apps.costeo.models import UNIDADES, CstCliente, CstMfp, CstMfpItem, CstMovimiento, CstSoporte, CstTipoDocumento, CstTipoItem
from app.apps.costeo.services import importador
from app.apps.costeo.services.mfp import HORAS, resumen, tope_movimiento
from app.core.archivos import leer_xlsx
from app.core.rate_limit import limitar
from app.core.auditoria import auditar
from app.core.respuestas import ApiError, ApiResponse, ok
from app.models import Usuario

router = APIRouter()
VER, MOVIMIENTOS, GESTIONAR, CONFIGURAR, AUTORIZAR = "costeo.ver", "costeo.movimientos", "costeo.mfp", "costeo.configurar", "costeo.autorizar"


def _mfps(db: DbSession, ids: list[int] | None = None) -> list[CstMfp]:
    q = select(CstMfp).options(selectinload(CstMfp.items).selectinload(CstMfpItem.movimientos).selectinload(CstMovimiento.soportes)) \
        .order_by(CstMfp.id.desc())
    if ids is not None:
        q = q.where(CstMfp.id.in_(ids))
    return list(db.scalars(q).unique())


def _mfp(db: DbSession, mfp_id: int) -> CstMfp:
    lista = _mfps(db, [mfp_id])
    if not lista:
        raise ApiError(404, "MFP no encontrada")
    return lista[0]


def _fecha_ref(fecha: date | None) -> date:
    return fecha or date.today()


# --- Clientes -----------------------------------------------------------------------------------------

class ClienteIn(BaseModel):
    nit: str = Field(default="", max_length=60)
    nombre: str = Field(min_length=2, max_length=200)
    activo: bool = True


@router.get("/clientes", response_model=ApiResponse[list[dict]])
def clientes(db: DbSession, _=Depends(require(VER))):
    hoy = date.today()
    por_cliente: dict[int, list[dict]] = defaultdict(list)
    for m in _mfps(db):
        por_cliente[m.cliente_id].append(resumen(m, hoy))
    out = []
    for c in db.scalars(select(CstCliente).order_by(CstCliente.nombre)):
        r = por_cliente.get(c.id, [])
        out.append({"id": c.id, "nit": c.nit, "nombre": c.nombre, "activo": c.activo, "mfp": len(r),
                    "vigentes": sum(1 for x in r if x["estado"] == "vigente"),
                    "facturacion_total": sum(x["facturacion_total"] for x in r), "pactado": sum(x["pactado"] for x in r),
                    "ejecutado": sum(x["ejecutado"] for x in r), "pendiente": sum(x["pendiente"] for x in r),
                    "reembolso": sum(x["reembolso"] for x in r), "alertas": sum(len(x["alertas"]) for x in r)})
    return ok(out)


@router.post("/clientes", response_model=ApiResponse[dict], status_code=201)
def crear_cliente(data: ClienteIn, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    c = CstCliente(nit=data.nit.strip(), nombre=data.nombre.strip(), activo=data.activo)
    db.add(c)
    db.flush()
    auditar(db, request, "cst_cliente_creado", actual.id, cliente=c.nombre, nit=c.nit)
    db.commit()
    return ok({"id": c.id, "nit": c.nit, "nombre": c.nombre, "activo": c.activo})


@router.put("/clientes/{cliente_id}", response_model=ApiResponse[dict])
def editar_cliente(cliente_id: int, data: ClienteIn, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    c = db.get(CstCliente, cliente_id)
    if c is None:
        raise ApiError(404, "Cliente no encontrado")
    c.nit, c.nombre, c.activo = data.nit.strip(), data.nombre.strip(), data.activo
    auditar(db, request, "cst_cliente_editado", actual.id, cliente=c.nombre, nit=c.nit)
    db.commit()
    return ok({"id": c.id, "nit": c.nit, "nombre": c.nombre, "activo": c.activo})


# --- Tipos de ítem ------------------------------------------------------------------------------------

class TipoIn(BaseModel):
    id: int | None = None
    codigo: str = Field(min_length=2, max_length=30, pattern=r"^[A-Z0-9_]+$")
    nombre: str = Field(min_length=2, max_length=120)
    unidad: str = Field(pattern=r"^(pesos|pesos_mes|horas)$")
    reembolsable: bool = True
    cuenta_en_mfp: bool = True
    activo: bool = True


def _tipo_out(t: CstTipoItem) -> dict:
    return {"id": t.id, "codigo": t.codigo, "nombre": t.nombre, "unidad": t.unidad, "reembolsable": t.reembolsable,
            "cuenta_en_mfp": t.cuenta_en_mfp, "activo": t.activo}


@router.get("/tipos-item", response_model=ApiResponse[list[dict]])
def tipos(db: DbSession, _=Depends(require(VER))):
    return ok([_tipo_out(t) for t in db.scalars(select(CstTipoItem).order_by(CstTipoItem.orden, CstTipoItem.nombre))])


@router.put("/tipos-item", response_model=ApiResponse[dict])
def guardar_tipo(data: TipoIn, request: Request, db: DbSession, actual: Usuario = Depends(require(CONFIGURAR))):
    t = db.get(CstTipoItem, data.id) if data.id else None
    if data.id and t is None:
        raise ApiError(404, "Tipo de ítem no encontrado")
    otro = db.scalar(select(CstTipoItem).where(CstTipoItem.codigo == data.codigo))
    if otro is not None and otro is not t:
        raise ApiError(409, f"Ya existe el tipo {data.codigo}")
    if t is None:
        t = CstTipoItem(codigo=data.codigo, orden=1000)
        db.add(t)
    elif t.unidad != data.unidad and db.scalar(select(CstMfpItem.id).where(CstMfpItem.tipo_id == t.id).limit(1)):
        raise ApiError(409, "No se puede cambiar la unidad de un tipo que ya tiene ítems pactados")
    t.codigo, t.nombre, t.unidad = data.codigo, data.nombre.strip(), data.unidad
    t.reembolsable, t.cuenta_en_mfp, t.activo = data.reembolsable, data.cuenta_en_mfp, data.activo
    auditar(db, request, "cst_tipo_item", actual.id, codigo=t.codigo, unidad=t.unidad, reembolsable=t.reembolsable)
    db.commit()
    return ok(_tipo_out(t))


# --- MFP ----------------------------------------------------------------------------------------------

class ItemIn(BaseModel):
    tipo_id: int
    pactado: float = Field(ge=0, le=1e13)
    descripcion: str = Field(default="", max_length=300)


class MfpIn(BaseModel):
    numero: str = Field(min_length=1, max_length=30)
    cliente_id: int
    contrato: str = Field(default="", max_length=80)
    fecha_inicio: date | None = None
    duracion_meses: int | None = Field(default=None, ge=1, le=240)
    valor_mensual: float = Field(default=0, ge=0, le=1e13)
    pct_comercial: float | None = Field(default=None, ge=0, le=1)
    notas: str = Field(default="", max_length=2000)
    items: list[ItemIn] = Field(default_factory=list, max_length=50)


def _detalle(m: CstMfp, hoy: date, fecha_reembolso: date | None = None) -> dict:
    r = resumen(m, hoy, fecha_reembolso)
    movimientos = {it.id: it.movimientos for it in m.items}
    for i in r["items"]:
        i["movimientos"] = [{"id": x.id, "fecha": x.fecha.isoformat(), "valor": float(x.valor), "descripcion": x.descripcion,
                             "tipo_documento": x.tipo_documento, "numero_documento": x.numero_documento,
                             "soportes": [{"id": s.id, "nombre": s.nombre, "mime": s.mime, "bytes": s.bytes} for s in x.soportes],
                             "soporte": x.soporte, "excede": x.excede, "autorizacion": x.autorizacion,
                             "creado_en": x.creado_en.isoformat() if x.creado_en else ""}
                            for x in sorted(movimientos.get(i["id"], []), key=lambda x: (x.fecha, x.id), reverse=True)]
    return r


@router.get("/mfp", response_model=ApiResponse[list[dict]])
def listar(db: DbSession, q: str = Query("", max_length=100), cliente_id: int | None = None,
           estado: str = Query("", max_length=20), con_alertas: bool = False, _=Depends(require(VER))):
    hoy = date.today()
    t = q.strip().lower()
    out = []
    for m in _mfps(db):
        if cliente_id and m.cliente_id != cliente_id:
            continue
        if t and t not in f"{m.numero} {m.contrato} {m.cliente.nombre} {m.cliente.nit}".lower():
            continue
        r = resumen(m, hoy)
        if estado and r["estado"] != estado:
            continue
        if con_alertas and not r["alertas"]:
            continue
        r.pop("items")
        out.append(r)
    totales = {k: sum(x[k] for x in out) for k in ("facturacion_total", "pactado", "ejecutado", "pendiente", "reembolso")}
    return ok(out, totales=totales)


@router.post("/mfp", response_model=ApiResponse[dict], status_code=201)
def crear(data: MfpIn, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    if db.get(CstCliente, data.cliente_id) is None:
        raise ApiError(422, "Cliente no encontrado")
    m = CstMfp(**data.model_dump(exclude={"items"}), creado_por=actual.id)
    db.add(m)
    db.flush()
    for it in data.items:
        _validar_tipo(db, it.tipo_id)
        db.add(CstMfpItem(mfp_id=m.id, tipo_id=it.tipo_id, pactado=it.pactado, descripcion=it.descripcion.strip()))
    auditar(db, request, "cst_mfp_creada", actual.id, numero=m.numero, cliente_id=m.cliente_id)
    db.commit()
    return ok(_detalle(_mfp(db, m.id), date.today()))


def _validar_tipo(db: DbSession, tipo_id: int) -> CstTipoItem:
    t = db.get(CstTipoItem, tipo_id)
    if t is None or not t.activo:
        raise ApiError(422, "Tipo de ítem no válido")
    return t


@router.get("/mfp/{mfp_id}", response_model=ApiResponse[dict])
def ver(mfp_id: int, db: DbSession, fecha_reembolso: date | None = None, _=Depends(require(VER))):
    return ok(_detalle(_mfp(db, mfp_id), date.today(), fecha_reembolso))


@router.put("/mfp/{mfp_id}", response_model=ApiResponse[dict])
def editar(mfp_id: int, data: MfpIn, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    m = _mfp(db, mfp_id)
    if db.get(CstCliente, data.cliente_id) is None:
        raise ApiError(422, "Cliente no encontrado")
    for k, v in data.model_dump(exclude={"items"}).items():
        setattr(m, k, v)
    auditar(db, request, "cst_mfp_editada", actual.id, numero=m.numero)
    db.commit()
    return ok(_detalle(_mfp(db, mfp_id), date.today()))


@router.delete("/mfp/{mfp_id}", response_model=ApiResponse[dict])
def eliminar(mfp_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    m = _mfp(db, mfp_id)
    if any(it.movimientos for it in m.items):
        raise ApiError(409, "La MFP tiene movimientos registrados: no se puede eliminar")
    auditar(db, request, "cst_mfp_eliminada", actual.id, numero=m.numero)
    db.delete(m)
    db.commit()
    return ok({"eliminado": mfp_id})


class TerminarIn(BaseModel):
    fecha: date


@router.post("/mfp/{mfp_id}/terminar", response_model=ApiResponse[dict])
def terminar(mfp_id: int, data: TerminarIn, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    """Terminación anticipada: fija la fecha con la que se calcula el reembolso; lo pactado sin ejecutar se cancela."""
    m = _mfp(db, mfp_id)
    if m.fecha_inicio and data.fecha < m.fecha_inicio:
        raise ApiError(422, "La fecha de terminación es anterior al inicio del contrato")
    m.terminada, m.fecha_terminacion = True, data.fecha
    r = _detalle(m, date.today())
    auditar(db, request, "cst_mfp_terminada", actual.id, numero=m.numero, fecha=data.fecha.isoformat(), reembolso=r["reembolso"])
    db.commit()
    return ok(r)


@router.post("/mfp/{mfp_id}/reactivar", response_model=ApiResponse[dict])
def reactivar(mfp_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    m = _mfp(db, mfp_id)
    m.terminada, m.fecha_terminacion = False, None
    auditar(db, request, "cst_mfp_reactivada", actual.id, numero=m.numero)
    db.commit()
    return ok(_detalle(m, date.today()))


# --- Ítems y movimientos ------------------------------------------------------------------------------

@router.post("/mfp/{mfp_id}/items", response_model=ApiResponse[dict], status_code=201)
def agregar_item(mfp_id: int, data: ItemIn, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    m = _mfp(db, mfp_id)
    t = _validar_tipo(db, data.tipo_id)
    db.add(CstMfpItem(mfp_id=m.id, tipo_id=t.id, pactado=data.pactado, descripcion=data.descripcion.strip()))
    auditar(db, request, "cst_item_agregado", actual.id, numero=m.numero, tipo=t.codigo, pactado=data.pactado)
    db.commit()
    db.expire_all()
    return ok(_detalle(_mfp(db, mfp_id), date.today()))


def _item(db: DbSession, item_id: int) -> CstMfpItem:
    it = db.get(CstMfpItem, item_id)
    if it is None:
        raise ApiError(404, "Ítem no encontrado")
    return it


class ItemEditar(BaseModel):
    pactado: float = Field(ge=0, le=1e13)
    descripcion: str = Field(default="", max_length=300)


@router.put("/items/{item_id}", response_model=ApiResponse[dict])
def editar_item(item_id: int, data: ItemEditar, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    it = _item(db, item_id)
    antes = float(it.pactado)
    it.pactado, it.descripcion = data.pactado, data.descripcion.strip()
    auditar(db, request, "cst_item_editado", actual.id, mfp_id=it.mfp_id, tipo=it.tipo.codigo, antes=antes, despues=data.pactado)
    db.commit()
    return ok(_detalle(_mfp(db, it.mfp_id), date.today()))


@router.delete("/items/{item_id}", response_model=ApiResponse[dict])
def eliminar_item(item_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    it = _item(db, item_id)
    if it.movimientos:
        raise ApiError(409, "El ítem tiene movimientos: elimínelos primero")
    mfp_id = it.mfp_id
    auditar(db, request, "cst_item_eliminado", actual.id, mfp_id=mfp_id, tipo=it.tipo.codigo)
    db.delete(it)
    db.commit()
    return ok(_detalle(_mfp(db, mfp_id), date.today()))


class MovimientoIn(BaseModel):
    fecha: date
    valor: float = Field(gt=0, le=1e13)
    descripcion: str = Field(min_length=2, max_length=300)
    tipo_documento: str = Field(default="", max_length=20)  # obligatorio en los ítems en pesos
    numero_documento: str = Field(default="", max_length=40)
    soporte: str = Field(default="", max_length=300)  # observación
    autorizacion: str = Field(default="", max_length=300)  # solo para superar el tope


@router.post("/items/{item_id}/movimientos", response_model=ApiResponse[dict], status_code=201)
def registrar(item_id: int, data: MovimientoIn, request: Request, db: DbSession, actual: Usuario = Depends(require(MOVIMIENTOS))):
    """Registra un pago, una aplicación o una solicitud de horas. Si supera lo pactado (o la bolsa del año), solo
    se acepta con el permiso de autorizar y el soporte de la autorización."""
    it = _item(db, item_id)
    m = _mfp(db, it.mfp_id)
    it = next(x for x in m.items if x.id == item_id)
    if m.fecha_inicio and data.fecha < m.fecha_inicio:
        raise ApiError(422, "La fecha es anterior al inicio del contrato")
    if it.tipo.unidad == HORAS and m.terminada:
        raise ApiError(422, "La MFP está terminada: la bolsa de horas ya no está disponible")
    # Las solicitudes de horas no llevan documento contable; los ítems en pesos sí
    tipo_doc, numero = ("", "") if it.tipo.unidad == HORAS else (data.tipo_documento.strip().upper(), data.numero_documento.strip())
    if it.tipo.unidad != HORAS and (not tipo_doc or not numero):
        raise ApiError(422, "Indique el tipo y el número del documento contable que respalda el movimiento")
    if tipo_doc:
        t = db.get(CstTipoDocumento, tipo_doc)
        if t is None or not t.activo:
            raise ApiError(422, f"Tipo de documento contable no válido: {tipo_doc}")
    exceso = tope_movimiento(m, it, data.valor, data.fecha)
    if exceso:
        if AUTORIZAR not in actual.permisos:
            raise ApiError(409, f"{exceso}. Para superarlo se necesita la autorización de un administrador.", "TOPE_EXCEDIDO",
                           details=[{"puede_autorizar": False}])
        if len(data.autorizacion.strip()) < 5:
            raise ApiError(409, f"{exceso}. Escriba la autorización (quién lo aprobó y el soporte) para registrarlo.", "TOPE_EXCEDIDO",
                           details=[{"puede_autorizar": True}])
    mov = CstMovimiento(item_id=it.id, fecha=data.fecha, valor=data.valor, descripcion=data.descripcion.strip(), soporte=data.soporte.strip(),
                        tipo_documento=tipo_doc, numero_documento=numero,
                        excede=bool(exceso), autorizacion=data.autorizacion.strip() if exceso else "",
                        autorizado_por=actual.id if exceso else None, creado_por=actual.id)
    db.add(mov)
    db.flush()
    mov_id = mov.id
    auditar(db, request, "cst_movimiento", actual.id, mfp=m.numero, tipo=it.tipo.codigo, valor=data.valor, fecha=data.fecha.isoformat(),
            documento=f"{tipo_doc} {numero}".strip(), excede=bool(exceso))
    db.commit()
    db.expire_all()
    return ok(_detalle(_mfp(db, m.id), date.today()), movimiento_id=mov_id)


@router.delete("/movimientos/{mov_id}", response_model=ApiResponse[dict])
def anular(mov_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    mov = db.get(CstMovimiento, mov_id)
    if mov is None:
        raise ApiError(404, "Movimiento no encontrado")
    mfp_id = mov.item.mfp_id
    auditar(db, request, "cst_movimiento_eliminado", actual.id, mfp_id=mfp_id, valor=float(mov.valor), fecha=mov.fecha.isoformat(),
            descripcion=mov.descripcion)
    db.delete(mov)
    db.commit()
    db.expire_all()
    return ok(_detalle(_mfp(db, mfp_id), date.today()))


# --- Soportes contables (única excepción a "no guardar archivos": se conservan como evidencia) ---------

MAX_SOPORTE = 10 * 1024 * 1024
MAX_SOPORTES = 5
FIRMAS = ((b"%PDF-", "application/pdf", ".pdf"), (b"\x89PNG\r\n\x1a\n", "image/png", ".png"), (b"\xff\xd8\xff", "image/jpeg", ".jpg"))


def _tipo_archivo(contenido: bytes) -> tuple[str, str] | None:
    return next(((mime, ext) for firma, mime, ext in FIRMAS if contenido.startswith(firma)), None)


@router.post("/movimientos/{mov_id}/soportes", response_model=ApiResponse[dict], status_code=201,
             dependencies=[Depends(limitar("cst_soporte", 30, 60))])
async def adjuntar(mov_id: int, request: Request, db: DbSession, archivo: UploadFile = File(...), actual: Usuario = Depends(require(MOVIMIENTOS))):
    """Adjunta el soporte contable (PDF, PNG o JPG; máx. 10 MB) a un movimiento. Se valida por su contenido real."""
    mov = db.get(CstMovimiento, mov_id)
    if mov is None:
        raise ApiError(404, "Movimiento no encontrado")
    if len(mov.soportes) >= MAX_SOPORTES:
        raise ApiError(409, f"El movimiento ya tiene {MAX_SOPORTES} soportes")
    try:
        contenido = await archivo.read(MAX_SOPORTE + 1)
    finally:
        await archivo.close()
    if len(contenido) > MAX_SOPORTE:
        raise ApiError(413, "El soporte supera los 10 MB")
    tipo = _tipo_archivo(contenido)
    if tipo is None:
        raise ApiError(415, "Solo se aceptan soportes en PDF, PNG o JPG")
    mime, ext = tipo
    base = re.sub(r"[^\w.\- ]+", "_", (archivo.filename or "soporte").rsplit(".", 1)[0]).strip()[:150] or "soporte"
    s = CstSoporte(movimiento_id=mov.id, nombre=base + ext, mime=mime, bytes=len(contenido), sha256=hashlib.sha256(contenido).hexdigest(),
                   contenido=contenido, cargado_por=actual.id)
    db.add(s)
    db.flush()
    auditar(db, request, "cst_soporte_cargado", actual.id, movimiento_id=mov.id, archivo=s.nombre, bytes=s.bytes, sha256=s.sha256)
    db.commit()
    return ok({"id": s.id, "nombre": s.nombre, "mime": s.mime, "bytes": s.bytes})


@router.get("/soportes/{soporte_id}")
def descargar_soporte(soporte_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(VER))):
    s = db.get(CstSoporte, soporte_id)
    if s is None:
        raise ApiError(404, "Soporte no encontrado")
    auditar(db, request, "cst_soporte_consultado", actual.id, soporte_id=s.id, movimiento_id=s.movimiento_id)
    db.commit()
    return RespuestaCruda(s.contenido, media_type=s.mime, headers={
        "Content-Disposition": f"inline; filename*=UTF-8''{quote(s.nombre)}",
        "Cache-Control": "private, no-store",  # nosniff ya lo pone el middleware de seguridad
    })


@router.delete("/soportes/{soporte_id}", response_model=ApiResponse[dict])
def quitar_soporte(soporte_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    s = db.get(CstSoporte, soporte_id)
    if s is None:
        raise ApiError(404, "Soporte no encontrado")
    auditar(db, request, "cst_soporte_eliminado", actual.id, movimiento_id=s.movimiento_id, archivo=s.nombre, sha256=s.sha256)
    db.delete(s)
    db.commit()
    return ok({"eliminado": soporte_id})


class TipoDocumentoIn(BaseModel):
    codigo: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9_-]+$")
    nombre: str = Field(min_length=2, max_length=120)
    activo: bool = True


@router.get("/tipos-documento", response_model=ApiResponse[list[dict]])
def tipos_documento(db: DbSession, _=Depends(require(VER))):
    return ok([{"codigo": t.codigo, "nombre": t.nombre, "activo": t.activo}
               for t in db.scalars(select(CstTipoDocumento).order_by(CstTipoDocumento.codigo))])


@router.put("/tipos-documento", response_model=ApiResponse[dict])
def guardar_tipo_documento(data: TipoDocumentoIn, request: Request, db: DbSession, actual: Usuario = Depends(require(CONFIGURAR))):
    codigo = data.codigo.strip().upper()
    t = db.get(CstTipoDocumento, codigo) or CstTipoDocumento(codigo=codigo)
    t.nombre, t.activo = data.nombre.strip(), data.activo
    db.add(t)
    auditar(db, request, "cst_tipo_documento", actual.id, codigo=codigo, nombre=t.nombre, activo=t.activo)
    db.commit()
    return ok({"codigo": t.codigo, "nombre": t.nombre, "activo": t.activo})


# --- Vistas generales ---------------------------------------------------------------------------------

@router.get("/resumen", response_model=ApiResponse[dict])
def resumen_general(db: DbSession, _=Depends(require(VER))):
    hoy = date.today()
    lista = [resumen(m, hoy) for m in _mfps(db)]
    por_tipo: dict[str, dict] = {}
    for r in lista:
        for i in r["items"]:
            t = por_tipo.setdefault(i["tipo_codigo"], {"tipo": i["tipo"], "unidad": i["unidad"], "mfp": 0, "pactado": 0.0,
                                                       "ejecutado": 0.0, "pendiente": 0.0, "reembolso": 0.0, "excedidos": 0})
            t["mfp"] += 1
            t["pactado"] += i["pactado_total"]
            t["ejecutado"] += i["ejecutado"]
            t["pendiente"] += max(0.0, i["pendiente"]) if r["estado"] == "vigente" or i["unidad"] != HORAS else 0.0
            t["reembolso"] += i["reembolso"]
            t["excedidos"] += int(i["excede"])
    estados = defaultdict(int)
    alertas = defaultdict(int)
    for r in lista:
        estados[r["estado"]] += 1
        for a in r["alertas"]:
            alertas[a["tipo"]] += 1
    vigentes = [r for r in lista if r["estado"] == "vigente"]
    return ok({
        "mfp": len(lista), "estados": dict(estados), "alertas": dict(alertas),
        "facturacion_total": sum(r["facturacion_total"] for r in lista), "pactado": sum(r["pactado"] for r in lista),
        "ejecutado": sum(r["ejecutado"] for r in lista), "pendiente_vigentes": sum(r["pendiente"] for r in vigentes),
        "reembolso_vigentes": sum(r["reembolso"] for r in vigentes),
        "por_tipo": sorted(por_tipo.values(), key=lambda x: -x["pactado"]),
        "por_vencer": sorted(({"id": r["id"], "numero": r["numero"], "cliente": r["cliente"]["nombre"], "fecha_fin": r["fecha_fin"],
                               "pendiente": r["pendiente"]} for r in vigentes if any(a["tipo"] == "por_vencer" for a in r["alertas"])),
                             key=lambda x: x["fecha_fin"] or ""),
    })


@router.get("/bolsas-horas", response_model=ApiResponse[list[dict]])
def bolsas_horas(db: DbSession, q: str = Query("", max_length=100), _=Depends(require(VER))):
    """Bolsas de horas de las MFP vigentes, con el saldo del año en curso (para programación y comercial)."""
    hoy = date.today()
    t = q.strip().lower()
    out = []
    for m in _mfps(db):
        if t and t not in f"{m.numero} {m.cliente.nombre} {m.cliente.nit}".lower():
            continue
        r = resumen(m, hoy)
        if r["estado"] != "vigente":
            continue
        for i in r["items"]:
            if i["unidad"] != HORAS:
                continue
            actual = next((a for a in i["anios"] if a["actual"]), None)
            out.append({"mfp_id": m.id, "numero": m.numero, "cliente": m.cliente.nombre, "item_id": i["id"], "tipo": i["tipo"],
                        "anio": actual["anio"] if actual else None, "desde": actual["desde"] if actual else None,
                        "hasta": actual["hasta"] if actual else None, "pactado": i["pactado"],
                        "usado": actual["usado"] if actual else 0, "saldo": actual["saldo"] if actual else 0})
    return ok(sorted(out, key=lambda x: x["cliente"]))


@router.post("/mfp/importar", response_model=ApiResponse[dict])
async def importar(request: Request, db: DbSession, archivo: UploadFile = File(...), actual: Usuario = Depends(require(GESTIONAR))):
    nombre = archivo.filename or ""
    contenido = await leer_xlsx(archivo)
    try:
        r = importador.importar(db, contenido, actual.id)
    except importador.ErrorImportacion as e:
        db.rollback()
        raise ApiError(422, str(e), "ARCHIVO_INVALIDO") from e
    auditar(db, request, "cst_mfp_importadas", actual.id, archivo=nombre[:120], creadas=r["creadas"], omitidas=r["omitidas"])
    db.commit()
    return ok(r)


@router.get("/mfp-excel")
def exportar(db: DbSession, _=Depends(require(VER))):
    hoy = date.today()
    lista = [resumen(m, hoy) for m in _mfps(db)]
    tipos_orden = [t for t in db.scalars(select(CstTipoItem).order_by(CstTipoItem.orden))]
    buf = BytesIO()
    libro = xlsxwriter.Workbook(buf, {"in_memory": True})
    neg = libro.add_format({"bold": True, "bg_color": "#0f2d5c", "font_color": "white", "text_wrap": True, "valign": "top"})
    pesos = libro.add_format({"num_format": "#,##0"})
    pct = libro.add_format({"num_format": "0.00%"})
    h = libro.add_worksheet("MFP")
    enc = ["MFP", "NIT", "Cliente", "Contrato", "Inicio", "Fin", "Meses", "Valor mensual", "Facturación total", "Estado"]
    for t in tipos_orden:
        if t.unidad == HORAS:
            enc += [f"{t.nombre} (h/año)", f"{t.nombre} saldo año"]
        else:
            enc += [f"{t.nombre} pactado", f"{t.nombre} ejecutado"]
    enc += ["MFP pactada", "Ejecutado", "Pendiente", "% MFP", "% comercial", "Diferencia", "Reembolso a hoy", "Alertas"]
    h.write_row(0, 0, enc, neg)
    for f, r in enumerate(lista, start=1):
        fila = [r["numero"], r["cliente"]["nit"], r["cliente"]["nombre"], r["contrato"], r["fecha_inicio"] or "", r["fecha_fin"] or "",
                r["duracion_meses"] or 0, r["valor_mensual"], r["facturacion_total"], r["estado"]]
        for t in tipos_orden:
            its = [i for i in r["items"] if i["tipo_codigo"] == t.codigo]
            if t.unidad == HORAS:
                fila += [sum(i["pactado"] for i in its), sum(i["pendiente"] for i in its)]
            else:
                fila += [sum(i["pactado_total"] for i in its), sum(i["ejecutado"] for i in its)]
        fila += [r["pactado"], r["ejecutado"], r["pendiente"], r["pct_mfp"] or 0, r["pct_comercial"] or 0, r["diferencia_pct"] or 0,
                 r["reembolso"], " · ".join(a["mensaje"] for a in r["alertas"])]
        h.write_row(f, 0, fila)
    n = len(enc)
    h.set_column(0, 1, 12)
    h.set_column(2, 2, 40)
    h.set_column(7, n - 8, 14, pesos)
    h.set_column(n - 5, n - 3, 10, pct)
    h.set_column(n - 2, n - 2, 14, pesos)
    h.set_column(n - 1, n - 1, 60)
    h.freeze_panes(1, 3)
    h.autofilter(0, 0, len(lista), n - 1)
    libro.close()
    return RespuestaCruda(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                          headers={"Content-Disposition": f'attachment; filename="mfp_servigpoder_{hoy:%Y-%m-%d}.xlsx"'})


__all__ = ["router", "UNIDADES"]
