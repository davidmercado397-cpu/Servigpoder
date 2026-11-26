"""Contabilidad (Speed): bandeja de facturas recibidas, plano de World Office, buzón de Gmail y catálogos."""

from datetime import date, datetime, timezone
from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DbSession, require
from app.apps.contabilidad.models import (
    APARTE, CONTABILIZADA, DESCARTADA, ESTADOS, LISTA, PENDIENTE, CtbCentroCostos, CtbCorreo, CtbFactura, CtbPlano, CtbProducto,
    CtbRegla, CtbTercero,
)
from app.apps.contabilidad.services import buzon, ia_contable, servicio
from app.core import ia, vectores
from app.core.archivos import leer_xlsx
from app.core.auditoria import auditar
from app.core.config import get_settings
from app.core.paginacion import Pagina, paginar_consulta
from app.core.rate_limit import limitar
from app.core.respuestas import ApiError, ApiResponse, ok
from app.core.security import cifrar_secreto
from app.models import Usuario

router = APIRouter(prefix="/contabilidad", tags=["contabilidad"])
VER, REVISAR, CONFIGURAR = "contabilidad.ver", "contabilidad.revisar", "contabilidad.configurar"
MAX_ARCHIVOS = 10
TAMANOS = (20, 50, 100)  # filas por página de los listados de este desarrollo


def _pagina(pagina: int = Query(1, ge=1, le=1_000_000), tamano: int = Query(20)) -> Pagina:
    if tamano not in TAMANOS:
        raise ApiError(422, "El tamaño de página debe ser 20, 50 o 100", "DATOS_INVALIDOS")
    return Pagina(pagina, tamano)


PaginaCtb = Annotated[Pagina, Depends(_pagina)]


def _linea(x) -> dict:
    return {"id": x.id, "orden": x.orden, "codigo_proveedor": x.codigo_proveedor, "descripcion": x.descripcion,
            "cantidad": float(x.cantidad), "valor_unitario": float(x.valor_unitario), "subtotal": float(x.subtotal),
            "iva_pct": float(x.iva_pct), "iva_valor": float(x.iva_valor), "producto": x.producto,
            "centro_costos": x.centro_costos, "nota": x.nota, "producto_ia": x.producto_ia or ""}


def _factura(f: CtbFactura, completa: bool = False) -> dict:
    out = {"id": f.id, "estado": f.estado, "tipo": f.tipo, "cuenta_cobro": f.cuenta_cobro, "motivo_aparte": f.motivo_aparte, "leida_con": f.leida_con,
           "origen": f.origen, "prefijo": f.prefijo, "numero": f.numero,
           "fecha_emision": f.fecha_emision.isoformat() if f.fecha_emision else None,
           "fecha_vencimiento": f.fecha_vencimiento.isoformat() if f.fecha_vencimiento else None,
           "emisor_nit": f.emisor_nit, "emisor_dv": f.emisor_dv, "emisor_nombre": f.emisor_nombre,
           "comprador_nit": f.comprador_nit, "comprador_nombre": f.comprador_nombre,
           "subtotal": float(f.subtotal), "iva": float(f.iva), "total": float(f.total), "nota": f.nota,
           "avisos": f.avisos or [], "faltantes": servicio.faltantes(f), "documento_numero": f.documento_numero,
           "fecha_contable": f.fecha_contable.isoformat() if f.fecha_contable else None,
           "correo_de": f.correo_de, "correo_asunto": f.correo_asunto,
           "creado_en": f.creado_en.isoformat() if f.creado_en else None, "lineas": len(f.lineas)}
    if completa:
        out.update(cufe=f.cufe, forma_pago=f.forma_pago, moneda=f.moneda, retenciones=f.retenciones or {},
                   lineas=[_linea(x) for x in f.lineas])
    return out


def _fac(db: DbSession, factura_id: int) -> CtbFactura:
    f = db.get(CtbFactura, factura_id)
    if f is None:
        raise ApiError(404, "Factura no encontrada")
    return f


