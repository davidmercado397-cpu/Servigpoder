"""Cookies de sesión y de pre-autenticación."""

from fastapi import Response

from app.core.config import get_settings
from app.core.security import crear_token_preauth, crear_token_sesion

COOKIE_PREAUTH = "preauth"


def _cookie(response: Response, nombre: str, valor: str, max_age: int, path: str) -> None:
    response.set_cookie(
        nombre, valor, max_age=max_age,
        httponly=True,  # inaccesible desde JavaScript (XSS)
        secure=get_settings().cookie_secure,
        samesite="strict",
        path=path,
    )


def emitir_sesion(response: Response, user_id: int, version: int, auth_time: int | None = None) -> None:
    s = get_settings()
    _cookie(response, s.cookie_name, crear_token_sesion(user_id, version, auth_time), s.sesion_max_horas * 3600, "/")


def emitir_preauth(response: Response, user_id: int, version: int) -> None:
    # Solo viaja a los endpoints de autenticación
    _cookie(response, COOKIE_PREAUTH, crear_token_preauth(user_id, version), get_settings().preauth_minutos * 60, "/api/auth")


def borrar_preauth(response: Response) -> None:
    response.delete_cookie(COOKIE_PREAUTH, path="/api/auth")


def borrar_sesion(response: Response) -> None:
    response.delete_cookie(get_settings().cookie_name, path="/")
    borrar_preauth(response)
