"""Modelos del Liquidador de horas. Todas las tablas llevan el prefijo `liq_`."""

from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, LargeBinary, Numeric, String, Text, Time, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import BaseEmpresa as Base
from app.models import Usuario

HORAS = Numeric(5, 2)

# Estados de una quincena
BORRADOR = "borrador"  # creada, sin Excel cargado
CALCULADA = "calculada"  # con Excel cargado y horas contadas
CERRADA = "cerrada"  # aprobada: no se puede volver a cargar ni recalcular
MENSUAL = 0  # valor de `quincena` para un periodo de mes completo


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
    # Novedad justificada: con el umbral semanal activo, cada día con este código baja el umbral de la semana
    justifica_umbral: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Código de vacaciones (V): sus días se liquidan como vacaciones en días hábiles y no hábiles
    vacaciones: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LiqFestivoAjuste(Base):
    """Ajuste manual sobre los festivos nacionales: agrega (es_festivo) o quita una fecha."""

    __tablename__ = "liq_festivo_ajuste"

    id: Mapped[int] = mapped_column(primary_key=True)
    fecha: Mapped[date] = mapped_column(Date, unique=True, index=True)
    es_festivo: Mapped[bool] = mapped_column(Boolean)
    descripcion: Mapped[str | None] = mapped_column(String(120), nullable=True)


# SERA no tiene vigilantes: quien llega sin cargo en el Excel queda como operario de aseo
CARGO_DEFECTO = "Operario de aseo"


class LiqEmpleado(Base):
    """Se crea o actualiza automáticamente al cargar el Excel de cada quincena."""

    __tablename__ = "liq_empleado"

    id: Mapped[int] = mapped_column(primary_key=True)
    documento: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(200))
    cargo: Mapped[str] = mapped_column(String(80), default=CARGO_DEFECTO)
    # Salario mensual propio; vacío = el salario mínimo vigente en cada fecha (así se crean todos)
    salario: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    # Días hábiles para vacaciones (0 = lunes … 6 = domingo); los festivos nunca son hábiles
    dias_habiles: Mapped[str] = mapped_column(String(7), default="012345", server_default="012345")
    # Saldo de vacaciones (15 días hábiles por año): fecha de ingreso y días hábiles disfrutados antes del liquidador
    fecha_ingreso: Mapped[date | None] = mapped_column(Date, nullable=True)
    vacaciones_previas: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0"), server_default="0")
    # Clase de riesgo ARL (1 a 5), configurada en Empleados
    arl_clase: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Saldo del libro de vacaciones: `vacaciones_previas` son los días disfrutados hasta esta fecha; el liquidador
    # cuenta los días de vacaciones (V) posteriores
    vacaciones_corte: Mapped[date | None] = mapped_column(Date, nullable=True)

    # --- Ficha del personal (base de datos de gestión humana; datos personales con su propio permiso) ---
    estado: Mapped[str] = mapped_column(String(10), default="activo", server_default="activo")  # activo | retirado
    fecha_retiro: Mapped[date | None] = mapped_column(Date, nullable=True)
    tipo_personal: Mapped[str | None] = mapped_column(String(20), nullable=True)  # operativo | administrativo
    puesto: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tipo_contrato: Mapped[str | None] = mapped_column(String(40), nullable=True)
    sexo: Mapped[str | None] = mapped_column(String(1), nullable=True)
    fecha_nacimiento: Mapped[date | None] = mapped_column(Date, nullable=True)
    rh: Mapped[str | None] = mapped_column(String(5), nullable=True)
    pais_nacimiento: Mapped[str | None] = mapped_column(String(80), nullable=True)
    depto_nacimiento: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ciudad_nacimiento: Mapped[str | None] = mapped_column(String(80), nullable=True)
    fecha_expedicion: Mapped[date | None] = mapped_column(Date, nullable=True)
    pais_expedicion: Mapped[str | None] = mapped_column(String(80), nullable=True)
    depto_expedicion: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ciudad_expedicion: Mapped[str | None] = mapped_column(String(80), nullable=True)
    estado_civil: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0 ninguno, 1 soltero, 2 casado, 3 viudo, 4 divorciado, 5 unión libre
    extranjero: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    celular: Mapped[str | None] = mapped_column(String(30), nullable=True)
    correo: Mapped[str | None] = mapped_column(String(150), nullable=True)
    direccion: Mapped[str | None] = mapped_column(String(200), nullable=True)
    barrio: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ciudad: Mapped[str | None] = mapped_column(String(80), nullable=True)
    eps: Mapped[str | None] = mapped_column(String(80), nullable=True)
    fondo_pensiones: Mapped[str | None] = mapped_column(String(80), nullable=True)
    pensionado: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    fondo_cesantias: Mapped[str | None] = mapped_column(String(80), nullable=True)
    caja_compensacion: Mapped[str | None] = mapped_column(String(80), nullable=True)
    plan_exequial: Mapped[str | None] = mapped_column(String(80), nullable=True)
    numero_cuenta: Mapped[str | None] = mapped_column(String(40), nullable=True)
    nivel_educativo: Mapped[str | None] = mapped_column(String(60), nullable=True)
    cursos: Mapped[str | None] = mapped_column(Text, nullable=True)