# --- Bandeja ------------------------------------------------------------------------------------------

@router.get("/resumen", response_model=ApiResponse[dict])
def resumen(db: DbSession, _=Depends(require(VER))):
    c = servicio.config(db)
    ia.cargar(db)
    return ok({"conteos": servicio.conteos(db), "buzon": {"correo": c.correo, "clave_guardada": bool(c.clave_cifrada),
                                                         "ultima_lectura": c.ultima_lectura.isoformat() if c.ultima_lectura else None,
                                                         "ultimo_error": c.ultimo_error},
               "ia": ia.configurada(), "productos": db.query(CtbProducto).count(), "terceros": db.query(CtbTercero).count()})


@router.get("/facturas", response_model=ApiResponse[list[dict]])
def facturas(db: DbSession, p: PaginaCtb, estado: str = PENDIENTE, todas: bool = False, _=Depends(require(VER))):
    """Por páginas de 20, 50 o 100. `todas`: sin paginar (el plano necesita todas las listas para elegirlas)."""
    if estado not in ESTADOS:
        raise ApiError(422, "Estado no válido")
    q = select(CtbFactura).where(CtbFactura.estado == estado)
    q = q.order_by(CtbFactura.contabilizada_en.desc() if estado == CONTABILIZADA else CtbFactura.id.desc(), CtbFactura.id.desc())
    if todas:
        lista = list(db.scalars(q.limit(2000)))
        return ok([_factura(f) for f in lista], total=len(lista), pagina=1, tamano=len(lista), paginas=1)
    items, meta = paginar_consulta(db, q, p)
    return ok([_factura(f) for f in items], **meta)


@router.get("/facturas/{factura_id}", response_model=ApiResponse[dict])
def factura(factura_id: int, db: DbSession, _=Depends(require(VER))):
    return ok(_factura(_fac(db, factura_id), True))


class LineaIn(BaseModel):
    id: int
    producto: str = Field(default="", max_length=40)
    centro_costos: str = Field(default="", max_length=80)
    nota: str = Field(default="", max_length=200)


class FacturaIn(BaseModel):
    nota: str = Field(default="", max_length=300)
    lineas: list[LineaIn] = Field(default_factory=list, max_length=500)
    lista: bool = False  # revisada: sale en el próximo plano
    cuenta_cobro: bool | None = None  # None = no cambia


@router.put("/facturas/{factura_id}", response_model=ApiResponse[dict])
def guardar(factura_id: int, data: FacturaIn, request: Request, db: DbSession, actual: Usuario = Depends(require(REVISAR))):
    f = _fac(db, factura_id)
    if f.estado in (CONTABILIZADA, DESCARTADA):
        raise ApiError(409, "La factura ya está " + ("contabilizada" if f.estado == CONTABILIZADA else "descartada"))
    por_id = {x.id: x for x in f.lineas}
    # Correcciones a lo que propuso el agente (en este guardado): el agente ofrece aprenderlas como regla
    correcciones = []
    for ln in data.lineas:
        x = por_id.get(ln.id)
        if x is not None:
            nuevo = ln.producto.strip()
            if x.producto_ia and x.producto == x.producto_ia and nuevo and nuevo != x.producto_ia:
                correcciones.append({"linea_id": x.id, "orden": x.orden, "descripcion": x.descripcion[:200],
                                     "cuenta_agente": x.producto_ia, "cuenta_correcta": nuevo})
            x.producto, x.centro_costos, x.nota = nuevo, ln.centro_costos.strip(), ln.nota.strip()
    # Salud de las reglas: si se corrige una factura donde el agente aplicó reglas, esas reglas quedan para revisar
    if correcciones and f.reglas_aplicadas:
        for rg in db.scalars(select(CtbRegla).where(CtbRegla.id.in_(f.reglas_aplicadas))):
            rg.corregida = (rg.corregida or 0) + 1
        f.reglas_aplicadas = []
    f.nota = data.nota.strip()
    if data.cuenta_cobro is not None:
        f.cuenta_cobro = data.cuenta_cobro
    if data.lista:
        falta = servicio.faltantes(f)
        if falta:
            raise ApiError(422, "No se puede pasar al plano: " + "; ".join(falta[:5]))
        if f.estado == APARTE:
            raise ApiError(409, "Primero confirme que esta factura se contabiliza («Incluir»)")
        f.estado = LISTA
    elif f.estado == LISTA:
        f.estado = PENDIENTE
    auditar(db, request, "ctb_factura_revisada", actual.id, factura=f"{f.prefijo}{f.numero}", nit=f.emisor_nit, estado=f.estado)
    db.commit()
    return ok({**_factura(f, True), "correcciones": correcciones})


