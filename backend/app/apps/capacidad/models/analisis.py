from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.apps.capacidad.models.maestros import Puesto

# Estado de un puesto en un día
OK = "ok"
HUECO = "hueco"  # horas vendidas sin nadie programado
EXCESO = "exceso"  # más personas programadas que las vendidas
MIXTO = "mixto"  # huecos y excesos el mismo día (p. ej. 2 de día, 0 de noche)
SIN_SERVICIO = "sin_servicio"  # no se vendió cobertura ese día y no hay programación


class Analisis(Base):
    """Resultado del cruce vendido (matriz) vs programado (carga de SIESA)."""

    __tablename__ = "analisis"

    id: Mapped[int] = mapped_column(primary_key=True)
    carga_id: Mapped[int] = mapped_column(ForeignKey("programacion_carga.id", ondelete="CASCADE"), index=True)
    periodo_id: Mapped[int] = mapped_column(ForeignKey("matriz_periodo.id", ondelete="CASCADE"), index=True)
    generado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True)
    resumen: Mapped[dict] = mapped_column(JSON, default=dict)

    puestos: Mapped[list["AnalisisPuesto"]] = relationship(cascade="all, delete-orphan")


class AnalisisPuesto(Base):
    __tablename__ = "analisis_puesto"

    id: Mapped[int] = mapped_column(primary_key=True)
    analisis_id: Mapped[int] = mapped_column(ForeignKey("analisis.id", ondelete="CASCADE"), index=True)
    puesto_id: Mapped[int] = mapped_column(ForeignKey("puesto.id"), index=True)
    hombres: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0)
    fijos: Mapped[int] = mapped_column(Integer, default=0)  # titulares: su puesto principal del mes es este
    personas: Mapped[int] = mapped_column(Integer, default=0)  # personas distintas con al menos un turno
    horas_requeridas: Mapped[Decimal] = mapped_column(Numeric(9, 1), default=0)
    horas_programadas: Mapped[Decimal] = mapped_column(Numeric(9, 1), default=0)
    horas_descubiertas: Mapped[Decimal] = mapped_column(Numeric(9, 1), default=0)
    horas_exceso: Mapped[Decimal] = mapped_column(Numeric(9, 1), default=0)
    dias_hueco: Mapped[int] = mapped_column(Integer, default=0)
    dias_exceso: Mapped[int] = mapped_column(Integer, default=0)
    estado: Mapped[str] = mapped_column(String(20), default=OK)

    puesto: Mapped[Puesto] = relationship(lazy="joined")
    dias: Mapped[list["AnalisisDia"]] = relationship(cascade="all, delete-orphan", order_by="AnalisisDia.fecha")


class AnalisisDia(Base):
    __tablename__ = "analisis_dia"

    id: Mapped[int] = mapped_column(primary_key=True)
    analisis_puesto_id: Mapped[int] = mapped_column(ForeignKey("analisis_puesto.id", ondelete="CASCADE"), index=True)
    fecha: Mapped[date] = mapped_column(Date)
    horas_requeridas: Mapped[Decimal] = mapped_column(Numeric(6, 1), default=0)
    horas_programadas: Mapped[Decimal] = mapped_column(Numeric(6, 1), default=0)
    horas_descubiertas: Mapped[Decimal] = mapped_column(Numeric(6, 1), default=0)
    horas_exceso: Mapped[Decimal] = mapped_column(Numeric(6, 1), default=0)
    estado: Mapped[str] = mapped_column(String(20), default=OK)
    # [{"inicio": "18:00", "fin": "06:00", "tipo": "hueco"|"exceso", "personas": n}]
    detalle: Mapped[list] = mapped_column(JSON, default=list)
