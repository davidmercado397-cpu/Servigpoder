from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.maestros import Puesto

# Clase de cada celda día
NOVEDAD = "novedad"
DESCONOCIDO = "desconocido"


class ProgramacionCarga(Base):
    """Una exportación de SIESA subida al sistema. Cada carga es una foto completa."""

    __tablename__ = "programacion_carga"

    id: Mapped[int] = mapped_column(primary_key=True)
    archivo: Mapped[str] = mapped_column(String(255))
    compania: Mapped[str] = mapped_column(String(200), default="")
    desde: Mapped[date] = mapped_column(Date)
    hasta: Mapped[date] = mapped_column(Date)
    anio: Mapped[int] = mapped_column(Integer, index=True)
    mes: Mapped[int] = mapped_column(Integer, index=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    cargado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resumen: Mapped[dict] = mapped_column(JSON, default=dict)

    filas: Mapped[list["ProgramacionFila"]] = relationship(cascade="all, delete-orphan", back_populates="carga")


class ProgramacionFila(Base):
    """Una fila del Excel: un empleado en un puesto."""

    __tablename__ = "programacion_fila"

    id: Mapped[int] = mapped_column(primary_key=True)
    carga_id: Mapped[int] = mapped_column(ForeignKey("programacion_carga.id", ondelete="CASCADE"), index=True)
    cedula: Mapped[str] = mapped_column(String(30), index=True)
    nombre: Mapped[str] = mapped_column(String(200))
    ubicacion_siesa: Mapped[str] = mapped_column(String(40), default="")
    ubicacion_nombre: Mapped[str] = mapped_column(String(200), default="")
    puesto_siesa: Mapped[str] = mapped_column(String(40))
    puesto_descripcion: Mapped[str] = mapped_column(String(300), default="")
    puesto_id: Mapped[int | None] = mapped_column(ForeignKey("puesto.id"), nullable=True, index=True)
    centro_operacion: Mapped[str] = mapped_column(String(120), default="")
    cliente: Mapped[str] = mapped_column(String(200), default="")

    carga: Mapped[ProgramacionCarga] = relationship(back_populates="filas")
    puesto: Mapped[Puesto | None] = relationship()
    dias: Mapped[list["ProgramacionDia"]] = relationship(cascade="all, delete-orphan")


class ProgramacionDia(Base):
    __tablename__ = "programacion_dia"

    id: Mapped[int] = mapped_column(primary_key=True)
    fila_id: Mapped[int] = mapped_column(ForeignKey("programacion_fila.id", ondelete="CASCADE"), index=True)
    fecha: Mapped[date] = mapped_column(Date)
    codigo: Mapped[str] = mapped_column(String(40))  # tal como viene de SIESA, sin corchetes
    clase: Mapped[str] = mapped_column(String(20))  # trabajo | descanso | novedad | desconocido