class LiqPeriodo(Base):
    """Una nómina de un periodo: cada periodo (año, mes, quincena) agrupa varias nóminas con nombre (Cliente 1,
    Administrativa…), cada una con su Excel, su cálculo y su cierre."""

    __tablename__ = "liq_periodo"
    __table_args__ = (UniqueConstraint("anio", "mes", "quincena", "nombre", name="uq_liq_periodo_nomina"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    anio: Mapped[int] = mapped_column(Integer, index=True)
    mes: Mapped[int] = mapped_column(Integer)
    quincena: Mapped[int] = mapped_column(Integer)  # 1: días 1-15, 2: 16 a fin de mes, 0: mes completo
    nombre: Mapped[str] = mapped_column(String(80), default="General", server_default="General")
    desde: Mapped[date] = mapped_column(Date)
    hasta: Mapped[date] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(String(20), default=BORRADOR)
    archivo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    advertencias: Mapped[list] = mapped_column(JSON, default=list)
    # Umbral semanal de horas (services/umbral.py): se marca al liquidar y vale para cada carga o recálculo del periodo
    umbral_activo: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    umbral_horas: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("42"), server_default="42")
    umbral_horas_novedad: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=Decimal("7"), server_default="7")
    cargado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    calculado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cerrado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cerrado_por: Mapped[int | None] = mapped_column(ForeignKey(Usuario.id, ondelete="SET NULL"), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    dias: Mapped[list["LiqDia"]] = relationship(back_populates="periodo", cascade="all, delete-orphan", passive_deletes=True)
    resultados: Mapped[list["LiqResultado"]] = relationship(back_populates="periodo", cascade="all, delete-orphan", passive_deletes=True)

    @property
    def tipo(self) -> str:
        return "Mensual" if self.quincena == MENSUAL else f"Q{self.quincena}"

    @property
    def etiqueta(self) -> str:
        """2026-06 Q1 · 2026-06 Mensual"""
        return f"{self.anio}-{self.mes:02d} {self.tipo}"


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
    # Nómina del periodo: valor por concepto, aportes, descuentos y la explicación del cálculo
    nomina: Mapped[dict] = mapped_column(JSON, default=dict)
    # Con el umbral semanal activo: por semana, umbral, horas, extras generadas, pagadas y descontadas
    umbral_semanas: Mapped[list] = mapped_column(JSON, default=list)
    devengado: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    neto: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))

    periodo: Mapped[LiqPeriodo] = relationship(back_populates="resultados")
    empleado: Mapped[LiqEmpleado] = relationship(lazy="joined")


class LiqTarifa(Base):
    """Valores de ley vigentes desde una fecha: salario mínimo, auxilio de transporte, horas del mes,
    aportes del empleado y % de cada recargo y hora extra. Cada día se paga con la tarifa vigente ese día."""

    __tablename__ = "liq_tarifa"

    id: Mapped[int] = mapped_column(primary_key=True)
    vigente_desde: Mapped[date] = mapped_column(Date, unique=True, index=True)
    smlmv: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    auxilio_transporte: Mapped[Decimal] = mapped_column(Numeric(14, 2))  # mensual
    horas_mes: Mapped[int] = mapped_column(Integer, default=210)  # divisor del valor de la hora
    salud_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("4"))
    pension_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("4"))
    # % sobre el valor de la hora por concepto. Recargos: solo el adicional; extras: la hora completa
    porcentajes: Mapped[dict] = mapped_column(JSON, default=dict)
    nota: Mapped[str] = mapped_column(String(300), default="")
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# Tipos de descuento: las cuotas son descuentos periódicos autorizados (plan exequial, pólizas, aportes…)
PRESTAMO = "prestamo"
EMBARGO = "embargo"
CUOTA = "cuota"