class EstadoIn(BaseModel):
    accion: str = Field(pattern=r"^(incluir|descartar|reabrir)$")


@router.post("/facturas/{factura_id}/estado", response_model=ApiResponse[dict])
def cambiar_estado(factura_id: int, data: EstadoIn, request: Request, db: DbSession, actual: Usuario = Depends(require(REVISAR))):
    """incluir: una factura aparte (otro comprador, nota) sí se contabiliza; descartar; reabrir: una descartada vuelve."""
    f = _fac(db, factura_id)
    if f.estado == CONTABILIZADA:
        raise ApiError(409, "La factura ya está contabilizada")
    if data.accion == "incluir":
        if f.estado != APARTE:
            raise ApiError(409, "Solo se incluyen las facturas que están aparte")
        f.estado = PENDIENTE
    elif data.accion == "descartar":
        f.estado = DESCARTADA
    else:
        if f.estado != DESCARTADA:
            raise ApiError(409, "Solo se reabren las facturas descartadas")
        f.estado = APARTE if f.motivo_aparte else PENDIENTE
    auditar(db, request, "ctb_factura_" + data.accion, actual.id, factura=f"{f.prefijo}{f.numero}", nit=f.emisor_nit)
    db.commit()
    return ok(_factura(f, True))


@router.post("/facturas/{factura_id}/proponer", response_model=ApiResponse[dict], dependencies=[Depends(limitar("ctb_ia", 20, 60))])
def proponer(factura_id: int, db: DbSession, _=Depends(require(REVISAR))):
    """La IA vuelve a proponer producto, centro de costos y notas (borra lo que haya en las líneas)."""
    f = _fac(db, factura_id)
    if f.estado in (CONTABILIZADA, DESCARTADA):
        raise ApiError(409, "La factura ya no se edita")
    ia.cargar(db)
    if not ia.configurada():
        raise ApiError(503, "La IA no está configurada (Administración → Inteligencia artificial)")
    for x in f.lineas:
        x.producto = x.centro_costos = x.nota = ""
    f.nota = ""
    f.avisos = [a for a in f.avisos or [] if not a.startswith("IA:") and "La IA no pudo" not in a]
    servicio.proponer_contabilizacion(db, f)
    db.commit()
    return ok(_factura(f, True))


@router.post("/cargar", response_model=ApiResponse[dict], dependencies=[Depends(limitar("ctb_cargar", 10, 60))])
async def cargar(request: Request, db: DbSession, archivos: list[UploadFile] = File(...), actual: Usuario = Depends(require(REVISAR))):
    """Facturas cargadas a mano (zip, XML o PDF), por si no llegaron al buzón. Se leen en memoria y se descartan."""
    if not 1 <= len(archivos) <= MAX_ARCHIVOS:
        raise ApiError(422, f"Cargue entre 1 y {MAX_ARCHIVOS} archivos")
    limite = get_settings().max_upload_mb * 1024 * 1024
    leidos = []
    for a in archivos:
        try:
            datos = await a.read(limite + 1)
        finally:
            await a.close()
        if len(datos) > limite:
            raise ApiError(413, f"«{a.filename}» supera el tamaño máximo")
        leidos.append(((a.filename or "archivo")[:200], datos))

    def procesar():
        ia.cargar(db)
        return servicio.procesar_archivos(db, leidos, origen="carga")

    res = await run_in_threadpool(procesar)
    del leidos
    auditar(db, request, "ctb_facturas_cargadas", actual.id, nuevas=len(res.nuevas), resultado=res.texto()[:300])
    db.commit()
    return ok({"nuevas": [_factura(f) for f in res.nuevas], "duplicadas": res.duplicadas, "errores": res.errores, "resultado": res.texto()})


