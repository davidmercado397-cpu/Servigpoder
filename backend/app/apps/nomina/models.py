"""Modelos de Validación de nómina. Todas las tablas llevan el prefijo `nom_`.

Los archivos de cada mes no se guardan: se guardan los datos extraídos (JSON) por periodo y archivo, y los
resultados del cálculo. Las decisiones sobre alertas y puestos sin modalidad viven aparte para que un
recálculo no las borre.
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import BaseEmpresa as Base
from app.models import Usuario  # noqa: F401  (tabla referenciada por las decisiones)

# Archivos de un periodo
MODALIDADES = "modalidades"
UBICACIONES = "ubicaciones"
CONTRATOS = "contratos"
CUOTAS = "cuotas"
PROGRAMACION = "programacion"
QUINCENAL = "quincenal"
MENSUAL = "mensual"
ARCHIVOS = (MODALIDADES, UBICACIONES, CONTRATOS, CUOTAS, PROGRAMACION, QUINCENAL, MENSUAL)
MAESTROS = (MODALIDADES, UBICACIONES, CONTRATOS, CUOTAS, PROGRAMACION)  # se exigen en todo periodo, más su nómina

# Tratamiento de un grupo de empleados del contrato
VALIDAR = "validar"
ADMINISTRATIVO = "administrativo"
EXCLUIDO = "excluido"

# Estados de una alerta / decisión
PENDIENTE = "pendiente"
REVISADA = "revisada"  # revisada y correcta
JUSTIFICADA = "justificada"
ERROR = "error"  # error confirmado para corregir


class NomPeriodo(Base):
    """Una revisión de nómina: año, mes y tipo (quincenal = 2.ª quincena; mensual = mes completo)."""

    __tablename__ = "nom_periodo"
    __table_args__ = (UniqueConstraint("anio", "mes", "nomina"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    anio: Mapped[int] = mapped_column(Integer)
    mes: Mapped[int] = mapped_column(Integer)
    nomina: Mapped[str] = mapped_column(String(10))  # quincenal | mensual
    # Cada cálculo deja una revisión: alertas corregidas, que persisten y nuevas frente a la anterior
    historial: Mapped[list] = mapped_column(JSON, default=list)
    resumen: Mapped[dict] = mapped_column(JSON, default=dict)
    calculado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    archivos: Mapped[list["NomArchivo"]] = relationship(back_populates="periodo", cascade="all, delete-orphan", passive_deletes=True)


class NomArchivo(Base):
    """Datos extraídos de un archivo cargado (el Excel no se guarda)."""

    __tablename__ = "nom_archivo"
    __table_args__ = (UniqueConstraint("periodo_id", "tipo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    periodo_id: Mapped[int] = mapped_column(ForeignKey("nom_periodo.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(20))
    nombre: Mapped[str] = mapped_column(String(255))
    registros: Mapped[int] = mapped_column(Integer, default=0)
    datos: Mapped[dict | list] = mapped_column(JSON)
    cargado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    cargado_por: Mapped[int | None] = mapped_column(ForeignKey(Usuario.id, ondelete="SET NULL"), nullable=True)

    periodo: Mapped[NomPeriodo] = relationship(back_populates="archivos")


class NomPersona(Base):
    """Resultado del cálculo para una persona en una nómina del periodo."""

    __tablename__ = "nom_persona"
    __table_args__ = (UniqueConstraint("periodo_id", "nomina", "cedula"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    periodo_id: Mapped[int] = mapped_column(ForeignKey("nom_periodo.id", ondelete="CASCADE"), index=True)
    nomina: Mapped[str] = mapped_column(String(10))  # quincenal | mensual
    cedula: Mapped[str] = mapped_column(String(30), index=True)
    nombre: Mapped[str] = mapped_column(String(200))
    grupo: Mapped[str] = mapped_column(String(80), default="")
    alertas: Mapped[int] = mapped_column(Integer, default=0)
    detalle: Mapped[dict] = mapped_column(JSON, default=dict)


class NomAlerta(Base):
    __tablename__ = "nom_alerta"

    id: Mapped[int] = mapped_column(primary_key=True)
    periodo_id: Mapped[int] = mapped_column(ForeignKey("nom_periodo.id", ondelete="CASCADE"), index=True)
    nomina: Mapped[str] = mapped_column(String(10))
    cedula: Mapped[str] = mapped_column(String(30), index=True)
    nombre: Mapped[str] = mapped_column(String(200))
    tipo: Mapped[str] = mapped_column(String(40), index=True)
    referencia: Mapped[str] = mapped_column(String(40), default="")  # concepto o cuota a la que se refiere
    severidad: Mapped[str] = mapped_column(String(10))  # alta | media | baja
    mensaje: Mapped[str] = mapped_column(Text)
    esperado: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    pagado: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    nueva: Mapped[bool] = mapped_column(Boolean, default=False)  # no estaba en el cálculo anterior
    datos: Mapped[dict] = mapped_column(JSON, default=dict)


class NomDecision(Base):
    """Revisión de una alerta. Se conserva al recalcular (clave: periodo, nómina, cédula, tipo, referencia)."""

    __tablename__ = "nom_decision"
    __table_args__ = (UniqueConstraint("periodo_id", "nomina", "cedula", "tipo", "referencia"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    periodo_id: Mapped[int] = mapped_column(ForeignKey("nom_periodo.id", ondelete="CASCADE"), index=True)
    nomina: Mapped[str] = mapped_column(String(10))
    cedula: Mapped[str] = mapped_column(String(30))
    tipo: Mapped[str] = mapped_column(String(40))
    referencia: Mapped[str] = mapped_column(String(40), default="")
    estado: Mapped[str] = mapped_column(String(20))
    comentario: Mapped[str] = mapped_column(Text, default="")
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey(Usuario.id, ondelete="SET NULL"), nullable=True)
    decidido_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class NomCodigo(Base):
    """Códigos de la programación con el check "Descuenta" (los días con este código no se pagan)."""

    __tablename__ = "nom_codigo"

    codigo: Mapped[str] = mapped_column(String(40), primary_key=True)
    descripcion: Mapped[str] = mapped_column(String(120), default="")
    descuenta: Mapped[bool] = mapped_column(Boolean, default=False)
    vacaciones: Mapped[bool] = mapped_column(Boolean, default=False)
    revisado: Mapped[bool] = mapped_column(Boolean, default=False)  # False = apareció solo y falta confirmarlo
    visto_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NomGrupo(Base):
    """Grupo de empleados del contrato y cómo se trata: validar, administrativo o excluido ("los 7")."""

    __tablename__ = "nom_grupo"

    nombre: Mapped[str] = mapped_column(String(80), primary_key=True)
    tratamiento: Mapped[str] = mapped_column(String(20), default=VALIDAR)
    revisado: Mapped[bool] = mapped_column(Boolean, default=False)


class NomPuestoDecision(Base):
    """Decisión sobre un puesto sin modalidad: aprobado (no lleva) o error de SIESA. Vale para todos los meses."""

    __tablename__ = "nom_puesto_decision"
    __table_args__ = (UniqueConstraint("ubicacion", "puesto"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ubicacion: Mapped[str] = mapped_column(String(40))
    puesto: Mapped[str] = mapped_column(String(40))
    estado: Mapped[str] = mapped_column(String(20))  # aprobado | error
    comentario: Mapped[str] = mapped_column(Text, default="")
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey(Usuario.id, ondelete="SET NULL"), nullable=True)
    decidido_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class NomParametros(Base):
    """Fila única (id = 1) con los parámetros del cálculo."""

    __tablename__ = "nom_parametros"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    tolerancia: Mapped[float] = mapped_column(Numeric(12, 2), default=1000)
    smlmv: Mapped[float] = mapped_column(Numeric(14, 2), default=1750905)
    auxilio_transporte: Mapped[float] = mapped_column(Numeric(14, 2), default=249095)  # mensual
    horas_dia: Mapped[float] = mapped_column(Numeric(5, 2), default=7)  # horas de salario por día (HORAS_100)
    # Conceptos de cuota que en la nómina quincenal solo se descuentan en la primera quincena
    solo_primera_quincena: Mapped[str] = mapped_column(String(200), default="600,630,631,632")
    # Conceptos que no entran en la base del embargo (además del auxilio de transporte 103)
    excluidos_base_embargo: Mapped[str] = mapped_column(String(200), default="103,132,142,143")
    # Embargos que se calculan sobre la base completa, sin restar el salario mínimo
    embargos_sin_minimo: Mapped[str] = mapped_column(String(200), default="606")
    # Cuotas que en la nómina se pagan con otro concepto: "152=129" (RODAMIENTO_ADM se paga como 129 RODAMIENTO)
    equivalencias_cuotas: Mapped[str] = mapped_column(String(200), default="152=129")
    # Ajustes que no se validan como cuotas: 610 deducción por mayor valor pagado, 151 menores valores pagados
    conceptos_ajuste: Mapped[str] = mapped_column(String(200), default="610,151")
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
