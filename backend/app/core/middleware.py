"""Middlewares de seguridad (ASGI puro, sin bloquear el streaming de archivos).

Orden de ejecución de afuera hacia adentro (ver `registrar_middlewares`):
1. RequestId          id único por petición (X-Request-ID) y log de acceso
2. SecurityHeaders    cabeceras de seguridad OWASP en todas las respuestas
3. TrustedHost        rechaza cabeceras Host no permitidas
4. RateLimitGlobal    tope de peticiones por IP para toda la API
5. CsrfHeader         peticiones que modifican datos deben traer X-Requested-With
6. BodySizeLimit      rechaza cuerpos más grandes que MAX_UPLOAD_MB
"""

import logging
import re
import time
import uuid

from fastapi import FastAPI
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import get_settings
from app.core.rate_limit import limitador
from app.core.respuestas import error_response, request_id_ctx

log = logging.getLogger("app.acceso")

METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}
_ID_VALIDO = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def _cabecera(scope: Scope, nombre: bytes) -> str | None:
    for k, v in scope.get("headers", []):
        if k == nombre:
            return v.decode("latin-1")
    return None


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        entrante = _cabecera(scope, b"x-request-id")
        rid = entrante if entrante and _ID_VALIDO.match(entrante) else uuid.uuid4().hex
        token = request_id_ctx.set(rid)
        inicio = time.perf_counter()
        estado = 500

        async def enviar(msg: Message) -> None:
            nonlocal estado
            if msg["type"] == "http.response.start":
                estado = msg["status"]
                msg.setdefault("headers", []).append((b"x-request-id", rid.encode()))
            await send(msg)

        try:
            await self.app(scope, receive, enviar)
        finally:
            cliente = scope.get("client") or ("-", 0)
            log.info('%s %s %s %s %.0fms rid=%s', cliente[0], scope["method"], scope["path"], estado,
                     (time.perf_counter() - inicio) * 1000, rid)
            request_id_ctx.reset(token)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, hsts: bool) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        es_docs = scope["path"].startswith("/api/docs")

        async def enviar(msg: Message) -> None:
            if msg["type"] == "http.response.start":
                h = [(k, v) for k, v in msg.get("headers", []) if k.lower() != b"server"]
                h += [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                    (b"cross-origin-opener-policy", b"same-origin"),
                    (b"cross-origin-resource-policy", b"same-origin"),
                    (b"cache-control", b"no-store"),
                ]
                if not es_docs:
                    # La API solo devuelve JSON: no debe cargar ningún recurso
                    h.append((b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"))
                if self.hsts:
                    h.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
                msg["headers"] = h
            await send(msg)

        await self.app(scope, receive, enviar)


class RateLimitGlobalMiddleware:
    def __init__(self, app: ASGIApp, limite: int) -> None:
        self.app = app
        self.limite = limite

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] == "/api/health":
            return await self.app(scope, receive, send)
        ip = (scope.get("client") or ("desconocida", 0))[0]
        espera = limitador.registrar(f"global:{ip}", self.limite, 60)
        if espera is not None:
            resp = error_response(429, f"Demasiadas solicitudes. Intente de nuevo en {espera} segundos.",
                                  headers={"Retry-After": str(espera)})
            return await resp(scope, receive, send)
        await self.app(scope, receive, send)


class CsrfHeaderMiddleware:
    """Defensa CSRF por cabecera personalizada (OWASP CSRF Cheat Sheet).

    La sesión viaja en una cookie, así que toda petición que modifica datos debe
    traer `X-Requested-With`. Un sitio externo no puede agregar esa cabecera sin
    un preflight CORS, y la API no habilita CORS.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] not in METODOS_SEGUROS:
            if not _cabecera(scope, b"x-requested-with"):
                resp = error_response(403, "Solicitud rechazada: falta la cabecera X-Requested-With", "CSRF")
                return await resp(scope, receive, send)
        await self.app(scope, receive, send)


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        largo = _cabecera(scope, b"content-length")
        if largo and largo.isdigit() and int(largo) > self.max_bytes:
            return await self._rechazar(scope, receive, send)

        recibido = 0

        async def recibir() -> Message:
            nonlocal recibido
            msg = await receive()
            if msg["type"] == "http.request":
                recibido += len(msg.get("body", b""))
                if recibido > self.max_bytes:
                    raise _CuerpoExcedido
            return msg

        try:
            await self.app(scope, recibir, send)
        except _CuerpoExcedido:
            await self._rechazar(scope, receive, send)

    async def _rechazar(self, scope: Scope, receive: Receive, send: Send) -> None:
        mb = self.max_bytes // (1024 * 1024)
        await error_response(413, f"El archivo supera el tamaño máximo de {mb} MB")(scope, receive, send)


class _CuerpoExcedido(Exception):
    pass


def registrar_middlewares(app: FastAPI) -> None:
    s = get_settings()
    # add_middleware apila: el último agregado es el más externo
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=s.max_upload_mb * 1024 * 1024)
    app.add_middleware(CsrfHeaderMiddleware)
    app.add_middleware(RateLimitGlobalMiddleware, limite=s.rate_limit_global)
    hosts = [h.strip() for h in s.allowed_hosts.split(",") if h.strip()] or ["*"]
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)
    app.add_middleware(SecurityHeadersMiddleware, hsts=s.cookie_secure)
    app.add_middleware(RequestIdMiddleware)
