import time
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.respuestas import ApiError
from app.core.security import SESION, decodificar
from app.core.sesion import emitir_sesion
from app.models import Usuario

DbSession = Annotated[Session, Depends(get_db)]

# Con contraseña temporal solo se permite consultar la sesión, cambiar la contraseña y salir
RUTAS_CON_PASSWORD_TEMPORAL = {"/api/auth/me", "/api/auth/cambiar-password", "/api/auth/logout"}
RENOVAR_CADA_SEGUNDOS = 60


def get_current_user(request: Request, response: Response, db: DbSession) -> Usuario:
    s = get_settings()
    token = request.cookies.get(s.cookie_name)
    desde_cookie = bool(token)
    auth = request.headers.get("Authorization", "")
    if not token and auth.lower().startswith("bearer "):
        token = auth[7:]
    datos = decodificar(token, SESION) if token else None
    user = db.get(Usuario, datos["sub"]) if datos else None
    # Denegar por defecto (OWASP A01): token inválido o vencido, usuario inactivo o sesión revocada
    if user is None or not user.activo or datos.get("ver") != user.sesion_version:
        raise ApiError(401, "Sesión inválida o expirada")
    if s.mfa_obligatorio and not user.mfa_activo:
        raise ApiError(401, "Debe configurar la verificación en dos pasos")
    if user.debe_cambiar_password and request.url.path not in RUTAS_CON_PASSWORD_TEMPORAL:
        raise ApiError(403, "Debe cambiar su contraseña temporal antes de continuar", "CAMBIO_PASSWORD_REQUERIDO")

    # Sesión deslizante: cada petición renueva el vencimiento por inactividad (sin pasar el máximo)
    if desde_cookie and time.time() - datos.get("iat", 0) > RENOVAR_CADA_SEGUNDOS:
        emitir_sesion(response, user.id, user.sesion_version, datos.get("auth"))
    return user


CurrentUser = Annotated[Usuario, Depends(get_current_user)]


def require(permiso: str) -> Callable[[Usuario], Usuario]:
    def checker(user: CurrentUser) -> Usuario:
        if permiso not in user.permisos:
            raise ApiError(403, "No tiene permiso para realizar esta acción", details=[{"permiso": permiso}])
        return user

    return checker
