from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.security import create_access_token, verify_password
from app.models import Usuario
from app.schemas.seguridad import LoginIn, SesionOut

router = APIRouter(prefix="/auth", tags=["auth"])


def sesion_out(user: Usuario) -> SesionOut:
    return SesionOut.model_validate(user, from_attributes=True).model_copy(
        update={"permisos": sorted(user.permisos)}
    )


@router.post("/login", response_model=SesionOut)
def login(data: LoginIn, response: Response, db: DbSession) -> SesionOut:
    user = db.scalar(select(Usuario).where(Usuario.username == data.username.strip().lower()))
    if user is None or not user.activo or not verify_password(data.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario o contraseña incorrectos")
    settings = get_settings()
    response.set_cookie(
        settings.cookie_name,
        create_access_token(user.id),
        max_age=settings.access_token_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return sesion_out(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    response.delete_cookie(get_settings().cookie_name, path="/")


@router.get("/me", response_model=SesionOut)
def me(user: CurrentUser) -> SesionOut:
    return sesion_out(user)