class LiqDescuento(Base):
    """Préstamo, embargo o cuota de un empleado: un valor mensual fijo (la quincena descuenta la mitad) o un % del
    devengado sin auxilio de transporte; con monto total, deja de descontar cuando se completa."""

    __tablename__ = "liq_descuento"

    id: Mapped[int] = mapped_column(primary_key=True)
    empleado_id: Mapped[int] = mapped_column(ForeignKey("liq_empleado.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(20))
    descripcion: Mapped[str] = mapped_column(String(200))
    valor_mensual: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    porcentaje: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    monto_total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    desde: Mapped[date] = mapped_column(Date)
    hasta: Mapped[date | None] = mapped_column(Date, nullable=True)
    # En qué quincena aplica: ambas (la mitad en cada una), primera o segunda (el valor completo en esa)
    quincena: Mapped[str] = mapped_column(String(10), default="ambas", server_default="ambas")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    empleado: Mapped[LiqEmpleado] = relationship(lazy="joined")


class LiqAuxilio(Base):
    """Auxilio no prestacional de un empleado (rodamiento, alimentación…): suma al devengado pero no a la base de
    salud y pensión (salvo lo que pase del 40 % de la remuneración, Ley 1393 de 2010). Valor mensual; se descuenta
    en proporción a los días de ausencia del periodo."""

    __tablename__ = "liq_auxilio"

    id: Mapped[int] = mapped_column(primary_key=True)
    empleado_id: Mapped[int] = mapped_column(ForeignKey("liq_empleado.id", ondelete="CASCADE"), index=True)
    descripcion: Mapped[str] = mapped_column(String(200))
    valor_mensual: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    desde: Mapped[date] = mapped_column(Date)
    hasta: Mapped[date | None] = mapped_column(Date, nullable=True)
    quincena: Mapped[str] = mapped_column(String(10), default="ambas", server_default="ambas")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    empleado: Mapped[LiqEmpleado] = relationship(lazy="joined")


class LiqVacacionBase(Base):
    """Promedio variable que nómina fija para las vacaciones de un empleado en un periodo (reemplaza el sugerido)."""

    __tablename__ = "liq_vacacion_base"
    __table_args__ = (UniqueConstraint("periodo_id", "empleado_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    periodo_id: Mapped[int] = mapped_column(ForeignKey("liq_periodo.id", ondelete="CASCADE"), index=True)
    empleado_id: Mapped[int] = mapped_column(ForeignKey("liq_empleado.id", ondelete="CASCADE"))
    promedio: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class LiqCosteo(Base):
    """Costeo de una nómina: lo que costaría a la empresa un Excel de turnos, sin que cuente como pagado. Guarda
    solo el resultado por persona (el Excel no se guarda) y los % de aportes y prestaciones usados."""

    __tablename__ = "liq_costeo"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    anio: Mapped[int] = mapped_column(Integer)
    mes: Mapped[int] = mapped_column(Integer)
    quincena: Mapped[int] = mapped_column(Integer)  # 1, 2 o 0 (mensual), como un periodo
    desde: Mapped[date] = mapped_column(Date)
    hasta: Mapped[date] = mapped_column(Date)
    umbral_activo: Mapped[bool] = mapped_column(Boolean, default=False)
    umbral_horas: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("42"))
    umbral_horas_novedad: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=Decimal("7"))
    # Auxilio no prestacional mensual por persona en el costeo (0 = no aplica)
    auxilio_mensual: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), server_default="0")
    parametros: Mapped[dict] = mapped_column(JSON, default=dict)
    archivo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    advertencias: Mapped[list] = mapped_column(JSON, default=list)
    resultados: Mapped[list] = mapped_column(JSON, default=list)
    totales: Mapped[dict] = mapped_column(JSON, default=dict)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey(Usuario.id, ondelete="SET NULL"), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def tipo(self) -> str:
        return "Mensual" if self.quincena == MENSUAL else f"Q{self.quincena}"

    @property
    def etiqueta(self) -> str:
        return f"{self.anio}-{self.mes:02d} {self.tipo}"


