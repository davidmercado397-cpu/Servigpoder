from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, Time, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.maestros import Puesto

BORRADOR = "borrador"
APROBADO = "aprobado"
CERRADO = "cerrado"

# Días en máscara de bits: lunes = bit 0 ... domingo = bit 6 (igual que date.weekday())
TODOS_LOS_DIAS = 0b1111111


class MatrizPeriodo(Base):
    """Matriz comercial de un mes: lo que se vendió por puesto."""

    __tablename__ = "matriz_periodo"
    __table_args__ = (UniqueConstraint("anio", "mes"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    anio: Mapped[int] = mapped_column(Integer)
    mes: Mapped[int] = mapped_column(Integer)
    estado: Mapped[str] = mapped_column(String(20), default=BORRADOR)
    proyectado_desde_id: Mapped[int | None] = mapped_column(ForeignKey("matriz_periodo.id"), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    puestos: Mapped[list["MatrizPuesto"]] = relationship(back_populates="periodo", cascade="all, delete-orphan")


class MatrizPuesto(Base):
    __tablename__ = "matriz_puesto"
    __table_args__ = (UniqueConstraint("periodo_id", "puesto_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    periodo_id: Mapped[int] = mapped_column(ForeignKey("matriz_periodo.id", ondelete="CASCADE"))
    puesto_id: Mapped[int] = mapped_column(ForeignKey("puesto.id"))
    hombres: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0)
    secuencia: Mapped[str] = mapped_column(String(80), default="")
    jornada: Mapped[str] = mapped_column(String(300), default="")  # texto original de la matriz
    incluye_festivos: Mapped[bool] = mapped_column(Boolean, default=True)
    requiere_revision: Mapped[bool] = mapped_column(Boolean, default=False)
    nota: Mapped[str] = mapped_column(Text, default="")

    periodo: Mapped[MatrizPeriodo] = relationship(back_populates="puestos")
    puesto: Mapped[Puesto] = relationship(lazy="joined")
    franjas: Mapped[list["MatrizFranja"]] = relationship(
        cascade="all, delete-orphan", order_by="MatrizFranja.inicio", lazy="selectin"
    )
    excepciones: Mapped[list["MatrizExcepcion"]] = relationship(
        cascade="all, delete-orphan", order_by="MatrizExcepcion.fecha", lazy="selectin"
    )


class MatrizFranja(Base):
    """Cobertura vendida: en los días marcados, `cantidad` personas de `inicio` a `fin`."""

    __tablename__ = "matriz_franja"

    id: Mapped[int] = mapped_column(primary_key=True)
    matriz_puesto_id: Mapped[int] = mapped_column(ForeignKey("matriz_puesto.id", ondelete="CASCADE"))
    dias: Mapped[int] = mapped_column(Integer, default=TODOS_LOS_DIAS)
    inicio: Mapped[time] = mapped_column(Time)
    fin: Mapped[time] = mapped_column(Time)  # fin <= inicio: termina al día siguiente
    cantidad: Mapped[int] = mapped_column(Integer, default=1)


class MatrizExcepcion(Base):
    """Ajuste de un día puntual: sin servicio, o una franja adicional."""

    __tablename__ = "matriz_excepcion"

    id: Mapped[int] = mapped_column(primary_key=True)
    matriz_puesto_id: Mapped[int] = mapped_column(ForeignKey("matriz_puesto.id", ondelete="CASCADE"))
    fecha: Mapped[date] = mapped_column(Date)
    sin_servicio: Mapped[bool] = mapped_column(Boolean, default=False)
    inicio: Mapped[time | None] = mapped_column(Time, nullable=True)
    fin: Mapped[time | None] = mapped_column(Time, nullable=True)
    cantidad: Mapped[int] = mapped_column(Integer, default=1)
    observacion: Mapped[str] = mapped_column(String(300), default="")
