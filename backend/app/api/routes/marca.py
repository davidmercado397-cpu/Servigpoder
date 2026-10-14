"""Marca de la plataforma. La lectura es pública (la pantalla de ingreso la usa antes de iniciar sesión);
editarla exige el permiso marca.gestionar."""

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import Response as RespuestaCruda
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DbSession, require
from app.core.auditoria import auditar
from app.core.marca import MAX_BYTES, TIPOS, ImagenInvalida, procesar
from app.core.rate_limit import limitar
from app.core.respuestas import ApiError, ApiResponse, ok
from app.models import Usuario
from app.models.marca import MARCA_INICIAL, Marca, MarcaImagen

router = APIRouter(prefix="/marca", tags=["marca"])
GESTIONAR = "marca.gestionar"
COLOR = r"^#[0-9a-fA-F]{6}$"


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


def _marca(db: DbSession) -> Marca:
    m = db.get(Marca, 1)
    if m is None:
        m = Marca(id=1, **MARCA_INICIAL)
        db.add(m)
        db.flush()
    return m


def _out(db: DbSession, m: Marca) -> dict:
    imagenes = {i.tipo: i for i in db.scalars(select(MarcaImagen))}
    datos = {k: getattr(m, k) for k in MARCA_INICIAL}
    datos["version"] = m.version
    for tipo in TIPOS:
        i = imagenes.get(tipo)
        datos[tipo] = {"url": f"/api/marca/imagen/{tipo}?v={m.version}", "ancho": i.ancho, "alto": i.alto, "bytes": i.bytes} if i else None
    if datos["login_fondo"] == "imagen" and not datos["fondo"]:
        datos["login_fondo"] = "degradado"  # sin imagen cargada, el fondo vuelve al degradado
    return datos


@router.get("", response_model=ApiResponse[dict])
def ver(db: DbSession):
    """Marca vigente (pública: no expone nada sensible)."""
    m = db.get(Marca, 1)
    if m is None:
        m = Marca(id=1, **MARCA_INICIAL, version=0)
    return ok(_out(db, m), valores_iniciales=MARCA_INICIAL)


@router.get("/imagen/{tipo}")
def imagen(tipo: str, request: Request, db: DbSession):
    if tipo not in TIPOS:
        raise ApiError(404, "Imagen no encontrada")
    i = db.get(MarcaImagen, tipo)
    if i is None:
        raise ApiError(404, "Imagen no encontrada")
    etiqueta = f'"{tipo}-{int(i.actualizado_en.timestamp()) if i.actualizado_en else 0}-{i.bytes}"'
    cabeceras = {"ETag": etiqueta, "Cache-Control": "public, max-age=86400"}
    if request.headers.get("if-none-match") == etiqueta:
        return RespuestaCruda(status_code=304, headers=cabeceras)
    return RespuestaCruda(content=i.contenido, media_type=i.mime, headers=cabeceras)


@router.put("", response_model=ApiResponse[dict])
def guardar(data: MarcaIn, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    m = _marca(db)
    antes = {k: getattr(m, k) for k in MARCA_INICIAL}
    for k, v in data.model_dump().items():
        setattr(m, k, v.lower() if k.startswith(("color_", "login_color")) else v.strip() if isinstance(v, str) else v)
    m.version += 1
    m.actualizado_por = actual.id
    cambios = {k: [antes[k], getattr(m, k)] for k in MARCA_INICIAL if antes[k] != getattr(m, k)}
    auditar(db, request, "marca_editada", actual.id, cambios=cambios)
    db.commit()
    return ok(_out(db, m))


@router.post("/imagen/{tipo}", response_model=ApiResponse[dict], dependencies=[Depends(limitar("marca_imagen", 20, 60))])
async def subir_imagen(tipo: str, request: Request, db: DbSession, archivo: UploadFile = File(...),
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
    except ImagenInvalida as e:
        raise ApiError(415 if "Formato" in str(e) or "válida" in str(e) else 413, str(e), "IMAGEN_INVALIDA") from e
    m = _marca(db)
    i = db.get(MarcaImagen, tipo) or MarcaImagen(tipo=tipo)
    i.contenido, i.mime, i.ancho, i.alto, i.bytes = datos, mime, ancho, alto, len(datos)
    db.add(i)
    if tipo == "fondo" and m.login_fondo != "imagen":
        m.login_fondo = "imagen"
    m.version += 1
    m.actualizado_por = actual.id
    auditar(db, request, "marca_imagen", actual.id, tipo=tipo, archivo=(archivo.filename or "")[:120], ancho=ancho, alto=alto)
    db.commit()
    return ok(_out(db, m))


@router.delete("/imagen/{tipo}", response_model=ApiResponse[dict])
def quitar_imagen(tipo: str, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    if tipo not in TIPOS:
        raise ApiError(404, "Tipo de imagen desconocido")
    i = db.get(MarcaImagen, tipo)
    m = _marca(db)
    if i is not None:
        db.delete(i)
        if tipo == "fondo" and m.login_fondo == "imagen":
            m.login_fondo = "degradado"
        m.version += 1
        auditar(db, request, "marca_imagen_quitada", actual.id, tipo=tipo)
        db.commit()
    return ok(_out(db, m))


@router.post("/restablecer", response_model=ApiResponse[dict])
def restablecer(request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    """Vuelve a la marca de fábrica: colores, nombre y sin imágenes propias."""
    m = _marca(db)
    for k, v in MARCA_INICIAL.items():
        setattr(m, k, v)
    for i in db.scalars(select(MarcaImagen)):
        db.delete(i)
    m.version += 1
    m.actualizado_por = actual.id
    auditar(db, request, "marca_restablecida", actual.id)
    db.commit()
    return ok(_out(db, m))
