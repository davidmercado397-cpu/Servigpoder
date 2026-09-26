"""Ingreso en dos pasos: contraseña + código de la app Authenticator (MFA obligatoria)."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.core.auditoria import auditar
from app.core.config import get_settings
from app.core.rate_limit import limitador, limitar
from app.core.respuestas import ApiError, ApiResponse, ok
from app.core.security import (
    PREAUTH, cifrar_secreto, decodificar, descifrar_secreto, generar_codigos_recuperacion, hash_password, nuevo_secreto_totp,
    qr_svg, uri_totp, usar_codigo_recuperacion, validar_password, verificar_totp, verify_password,
)
from app.core.sesion import COOKIE_PREAUTH, borrar_preauth, borrar_sesion, emitir_preauth, emitir_sesion
from app.models import Usuario
from app.schemas.seguridad import LoginIn, SesionOut

router = APIRouter(prefix="/auth", tags=["auth"])

PASO_MFA, PASO_ENROLAR, PASO_LISTO = "mfa", "enrolar_mfa", "listo"


class PasoOut(BaseModel):
    paso: str  # mfa | enrolar_mfa | listo
    sesion: SesionOut | None = None
    codigos_recuperacion: list[str] | None = None  # solo al activar MFA: se muestran una única vez


class CodigoIn(BaseModel):
    codigo: str = Field(min_length=6, max_length=20)


class ConfigurarMfaOut(BaseModel):
    secreto: str
    uri: str
    qr: str  # data URI SVG


class CambiarPasswordIn(BaseModel):
    actual: str = Field(min_length=1, max_length=200)
    nueva: str

    @field_validator("nueva")
    @classmethod
    def _politica(cls, v: str) -> str:
        return validar_password(v)


class PasswordIn(BaseModel):
    password: str = Field(min_length=1, max_length=200)


def sesion_out(user: Usuario) -> SesionOut:
    return SesionOut.model_validate(user, from_attributes=True).model_copy(update={"permisos": sorted(user.permisos)})


def _bloqueado(clave: str) -> bool:
    s = get_settings()
    return limitador.contar(clave, s.login_bloqueo_minutos * 60) >= s.login_max_intentos


def _fallo(clave: str) -> None:
    limitador.registrar(clave, 10_000, get_settings().login_bloqueo_minutos * 60)


def _usuario_preauth(request: Request, db: DbSession) -> Usuario:
    token = request.cookies.get(COOKIE_PREAUTH)
    datos = decodificar(token, PREAUTH) if token else None
    user = db.get(Usuario, datos["sub"]) if datos else None
    if user is None or not user.activo or datos.get("ver") != user.sesion_version:
        raise ApiError(401, "El tiempo para completar el ingreso expiró. Ingrese de nuevo su usuario y contraseña.")
    return user


def _completar(response: Response, request: Request, db: DbSession, user: Usuario, metodo: str) -> None:
    user.ultimo_acceso = datetime.now(timezone.utc)
    auditar(db, request, "login_exitoso", user.id, mfa=metodo)
    db.commit()
    borrar_preauth(response)
    emitir_sesion(response, user.id, user.sesion_version)


@router.post(
    "/login",
    response_model=ApiResponse[PasoOut],
    # Por IP: 10 intentos por minuto y 50 por hora (fuerza bruta / credential stuffing)
    dependencies=[Depends(limitar("login-min", 10, 60)), Depends(limitar("login-hora", 50, 3600))],
)
def login(data: LoginIn, request: Request, response: Response, db: DbSession):
    """Paso 1: usuario y contraseña. Nunca entrega la sesión si la MFA es obligatoria."""
    s = get_settings()
    username = data.username.strip().lower()
    clave = f"login-fallido:{username}"

    # Bloqueo temporal por usuario tras varios intentos fallidos (OWASP A07)
    if _bloqueado(clave):
        auditar(db, request, "login_bloqueado", username=username)
        db.commit()
        raise ApiError(423, f"Usuario bloqueado temporalmente por intentos fallidos. Intente en {s.login_bloqueo_minutos} minutos.")

    user = db.scalar(select(Usuario).where(func.lower(Usuario.username) == username))
    # verify_password siempre calcula bcrypt, exista o no el usuario (sin diferencia de tiempos)
    valido = verify_password(data.password, user.password_hash if user else None)
    if not valido or user is None or not user.activo:
        _fallo(clave)
        auditar(db, request, "login_fallido", user.id if user else None, username=username)
        db.commit()
        # Mensaje genérico: no revela si el usuario existe (OWASP A07)
        raise ApiError(401, "Usuario o contraseña incorrectos")

    limitador.limpiar(clave)
    if user.mfa_activo:
        emitir_preauth(response, user.id, user.sesion_version)
        return ok(PasoOut(paso=PASO_MFA))
    if s.mfa_obligatorio:
        emitir_preauth(response, user.id, user.sesion_version)
        return ok(PasoOut(paso=PASO_ENROLAR))
    _completar(response, request, db, user, "no_requerida")
    return ok(PasoOut(paso=PASO_LISTO, sesion=sesion_out(user)))


@router.post("/mfa/verificar", response_model=ApiResponse[PasoOut],
             dependencies=[Depends(limitar("mfa-min", 10, 60))])
def verificar_mfa(data: CodigoIn, request: Request, response: Response, db: DbSession):
    """Paso 2: código de 6 dígitos de la app Authenticator, o un código de recuperación."""
    user = _usuario_preauth(request, db)
    if not user.mfa_activo:
        raise ApiError(400, "El usuario no tiene la verificación en dos pasos configurada")
    clave = f"mfa-fallido:{user.id}"
    if _bloqueado(clave):
        raise ApiError(423, f"Demasiados códigos incorrectos. Intente en {get_settings().login_bloqueo_minutos} minutos.")

    secreto = descifrar_secreto(user.mfa_secreto or "")
    paso = verificar_totp(secreto, data.codigo, user.mfa_ultimo_paso) if secreto else None
    metodo = "totp"
    if paso is not None:
        user.mfa_ultimo_paso = paso
    else:
        restantes = usar_codigo_recuperacion(data.codigo, user.mfa_recuperacion or [])
        if restantes is None:
            _fallo(clave)
            auditar(db, request, "mfa_fallido", user.id)
            db.commit()
            raise ApiError(401, "Código incorrecto o vencido")
        user.mfa_recuperacion = restantes
        metodo = "codigo_recuperacion"
        auditar(db, request, "mfa_codigo_recuperacion_usado", user.id, restantes=len(restantes))

    limitador.limpiar(clave)
    _completar(response, request, db, user, metodo)
    return ok(PasoOut(paso=PASO_LISTO, sesion=sesion_out(user)))


@router.post("/mfa/configurar", response_model=ApiResponse[ConfigurarMfaOut],
             dependencies=[Depends(limitar("mfa-config", 10, 60))])
def configurar_mfa(request: Request, db: DbSession):
    """Genera el secreto TOTP y su código QR para escanear con la app Authenticator."""
    user = _usuario_preauth(request, db)
    if user.mfa_activo:
        raise ApiError(409, "La verificación en dos pasos ya está configurada")
    secreto = nuevo_secreto_totp()
    user.mfa_secreto = cifrar_secreto(secreto)
    db.commit()
    uri = uri_totp(secreto, user.username)
    return ok(ConfigurarMfaOut(secreto=secreto, uri=uri, qr=qr_svg(uri)))


@router.post("/mfa/activar", response_model=ApiResponse[PasoOut], dependencies=[Depends(limitar("mfa-min", 10, 60))])
def activar_mfa(data: CodigoIn, request: Request, response: Response, db: DbSession):
    """Confirma la configuración con un primer código válido y entrega los códigos de recuperación."""
    user = _usuario_preauth(request, db)
    if user.mfa_activo:
        raise ApiError(409, "La verificación en dos pasos ya está configurada")
    secreto = descifrar_secreto(user.mfa_secreto or "")
    paso = verificar_totp(secreto, data.codigo, None) if secreto else None
    if paso is None:
        raise ApiError(401, "Código incorrecto. Verifique la hora de su teléfono y vuelva a intentar.")
    codigos, hashes = generar_codigos_recuperacion()
    user.mfa_activo, user.mfa_ultimo_paso, user.mfa_recuperacion = True, paso, hashes
    auditar(db, request, "mfa_activada", user.id)
    _completar(response, request, db, user, "totp")
    return ok(PasoOut(paso=PASO_LISTO, sesion=sesion_out(user), codigos_recuperacion=codigos))


@router.post("/cambiar-password", response_model=ApiResponse[SesionOut], dependencies=[Depends(limitar("password", 10, 60))])
def cambiar_password(data: CambiarPasswordIn, request: Request, response: Response, db: DbSession, user: CurrentUser):
    if not verify_password(data.actual, user.password_hash):
        auditar(db, request, "password_cambio_fallido", user.id)
        db.commit()
        raise ApiError(400, "La contraseña actual no es correcta")
    if verify_password(data.nueva, user.password_hash):
        raise ApiError(400, "La nueva contraseña debe ser distinta a la actual")
    user.password_hash = hash_password(data.nueva)
    user.debe_cambiar_password = False
    user.password_actualizado_en = datetime.now(timezone.utc)
    user.sesion_version += 1  # cierra las demás sesiones abiertas
    auditar(db, request, "password_cambiada", user.id)
    db.commit()
    emitir_sesion(response, user.id, user.sesion_version)
    return ok(sesion_out(user))


@router.post("/mfa/codigos-recuperacion", response_model=ApiResponse[list[str]], dependencies=[Depends(limitar("password", 10, 60))])
def regenerar_codigos(data: PasswordIn, request: Request, db: DbSession, user: CurrentUser):
    """Genera códigos de recuperación nuevos (invalida los anteriores). Pide la contraseña."""
    if not verify_password(data.password, user.password_hash):
        raise ApiError(400, "La contraseña no es correcta")
    codigos, hashes = generar_codigos_recuperacion()
    user.mfa_recuperacion = hashes
    auditar(db, request, "mfa_codigos_regenerados", user.id)
    db.commit()
    return ok(codigos)


@router.post("/logout", response_model=ApiResponse[None])
def logout(response: Response):
    borrar_sesion(response)
    return ok()


@router.get("/me", response_model=ApiResponse[SesionOut])
def me(user: CurrentUser):
    return ok(sesion_out(user))