# --- Plano --------------------------------------------------------------------------------------------

class PlanoIn(BaseModel):
    fecha: date  # fecha de cargue en World Office
    ids: list[int] = Field(default_factory=list, max_length=2000)


@router.post("/plano", dependencies=[Depends(limitar("ctb_plano", 20, 60))])
def descargar_plano(data: PlanoIn, request: Request, db: DbSession, actual: Usuario = Depends(require(REVISAR))):
    try:
        contenido, p, facs = servicio.armar_plano(db, data.fecha, data.ids or None, actual.id)
    except ValueError as e:
        raise ApiError(422, str(e)) from e
    auditar(db, request, "ctb_plano_descargado", actual.id, plano=p.id, fecha=data.fecha.isoformat(), facturas=len(facs))
    db.commit()
    nombre = f"plano_compras_{data.fecha:%Y-%m-%d}_{p.id}.xls"
    return StreamingResponse(BytesIO(contenido), media_type="application/vnd.ms-excel",
                             headers={"Content-Disposition": f'attachment; filename="{nombre}"', "X-Plano-Id": str(p.id),
                                      "Access-Control-Expose-Headers": "X-Plano-Id"})


@router.get("/planos", response_model=ApiResponse[list[dict]])
def planos(db: DbSession, pag: PaginaCtb, _=Depends(require(VER))):
    out = []
    items, meta = paginar_consulta(db, select(CtbPlano).order_by(CtbPlano.id.desc()), pag)
    for p in items:
        ids = [x["factura_id"] for x in p.items]
        facs = {f.id: f for f in db.scalars(select(CtbFactura).where(CtbFactura.id.in_(ids)))} if ids else {}
        out.append({"id": p.id, "fecha": p.fecha.isoformat(), "creado_en": p.creado_en.isoformat() if p.creado_en else None,
                    "facturas": [{"documento": x["documento"], "serie": x.get("serie", "FC"), **(_factura(facs[x["factura_id"]]) if x["factura_id"] in facs else
                                                                 {"id": x["factura_id"], "estado": "eliminada"})} for x in p.items]})
    return ok(out, **meta)


class ContabilizarIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=2000)


@router.delete("/planos/{plano_id}", response_model=ApiResponse[dict])
def eliminar_plano(plano_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(REVISAR))):
    """Elimina un plano descargado; si con él se marcaron facturas contabilizadas, vuelven a «lista»."""
    p = db.get(CtbPlano, plano_id)
    if p is None:
        raise ApiError(404, "Plano no encontrado")
    devueltas = servicio.eliminar_plano(db, p)
    auditar(db, request, "ctb_plano_eliminado", actual.id, plano=plano_id, fecha=p.fecha.isoformat(),
            devueltas=[f"{f.prefijo}{f.numero}" for f in devueltas])
    db.commit()
    return ok({"devueltas": len(devueltas)})


@router.post("/planos/{plano_id}/contabilizar", response_model=ApiResponse[dict])
def contabilizar(plano_id: int, data: ContabilizarIn, request: Request, db: DbSession, actual: Usuario = Depends(require(REVISAR))):
    p = db.get(CtbPlano, plano_id)
    if p is None:
        raise ApiError(404, "Plano no encontrado")
    try:
        facs = servicio.contabilizar(db, p, data.ids, actual.id)
    except ValueError as e:
        raise ApiError(409, str(e)) from e
    auditar(db, request, "ctb_contabilizadas", actual.id, plano=p.id, facturas=[f"{f.prefijo}{f.numero}" for f in facs])
    db.commit()
    return ok({"contabilizadas": len(facs)})


