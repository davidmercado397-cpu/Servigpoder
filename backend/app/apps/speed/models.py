"""Nómina Speed: empleados (desde el Excel «Listado»), quincenas, novedades por persona, liquidación y descuentos.

Las tablas viven en el esquema de cada empresa (BaseEmpresa); este desarrollo se habilita solo para Speed.
"""

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import BaseEmpresa

ABIERTO, CERRADO = "abierto", "cerrado"
# Descuentos: lo que se le quita (embargos, préstamos, cuotas por mayores valores pagados) y lo que se le paga de más
EMBARGO, PRESTAMO, CUOTA, ADICIONAL = "embargo", "prestamo", "cuota", "adicional"
TIPOS_DESCUENTO = {EMBARGO: "Embargo", PRESTAMO: "Préstamo", CUOTA: "Cuota por mayor valor pagado",
                   ADICIONAL: "Pago adicional por menor valor pagado"}


class SpdEmpleado(BaseEmpresa):
    """Un colaborador con sus valores mensuales. Lo actualiza la importación del Listado."""

    __tablename__ = "spd_empleado"

    id: Mapped[int] = mapped_column(primary_key=True)
    cedula: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(160))
    fecha_ingreso: Mapped[date | None] = mapped_column(Date, nullable=True)
    tipo_contrato: Mapped[str] = mapped_column(String(40), default="")
    grupo: Mapped[str] = mapped_column(String(40), default="")  # «TIPO DE NOMINA» del Listado (GENERAL, SANDRA…)
    cargo: Mapped[str] = mapped_column(String(120), default="")
    area: Mapped[str] = mapped_column(String(80), default="")
    puesto: Mapped[str] = mapped_column(String(120), default="")
    cliente: Mapped[str] = mapped_column(String(160), default="")
    tipo_turno: Mapped[str] = mapped_column(String(120), default="")
    # Valores mensuales
    salario: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    auxilio_listado: Mapped[float] = mapped_column(Numeric(14, 2), default=0)  # el del Excel (informativo: se calcula)
    horas_extras: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    comisiones: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    ley_2466: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    bonificaciones: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    rodamiento: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    nota: Mapped[str] = mapped_column(String(300), default="")  # la columna de texto del Listado (qué es el auxilio)
    # Columna V: los variables se pagan ÷ 30 × días con programación
    aplica_programacion: Mapped[bool] = mapped_column(Boolean, default=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SpdParametro(BaseEmpresa):
    __tablename__ = "spd_parametro"

    clave: Mapped[str] = mapped_column(String(40), primary_key=True)
    valor: Mapped[float] = mapped_column(Numeric(16, 4))
    nombre: Mapped[str] = mapped_column(String(160))
    ayuda: Mapped[str] = mapped_column(String(300), default="")
    orden: Mapped[int] = mapped_column(Integer, default=0)


class SpdPeriodo(BaseEmpresa):
    """Una quincena (comercial: 1–15 y 16–30)."""

    __tablename__ = "spd_periodo"
    __table_args__ = (UniqueConstraint("anio", "mes", "quincena", name="uq_spd_periodo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    anio: Mapped[int] = mapped_column(Integer)
    mes: Mapped[int] = mapped_column(Integer)
    quincena: Mapped[int] = mapped_column(Integer)
    estado: Mapped[str] = mapped_column(String(10), default=ABIERTO)
    parametros: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # con los que se liquidó la última vez
    calculado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    creado_por: Mapped[int | None] = mapped_column(Integer, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    novedades: Mapped[list["SpdNovedad"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)
    liquidaciones: Mapped[list["SpdLiquidacion"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)


class SpdNovedad(BaseEmpresa):
    """Días de la quincena de una persona: programados, tiempos no laborados e incapacidad."""

    __tablename__ = "spd_novedad"
    __table_args__ = (UniqueConstraint("periodo_id", "empleado_id", name="uq_spd_novedad"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    periodo_id: Mapped[int] = mapped_column(ForeignKey("spd_periodo.id", ondelete="CASCADE"), index=True)
    empleado_id: Mapped[int] = mapped_column(ForeignKey("spd_empleado.id", ondelete="CASCADE"), index=True)
    # Vacío = toda la quincena (desde la fecha de ingreso); lo llena el archivo de programación o se digita
    dias_programados: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    ausencias: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    licencias: Mapped[float] = mapped_column(Numeric(5, 2), default=0)  # no remuneradas
    suspensiones: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    desprogramados: Mapped[float] = mapped_column(Numeric(5, 2), default=0)  # renuncia (RUN) y desprogramado (DESPR)
    # Pagan salario pero no auxilio ni variables
    permisos_remunerados: Mapped[float] = mapped_column(Numeric(5, 2), default=0)  # PR, CD, LUT, DDF, LYM
    vacaciones: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    incapacidad: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    turnos_tad: Mapped[int] = mapped_column(Integer, default=0)  # turnos adicionales (se pagan aparte)
    turnos_tan: Mapped[int] = mapped_column(Integer, default=0)
    sin_programacion: Mapped[float] = mapped_column(Numeric(5, 2), default=0)  # días sin código en la programación
    # Códigos por día, puestos, tramos de incapacidad y avisos del archivo de programación (el archivo no se guarda)
    programacion: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Días que ya llevaba la misma incapacidad antes de esta quincena (para saber desde cuándo va al 66,67 %)
    incapacidad_previos: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    observacion: Mapped[str] = mapped_column(String(300), default="")
    origen: Mapped[str] = mapped_column(String(20), default="manual")  # manual | plantilla | programacion

    empleado: Mapped[SpdEmpleado] = relationship(lazy="joined")


class SpdLiquidacion(BaseEmpresa):
    """Resultado de una persona en la quincena (queda congelado al cerrar)."""

    __tablename__ = "spd_liquidacion"
    __table_args__ = (UniqueConstraint("periodo_id", "empleado_id", name="uq_spd_liquidacion"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    periodo_id: Mapped[int] = mapped_column(ForeignKey("spd_periodo.id", ondelete="CASCADE"), index=True)
    empleado_id: Mapped[int] = mapped_column(ForeignKey("spd_empleado.id", ondelete="CASCADE"), index=True)
    devengado: Mapped[float] = mapped_column(Numeric(16, 2), default=0)
    deducciones: Mapped[float] = mapped_column(Numeric(16, 2), default=0)
    neto: Mapped[float] = mapped_column(Numeric(16, 2), default=0)
    detalle: Mapped[dict] = mapped_column(JSON, default=dict)  # conceptos, días, empleado y alertas

    empleado: Mapped[SpdEmpleado] = relationship(lazy="joined")


class SpdDescuento(BaseEmpresa):
    """Préstamo, embargo, cuota por mayor valor pagado o pago adicional: una cuota por quincena hasta agotar el total."""

    __tablename__ = "spd_descuento"

    id: Mapped[int] = mapped_column(primary_key=True)
    empleado_id: Mapped[int] = mapped_column(ForeignKey("spd_empleado.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(12))
    descripcion: Mapped[str] = mapped_column(String(300), default="")
    valor_total: Mapped[float | None] = mapped_column(Numeric(16, 2), nullable=True)  # vacío = sin tope (embargo)
    cuota: Mapped[float] = mapped_column(Numeric(16, 2))  # por quincena
    salarial: Mapped[bool] = mapped_column(Boolean, default=True)  # pagos adicionales: entra a salud y pensión
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_por: Mapped[int | None] = mapped_column(Integer, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    empleado: Mapped[SpdEmpleado] = relationship(lazy="joined")
    aplicaciones: Mapped[list["SpdDescuentoAplicado"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)


class SpdDescuentoAplicado(BaseEmpresa):
    """Lo que se aplicó de un descuento en una quincena (se rehace al recalcular una quincena abierta)."""

    __tablename__ = "spd_descuento_aplicado"
    __table_args__ = (UniqueConstraint("descuento_id", "periodo_id", name="uq_spd_desc_aplicado"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    descuento_id: Mapped[int] = mapped_column(ForeignKey("spd_descuento.id", ondelete="CASCADE"), index=True)
    periodo_id: Mapped[int] = mapped_column(ForeignKey("spd_periodo.id", ondelete="CASCADE"), index=True)
    valor: Mapped[float] = mapped_column(Numeric(16, 2))
    nota: Mapped[str] = mapped_column(Text, default="")
