"""Configuración del agente de IA desde el panel de administración: clave de la API (OpenRouter) y modelos.

La clave se guarda cifrada y nunca se devuelve: solo sus últimos 4 caracteres. Lo que se deje vacío se toma de las
variables del servidor (IA_API_KEY, IA_MODELO). Exige el permiso ia.gestionar.
"""

import time

import httpx
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.deps import DbSession, require
from app.core import ia
from app.core.auditoria import auditar
from app.core.config import get_settings
from app.core.rate_limit import limitar
from app.core.respuestas import ApiError, ApiResponse, ok
from app.core.security import cifrar_secreto
from app.models import IAConfig, Usuario

router = APIRouter(prefix="/ia", tags=["inteligencia artificial"])
GESTIONAR = "ia.gestionar"
# Identificador de modelo de OpenRouter: proveedor/modelo (p. ej. anthropic/claude-opus-5, openai/gpt-5:online)
MODELO = r"^$|^[A-Za-z0-9._\-]+/[A-Za-z0-9._:\-]+$"

# Lista de modelos del proveedor (pública, sin datos de la empresa): se guarda una hora en memoria
_modelos: dict = {"cuando": 0.0, "lista": []}


class ConfigIn(BaseModel):
    # Vacía = se conserva la clave guardada
    api_key: str = Field(default="", max_length=300, pattern=r"^\S*$")
    borrar_clave: bool = False
    modelo: str = Field(default="", max_length=150, pattern=MODELO)
    modelo_costeo: str = Field(default="", max_length=150, pattern=MODELO)


class PruebaIn(BaseModel):
    modelo: str = Field(default="", max_length=150, pattern=MODELO)


def _config(db: DbSession, crear: bool = False) -> IAConfig | None:
    c = db.get(IAConfig, 1)
    if c is None and crear:
        c = IAConfig(id=1)
        db.add(c)
        db.flush()
    return c


def _out(db: DbSession) -> dict:
    ia.cargar(db)
    c, s, a = _config(db), get_settings(), ia.ajustes()
    return {
        "configurada": bool(a.api_key),
        "origen_clave": a.origen_clave,  # panel | servidor | ""
        "clave_final": (c.api_key_final if c and a.origen_clave == "panel" else (s.ia_api_key[-4:] if s.ia_api_key else "")),
        "modelo": (c.modelo if c else None) or "",
        "modelo_costeo": (c.modelo_costeo if c else None) or "",
        "modelo_servidor": s.ia_modelo,
        "modelo_vigente": a.modelo,
        "modelo_costeo_vigente": a.modelo_costeo,
        "proveedor": s.ia_base_url,
        "retencion_cero": s.ia_zdr,
    }


@router.get("/config", response_model=ApiResponse[dict])
def ver(db: DbSession, _=Depends(require(GESTIONAR))):
    return ok(_out(db))


@router.put("/config", response_model=ApiResponse[dict])
def guardar(data: ConfigIn, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    c = _config(db, crear=True)
    cambios = []
    if data.borrar_clave:
        if c.api_key_cifrada:
            cambios.append("clave borrada")
        c.api_key_cifrada = c.api_key_final = None
    elif data.api_key:
        if len(data.api_key) < 10:
            raise ApiError(422, "La clave de la API parece incompleta")
        c.api_key_cifrada = cifrar_secreto(data.api_key, "ia")
        c.api_key_final = data.api_key[-4:]
        cambios.append("clave nueva")
    for campo in ("modelo", "modelo_costeo"):
        nuevo = getattr(data, campo).strip() or None
        if getattr(c, campo) != nuevo:
            cambios.append(f"{campo}: {getattr(c, campo) or '(servidor)'} → {nuevo or '(servidor)'}")
            setattr(c, campo, nuevo)
    c.actualizado_por = actual.id
    # Auditoría: qué cambió, nunca la clave
    auditar(db, request, "ia_configurada", actual.id, cambios=cambios)
    db.commit()
    return ok(_out(db))


@router.post("/probar", response_model=ApiResponse[dict], dependencies=[Depends(limitar("ia_probar", 5, 60))])
def probar(data: PruebaIn, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    ia.cargar(db)
    modelo = data.modelo or ia.ajustes().modelo
    inicio = time.monotonic()
    try:
        r = ia.completar("Eres una prueba de conexión. Responde únicamente: Conexión correcta.",
                         [{"role": "user", "content": "Prueba de conexión"}], modelo=modelo, max_tokens=600)
    except ia.IANoConfigurada as e:
        raise ApiError(422, "Falta la clave de la API: escríbala y guarde antes de probar.") from e
    except ia.IAError as e:
        raise ApiError(e.status, e.mensaje, e.codigo) from e
    auditar(db, request, "ia_prueba", actual.id, modelo=r.modelo, tokens_entrada=r.tokens_entrada, tokens_salida=r.tokens_salida)
    db.commit()
    return ok({"modelo": r.modelo, "respuesta": r.texto[:200], "segundos": round(time.monotonic() - inicio, 1)})


def _precio(v) -> float | None:
    try:
        return round(float(v) * 1_000_000, 4)  # USD por millón de tokens
    except (TypeError, ValueError):
        return None


@router.get("/modelos", response_model=ApiResponse[list[dict]])
def modelos(_=Depends(require(GESTIONAR))):
    """Modelos disponibles en el proveedor, con su precio y si leen imágenes o PDF."""
    if _modelos["lista"] and time.time() - _modelos["cuando"] < 3600:
        return ok(_modelos["lista"])
    url = get_settings().ia_base_url.rstrip("/") + "/models"
    try:
        with ia.cliente_http() as http:
            r = http.get(url)
        datos = r.json().get("data") or []
    except (httpx.HTTPError, ValueError, AttributeError) as e:
        raise ApiError(502, "No fue posible traer la lista de modelos del proveedor. Puede escribir el modelo a mano.") from e
    lista = []
    for m in datos:
        if not isinstance(m, dict) or not m.get("id"):
            continue
        entradas = ((m.get("architecture") or {}).get("input_modalities")) or []
        precio = m.get("pricing") or {}
        lista.append({"id": m["id"], "nombre": m.get("name") or m["id"], "contexto": m.get("context_length"),
                      "precio_entrada": _precio(precio.get("prompt")), "precio_salida": _precio(precio.get("completion")),
                      "imagenes": "image" in entradas, "archivos": "file" in entradas})
    lista.sort(key=lambda x: x["id"])
    _modelos.update(cuando=time.time(), lista=lista)
    return ok(lista)
