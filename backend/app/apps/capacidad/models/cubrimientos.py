from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.apps.capacidad.models.maestros import Puesto

# Motivo detectado automáticamente
MOTIVO_NOVEDAD = "novedad"  # un titular del puesto tiene novedad ese día (VAC, IEG, IND…)
MOTIVO_DESCANSO = "descanso"  # relevo del día de descanso de un titular
MOTIVO_SIN = "sin_motivo"  # no se encontró razón: nómina debe revisar

# Estado del cubrimiento
JUSTIFICADO = "justificado"  # justificado automáticamente
PENDIENTE = "pendiente"  # requiere revisión de nómina
APROBADO = "aprobado"
RECHAZADO = "rechazado"


class Cubrimiento(Base):
    """Turno de una persona en un puesto que no es el suyo (no es titular).

    Se regenera con cada análisis; la decisión de nómina vive aparte
    (`CubrimientoDecision`) para no perderse al recalcular.
    """

    __tablename__ = "cubrimiento"

    id: Mapped[int] = mapped_column(primary_key=True)
    analisis_id: Mapped[int] = mapped_column(ForeignKey("analisis.id", ondelete="CASCADE"), index=True)
    puesto_id: Mapped[int] = mapped_column(ForeignKey("puesto.id"), index=True)
    fecha: Mapped[date] = mapped_column(Date, index=True)
    cedula: Mapped[str] = mapped_column(String(30), index=True)
    nombre: Mapped[str] = mapped_column(String(200))
    codigo_turno: Mapped[str] = mapped_column(String(40))
    horas: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=0)
    puesto_titular: Mapped[str | None] = mapped_column(String(30), nullable=True)
    motivo: Mapped[str] = mapped_column(String(20))
    # [{"cedula", "nombre", "codigo"}] de los titulares con novedad o descanso
    referencia: Mapped[list] = mapped_column(JSON, default=list)
    genera_exceso: Mapped[bool] = mapped_column(Boolean, default=False)
    doble_turno: Mapped[bool] = mapped_column(Boolean, default=False)
    estado_auto: Mapped[str] = mapped_column(String(20))

    puesto: Mapped[Puesto] = relationship(lazy="joined")


class CubrimientoDecision(Base):
    """Aprobación o rechazo de nómina, identificado por mes, persona, puesto y día."""

    __tablename__ = "cubrimiento_decision"
    __table_args__ = (UniqueConstraint("anio", "mes", "cedula", "puesto_id", "fecha"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    anio: Mapped[int] = mapped_column(Integer)
    mes: Mapped[int] = mapped_column(Integer)
    cedula: Mapped[str] = mapped_column(String(30))
    puesto_id: Mapped[int] = mapped_column(ForeignKey("puesto.id"))
    fecha: Mapped[date] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(String(20))  # aprobado | rechazado
    comentario: Mapped[str] = mapped_column(Text, default="")
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True)
    decidido_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Parametro(Base):
    """Parámetros configurables del sistema (umbrales de alertas)."""

    __tablename__ = "parametro"

    clave: Mapped[str] = mapped_column(String(60), primary_key=True)
    valor: Mapped[str] = mapped_column(String(200))
    descripcion: Mapped[str] = mapped_column(String(300), default="")
