"""Formato estándar de todas las respuestas JSON de la API.

Éxito:
    {"success": true,  "data": <cualquier cosa>, "error": null, "meta": {...}}
Error:
    {"success": false, "data": null, "error": {"code": "...", "message": "...", "details": [...]}, "meta": {...}}

`meta` siempre trae la versión de la API, el id de la petición (también en la
cabecera X-Request-ID) y la hora del servidor, más datos opcionales (paginación).
"""

import logging
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import API_VERSION

log = logging.getLogger("app")
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

T = TypeVar("T")


class Meta(BaseModel):
    api_version: str = API_VERSION
    request_id: str = "-"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    extra: dict[str, Any] | None = None


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[Any] | None = None


class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T | None = None
    error: ErrorBody | None = None
    meta: Meta


def ok(data: Any = None, **extra: Any) -> dict[str, Any]:
    """Envuelve `data` en el formato estándar. Úsese con response_model=ApiResponse[...]."""
    return {
        "success": True,
        "data": data,
        "error": None,
        "meta": Meta(request_id=request_id_ctx.get(), extra=extra or None),
    }


CODIGOS = {
    400: "SOLICITUD_INVALIDA",
    401: "NO_AUTENTICADO",
    403: "SIN_PERMISO",
    404: "NO_ENCONTRADO",
    405: "METODO_NO_PERMITIDO",
    409: "CONFLICTO",
    413: "ARCHIVO_DEMASIADO_GRANDE",
    415: "TIPO_NO_SOPORTADO",
    422: "DATOS_INVALIDOS",
    423: "BLOQUEADO",
    429: "DEMASIADAS_SOLICITUDES",
    500: "ERROR_INTERNO",
}


class ApiError(HTTPException):
    """Error de negocio con código propio además del estado HTTP."""

    def __init__(self, status_code: int, message: str, code: str | None = None, details: list[Any] | None = None,
                 headers: dict[str, str] | None = None):
        super().__init__(status_code, message, headers)
        self.code = code or CODIGOS.get(status_code, "ERROR")
        self.details = details


def error_response(status_code: int, message: str, code: str | None = None, details: list[Any] | None = None,
                   headers: dict[str, str] | None = None) -> JSONResponse:
    body = {
        "success": False,
        "data": None,
        "error": {"code": code or CODIGOS.get(status_code, "ERROR"), "message": message, "details": details},
        "meta": Meta(request_id=request_id_ctx.get()).model_dump(mode="json"),
    }
    return JSONResponse(body, status_code=status_code, headers=headers)


def registrar_manejadores(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return error_response(exc.status_code, str(exc.detail), exc.code, exc.details, exc.headers)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        mensaje = exc.detail if isinstance(exc.detail, str) else "Error en la solicitud"
        return error_response(exc.status_code, mensaje, headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def _validacion(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Solo ubicación y mensaje: nunca se devuelve el valor recibido (podría ser una contraseña)
        detalles = [{"campo": ".".join(str(p) for p in e["loc"][1:]), "mensaje": e["msg"]} for e in exc.errors()]
        return error_response(status.HTTP_422_UNPROCESSABLE_ENTITY, "Los datos enviados no son válidos", details=detalles)

    @app.exception_handler(Exception)
    async def _inesperado(_: Request, exc: Exception) -> JSONResponse:
        # OWASP A05: sin trazas ni detalles internos hacia el cliente
        log.exception("Error no controlado request_id=%s", request_id_ctx.get())
        return error_response(500, "Ocurrió un error interno. Informe el código de la solicitud a soporte.")