# --- Buzón de Gmail -----------------------------------------------------------------------------------

@router.post("/buzon/leer", response_model=ApiResponse[dict], dependencies=[Depends(limitar("ctb_buzon", 6, 60))])
async def leer_buzon(request: Request, db: DbSession, actual: Usuario = Depends(require(REVISAR))):
    """Revisa el correo: la única forma de leer el buzón (no hay revisión automática; la ejecuta el usuario)."""
    try:
        registros = await run_in_threadpool(buzon.leer, db)
    except buzon.ErrorBuzon as e:
        raise ApiError(502, str(e)) from e
    auditar(db, request, "ctb_buzon_leido", actual.id, correos=len(registros), facturas=sum(r.facturas for r in registros))
    db.commit()
    return ok({"correos": len(registros), "facturas": sum(r.facturas for r in registros),
               "detalle": [{"de": r.de, "asunto": r.asunto, "resultado": r.resultado} for r in registros]})


@router.get("/correos", response_model=ApiResponse[list[dict]])
def correos(db: DbSession, p: PaginaCtb, _=Depends(require(VER))):
    items, meta = paginar_consulta(db, select(CtbCorreo).order_by(CtbCorreo.id.desc()), p)
    return ok([{"id": r.id, "de": r.de, "asunto": r.asunto, "fecha": r.fecha.isoformat() if r.fecha else None,
                "resultado": r.resultado, "facturas": r.facturas, "leido_en": r.creado_en.isoformat() if r.creado_en else None}
               for r in items], **meta)


# --- Configuración y catálogos ------------------------------------------------------------------------

def _config_out(db: DbSession) -> dict:
    c = servicio.config(db)
    ia.cargar(db)
    return {"correo": c.correo, "clave_guardada": bool(c.clave_cifrada), "carpeta": c.carpeta,
            "modelo": c.modelo, "modelo_general": ia.ajustes().modelo, "ia": ia.configurada(),
            "ultima_lectura": c.ultima_lectura.isoformat() if c.ultima_lectura else None, "ultimo_error": c.ultimo_error,
            "empresa_nombre": c.empresa_nombre, "empresa_nit": c.empresa_nit, "tipo_documento": c.tipo_documento,
            "prefijo": c.prefijo, "tipo_documento_ds": c.tipo_documento_ds, "prefijo_ds": c.prefijo_ds,
            "ultimo_fc": c.ultimo_fc, "ultimo_ds": c.ultimo_ds, "bodega": c.bodega, "unidad": c.unidad}


@router.get("/config", response_model=ApiResponse[dict])
def ver_config(db: DbSession, _=Depends(require(VER))):
    return ok(_config_out(db))


class ConfigIn(BaseModel):
    correo: str = Field(default="", max_length=160, pattern=r"^$|^[^@\s]+@[^@\s]+\.[^@\s]+$")
    clave: str = Field(default="", max_length=100)  # contraseña de aplicación de Gmail; vacía = se conserva
    carpeta: str = Field(default="INBOX", min_length=1, max_length=80)
    # Modelo de OpenRouter para este desarrollo (vacío = el general de la plataforma)
    modelo: str = Field(default="", max_length=150, pattern=r"^$|^[A-Za-z0-9._\-]+/[A-Za-z0-9._:\-]+$")
    empresa_nombre: str = Field(min_length=2, max_length=160)
    empresa_nit: str = Field(min_length=5, max_length=20, pattern=r"^[\d.\-\s]+$")
    tipo_documento: str = Field(default="FC", min_length=1, max_length=10)
    prefijo: str = Field(default="FC", min_length=1, max_length=10)
    tipo_documento_ds: str = Field(default="DSS", min_length=1, max_length=10)
    prefijo_ds: str = Field(default="DSS", min_length=1, max_length=10)
    # Último número usado en World Office (AAMM + consecutivo); vacío = ninguno
    ultimo_fc: int | None = Field(default=None, ge=0, le=99999999)
    ultimo_ds: int | None = Field(default=None, ge=0, le=99999999)
    bodega: str = Field(default="Principal", min_length=1, max_length=60)
    unidad: str = Field(default="Und.", min_length=1, max_length=20)


