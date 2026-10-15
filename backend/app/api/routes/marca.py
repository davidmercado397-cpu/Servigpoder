"""Marca de la plataforma, general o por empresa.

La lectura es pública (la pantalla de ingreso la usa antes de iniciar sesión): devuelve la marca de la empresa
elegida (parámetro `empresa` o la última empresa con la que se trabajó en este navegador) o, si esa empresa no
tiene marca propia, la general. Una marca de empresa sin logo, favicon o fondo propio usa los de la general.
Editarla exige el permiso marca.gestionar; `empresa` vacío = la marca general.
"""

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import Response as RespuestaCruda
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DbSession, require
from app.core.auditoria import auditar
from app.core.empresas import COOKIE_EMPRESA
from app.core.marca import MAX_BYTES, TIPOS, ImagenInvalida, procesar
from app.core.rate_limit import limitar
from app.core.respuestas import ApiError, ApiResponse, ok
from app.models import Empresa, Usuario
from app.models.marca import MARCA_INICIAL, Marca, MarcaImagen

router = APIRouter(prefix="/marca", tags=["marca"])
GESTIONAR = "marca.gestionar"
COLOR = r"^#[0-9a-fA-F]{6}$"
PARAM_EMPRESA = Query(default=None, max_length=20, description="Código de la empresa; vacío = marca general")


class MarcaIn(BaseModel):
    nombre: str = Field(min_length=2, max_length=80)
    subtitulo: str = Field(default="", max_length=80)
    color_primario: str = Field(pattern=COLOR)
    color_acento: str = Field(pattern=COLOR)
    color_barra: str = Field(pattern=COLOR)
    color_barra_fin: str = Field(pattern=COLOR)
    login_fondo: str = Field(pattern=r"^(degradado|color|imagen)$")
    login_color: str = Field(pattern=COLOR)
    login_oscurecer: int = Field(ge=0, le=85)


def _empresa(db: DbSession, codigo: str | None, obligatoria: bool = True) -> Empresa | None:
    """None = marca general. Un código inexistente es un error al editar; al leer, se usa la general."""
    if not codigo:
        return None
    e = db.scalar(select(Empresa).where(Empresa.codigo == codigo))
    if e is None and obligatoria:
        raise ApiError(404, "Empresa no encontrada")
    return e


def _general(db: DbSession, crear: bool = False) -> Marca | None:
    m = db.scalar(select(Marca).where(Marca.empresa_id.is_(None)))
    if m is None and crear:
        m = Marca(id=1 if db.get(Marca, 1) is None else None, **MARCA_INICIAL, version=1)
        db.add(m)
        db.flush()
    return m


def _de_empresa(db: DbSession, empresa: Empresa | None) -> Marca | None:
    if empresa is None:
        return None
    return db.scalar(select(Marca).where(Marca.empresa_id == empresa.id))


def _para_editar(db: DbSession, empresa: Empresa | None) -> Marca:
    """La marca que se edita. La primera vez que se edita la de una empresa, nace como copia de la general."""
    general = _general(db, crear=True)
    if empresa is None:
        return general
    m = _de_empresa(db, empresa)
    if m is None:
        m = Marca(empresa_id=empresa.id, **{k: getattr(general, k) for k in MARCA_INICIAL}, version=1)
        if m.nombre == MARCA_INICIAL["nombre"]:
            m.nombre = empresa.nombre
        db.add(m)
        db.flush()
    return m


def _out(db: DbSession, m: Marca | None, general: Marca | None, empresa: Empresa | None) -> dict:
    base = m or general
    datos = {k: getattr(base, k) if base else v for k, v in MARCA_INICIAL.items()}
    datos["version"] = (base.version if base else 0) + (general.version if general and m else 0)
    datos["empresa"] = empresa.codigo if empresa else None
    datos["propia"] = m is not None
    propias = {i.tipo: i for i in db.scalars(select(MarcaImagen).where(MarcaImagen.marca_id == m.id))} if m else {}
    generales = {i.tipo: i for i in db.scalars(select(MarcaImagen).where(MarcaImagen.marca_id == general.id))} if general else {}
    for tipo in TIPOS:
        i, heredada = (propias[tipo], False) if tipo in propias else (generales.get(tipo), m is not None)
        datos[tipo] = {"url": f"/api/marca/imagen/{tipo}?m={i.marca_id}&v={datos['version']}", "ancho": i.ancho, "alto": i.alto,
                       "bytes": i.bytes, "heredada": heredada} if i else None
    if datos["login_fondo"] == "imagen" and not datos["fondo"]:
        datos["login_fondo"] = "degradado"  # sin imagen cargada, el fondo vuelve al degradado
    return datos


@router.get("", response_model=ApiResponse[dict])
def ver(request: Request, db: DbSession, empresa: str | None = PARAM_EMPRESA):
    """Marca vigente (pública: no expone nada sensible)."""
    codigo = empresa if empresa is not None else request.cookies.get(COOKIE_EMPRESA)
    e = _empresa(db, codigo, obligatoria=False)
    return ok(_out(db, _de_empresa(db, e), _general(db), e), valores_iniciales=MARCA_INICIAL)


