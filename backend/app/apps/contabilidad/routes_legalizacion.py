"""Contabilidad → Legalizaciones: formatos de legalización de anticipos y reembolsos → nota contable de World Office."""

from datetime import date
from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DbSession, require
from app.apps.contabilidad.models import (
    CONTABILIZADA, DESCARTADA, LEG_COLUMNAS, LISTA, PENDIENTE, CtbLegalizacion, CtbLegPlano, CtbPersona,
)
from app.apps.contabilidad.services import legalizacion as lg
from app.apps.contabilidad.services import servicio
from app.core import ia
from app.core.archivos import leer_xlsx
from app.core.auditoria import auditar
from app.core.config import get_settings
from app.core.paginacion import Pagina, paginar_consulta
from app.core.rate_limit import limitar
from app.core.respuestas import ApiError, ApiResponse, ok
from app.models import Usuario

router = APIRouter(prefix="/legalizaciones", tags=["contabilidad: legalizaciones"])
VER, REVISAR, CONFIGURAR = "contabilidad.ver", "contabilidad.revisar", "contabilidad.configurar"
TAMANOS = (20, 50, 100)
ESTADOS = (PENDIENTE, LISTA, CONTABILIZADA, DESCARTADA)


def _pagina(pagina: int = Query(1, ge=1, le=1_000_000), tamano: int = Query(20)) -> Pagina:
    if tamano not in TAMANOS:
        raise ApiError(422, "El tamaño de página debe ser 20, 50 o 100", "DATOS_INVALIDOS")
    return Pagina(pagina, tamano)


PaginaCtb = Annotated[Pagina, Depends(_pagina)]


def _nombre(db: DbSession, tipo: str, documento: str) -> str:
    return db.scalar(select(CtbPersona.nombre).where(CtbPersona.tipo == tipo, CtbPersona.documento == documento)) or "" if documento else ""


def _leg(db: DbSession, x: CtbLegalizacion, completa: bool = False) -> dict:
    gastos = [ln for ln in x.lineas if not ln.excluida]
    out = {"id": x.id, "estado": x.estado, "numero_formato": x.numero_formato, "archivo": x.archivo, "leida_con": x.leida_con,
           "colaborador_nombre": x.colaborador_nombre, "colaborador_documento": x.colaborador_documento,
           "elabora_documento": x.elabora_documento, "sucursal": x.sucursal, "motivo": x.motivo,
           "fecha_legalizacion": x.fecha_legalizacion.isoformat() if x.fecha_legalizacion else None,
           "anticipo_fecha": x.anticipo_fecha.isoformat() if x.anticipo_fecha else None, "anticipo_valor": float(x.anticipo_valor or 0),
           "anticipo_descripcion": x.anticipo_descripcion, "total_formato": float(x.total or 0),
           "total": round(sum(float(ln.valor) for ln in gastos), 2), "gastos": len(gastos), "nota": x.nota, "avisos": x.avisos or [],
           "faltantes": lg.faltantes(x), "soportes_revisados": x.soportes_revisados,
           "sin_soporte": sum(1 for ln in gastos if ln.soporte is False), "documento_numero": x.documento_numero,
           "fecha_contable": x.fecha_contable.isoformat() if x.fecha_contable else None,
           "creado_en": x.creado_en.isoformat() if x.creado_en else None}
    if completa:
        c = lg.config(db)
        out["elabora_nombre"] = _nombre(db, "elabora", x.elabora_documento)
        out["colaborador_en_listado"] = bool(_nombre(db, "empleado", x.colaborador_documento))
        out["lineas"] = [{"id": ln.id, "orden": ln.orden, "fecha": ln.fecha.isoformat() if ln.fecha else None, "beneficiario": ln.beneficiario,
                          "documento": ln.documento, "columna": ln.columna, "valor": float(ln.valor), "iva": float(ln.iva),
                          "retencion": float(ln.retencion), "detalle": ln.detalle, "cuenta": ln.cuenta, "soporte": ln.soporte,
                          "soporte_nota": ln.soporte_nota, "excluida": ln.excluida} for ln in x.lineas]
        out["movimientos"] = [m.__dict__ for m in lg.movimientos(x, c)] if gastos else []
    return out


