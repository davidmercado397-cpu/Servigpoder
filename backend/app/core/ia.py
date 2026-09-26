"""Motor de IA de la plataforma, independiente del proveedor.

Habla el formato de "chat completions" compatible con OpenAI, que ofrecen OpenRouter (por
defecto), OpenAI, Azure y servidores locales. Cambiar de proveedor o de modelo es solo
configuración: IA_BASE_URL, IA_API_KEY e IA_MODELO.

Cada app aporta sus instrucciones y sus herramientas de SOLO LECTURA (decoradas con
@herramienta); este módulo ejecuta el ciclo pregunta → herramientas → respuesta.
"""

import inspect
import json
import logging
import re
import types
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Union, get_args, get_origin

import httpx

from app.core.config import get_settings

log = logging.getLogger("app.ia")

MAX_ITERACIONES = 10
MAX_TOKENS = 8000

_TIPOS = {int: "integer", float: "number", str: "string", bool: "boolean"}


class IANoConfigurada(Exception):
    pass


class IAError(Exception):
    """Error del proveedor traducido a un mensaje para el usuario."""

    def __init__(self, status: int, mensaje: str, codigo: str = "ERROR_IA"):
        super().__init__(mensaje)
        self.status, self.mensaje, self.codigo = status, mensaje, codigo


@dataclass
class Herramienta:
    nombre: str
    descripcion: str
    parametros: dict
    fn: Callable[..., str]

    def call(self, argumentos: dict | None = None) -> str:
        return self.fn(**(argumentos or {}))

    def definicion(self) -> dict:
        return {"type": "function", "function": {"name": self.nombre, "description": self.descripcion, "parameters": self.parametros}}


def _tipo_json(anotacion: Any) -> str:
    if get_origin(anotacion) in (Union, types.UnionType):
        anotacion = next(a for a in get_args(anotacion) if a is not type(None))
    return _TIPOS.get(anotacion, "string")


def herramienta(fn: Callable[..., str]) -> Herramienta:
    """Convierte una función en herramienta: el esquema sale de la firma y la sección Args del docstring."""
    doc = inspect.getdoc(fn) or ""
    descripcion, _, args = doc.partition("Args:")
    ayudas: dict[str, str] = {}
    actual = None
    for linea in args.splitlines():
        m = re.match(r"^\s{0,8}(\w+):\s*(.*)$", linea)
        if m:
            actual = m.group(1)
            ayudas[actual] = m.group(2).strip()
        elif actual and linea.strip():
            ayudas[actual] += " " + linea.strip()
    propiedades: dict[str, dict] = {}
    requeridos: list[str] = []
    for nombre, p in inspect.signature(fn).parameters.items():
        propiedades[nombre] = {"type": _tipo_json(p.annotation), "description": ayudas.get(nombre, "")}
        if p.default is inspect.Parameter.empty:
            requeridos.append(nombre)
    esquema = {"type": "object", "properties": propiedades, "required": requeridos}
    return Herramienta(fn.__name__, " ".join(descripcion.split()), esquema, fn)


@dataclass
class Respuesta:
    texto: str
    herramientas: list[str] = field(default_factory=list)
    tokens_entrada: int = 0
    tokens_salida: int = 0
    modelo: str = ""


def configurada() -> bool:
    return bool(get_settings().ia_api_key)


def cliente_http() -> httpx.Client:
    return httpx.Client(timeout=120.0)


def _es_openrouter(base_url: str) -> bool:
    return "openrouter.ai" in base_url


