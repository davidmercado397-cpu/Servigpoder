import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "admin-clave-123"

from io import BytesIO

import time

import pyotp
import pytest
import xlsxwriter
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.core.rate_limit import limitador
from app.main import app
from app.seed import seed

CSRF = {"X-Requested-With": "fetch"}


# Estado de MFA y contraseñas de los usuarios de prueba (se reinicia en cada prueba)
SECRETOS: dict[str, str] = {}
RECUPERACION: dict[str, list[str]] = {}
PASOS_USADOS: dict[str, set[int]] = {}
CLAVES: dict[str, str] = {}


def _codigo(username: str) -> str:
    """Código TOTP no usado aún (±1 intervalo); si se agotan, un código de recuperación."""
    totp = pyotp.TOTP(SECRETOS[username])
    ahora = int(time.time()) // 30
    usados = PASOS_USADOS.setdefault(username, set())
    for paso in (ahora, ahora + 1):
        if paso not in usados and all(paso > u for u in usados):
            usados.add(paso)
            return totp.generate_otp(paso)
    return RECUPERACION[username].pop()


def entrar(client, username: str, password: str):
    """Ingreso completo: contraseña → MFA (la configura si hace falta) → cambio de contraseña temporal."""
    password = CLAVES.get(username, password)
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    if r.status_code != 200:
        return r
    paso = r.json()["data"]["paso"]
    if paso == "enrolar_mfa":
        conf = client.post("/api/auth/mfa/configurar").json()["data"]
        SECRETOS[username] = conf["secreto"]
        ahora = int(time.time()) // 30
        PASOS_USADOS[username] = {ahora}
        r = client.post("/api/auth/mfa/activar", json={"codigo": pyotp.TOTP(conf["secreto"]).generate_otp(ahora)})
        RECUPERACION[username] = r.json()["data"]["codigos_recuperacion"]
    elif paso == "mfa":
        r = client.post("/api/auth/mfa/verificar", json={"codigo": _codigo(username)})
    if r.status_code == 200 and r.json()["data"]["sesion"]["debe_cambiar_password"]:
        nueva = f"{password}-n1"
        assert client.post("/api/auth/cambiar-password", json={"actual": password, "nueva": nueva}).status_code == 200
        CLAVES[username] = nueva
    return r


@pytest.fixture(autouse=True)
def _limpiar_estado_mfa():
    for d in (SECRETOS, RECUPERACION, PASOS_USADOS, CLAVES):
        d.clear()


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with Session() as session:
        seed(session)
    limitador.reiniciar()
    yield Session
    engine.dispose()


@pytest.fixture
def client(db):
    def override():
        with db() as s:
            yield s

    app.dependency_overrides[get_db] = override
    with TestClient(app, headers=CSRF) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def admin(client):
    r = entrar(client, "admin", "admin-clave-123")
    assert r.status_code == 200, r.text
    return client


def xlsx(filas: list[list[object]]) -> bytes:
    """Construye un .xlsx en memoria con las filas dadas."""
    buf = BytesIO()
    libro = xlsxwriter.Workbook(buf, {"in_memory": True})
    hoja = libro.add_worksheet()
    for i, fila in enumerate(filas):
        for j, valor in enumerate(fila):
            if valor is not None:
                hoja.write(i, j, valor)
    libro.close()
    return buf.getvalue()


def archivo(contenido: bytes, nombre: str = "archivo.xlsx"):
    return {"archivo": (nombre, contenido, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
