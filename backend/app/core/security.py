"""Contraseñas, tokens de sesión y verificación en dos pasos (TOTP).

Flujo de ingreso (OWASP ASVS V2 / Authentication Cheat Sheet):
1. Usuario y contraseña correctos → token temporal de "pre-autenticación" (5 min) en cookie propia.
2. Código de la app Authenticator (o código de recuperación) → token de sesión.
   Si el usuario no tiene MFA configurada, la configura en ese momento (MFA obligatoria).
3. Si la contraseña es temporal (creada por un administrador), la sesión solo permite cambiarla.

La sesión vence por inactividad (se renueva con cada petición) y tiene una duración máxima.
"""

import base64
import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from io import BytesIO

import bcrypt
import jwt
import pyotp
import qrcode
import qrcode.image.svg
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

ALGORITHM = "HS256"
SESION, PREAUTH = "sesion", "preauth"

# Hash de referencia para comparar cuando el usuario no existe: el login tarda
# lo mismo exista o no el usuario (evita enumerar usuarios por tiempo de respuesta).
_HASH_FICTICIO = bcrypt.hashpw(secrets.token_bytes(16), bcrypt.gensalt()).decode()


# --- Contraseñas --------------------------------------------------------------

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str | None) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), (hashed or _HASH_FICTICIO).encode()) and hashed is not None
    except ValueError:
        return False


def validar_password(password: str) -> str:
    """Política mínima (OWASP ASVS 2.1): 10+ caracteres, con letras y números, máx. 72 bytes (límite de bcrypt)."""
    if len(password) < 10:
        raise ValueError("La contraseña debe tener al menos 10 caracteres")
    if len(password.encode()) > 72:
        raise ValueError("La contraseña no puede superar 72 caracteres")
    if not re.search(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]", password) or not re.search(r"\d", password):
        raise ValueError("La contraseña debe combinar letras y números")
    return password


# --- Tokens -------------------------------------------------------------------

def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def crear_token_sesion(user_id: int, version: int, auth_time: int | None = None) -> str:
    """Token de sesión. `exp` = ahora + inactividad (se renueva); `auth` = momento del ingreso (límite absoluto)."""
    s = get_settings()
    ahora = _ahora()
    auth = auth_time or int(ahora.timestamp())
    limite = datetime.fromtimestamp(auth, timezone.utc) + timedelta(hours=s.sesion_max_horas)
    exp = min(ahora + timedelta(minutes=s.sesion_inactividad_min), limite)
    payload = {"sub": str(user_id), "ver": version, "typ": SESION, "auth": auth, "iat": ahora, "exp": exp,
               "jti": secrets.token_hex(8)}
    return jwt.encode(payload, s.secret_key, algorithm=ALGORITHM)


def crear_token_preauth(user_id: int, version: int) -> str:
    s = get_settings()
    ahora = _ahora()
    payload = {"sub": str(user_id), "ver": version, "typ": PREAUTH, "iat": ahora,
               "exp": ahora + timedelta(minutes=s.preauth_minutos), "jti": secrets.token_hex(8)}
    return jwt.encode(payload, s.secret_key, algorithm=ALGORITHM)


def decodificar(token: str, tipo: str) -> dict | None:
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM],
                             options={"require": ["exp", "sub", "typ"]})
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != tipo:
        return None
    try:
        payload["sub"] = int(payload["sub"])
    except (TypeError, ValueError):
        return None
    return payload


# --- MFA (TOTP) ---------------------------------------------------------------

def _fernet() -> Fernet:
    clave = hashlib.sha256(f"{get_settings().secret_key}:mfa".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(clave))


def cifrar_secreto(secreto: str) -> str:
    return _fernet().encrypt(secreto.encode()).decode()


def descifrar_secreto(cifrado: str) -> str | None:
    try:
        return _fernet().decrypt(cifrado.encode()).decode()
    except InvalidToken:
        return None


def nuevo_secreto_totp() -> str:
    return pyotp.random_base32()


def uri_totp(secreto: str, cuenta: str) -> str:
    return pyotp.TOTP(secreto).provisioning_uri(name=cuenta, issuer_name=get_settings().mfa_emisor)


def qr_svg(texto: str) -> str:
    """QR como imagen SVG embebible (data URI), generado en el servidor: el secreto no sale a terceros."""
    img = qrcode.make(texto, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    buf = BytesIO()
    img.save(buf)
    return "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode()


def verificar_totp(secreto: str, codigo: str, ultimo_paso: int | None) -> int | None:
    """Devuelve el paso de tiempo del código si es válido y no fue usado antes; si no, None.

    Acepta ±1 intervalo de 30 s por desfase de reloj del teléfono.
    """
    codigo = re.sub(r"\s", "", codigo)
    if not re.fullmatch(r"\d{6}", codigo):
        return None
    totp = pyotp.TOTP(secreto)
    ahora = int(_ahora().timestamp()) // totp.interval
    for paso in (ahora - 1, ahora, ahora + 1):
        if secrets.compare_digest(totp.generate_otp(paso), codigo):
            if ultimo_paso is not None and paso <= ultimo_paso:
                return None  # código ya usado (protección contra repetición)
            return paso
    return None


def generar_codigos_recuperacion(cantidad: int = 10) -> tuple[list[str], list[str]]:
    """Códigos de un solo uso para cuando no se tiene el teléfono. Se guardan solo sus hashes."""
    codigos = [f"{secrets.token_hex(4)}-{secrets.token_hex(4)}" for _ in range(cantidad)]
    return codigos, [_hash_codigo(c) for c in codigos]


def _hash_codigo(codigo: str) -> str:
    return hashlib.sha256(codigo.strip().lower().replace(" ", "").encode()).hexdigest()


def usar_codigo_recuperacion(codigo: str, hashes: list[str]) -> list[str] | None:
    """Si el código es válido devuelve la lista de hashes sin él (se consume); si no, None."""
    h = _hash_codigo(codigo)
    for guardado in hashes:
        if secrets.compare_digest(guardado, h):
            return [x for x in hashes if x != guardado]
    return None