def _llamar(http: httpx.Client, cuerpo: dict) -> dict:
    s = get_settings()
    url = s.ia_base_url.rstrip("/") + "/chat/completions"
    cabeceras = {"Authorization": f"Bearer {s.ia_api_key}"}
    if _es_openrouter(s.ia_base_url):
        cabeceras["X-Title"] = "Plataforma Servigpoder"
    try:
        r = http.post(url, headers=cabeceras, json=cuerpo)
    except httpx.HTTPError as e:
        raise IAError(503, "No fue posible conectar con el servicio de IA.") from e
    try:
        datos = r.json()
    except ValueError:
        datos = {}
    error = datos.get("error") if isinstance(datos, dict) else None
    if r.status_code >= 400 or error:
        codigo = r.status_code if r.status_code >= 400 else int((error or {}).get("code") or 502)
        detalle = (error or {}).get("message", "") if isinstance(error, dict) else ""
        log.warning("Proveedor de IA respondió %s: %s", codigo, detalle[:300])
        if codigo in (401, 403):
            raise IAError(503, "La clave del servicio de IA no es válida. Revise IA_API_KEY.", "ASISTENTE_NO_CONFIGURADO")
        if codigo == 402:
            raise IAError(503, "La cuenta del servicio de IA no tiene créditos suficientes.", "ASISTENTE_NO_CONFIGURADO")
        if codigo == 429:
            raise IAError(429, "El servicio de IA está ocupado. Intente de nuevo en un minuto.")
        if codigo == 404 and s.ia_zdr:
            raise IAError(502, "El modelo configurado no está disponible con retención cero de datos (IA_ZDR). "
                               "Elija otro modelo en IA_MODELO.")
        raise IAError(502, "El servicio de IA respondió con un error. Intente de nuevo.")
    return datos


def conversar(instrucciones: str, mensajes: list[dict], herramientas: list[Herramienta]) -> Respuesta:
    """Ciclo del agente: el modelo pide herramientas, se ejecutan aquí y se le devuelve el resultado."""
    s = get_settings()
    if not s.ia_api_key:
        raise IANoConfigurada()
    por_nombre = {h.nombre: h for h in herramientas}
    historial: list[dict] = [{"role": "system", "content": instrucciones}, *mensajes]
    res = Respuesta(texto="", modelo=s.ia_modelo)
    extra: dict = {}
    if _es_openrouter(s.ia_base_url):
        # Solo proveedores que no guardan ni entrenan con los datos (y, si se pide, con retención cero)
        extra["provider"] = {"data_collection": "deny", **({"zdr": True} if s.ia_zdr else {})}

    with cliente_http() as http:
        for iteracion in range(MAX_ITERACIONES):
            ultima = iteracion == MAX_ITERACIONES - 1
            cuerpo = {"model": s.ia_modelo, "max_tokens": MAX_TOKENS, "messages": historial, **extra}
            if herramientas:
                cuerpo["tools"] = [h.definicion() for h in herramientas]
                cuerpo["tool_choice"] = "none" if ultima else "auto"
            datos = _llamar(http, cuerpo)
            uso = datos.get("usage") or {}
            res.tokens_entrada += uso.get("prompt_tokens") or 0
            res.tokens_salida += uso.get("completion_tokens") or 0
            res.modelo = datos.get("model") or res.modelo
            eleccion = (datos.get("choices") or [{}])[0]
            mensaje = eleccion.get("message") or {}
            llamadas = mensaje.get("tool_calls") or []
            if not llamadas:
                texto = (mensaje.get("content") or "").strip()
                if eleccion.get("finish_reason") == "length":
                    texto += "\n\n_(Respuesta recortada por longitud. Haga una pregunta más específica.)_"
                res.texto = texto or "No encontré información para responder."
                return res

            historial.append({"role": "assistant", "content": mensaje.get("content") or "", "tool_calls": llamadas})
            for llamada in llamadas:
                nombre = llamada.get("function", {}).get("name", "")
                res.herramientas.append(nombre)
                historial.append({"role": "tool", "tool_call_id": llamada.get("id", ""),
                                  "content": _ejecutar(por_nombre.get(nombre), llamada.get("function", {}).get("arguments"))})
    res.texto = "No logré completar la respuesta. Haga una pregunta más específica."
    return res


def _ejecutar(h: Herramienta | None, argumentos: str | None) -> str:
    if h is None:
        return json.dumps({"error": "Herramienta desconocida"})
    try:
        args = json.loads(argumentos or "{}")
        if not isinstance(args, dict):
            raise ValueError
        permitidos = h.parametros["properties"].keys()
        return h.call({k: v for k, v in args.items() if k in permitidos})
    except (ValueError, TypeError) as e:
        return json.dumps({"error": f"Argumentos inválidos: {e}"}, ensure_ascii=False)
    except Exception:  # una herramienta que falla no debe tumbar la conversación
        log.exception("Falló la herramienta %s", h.nombre)
        return json.dumps({"error": "La consulta falló en el servidor."})