@router.put("/config", response_model=ApiResponse[dict])
def guardar_config(data: ConfigIn, request: Request, db: DbSession, actual: Usuario = Depends(require(CONFIGURAR))):
    c = servicio.config(db)
    for k in ("correo", "carpeta", "modelo", "empresa_nombre", "tipo_documento", "prefijo", "tipo_documento_ds", "prefijo_ds",
              "ultimo_fc", "ultimo_ds", "bodega", "unidad"):
        v = getattr(data, k)
        setattr(c, k, v.strip() if isinstance(v, str) else v)
    c.empresa_nit = servicio.dian.solo_nit(data.empresa_nit)
    if data.clave.strip():
        c.clave_cifrada = cifrar_secreto(data.clave.replace(" ", ""), "imap")  # Gmail la muestra en grupos de 4
    auditar(db, request, "ctb_config", actual.id, correo=c.correo, modelo=c.modelo or "(general)", clave_nueva=bool(data.clave.strip()))
    db.commit()
    return ok(_config_out(db))


@router.post("/config/probar", response_model=ApiResponse[dict], dependencies=[Depends(limitar("ctb_buzon", 6, 60))])
async def probar_buzon(db: DbSession, _=Depends(require(CONFIGURAR))):
    try:
        sin_leer = await run_in_threadpool(buzon.probar, servicio.config(db))
    except buzon.ErrorBuzon as e:
        raise ApiError(502, str(e)) from e
    return ok({"sin_leer": sin_leer})


@router.get("/modelos", response_model=ApiResponse[list[dict]])
def modelos(_=Depends(require(CONFIGURAR))):
    """Modelos de OpenRouter (misma cuenta de la plataforma) para elegir el de Contabilidad."""
    from app.api.routes.ia import lista_modelos

    return ok(lista_modelos())


@router.get("/productos", response_model=ApiResponse[list[dict]])
def productos(db: DbSession, _=Depends(require(VER))):
    return ok([{"codigo": p.codigo, "nombre": p.nombre, "activo": p.activo}
               for p in db.scalars(select(CtbProducto).order_by(CtbProducto.codigo))])


@router.get("/centros", response_model=ApiResponse[list[dict]])
def centros(db: DbSession, _=Depends(require(VER))):
    return ok([{"id": c.id, "nombre": c.nombre, "codigo": c.codigo, "activo": c.activo}
               for c in db.scalars(select(CtbCentroCostos).order_by(CtbCentroCostos.nombre))])


class CentroIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=80)
    codigo: str = Field(default="", max_length=40)
    activo: bool = True


@router.put("/centros", response_model=ApiResponse[dict])
def guardar_centro(data: CentroIn, request: Request, db: DbSession, actual: Usuario = Depends(require(CONFIGURAR))):
    c = db.scalar(select(CtbCentroCostos).where(CtbCentroCostos.nombre == data.nombre.strip()))
    if c is None:
        c = CtbCentroCostos(nombre=data.nombre.strip())
        db.add(c)
    c.codigo, c.activo = data.codigo.strip(), data.activo
    auditar(db, request, "ctb_centro", actual.id, nombre=c.nombre, activo=c.activo)
    db.commit()
    return ok({"nombre": c.nombre, "codigo": c.codigo, "activo": c.activo})


