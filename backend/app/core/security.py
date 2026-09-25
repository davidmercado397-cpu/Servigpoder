import re
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import get_settings

ALGORITHM = "HS256"

# Hash de referencia para comparar cuando el usuario no existe: el login tarda
# lo mismo exista o no el usuario (evita enumerar usuarios por tiempo de respuesta).
_HASH_FICTICIO = bcrypt.hashpw(secrets.token_bytes(16), bcrypt.gensalt()).decode()


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


def create_access_token(user_id: int, version: int) -> str:
    settings = get_settings()
    ahora = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "ver": version,  # cambia al cambiar la contraseña o desactivar: invalida sesiones abiertas
        "iat": ahora,
        "exp": ahora + timedelta(minutes=settings.access_token_minutes),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> tuple[int, int] | None:
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM], options={"require": ["exp", "sub"]})
        return int(payload["sub"]), int(payload.get("ver", 0))
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