def _get(db: DbSession, leg_id: int) -> CtbLegalizacion:
    x = db.get(CtbLegalizacion, leg_id)
    if x is None:
        raise ApiError(404, "Legalización no encontrada")
    return x


async def _leer(archivo: UploadFile) -> tuple[str, bytes]:
    limite = get_settings().max_upload_mb * 1024 * 1024
    try:
        datos = await archivo.read(limite + 1)
    finally:
        await archivo.close()  # el archivo no se guarda
    if len(datos) > limite:
        raise ApiError(413, f"«{archivo.filename}» supera el tamaño máximo")
    return (archivo.filename or "archivo")[:200], datos


@router.get("", response_model=ApiResponse[list[dict]])
def listar(db: DbSession, p: PaginaCtb, estado: str = PENDIENTE, _=Depends(require(VER))):
    if estado not in ESTADOS:
        raise ApiError(422, "Estado no válido")
    q = select(CtbLegalizacion).where(CtbLegalizacion.estado == estado).order_by(CtbLegalizacion.id.desc())
    items, meta = paginar_consulta(db, q, p)
    conteos = {e: db.query(CtbLegalizacion).filter(CtbLegalizacion.estado == e).count() for e in ESTADOS}
    return ok([_leg(db, x) for x in items], conteos=conteos, **meta)


@router.post("", response_model=ApiResponse[dict], dependencies=[Depends(limitar("ctb_leg", 10, 60))])
async def cargar(request: Request, db: DbSession, formato: UploadFile = File(...), soportes: UploadFile | None = File(None),
                 elabora_documento: str = Form("", max_length=20), actual: Usuario = Depends(require(REVISAR))):
    """Lee el formato (Excel o PDF) y, si vienen, revisa los soportes. Los archivos se leen en memoria y se descartan."""
    nombre, contenido = await _leer(formato)
    sop = await _leer(soportes) if soportes is not None and soportes.filename else None
    ia.cargar(db)
    if not ia.configurada():
        raise ApiError(503, "La IA no está configurada (Administración → Inteligencia artificial): se necesita para leer el formato")
    modelo = servicio.config(db).modelo

    def procesar():
        datos = lg.leer_formato(nombre, contenido, modelo)
        leg = lg.registrar(db, datos, nombre, "excel" if nombre.lower().endswith(lg.EXT_EXCEL) else "ia", actual.id)
        # Quien elabora: el elegido; si no se eligió y hay una sola persona activa en la lista, esa
        leg.elabora_documento = lg._doc(elabora_documento) or lg.elabora_unica(db)
        if sop:
            try:
                lg.revisar_soportes(leg, sop[0], sop[1], modelo)
            except ia.IAError as e:
                leg.avisos = [*leg.avisos, f"No se pudieron revisar los soportes: {e.mensaje}"]
        return leg

    try:
        leg = await run_in_threadpool(procesar)
    except ia.IAError as e:
        raise ApiError(e.status, e.mensaje, e.codigo) from e
    except ValueError as e:
        raise ApiError(422, str(e)) from e
    auditar(db, request, "ctb_legalizacion_cargada", actual.id, formato=nombre, gastos=len(leg.lineas), soportes=bool(sop))
    db.commit()
    return ok(_leg(db, leg, True))


@router.get("/{leg_id}", response_model=ApiResponse[dict])
def ver(leg_id: int, db: DbSession, _=Depends(require(VER))):
    return ok(_leg(db, _get(db, leg_id), True))


class LineaIn(BaseModel):
    id: int
    cuenta: str = Field(default="", max_length=20)
    documento: str = Field(default="", max_length=20)
    columna: str = Field(default="otros", max_length=20)
    excluida: bool = False