@router.post("/productos/importar", response_model=ApiResponse[dict], dependencies=[Depends(limitar("ctb_cargar", 10, 60))])
async def importar_productos(request: Request, db: DbSession, archivo: UploadFile = File(...), actual: Usuario = Depends(require(CONFIGURAR))):
    try:
        n = servicio.importar_cuentas(db, await leer_xlsx(archivo))
    except ValueError as e:
        raise ApiError(422, str(e)) from e
    auditar(db, request, "ctb_cuentas_importadas", actual.id, cuentas=n)
    db.commit()
    return ok({"cuentas": n})


@router.post("/terceros/importar", response_model=ApiResponse[dict], dependencies=[Depends(limitar("ctb_cargar", 10, 60))])
async def importar_terceros(request: Request, db: DbSession, archivo: UploadFile = File(...), actual: Usuario = Depends(require(CONFIGURAR))):
    try:
        n = servicio.importar_terceros(db, await leer_xlsx(archivo))
    except ValueError as e:
        raise ApiError(422, str(e)) from e
    auditar(db, request, "ctb_terceros_importados", actual.id, terceros=n)
    db.commit()
    return ok({"terceros": n})


# --- Reglas del agente contable (lo que aprende de cómo se hace en la empresa) -------------------------

def _regla(r: CtbRegla) -> dict:
    return {"id": r.id, "texto": r.texto, "cuentas": r.cuentas, "activa": r.activa, "origen": r.origen, "ejemplo": r.ejemplo,
            "usos": r.usos or 0, "corregida": r.corregida or 0, "creado_en": r.creado_en.isoformat() if r.creado_en else None,
            "actualizado_en": r.actualizado_en.isoformat() if r.actualizado_en else None}


class ReglaIn(BaseModel):
    texto: str = Field(min_length=5, max_length=2000)
    cuentas: str = Field(default="", max_length=200)
    activa: bool = True
    origen: str = Field(default="manual", pattern=r"^(manual|correccion)$")
    ejemplo: str = Field(default="", max_length=400)


@router.get("/reglas", response_model=ApiResponse[list[dict]])
def reglas(db: DbSession, _=Depends(require(VER))):
    return ok([_regla(r) for r in db.scalars(select(CtbRegla).order_by(CtbRegla.activa.desc(), CtbRegla.id))])


@router.post("/reglas", response_model=ApiResponse[dict], status_code=201)
def crear_regla(data: ReglaIn, request: Request, db: DbSession, actual: Usuario = Depends(require(REVISAR))):
    r = CtbRegla(texto=data.texto.strip(), cuentas=data.cuentas.strip(), activa=data.activa, origen=data.origen,
                 ejemplo=data.ejemplo.strip(), creado_por=actual.id, actualizado_en=datetime.now(timezone.utc))
    db.add(r)
    db.flush()
    auditar(db, request, "ctb_regla_creada", actual.id, regla=r.id, origen=r.origen, texto=r.texto[:300])
    db.commit()
    return ok(_regla(r))


@router.put("/reglas/{regla_id}", response_model=ApiResponse[dict])
def editar_regla(regla_id: int, data: ReglaIn, request: Request, db: DbSession, actual: Usuario = Depends(require(REVISAR))):
    r = db.get(CtbRegla, regla_id)
    if r is None:
        raise ApiError(404, "Regla no encontrada")
    antes = r.texto
    r.texto, r.cuentas, r.activa = data.texto.strip(), data.cuentas.strip(), data.activa
    r.actualizado_en = datetime.now(timezone.utc)  # lo contabilizado antes de este cambio ya no se repite sin el agente
    auditar(db, request, "ctb_regla_editada", actual.id, regla=r.id, antes=antes[:300], despues=r.texto[:300], activa=r.activa)
    db.commit()
    return ok(_regla(r))


@router.delete("/reglas/{regla_id}", response_model=ApiResponse[dict])
def eliminar_regla(regla_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(REVISAR))):
    r = db.get(CtbRegla, regla_id)
    if r is None:
        raise ApiError(404, "Regla no encontrada")
    auditar(db, request, "ctb_regla_eliminada", actual.id, regla=r.id, texto=r.texto[:300])
    db.delete(r)
    db.commit()
    return ok({"eliminada": regla_id})


