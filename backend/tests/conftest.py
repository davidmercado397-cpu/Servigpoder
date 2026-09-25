import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "admin-clave-123"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.main import app
from app.seed import seed


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with Session() as session:
        seed(session)
    yield Session
    engine.dispose()


@pytest.fixture
def client(db):
    def override():
        with db() as s:
            yield s

    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def admin(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin-clave-123"})
    assert r.status_code == 200
    return client
