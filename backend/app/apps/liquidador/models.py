"""Modelos del Liquidador de horas. Todas las tablas llevan el prefijo `liq_`."""

from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Time, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models import Usuario  # noqa: F401  (tabla referenciada por cerrado_por)

HORAS = Numeric(5, 2)

# Estados de una quincena
BORRADOR = "borrador"  # creada, sin Excel cargado
CALCULADA = "calculada"  # con Excel cargado y horas contadas
CERRADA = "cerrada"  # aprobada: no se puede volver a cargar ni recalcular


class LiqParametros(Base):
    """Fila única (id = 1) con los parámetros que usa el conteo."""

    __tablename__ = "liq_parametros"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    # Hora (0-23) en que empieza lo nocturno; lo diurno va de 06:00 a esta hora
    hora_inicio_nocturna: Mapped[int] = mapped_column(Integer, default=19)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class LiqTurno(Base):
    """Plantilla de turno. La matriz de 12 conceptos × 8 tipos de día se calcula de las horas
    ordinarias, las extras, la hora de inicio y la hora nocturna; la hora fin es informativa."""

    __tablename__ = "liq_turno"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(8), unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(80))
    hora_inicio: Mapped[time] = mapped_column(Time)
    hora_fin: Mapped[time] = mapped_column(Time)
    horas_ordinarias: Mapped[Decimal] = mapped_column(HORAS, default=Decimal("0"))
    horas_extras: Mapped[Decimal] = mapped_column(HORAS, default=Decimal("0"))
    matriz: Mapped[dict] = mapped_column(JSON, default=dict)
    # Día remunerado (Z sí, L no). Informativo mientras no se calculen salarios.
    remunerado: Mapped[bool] = mapped_column(Boolean, default=True)
    # Incapacidad: se cuenta aparte, nunca genera horas
    incapacidad: Mapped[bool] = mapped_column(Boolean, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LiqFestivoAjuste(Base):
    """Ajuste manual sobre los festivos nacionales: agrega (es_festivo) o quita una fecha."""

    __tablename__ = "liq_festivo_ajuste"

    id: Mapped[int] = mapped_column(primary_key=True)
    fecha: Mapped[date] = mapped_column(Date, unique=True, index=True)
    es_festivo: Mapped[bool] = mapped_column(Boolean)
    descripcion: Mapped[str | None] = mapped_column(String(120), nullable=True)


class LiqEmpleado(Base):
    """Se crea o actualiza automáticamente al cargar el Excel de cada quincena."""

    __tablename__ = "liq_empleado"

    id: Mapped[int] = mapped_column(primary_key=True)
    documento: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(200))
    cargo: Mapped[str] = mapped_column(String(80), default="Vigilante")


class LiqPeriodo(Base):
    __tablename__ = "liq_periodo"
    __table_args__ = (UniqueConstraint("anio", "mes", "quincena"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    anio: Mapped[int] = mapped_column(Integer, index=True)
    mes: Mapped[int] = mapped_column(Integer)
    quincena: Mapped[int] = mapped_column(Integer)  # 1: días 1-15, 2: 16 a fin de mes
    desde: Mapped[date] = mapped_column(Date)
    hasta: Mapped[date] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(String(20), default=BORRADOR)
    archivo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    advertencias: Mapped[list] = mapped_column(JSON, default=list)
    cargado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    calculado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cerrado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cerrado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    dias: Mapped[list["LiqDia"]] = relationship(back_populates="periodo", cascade="all, delete-orphan", passive_deletes=True)
    resultados: Mapped[list["LiqResultado"]] = relationship(back_populates="periodo", cascade="all, delete-orphan", passive_deletes=True)


class LiqDia(Base):
    """Un día de un empleado: el turno cargado y las horas por concepto que generó."""

    __tablename__ = "liq_dia"
    __table_args__ = (UniqueConstraint("periodo_id", "empleado_id", "fecha"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    periodo_id: Mapped[int] = mapped_column(ForeignKey("liq_periodo.id", ondelete="CASCADE"), index=True)
    empleado_id: Mapped[int] = mapped_column(ForeignKey("liq_empleado.id"), index=True)
    fecha: Mapped[date] = mapped_column(Date)
    turno_id: Mapped[int] = mapped_column(ForeignKey("liq_turno.id"))
    codigo: Mapped[str] = mapped_column(String(8))  # código tal como se cargó
    tipo_dia: Mapped[str] = mapped_column(String(24), default="")  # columna de la matriz (weekday, sunday…)
    clase: Mapped[str] = mapped_column(String(20), default="")  # trabajado, descanso_pago, libre, ausencia…
    horas: Mapped[dict] = mapped_column(JSON, default=dict)  # {concepto: horas} solo los que aplican

    periodo: Mapped[LiqPeriodo] = relationship(back_populates="dias")
    empleado: Mapped[LiqEmpleado] = relationship(lazy="joined")
    turno: Mapped[LiqTurno] = relationship(lazy="joined")


class LiqResultado(Base):
    """Totales de un empleado en la quincena: horas por concepto y conteo de días."""

    __tablename__ = "liq_resultado"
    __table_args__ = (UniqueConstraint("periodo_id", "empleado_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    periodo_id: Mapped[int] = mapped_column(ForeignKey("liq_periodo.id", ondelete="CASCADE"), index=True)
    empleado_id: Mapped[int] = mapped_column(ForeignKey("liq_empleado.id"), index=True)
    horas: Mapped[dict] = mapped_column(JSON, default=dict)  # 12 conceptos
    dias: Mapped[dict] = mapped_column(JSON, default=dict)  # trabajado, descanso_pago, libre, ausencia, incapacidad, novedad
    total_horas: Mapped[Decimal] = mapped_column(Numeric(7, 2), default=Decimal("0"))

    periodo: Mapped[LiqPeriodo] = relationship(back_populates="resultados")
    empleado: Mapped[LiqEmpleado] = relationship(lazy="joined")
