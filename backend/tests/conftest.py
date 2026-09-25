import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "admin-clave-123"

from io import BytesIO

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
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin-clave-123"})
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
