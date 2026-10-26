"""Costeo y MFP's (matriz de fortalecimiento de puesto). Todas las tablas llevan el prefijo `cst_`.

- MFP: lo que se pacta con el cliente a nivel de contrato (ítems en pesos, pesos por mes u horas) y cada
  movimiento con el que se ejecuta (pago, aplicación, servicio prestado). Un movimiento que supera lo pactado
  solo se registra con autorización.
- Costeo: el cálculo de rentabilidad de un servicio antes de firmarlo. Todos sus valores son parámetros y
  catálogos editables; un costeo aprobado conserva los parámetros con los que se aprobó.
"""

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, LargeBinary, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import BaseEmpresa as Base
from app.models import Usuario

# Unidad de un ítem de MFP
PESOS = "pesos"  # un valor en pesos por todo el contrato (bono, equipo, capacitación, nota crédito)
PESOS_MES = "pesos_mes"  # un valor mensual (plan celular, mantenimiento): se causa mes a mes
HORAS = "horas"  # bolsa de horas por cada año de contrato; lo no usado en el año se pierde
UNIDADES = (PESOS, PESOS_MES, HORAS)

# Estados del costeo
BORRADOR, ENVIADO, APROBADO, RECHAZADO = "borrador", "enviado", "aprobado", "rechazado"


class CstCliente(Base):
    __tablename__ = "cst_cliente"

    id: Mapped[int] = mapped_column(primary_key=True)
    nit: Mapped[str] = mapped_column(String(60), index=True)  # puede traer más de un NIT ("800… Y 900…")
    nombre: Mapped[str] = mapped_column(String(200))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CstTipoItem(Base):
    """Catálogo de ítems de MFP (reinversión, nota crédito, Acces Too, bolsa de horas, publicidad…)."""

    __tablename__ = "cst_tipo_item"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    nombre: Mapped[str] = mapped_column(String(120))
    unidad: Mapped[str] = mapped_column(String(10), default=PESOS)
    # Si el cliente termina antes, devuelve la parte no amortizada de lo ejecutado
    reembolsable: Mapped[bool] = mapped_column(Boolean, default=True)
    # Suma en el % de MFP (lo que se le da al cliente). Las bolsas internas (publicidad, representación) no.
    cuenta_en_mfp: Mapped[bool] = mapped_column(Boolean, default=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    orden: Mapped[int] = mapped_column(Integer, default=100)


class CstMfp(Base):
    __tablename__ = "cst_mfp"

    id: Mapped[int] = mapped_column(primary_key=True)
    numero: Mapped[str] = mapped_column(String(30), index=True)  # número de la MFP física
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cst_cliente.id", ondelete="RESTRICT"), index=True)
    contrato: Mapped[str] = mapped_column(String(80), default="")
    fecha_inicio: Mapped[date | None] = mapped_column(Date, nullable=True)
    duracion_meses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    valor_mensual: Mapped[float] = mapped_column(Numeric(16, 2), default=0)  # facturación mensual pactada
    pct_comercial: Mapped[float | None] = mapped_column(Numeric(8, 5), nullable=True)  # % de la MFP física (0,12 = 12 %)
    # Terminación anticipada: fija la fecha con la que se calcula el reembolso
    terminada: Mapped[bool] = mapped_column(Boolean, default=False)
    fecha_terminacion: Mapped[date | None] = mapped_column(Date, nullable=True)
    notas: Mapped[str] = mapped_column(Text, default="")
    costeo_id: Mapped[int | None] = mapped_column(ForeignKey("cst_costeo.id", ondelete="SET NULL"), nullable=True)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey(Usuario.id, ondelete="SET NULL"), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    cliente: Mapped[CstCliente] = relationship(lazy="joined")
    items: Mapped[list["CstMfpItem"]] = relationship(back_populates="mfp", cascade="all, delete-orphan", passive_deletes=True,
                                                     order_by="CstMfpItem.id")


class CstMfpItem(Base):
    """Un ítem pactado. pactado: pesos (total), valor mensual (pesos_mes) u horas por año (horas)."""

    __tablename__ = "cst_mfp_item"

    id: Mapped[int] = mapped_column(primary_key=True)
    mfp_id: Mapped[int] = mapped_column(ForeignKey("cst_mfp.id", ondelete="CASCADE"), index=True)
    tipo_id: Mapped[int] = mapped_column(ForeignKey("cst_tipo_item.id", ondelete="RESTRICT"))
    descripcion: Mapped[str] = mapped_column(String(300), default="")
    pactado: Mapped[float] = mapped_column(Numeric(16, 2), default=0)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    mfp: Mapped[CstMfp] = relationship(back_populates="items")
    tipo: Mapped[CstTipoItem] = relationship(lazy="joined")
    movimientos: Mapped[list["CstMovimiento"]] = relationship(back_populates="item", cascade="all, delete-orphan",
                                                              passive_deletes=True, order_by="CstMovimiento.fecha")


class CstMovimiento(Base):
    """Ejecución de un ítem: un pago, una nota aplicada, un equipo entregado o una solicitud de horas."""

    __tablename__ = "cst_movimiento"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("cst_mfp_item.id", ondelete="CASCADE"), index=True)
    fecha: Mapped[date] = mapped_column(Date)
    valor: Mapped[float] = mapped_column(Numeric(16, 2))  # pesos u horas, según la unidad del ítem
    descripcion: Mapped[str] = mapped_column(String(300), default="")  # motivo: "2 h de acompañamiento por cumpleaños"
    # Documento contable que respalda el movimiento (tipo del catálogo y número)
    tipo_documento: Mapped[str] = mapped_column(String(20), default="", server_default="")
    numero_documento: Mapped[str] = mapped_column(String(40), default="", server_default="")
    soporte: Mapped[str] = mapped_column(String(300), default="")  # observación: proveedor, factura cruzada…
    # Si superó lo pactado: quién lo autorizó y con qué soporte
    excede: Mapped[bool] = mapped_column(Boolean, default=False)
    autorizacion: Mapped[str] = mapped_column(String(300), default="")
    autorizado_por: Mapped[int | None] = mapped_column(ForeignKey(Usuario.id, ondelete="SET NULL"), nullable=True)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey(Usuario.id, ondelete="SET NULL"), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    item: Mapped[CstMfpItem] = relationship(back_populates="movimientos")
    soportes: Mapped[list["CstSoporte"]] = relationship(back_populates="movimiento", cascade="all, delete-orphan",
                                                         passive_deletes=True, order_by="CstSoporte.id")