class RedactarIn(BaseModel):
    factura_id: int
    linea_id: int
    cuenta_agente: str = Field(max_length=40)
    cuenta_correcta: str = Field(min_length=1, max_length=40)
    motivo: str = Field(default="", max_length=1000)  # por qué va en esa cuenta (opcional, lo dice contabilidad)


@router.post("/reglas/redactar", response_model=ApiResponse[dict], dependencies=[Depends(limitar("ctb_ia", 20, 60))])
def redactar_regla(data: RedactarIn, db: DbSession, _=Depends(require(REVISAR))):
    """El agente redacta la regla que aprende de una corrección. No la guarda: contabilidad la revisa y la guarda."""
    f = _fac(db, data.factura_id)
    x = next((ln for ln in f.lineas if ln.id == data.linea_id), None)
    if x is None:
        raise ApiError(404, "Línea no encontrada")
    ia.cargar(db)
    if not ia.configurada():
        raise ApiError(503, "La IA no está configurada (Administración → Inteligencia artificial)")
    productos = [(c, n) for c, n in db.execute(select(CtbProducto.codigo, CtbProducto.nombre).where(CtbProducto.activo.is_(True)))]
    activas = servicio.reglas_activas(db)
    # Reglas parecidas (RAG): para actualizar la que ya existe en vez de duplicarla, sin mandar todas
    parecidas = activas
    if len(activas) > servicio.TOPE_REGLAS:
        try:
            vecs, t = ia.embeber([f"{x.descripcion} {data.cuenta_correcta} {data.motivo}"[:1000]])
            t += vectores.sincronizar(db, "ctb_regla", {str(r.id): r.texto for r in activas})
            ids = {int(ref) for ref, _ in vectores.buscar(db, "ctb_regla", vecs, 5)}
            parecidas = [r for r in activas if r.id in ids]
            vectores.registrar_uso(db, servicio.AGENTE, "vectores", t, 0, ia.ajustes().modelo_vectores)
        except ia.IAError:
            parecidas = activas[-servicio.TOPE_REGLAS:]
    try:
        d, r = ia_contable.redactar_regla({"proveedor": f.emisor_nombre, "descripcion": x.descripcion, "cuenta_agente": data.cuenta_agente,
                                           "cuenta_correcta": data.cuenta_correcta, "motivo": data.motivo.strip()},
                                          productos if len(productos) <= servicio.TOPE_CUENTAS else
                                          [(c, n) for c, n in productos if c in (data.cuenta_agente, data.cuenta_correcta)],
                                          [(rg.id, rg.texto) for rg in parecidas], servicio.config(db).modelo)
    except ia.IAError as e:
        raise ApiError(e.status, e.mensaje, e.codigo) from e
    vectores.registrar_uso(db, servicio.AGENTE, "regla", r.tokens_entrada, r.tokens_salida, r.modelo)
    db.commit()
    if not d["texto"]:
        raise ApiError(502, "El agente no redactó la regla. Escríbala usted.")
    actualiza = db.get(CtbRegla, d["actualiza"]) if d["actualiza"] else None
    return ok({**d, "regla_actual": actualiza.texto if actualiza else None,
               "ejemplo": f"{f.emisor_nombre[:80]} · «{x.descripcion[:120]}»: {data.cuenta_agente or '—'} → {data.cuenta_correcta}"})


@router.get("/agente/uso", response_model=ApiResponse[dict])
def uso_agente(db: DbSession, _=Depends(require(VER))):
    """Consumo del agente contable en el mes: propuestas con IA, las resueltas con la memoria (sin IA) y los tokens."""
    hoy = date.today()
    return ok({**vectores.resumen_uso(db, servicio.AGENTE, hoy.replace(day=1)),
               "modelo": servicio.config(db).modelo or ia.ajustes().modelo, "modelo_vectores": ia.ajustes().modelo_vectores})