class LegIn(BaseModel):
    colaborador_nombre: str = Field(default="", max_length=200)
    colaborador_documento: str = Field(default="", max_length=20)
    elabora_documento: str = Field(default="", max_length=20)
    nota: str = Field(default="", max_length=300)
    anticipo_valor: float = Field(default=0, ge=0, le=1e12)
    lineas: list[LineaIn] = Field(default_factory=list, max_length=500)
    lista: bool = False


@router.put("/{leg_id}", response_model=ApiResponse[dict])
def guardar(leg_id: int, data: LegIn, request: Request, db: DbSession, actual: Usuario = Depends(require(REVISAR))):
    x = _get(db, leg_id)
    if x.estado in (CONTABILIZADA, DESCARTADA):
        raise ApiError(409, "La legalización ya no se edita")
    x.colaborador_nombre, x.colaborador_documento = data.colaborador_nombre.strip(), lg._doc(data.colaborador_documento)
    x.elabora_documento, x.nota, x.anticipo_valor = lg._doc(data.elabora_documento), data.nota.strip(), data.anticipo_valor
    por_id = {ln.id: ln for ln in x.lineas}
    for ln in data.lineas:
        y = por_id.get(ln.id)
        if y is not None:
            y.cuenta, y.documento, y.excluida = ln.cuenta.strip(), lg._doc(ln.documento), ln.excluida
            y.columna = ln.columna if ln.columna in LEG_COLUMNAS else y.columna
    if data.lista:
        falta = lg.faltantes(x)
        if falta:
            raise ApiError(422, "No se puede pasar al plano: " + "; ".join(falta[:5]))
        x.estado = LISTA
    elif x.estado == LISTA:
        x.estado = PENDIENTE
    auditar(db, request, "ctb_legalizacion_revisada", actual.id, legalizacion=x.id, estado=x.estado)
    db.commit()
    return ok(_leg(db, x, True))


@router.post("/{leg_id}/soportes", response_model=ApiResponse[dict], dependencies=[Depends(limitar("ctb_leg", 10, 60))])
async def soportes(leg_id: int, request: Request, db: DbSession, archivo: UploadFile = File(...), actual: Usuario = Depends(require(REVISAR))):
    """Revisa (otra vez) los soportes con la IA. El PDF no se guarda."""
    x = _get(db, leg_id)
    nombre, contenido = await _leer(archivo)
    ia.cargar(db)
    try:
        await run_in_threadpool(lg.revisar_soportes, x, nombre, contenido, servicio.config(db).modelo)
    except ia.IAError as e:
        raise ApiError(e.status, e.mensaje, e.codigo) from e
    auditar(db, request, "ctb_legalizacion_soportes", actual.id, legalizacion=x.id, sin_soporte=sum(1 for ln in x.lineas if ln.soporte is False))
    db.commit()
    return ok(_leg(db, x, True))


class EstadoIn(BaseModel):
    accion: str = Field(pattern=r"^(descartar|reabrir)$")


@router.post("/{leg_id}/estado", response_model=ApiResponse[dict])
def estado(leg_id: int, data: EstadoIn, request: Request, db: DbSession, actual: Usuario = Depends(require(REVISAR))):
    x = _get(db, leg_id)
    if x.estado == CONTABILIZADA:
        raise ApiError(409, "La legalización ya está contabilizada")
    x.estado = DESCARTADA if data.accion == "descartar" else PENDIENTE
    auditar(db, request, f"ctb_legalizacion_{data.accion}", actual.id, legalizacion=x.id)
    db.commit()
    return ok(_leg(db, x, True))


# --- Plano (nota contable NC / LG) --------------------------------------------------------------------

class PlanoIn(BaseModel):
    fecha: date
    ids: list[int] = Field(default_factory=list, max_length=2000)


