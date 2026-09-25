from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.core.auditoria import auditar
from app.core.config import get_settings
from app.core.rate_limit import limitador, limitar
from app.core.respuestas import ApiError, ApiResponse, ok
from app.core.security import create_access_token, verify_password
from app.models import Usuario
from app.schemas.seguridad import LoginIn, SesionOut

router = APIRouter(prefix="/auth", tags=["auth"])


def sesion_out(user: Usuario) -> SesionOut:
    return SesionOut.model_validate(user, from_attributes=True).model_copy(update={"permisos": sorted(user.permisos)})


@router.post(
    "/login",
    response_model=ApiResponse[SesionOut],
    # Por IP: 10 intentos por minuto y 50 por hora (fuerza bruta / credential stuffing)
    dependencies=[Depends(limitar("login-min", 10, 60)), Depends(limitar("login-hora", 50, 3600))],
)
def login(data: LoginIn, request: Request, response: Response, db: DbSession):
    s = get_settings()
    username = data.username.strip().lower()
    clave_bloqueo = f"login-fallido:{username}"
    ventana = s.login_bloqueo_minutos * 60

    # Bloqueo temporal por usuario tras varios intentos fallidos (OWASP A07)
    if limitador.contar(clave_bloqueo, ventana) >= s.login_max_intentos:
        auditar(db, request, "login_bloqueado", username=username)
        db.commit()
        raise ApiError(423, f"Usuario bloqueado temporalmente por intentos fallidos. Intente en {s.login_bloqueo_minutos} minutos.")

    user = db.scalar(select(Usuario).where(func.lower(Usuario.username) == username))
    # verify_password siempre calcula bcrypt, exista o no el usuario (sin diferencia de tiempos)
    valido = verify_password(data.password, user.password_hash if user else None)
    if not valido or user is None or not user.activo:
        limitador.registrar(clave_bloqueo, 10_000, ventana)
        auditar(db, request, "login_fallido", user.id if user else None, username=username)
        db.commit()
        # Mensaje genérico: no revela si el usuario existe (OWASP A07)
        raise ApiError(401, "Usuario o contraseña incorrectos")

    limitador.limpiar(clave_bloqueo)
    user.ultimo_acceso = datetime.now(timezone.utc)
    auditar(db, request, "login_exitoso", user.id)
    db.commit()
    response.set_cookie(
        s.cookie_name,
        create_access_token(user.id, user.sesion_version),
        max_age=s.access_token_minutes * 60,
        httponly=True,  # inaccesible desde JavaScript (XSS)
        secure=s.cookie_secure,
        samesite="strict",
        path="/",
    )
    return ok(sesion_out(user))


@router.post("/logout", response_model=ApiResponse[None])
def logout(response: Response):
    response.delete_cookie(get_settings().cookie_name, path="/")
    return ok()


@router.get("/me", response_model=ApiResponse[SesionOut])
def me(user: CurrentUser):
    return ok(sesion_out(user))
