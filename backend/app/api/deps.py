from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import decode_access_token
from app.models import Usuario

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(request: Request, db: DbSession) -> Usuario:
    token = request.cookies.get(get_settings().cookie_name)
    auth = request.headers.get("Authorization", "")
    if not token and auth.lower().startswith("bearer "):
        token = auth[7:]
    user_id = decode_access_token(token) if token else None
    user = db.get(Usuario, user_id) if user_id else None
    if user is None or not user.activo:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión inválida o expirada")
    return user


CurrentUser = Annotated[Usuario, Depends(get_current_user)]


def require(permiso: str) -> Callable[[Usuario], Usuario]:
    def checker(user: CurrentUser) -> Usuario:
        if permiso not in user.permisos:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requiere el permiso '{permiso}'")
        return user

    return checker