@router.post("/plano/descargar", dependencies=[Depends(limitar("ctb_plano", 20, 60))])
def descargar_plano(data: PlanoIn, request: Request, db: DbSession, actual: Usuario = Depends(require(REVISAR))):
    try:
        contenido, p, legs = lg.armar_plano(db, data.fecha, data.ids or None, servicio.config(db).empresa_nombre, actual.id)
    except ValueError as e:
        raise ApiError(422, str(e)) from e
    auditar(db, request, "ctb_leg_plano_descargado", actual.id, plano=p.id, fecha=data.fecha.isoformat(), legalizaciones=len(legs))
    db.commit()
    return StreamingResponse(BytesIO(contenido), media_type="application/vnd.ms-excel", headers={
        "Content-Disposition": f'attachment; filename="plano_legalizaciones_{data.fecha:%Y-%m-%d}_{p.id}.xls"', "X-Plano-Id": str(p.id)})


@router.get("/plano/todas", response_model=ApiResponse[list[dict]])
def listas(db: DbSession, _=Depends(require(VER))):
    return ok([_leg(db, x) for x in db.scalars(select(CtbLegalizacion).where(CtbLegalizacion.estado == LISTA).order_by(CtbLegalizacion.id))])


@router.get("/plano/planos", response_model=ApiResponse[list[dict]])
def planos(db: DbSession, pag: PaginaCtb, _=Depends(require(VER))):
    items, meta = paginar_consulta(db, select(CtbLegPlano).order_by(CtbLegPlano.id.desc()), pag)
    out = []
    for p in items:
        ids = [x["legalizacion_id"] for x in p.items]
        legs = {x.id: x for x in db.scalars(select(CtbLegalizacion).where(CtbLegalizacion.id.in_(ids)))} if ids else {}
        out.append({"id": p.id, "fecha": p.fecha.isoformat(), "creado_en": p.creado_en.isoformat() if p.creado_en else None,
                    "legalizaciones": [{"documento": x["documento"], **(_leg(db, legs[x["legalizacion_id"]]) if x["legalizacion_id"] in legs
                                                                        else {"id": x["legalizacion_id"], "estado": "eliminada"})} for x in p.items]})
    return ok(out, **meta)


class ContabilizarIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=2000)


@router.post("/plano/planos/{plano_id}/contabilizar", response_model=ApiResponse[dict])
def contabilizar(plano_id: int, data: ContabilizarIn, request: Request, db: DbSession, actual: Usuario = Depends(require(REVISAR))):
    p = db.get(CtbLegPlano, plano_id)
    if p is None:
        raise ApiError(404, "Plano no encontrado")
    try:
        legs = lg.contabilizar(db, p, data.ids, actual.id)
    except ValueError as e:
        raise ApiError(409, str(e)) from e
    auditar(db, request, "ctb_legalizaciones_contabilizadas", actual.id, plano=p.id, legalizaciones=[x.id for x in legs])
    db.commit()
    return ok({"contabilizadas": len(legs)})


@router.delete("/plano/planos/{plano_id}", response_model=ApiResponse[dict])
def eliminar_plano(plano_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(REVISAR))):
    p = db.get(CtbLegPlano, plano_id)
    if p is None:
        raise ApiError(404, "Plano no encontrado")
    devueltas = lg.eliminar_plano(db, p)
    auditar(db, request, "ctb_leg_plano_eliminado", actual.id, plano=plano_id, devueltas=[x.id for x in devueltas])
    db.commit()
    return ok({"devueltas": len(devueltas)})


# --- Configuración y personas ---------------------------------------------------------------------------

def _config_out(db: DbSession) -> dict:
    c = lg.config(db)
    return {"tipo_documento": c.tipo_documento, "prefijo": c.prefijo, "ultimo_numero": c.ultimo_numero, "nota": c.nota,
            "cuentas": lg.cuentas(c), "columnas": {k: n for k, (n, _) in LEG_COLUMNAS.items()},
            "cuenta_reintegro": c.cuenta_reintegro, "cuenta_anticipo": c.cuenta_anticipo, "cuenta_por_cobrar": c.cuenta_por_cobrar}


