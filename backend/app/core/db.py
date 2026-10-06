from collections.abc import Iterator

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Tablas del núcleo (usuarios, roles, empresas, auditoría): esquema public, compartidas."""


# Esquema simbólico de las tablas de los desarrollos. En cada petición se traduce al esquema de la
# empresa elegida (emp_servigpoder, emp_sera…), así los datos de una empresa nunca se mezclan con otra.
ESQUEMA_EMPRESA = "empresa"


class BaseEmpresa(DeclarativeBase):
    """Tablas de los desarrollos: cada empresa tiene su propio juego en su esquema."""

    metadata = MetaData(schema=ESQUEMA_EMPRESA)


def traduccion(esquema: str) -> dict:
    return {"schema_translate_map": {ESQUEMA_EMPRESA: esquema}}


engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