@router.get("/imagen/{tipo}")
def imagen(tipo: str, request: Request, db: DbSession, m: int | None = None):
    if tipo not in TIPOS:
        raise ApiError(404, "Imagen no encontrada")
    marca_id = m or (g.id if (g := _general(db)) else 0)
    i = db.get(MarcaImagen, (marca_id, tipo))
    if i is None:
        raise ApiError(404, "Imagen no encontrada")
    etiqueta = f'"{marca_id}-{tipo}-{int(i.actualizado_en.timestamp()) if i.actualizado_en else 0}-{i.bytes}"'
    cabeceras = {"ETag": etiqueta, "Cache-Control": "public, max-age=86400"}
    if request.headers.get("if-none-match") == etiqueta:
        return RespuestaCruda(status_code=304, headers=cabeceras)
    return RespuestaCruda(content=i.contenido, media_type=i.mime, headers=cabeceras)


def _respuesta(db: DbSession, empresa: Empresa | None) -> dict:
    return _out(db, _de_empresa(db, empresa), _general(db), empresa)


@router.put("", response_model=ApiResponse[dict])
def guardar(data: MarcaIn, request: Request, db: DbSession, empresa: str | None = PARAM_EMPRESA,
            actual: Usuario = Depends(require(GESTIONAR))):
    e = _empresa(db, empresa)
    m = _para_editar(db, e)
    antes = {k: getattr(m, k) for k in MARCA_INICIAL}
    for k, v in data.model_dump().items():
        setattr(m, k, v.lower() if k.startswith(("color_", "login_color")) else v.strip() if isinstance(v, str) else v)
    m.version += 1
    m.actualizado_por = actual.id
    cambios = {k: [antes[k], getattr(m, k)] for k in MARCA_INICIAL if antes[k] != getattr(m, k)}
    auditar(db, request, "marca_editada", actual.id, marca=e.codigo if e else "general", cambios=cambios)
    db.commit()
    return ok(_respuesta(db, e))


@router.post("/imagen/{tipo}", response_model=ApiResponse[dict], dependencies=[Depends(limitar("marca_imagen", 20, 60))])
async def subir_imagen(tipo: str, request: Request, db: DbSession, archivo: UploadFile = File(...), empresa: str | None = PARAM_EMPRESA,
                       actual: Usuario = Depends(require(GESTIONAR))):
    """La imagen se valida, se ajusta a su tamaño y se guarda en la base; el archivo subido no se conserva."""
    if tipo not in TIPOS:
        raise ApiError(404, "Tipo de imagen desconocido: use logo, favicon o fondo")
    try:
        contenido = await archivo.read(MAX_BYTES + 1)
    finally:
        await archivo.close()
    try:
        datos, mime, ancho, alto = procesar(tipo, contenido)
    except ImagenInvalida as err:
        raise ApiError(415 if "Formato" in str(err) or "válida" in str(err) else 413, str(err), "IMAGEN_INVALIDA") from err
    e = _empresa(db, empresa)
    m = _para_editar(db, e)
    i = db.get(MarcaImagen, (m.id, tipo)) or MarcaImagen(marca_id=m.id, tipo=tipo)
    i.contenido, i.mime, i.ancho, i.alto, i.bytes = datos, mime, ancho, alto, len(datos)
    db.add(i)
    if tipo == "fondo" and m.login_fondo != "imagen":
        m.login_fondo = "imagen"
    m.version += 1
    m.actualizado_por = actual.id
    auditar(db, request, "marca_imagen", actual.id, marca=e.codigo if e else "general", tipo=tipo,
            archivo=(archivo.filename or "")[:120], ancho=ancho, alto=alto)
    db.commit()
    return ok(_respuesta(db, e))


@router.delete("/imagen/{tipo}", response_model=ApiResponse[dict])
def quitar_imagen(tipo: str, request: Request, db: DbSession, empresa: str | None = PARAM_EMPRESA,
                  actual: Usuario = Depends(require(GESTIONAR))):
    """Quita la imagen de esta marca; en una empresa vuelve a verse la de la marca general."""
    if tipo not in TIPOS:
        raise ApiError(404, "Tipo de imagen desconocido")
    e = _empresa(db, empresa)
    m = _de_empresa(db, e) if e else _general(db)
    i = db.get(MarcaImagen, (m.id, tipo)) if m else None
    if i is not None:
        db.delete(i)
        if tipo == "fondo" and m.login_fondo == "imagen" and e is None:
            m.login_fondo = "degradado"
        m.version += 1
        auditar(db, request, "marca_imagen_quitada", actual.id, marca=e.codigo if e else "general", tipo=tipo)
        db.commit()
    return ok(_respuesta(db, e))


@router.post("/restablecer", response_model=ApiResponse[dict])
def restablecer(request: Request, db: DbSession, empresa: str | None = PARAM_EMPRESA, actual: Usuario = Depends(require(GESTIONAR))):
    """General: vuelve a los valores de fábrica, sin imágenes. Empresa: quita su marca propia y vuelve a usar la general."""
    e = _empresa(db, empresa)
    if e is not None:
        m = _de_empresa(db, e)
        if m is not None:
            db.query(MarcaImagen).filter(MarcaImagen.marca_id == m.id).delete()
            db.delete(m)
            general = _general(db)
            if general:
                general.version += 1  # cambia la url de las imágenes para que el navegador no muestre las de la empresa
    else:
        m = _general(db, crear=True)
        for k, v in MARCA_INICIAL.items():
            setattr(m, k, v)
        db.query(MarcaImagen).filter(MarcaImagen.marca_id == m.id).delete()
        m.version += 1
        m.actualizado_por = actual.id
    auditar(db, request, "marca_restablecida", actual.id, marca=e.codigo if e else "general")
    db.commit()
    return ok(_respuesta(db, e))