class LiqContrato(Base):
    """Historial laboral: cada vinculación con su inicio y, si terminó, su retiro (hay reintegros)."""

    __tablename__ = "liq_contrato"
    __table_args__ = (UniqueConstraint("empleado_id", "fecha_inicio"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    empleado_id: Mapped[int] = mapped_column(ForeignKey("liq_empleado.id", ondelete="CASCADE"), index=True)
    fecha_inicio: Mapped[date] = mapped_column(Date)
    fecha_retiro: Mapped[date | None] = mapped_column(Date, nullable=True)
    tipo_contrato: Mapped[str | None] = mapped_column(String(40), nullable=True)
    cargo: Mapped[str | None] = mapped_column(String(120), nullable=True)
    puesto: Mapped[str | None] = mapped_column(String(200), nullable=True)
    motivo_retiro: Mapped[str | None] = mapped_column(String(200), nullable=True)
    observacion: Mapped[str | None] = mapped_column(String(300), nullable=True)


class LiqVacacionSalida(Base):
    """Historial de vacaciones (libro de vacaciones o registro manual): disfrutadas o compensadas, ya tomadas o
    programadas. Es informativo: el saldo sale de los días previos al corte y de los días V liquidados después."""

    __tablename__ = "liq_vacacion_salida"

    id: Mapped[int] = mapped_column(primary_key=True)
    empleado_id: Mapped[int] = mapped_column(ForeignKey("liq_empleado.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(15), default="disfrutadas")  # disfrutadas | compensadas
    desde: Mapped[date | None] = mapped_column(Date, nullable=True)
    hasta: Mapped[date | None] = mapped_column(Date, nullable=True)
    retorno: Mapped[date | None] = mapped_column(Date, nullable=True)
    dias_habiles: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estado: Mapped[str] = mapped_column(String(12), default="historico")  # historico | programada | cancelada
    observacion: Mapped[str | None] = mapped_column(String(300), nullable=True)
    origen: Mapped[str] = mapped_column(String(10), default="manual")  # libro | manual
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------- Gestión humana: salud y casos jurídicos (repositorio de consulta; no afecta la nómina) ----------------
# Se registran por documento: la persona puede no estar (o ya no estar) en la base de empleados.

class LiqCie(Base):
    """Catálogo CIE-10 de diagnósticos (datos/cie10.csv)."""

    __tablename__ = "liq_cie"

    codigo: Mapped[str] = mapped_column(String(10), primary_key=True)
    descripcion: Mapped[str] = mapped_column(String(300))


class LiqIncapacidad(Base):
    """Incapacidad o licencia con su diagnóstico CIE. Las prórrogas se encadenan para sumar los días acumulados."""

    __tablename__ = "liq_incapacidad"

    id: Mapped[int] = mapped_column(primary_key=True)
    documento: Mapped[str] = mapped_column(String(32), index=True)
    nombre: Mapped[str] = mapped_column(String(200))
    empleado_id: Mapped[int | None] = mapped_column(ForeignKey("liq_empleado.id", ondelete="SET NULL"), nullable=True, index=True)
    puesto: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # incapacidad | licencia_maternidad | licencia_paternidad | calamidad | otra
    novedad: Mapped[str] = mapped_column(String(30), default="incapacidad")
    # enfermedad_general | accidente_trabajo | enfermedad_laboral | accidente_transito
    origen: Mapped[str | None] = mapped_column(String(20), nullable=True)
    prorroga: Mapped[bool] = mapped_column(Boolean, default=False)
    desde: Mapped[date] = mapped_column(Date, index=True)
    hasta: Mapped[date] = mapped_column(Date)
    dias: Mapped[int] = mapped_column(Integer)
    entidad: Mapped[str | None] = mapped_column(String(80), nullable=True)  # EPS, ARL, SOAT o centro médico
    cie: Mapped[str | None] = mapped_column(String(60), nullable=True)  # uno o varios códigos separados por coma
    diagnostico: Mapped[str | None] = mapped_column(String(300), nullable=True)
    soporte: Mapped[str | None] = mapped_column(String(12), nullable=True)  # fisico | escaneado | virtual
    observacion: Mapped[str | None] = mapped_column(String(300), nullable=True)
    origen_registro: Mapped[str] = mapped_column(String(10), default="manual")  # libro | manual
    creado_por: Mapped[int | None] = mapped_column(ForeignKey(Usuario.id, ondelete="SET NULL"), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LiqRestriccion(Base):
    """Restricción o recomendación médica con su vigencia, o caso de seguimiento (p. ej. oncológico)."""

    __tablename__ = "liq_restriccion"

    id: Mapped[int] = mapped_column(primary_key=True)
    documento: Mapped[str] = mapped_column(String(32), index=True)
    nombre: Mapped[str] = mapped_column(String(200))
    empleado_id: Mapped[int | None] = mapped_column(ForeignKey("liq_empleado.id", ondelete="SET NULL"), nullable=True, index=True)
    puesto: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tipo: Mapped[str] = mapped_column(String(20), default="restriccion")  # restriccion | recomendacion | oncologico
    desde: Mapped[date | None] = mapped_column(Date, nullable=True)
    hasta: Mapped[date | None] = mapped_column(Date, nullable=True)
    cie: Mapped[str | None] = mapped_column(String(60), nullable=True)
    diagnostico: Mapped[str | None] = mapped_column(String(300), nullable=True)
    detalle: Mapped[str | None] = mapped_column(Text, nullable=True)  # qué no puede hacer o qué se recomienda
    observacion: Mapped[str | None] = mapped_column(String(300), nullable=True)
    origen_registro: Mapped[str] = mapped_column(String(10), default="manual")
    creado_por: Mapped[int | None] = mapped_column(ForeignKey(Usuario.id, ondelete="SET NULL"), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LiqCaso(Base):
    """Derecho de petición, tutela, desacato, demanda, orden judicial o queja de acoso laboral, con su seguimiento."""

    __tablename__ = "liq_caso"

    id: Mapped[int] = mapped_column(primary_key=True)
    documento: Mapped[str] = mapped_column(String(32), index=True)
    nombre: Mapped[str] = mapped_column(String(200))
    empleado_id: Mapped[int | None] = mapped_column(ForeignKey("liq_empleado.id", ondelete="SET NULL"), nullable=True, index=True)
    # derecho_peticion | tutela | desacato | demanda | orden_judicial | acoso_laboral | otro
    tipo: Mapped[str] = mapped_column(String(20))
    asunto: Mapped[str] = mapped_column(String(300))  # quién lo envía y de qué se trata
    recibido: Mapped[date] = mapped_column(Date, index=True)
    vence: Mapped[date | None] = mapped_column(Date, nullable=True)
    estado: Mapped[str] = mapped_column(String(12), default="abierto")  # abierto | contestado | cerrado
    contacto: Mapped[str | None] = mapped_column(String(200), nullable=True)  # correo o celular para responder
    observacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    origen_registro: Mapped[str] = mapped_column(String(10), default="manual")
    creado_por: Mapped[int | None] = mapped_column(ForeignKey(Usuario.id, ondelete="SET NULL"), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    actuaciones: Mapped[list["LiqCasoActuacion"]] = relationship(back_populates="caso", cascade="all, delete-orphan",
                                                                 passive_deletes=True, order_by="LiqCasoActuacion.id")


class LiqCasoActuacion(Base):
    """Seguimiento de un caso: cada contestación o gestión con su fecha y medio."""

    __tablename__ = "liq_caso_actuacion"

    id: Mapped[int] = mapped_column(primary_key=True)
    caso_id: Mapped[int] = mapped_column(ForeignKey("liq_caso.id", ondelete="CASCADE"), index=True)
    fecha: Mapped[date | None] = mapped_column(Date, nullable=True)
    descripcion: Mapped[str] = mapped_column(String(300))
    medio: Mapped[str | None] = mapped_column(String(60), nullable=True)  # correo, WhatsApp, físico…
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    caso: Mapped[LiqCaso] = relationship(back_populates="actuaciones")


class LiqDocumento(Base):
    """Soporte adjunto (PDF o imagen) de una incapacidad, restricción o caso, guardado en la base. Es una excepción
    a "no guardar archivos", pedida para tener el repositorio documental de gestión humana."""

    __tablename__ = "liq_documento"

    id: Mapped[int] = mapped_column(primary_key=True)
    modulo: Mapped[str] = mapped_column(String(12), index=True)  # incapacidad | restriccion | caso
    registro_id: Mapped[int] = mapped_column(Integer, index=True)
    nombre: Mapped[str] = mapped_column(String(200))
    mime: Mapped[str] = mapped_column(String(60))
    bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    contenido: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)  # solo se lee al descargarlo
    cargado_por: Mapped[int | None] = mapped_column(ForeignKey(Usuario.id, ondelete="SET NULL"), nullable=True)
    cargado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# Módulos que admiten soportes adjuntos
DOCUMENTOS_DE = {"incapacidad": LiqIncapacidad, "restriccion": LiqRestriccion, "caso": LiqCaso}