class CstTipoDocumento(Base):
    """Tipos de documento contable (comprobante de egreso, factura, nota crédito…): catálogo editable."""

    __tablename__ = "cst_tipo_documento"

    codigo: Mapped[str] = mapped_column(String(20), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class CstSoporte(Base):
    """Archivo del soporte contable de un movimiento (PDF o imagen), guardado en la base para consultarlo luego.
    Es la excepción a "no guardar archivos": el soporte es evidencia y se pidió conservarlo."""

    __tablename__ = "cst_soporte"

    id: Mapped[int] = mapped_column(primary_key=True)
    movimiento_id: Mapped[int] = mapped_column(ForeignKey("cst_movimiento.id", ondelete="CASCADE"), index=True)
    nombre: Mapped[str] = mapped_column(String(200))
    mime: Mapped[str] = mapped_column(String(60))
    bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    contenido: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)  # solo se lee al descargarlo
    cargado_por: Mapped[int | None] = mapped_column(ForeignKey(Usuario.id, ondelete="SET NULL"), nullable=True)
    cargado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    movimiento: Mapped[CstMovimiento] = relationship(back_populates="soportes")


# ---------------- Costeo ----------------

class CstParametro(Base):
    """Valor numérico editable del costeo (salario mínimo, % de prestaciones, renta, ICA, publicidad…)."""

    __tablename__ = "cst_parametro"

    clave: Mapped[str] = mapped_column(String(40), primary_key=True)
    valor: Mapped[float] = mapped_column(Numeric(20, 6))
    nombre: Mapped[str] = mapped_column(String(160))
    grupo: Mapped[str] = mapped_column(String(40))
    ayuda: Mapped[str] = mapped_column(String(300), default="")
    orden: Mapped[int] = mapped_column(Integer, default=100)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CstComisionRango(Base):
    """Comisión según el % de MFP con que se vende: hasta ese %, la comisión y la carga prestacional del vendedor."""

    __tablename__ = "cst_comision_rango"

    id: Mapped[int] = mapped_column(primary_key=True)
    hasta_pct: Mapped[float | None] = mapped_column(Numeric(8, 5), nullable=True)  # vacío = en adelante
    pct_comision: Mapped[float] = mapped_column(Numeric(8, 5))
    carga_prestacional: Mapped[float] = mapped_column(Numeric(8, 5), default=1.37872)


class CstServicio(Base):
    """Servicio vendible con su tarifa y los hombres que necesita (24 h = 3, 12 h = 1,5…)."""

    __tablename__ = "cst_servicio"

    id: Mapped[int] = mapped_column(primary_key=True)
    descripcion: Mapped[str] = mapped_column(String(400))
    tarifa: Mapped[float] = mapped_column(Numeric(16, 2), default=0)
    hombres: Mapped[float] = mapped_column(Numeric(6, 2), default=3)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class CstCatalogoCosto(Base):
    """Dotación de la tarifa, dotación adicional del puesto y otros costos directos, con precio y vida útil."""

    __tablename__ = "cst_catalogo_costo"
    __table_args__ = (UniqueConstraint("grupo", "nombre", name="uq_cst_catalogo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    grupo: Mapped[str] = mapped_column(String(20))  # dotacion_tarifa | dotacion_puesto | otros
    nombre: Mapped[str] = mapped_column(String(200))
    valor_unitario: Mapped[float] = mapped_column(Numeric(16, 2), default=0)
    vida_util_meses: Mapped[int | None] = mapped_column(Integer, nullable=True)  # costo mensual = valor × cantidad ÷ vida útil
    entregas_anio: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)  # costo mensual = valor × cantidad × entregas ÷ 12
    por_hombre: Mapped[bool] = mapped_column(Boolean, default=False)  # la cantidad por defecto es el número de hombres
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    fuente: Mapped[str] = mapped_column(String(120), default="")
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CstCosteo(Base):
    __tablename__ = "cst_costeo"

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cst_cliente.id", ondelete="RESTRICT"), index=True)
    nombre: Mapped[str] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(Integer, default=1)
    estado: Mapped[str] = mapped_column(String(12), default=BORRADOR)
    # Entradas (servicios, personal, otros costos, dotación…) y, si está aprobado, los parámetros con que se aprobó
    datos: Mapped[dict] = mapped_column(JSON, default=dict)
    parametros_aprobados: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    resultado: Mapped[dict] = mapped_column(JSON, default=dict)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey(Usuario.id, ondelete="SET NULL"), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    cliente: Mapped[CstCliente] = relationship(lazy="joined")
