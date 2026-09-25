from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.respuestas import ApiError
from app.core.security import decode_access_token
from app.models import Usuario

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(request: Request, db: DbSession) -> Usuario:
    token = request.cookies.get(get_settings().cookie_name)
    auth = request.headers.get("Authorization", "")
    if not token and auth.lower().startswith("bearer "):
        token = auth[7:]
    datos = decode_access_token(token) if token else None
    user = db.get(Usuario, datos[0]) if datos else None
    # Denegar por defecto (OWASP A01): token inválido, usuario inactivo o sesión revocada
    if user is None or not user.activo or datos[1] != user.sesion_version:
        raise ApiError(401, "Sesión inválida o expirada")
    return user


CurrentUser = Annotated[Usuario, Depends(get_current_user)]


def require(permiso: str) -> Callable[[Usuario], Usuario]:
    def checker(user: CurrentUser) -> Usuario:
        if permiso not in user.permisos:
            raise ApiError(403, "No tiene permiso para realizar esta acción", details=[{"permiso": permiso}])
        return user

    return checker
