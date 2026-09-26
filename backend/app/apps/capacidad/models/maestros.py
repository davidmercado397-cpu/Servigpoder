from datetime import time

from sqlalchemy import Boolean, ForeignKey, Integer, String, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

# Tipos de puesto
OPERATIVO = "operativo"
BOLSA = "bolsa"  # 05 disponibles, 06 relevantes, 07 incapacitados, 08 vacaciones

# Clases de código de programación
TRABAJO = "trabajo"
DESCANSO = "descanso"


class Ubicacion(Base):
    """PODER principal: el sitio del cliente."""

    __tablename__ = "ubicacion"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    nombre: Mapped[str] = mapped_column(String(200))
    nit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    ciudad: Mapped[str | None] = mapped_column(String(80), nullable=True)

    puestos: Mapped[list["Puesto"]] = relationship(back_populates="ubicacion")


class Puesto(Base):
    """PODER interno: el puesto de trabajo dentro de la ubicación."""

    __tablename__ = "puesto"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    ubicacion_id: Mapped[int] = mapped_column(ForeignKey("ubicacion.id"))
    descripcion: Mapped[str] = mapped_column(String(200), default="")
    tipo: Mapped[str] = mapped_column(String(20), default=OPERATIVO)
    # Escoltas, coordinadores, supervisores: fuera del control en el alcance 1
    excluido: Mapped[bool] = mapped_column(Boolean, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    ubicacion: Mapped[Ubicacion] = relationship(back_populates="puestos", lazy="joined")


class PuestoEquivalencia(Base):
    """Código de puesto tal como llega en el Excel de SIESA → puesto del maestro."""

    __tablename__ = "puesto_equivalencia"

    codigo_siesa: Mapped[str] = mapped_column(String(40), primary_key=True)
    puesto_id: Mapped[int] = mapped_column(ForeignKey("puesto.id", ondelete="CASCADE"))
    # exacta | aproximada (verificar) | manual
    origen: Mapped[str] = mapped_column(String(20))

    puesto: Mapped[Puesto] = relationship(lazy="joined")


class Turno(Base):
    """Horario configurado en SIESA (GenConsultaMaestroGrid)."""

    __tablename__ = "turno"

    codigo: Mapped[str] = mapped_column(String(40), primary_key=True)
    descripcion: Mapped[str] = mapped_column(String(200), default="")
    clase: Mapped[str] = mapped_column(String(20), default=TRABAJO)

    franjas: Mapped[list["TurnoFranja"]] = relationship(
        cascade="all, delete-orphan", order_by="TurnoFranja.orden", lazy="selectin"
    )


class TurnoFranja(Base):
    __tablename__ = "turno_franja"

    id: Mapped[int] = mapped_column(primary_key=True)
    turno_codigo: Mapped[str] = mapped_column(ForeignKey("turno.codigo", ondelete="CASCADE"))
    orden: Mapped[int] = mapped_column(Integer, default=0)
    inicio: Mapped[time] = mapped_column(Time)
    fin: Mapped[time] = mapped_column(Time)  # fin <= inicio: termina al día siguiente


class Novedad(Base):
    """Código de ausencia: la persona no trabaja y el puesto debe cubrirse."""

    __tablename__ = "novedad"

    codigo: Mapped[str] = mapped_column(String(40), primary_key=True)
    descripcion: Mapped[str] = mapped_column(String(200))
    requiere_cubrimiento: Mapped[bool] = mapped_column(Boolean, default=True)
