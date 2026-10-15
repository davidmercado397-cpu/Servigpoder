"""Planos SIESA: catálogos editables, alias, correcciones manuales y salario mínimo por año.

Los planos que se suben NO se guardan: se procesan en memoria y se devuelven. Aquí solo vive la configuración.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import BaseEmpresa as Base
from app.models import Usuario


class PlanoEntidad(Base):
    """Catálogos de SIESA para el plano de contratos: BANCOS, AFP, EPS, CESANTIAS, CAJAS y CARGOS."""

    __tablename__ = "plano_entidad"

    catalogo: Mapped[str] = mapped_column(String(20), primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), primary_key=True)
    descripcion: Mapped[str] = mapped_column(String(200))
    observacion: Mapped[str] = mapped_column(String(200), default="", server_default="")


class PlanoAlias(Base):
    """Texto que llega en el plano → código. catalogo: DEPARTAMENTO, CIUDAD o un catálogo de entidades.
    País y departamento acotan los alias DANE (una ciudad solo se busca dentro de su departamento)."""

    __tablename__ = "plano_alias"
    __table_args__ = (UniqueConstraint("catalogo", "pais", "departamento", "texto", name="uq_plano_alias"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    catalogo: Mapped[str] = mapped_column(String(20), index=True)
    pais: Mapped[str] = mapped_column(String(3), default="", server_default="")
    departamento: Mapped[str] = mapped_column(String(2), default="", server_default="")
    texto: Mapped[str] = mapped_column(String(120))  # normalizado: mayúsculas, sin tildes ni signos
    codigo: Mapped[str] = mapped_column(String(20))
    nota: Mapped[str] = mapped_column(String(200), default="", server_default="")
    creado_por: Mapped[int | None] = mapped_column(ForeignKey(Usuario.id, ondelete="SET NULL"), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PlanoCorreccion(Base):
    """Valor que dicta el usuario para una cédula y columna (no por fila: al borrar filas las posiciones se corren)."""

    __tablename__ = "plano_correccion"
    __table_args__ = (UniqueConstraint("plano", "cedula", "columna", name="uq_plano_correccion"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    plano: Mapped[str] = mapped_column(String(12))  # empleados | contratos
    cedula: Mapped[str] = mapped_column(String(20), index=True)
    columna: Mapped[str] = mapped_column(String(3))
    valor: Mapped[str] = mapped_column(String(120))
    nota: Mapped[str] = mapped_column(String(200), default="", server_default="")
    creado_por: Mapped[int | None] = mapped_column(ForeignKey(Usuario.id, ondelete="SET NULL"), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PlanoSalarioMinimo(Base):
    __tablename__ = "plano_salario_minimo"

    anio: Mapped[int] = mapped_column(Integer, primary_key=True)
    valor: Mapped[int] = mapped_column(BigInteger)