@router.get("/config/datos", response_model=ApiResponse[dict])
def ver_config(db: DbSession, _=Depends(require(VER))):
    return ok(_config_out(db))


class ConfigIn(BaseModel):
    tipo_documento: str = Field(default="NC", min_length=1, max_length=10)
    prefijo: str = Field(default="LG", min_length=1, max_length=10)
    ultimo_numero: int = Field(default=0, ge=0, le=99999999)
    nota: str = Field(default="Legalizacion de gastos", min_length=1, max_length=200)
    cuentas: dict[str, str] = Field(default_factory=dict)
    cuenta_reintegro: str = Field(default="233595", min_length=4, max_length=20, pattern=r"^\d+$")
    cuenta_anticipo: str = Field(default="13301501", min_length=4, max_length=20, pattern=r"^\d+$")
    cuenta_por_cobrar: str = Field(default="13301501", min_length=4, max_length=20, pattern=r"^\d+$")


@router.put("/config/datos", response_model=ApiResponse[dict])
def guardar_config(data: ConfigIn, request: Request, db: DbSession, actual: Usuario = Depends(require(CONFIGURAR))):
    c = lg.config(db)
    for k in ("tipo_documento", "prefijo", "ultimo_numero", "nota", "cuenta_reintegro", "cuenta_anticipo", "cuenta_por_cobrar"):
        v = getattr(data, k)
        setattr(c, k, v.strip() if isinstance(v, str) else v)
    c.cuentas = {k: v.strip() for k, v in data.cuentas.items() if k in LEG_COLUMNAS and v.strip().isdigit()}
    auditar(db, request, "ctb_leg_config", actual.id, prefijo=c.prefijo, ultimo=c.ultimo_numero)
    db.commit()
    return ok(_config_out(db))


@router.get("/personas/lista", response_model=ApiResponse[list[dict]])
def personas(db: DbSession, tipo: str = Query(pattern=r"^(elabora|empleado)$"), _=Depends(require(VER))):
    return ok([{"id": p.id, "documento": p.documento, "nombre": p.nombre, "activo": p.activo}
               for p in db.scalars(select(CtbPersona).where(CtbPersona.tipo == tipo).order_by(CtbPersona.nombre))])


class PersonaIn(BaseModel):
    tipo: str = Field(pattern=r"^(elabora|empleado)$")
    documento: str = Field(min_length=4, max_length=20)
    nombre: str = Field(default="", max_length=200)
    activo: bool = True


@router.put("/personas/lista", response_model=ApiResponse[dict])
def guardar_persona(data: PersonaIn, request: Request, db: DbSession, actual: Usuario = Depends(require(CONFIGURAR))):
    doc = lg._doc(data.documento)
    p = db.scalar(select(CtbPersona).where(CtbPersona.tipo == data.tipo, CtbPersona.documento == doc))
    if p is None:
        p = CtbPersona(tipo=data.tipo, documento=doc)
        db.add(p)
    p.nombre, p.activo = data.nombre.strip() or p.nombre, data.activo
    auditar(db, request, "ctb_persona", actual.id, tipo=data.tipo, documento=doc, activo=p.activo)
    db.commit()
    return ok({"documento": p.documento, "nombre": p.nombre, "activo": p.activo})


@router.post("/personas/importar", response_model=ApiResponse[dict], dependencies=[Depends(limitar("ctb_cargar", 10, 60))])
async def importar_personas(request: Request, db: DbSession, tipo: str = Query(pattern=r"^(elabora|empleado)$"),
                            archivo: UploadFile = File(...), actual: Usuario = Depends(require(CONFIGURAR))):
    """Listado en Excel (nombre y cédula). El archivo no se guarda."""
    contenido = await leer_xlsx(archivo)
    try:
        n = lg.importar_personas(db, tipo, servicio._filas(contenido))
    except ValueError as e:
        raise ApiError(422, str(e)) from e
    auditar(db, request, "ctb_personas_importadas", actual.id, tipo=tipo, personas=n)
    db.commit()
    return ok({"personas": n})
