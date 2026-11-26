"""Contabilidad (Speed): facturas de compra que llegan por correo → plano de World Office.

Los documentos (zip, XML, PDF) se leen en memoria y se descartan: aquí solo quedan los datos de cada factura para
armar el plano. Las tablas viven en el esquema de cada empresa (BaseEmpresa); el desarrollo se habilita para Speed.
"""

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import BaseEmpresa

# Estados de una factura
PENDIENTE = "pendiente"  # por revisar (producto, centro de costos, nota)
LISTA = "lista"  # revisada: sale en el próximo plano
APARTE = "aparte"  # no es a nombre de la empresa o es una nota: se confirma si se contabiliza
DESCARTADA = "descartada"
CONTABILIZADA = "contabilizada"  # ya se cargó en World Office: no vuelve a salir en el plano
ESTADOS = (PENDIENTE, LISTA, APARTE, DESCARTADA, CONTABILIZADA)


class CtbConfig(BaseEmpresa):
    """Configuración del desarrollo (una fila): el buzón de Gmail que se lee y los datos fijos del plano."""

    __tablename__ = "ctb_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Buzón (IMAP de Gmail con contraseña de aplicación). La clave se guarda cifrada.
    correo: Mapped[str] = mapped_column(String(160), default="")
    clave_cifrada: Mapped[str | None] = mapped_column(Text, nullable=True)
    carpeta: Mapped[str] = mapped_column(String(80), default="INBOX")
    # El correo se revisa solo cuando el usuario lo pide (botón «Revisar correo»): no hay lectura automática
    # Modelo de IA para leer y proponer las facturas (solo este desarrollo; vacío = el modelo general de la plataforma)
    modelo: Mapped[str] = mapped_column(String(150), default="", server_default="")
    ultima_lectura: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ultimo_error: Mapped[str] = mapped_column(Text, default="")
    # Datos de la empresa y fijos del plano de World Office
    empresa_nombre: Mapped[str] = mapped_column(String(160), default="SPEED SECURITY LTDA")
    empresa_nit: Mapped[str] = mapped_column(String(20), default="900259118")
    tipo_documento: Mapped[str] = mapped_column(String(10), default="FC")
    prefijo: Mapped[str] = mapped_column(String(10), default="FC")
    # Cuentas de cobro: tipo de documento y prefijo DSS, con su propio número seguido
    tipo_documento_ds: Mapped[str] = mapped_column(String(10), default="DSS", server_default="DSS")
    prefijo_ds: Mapped[str] = mapped_column(String(10), default="DSS", server_default="DSS")
    # Último número ya usado en World Office por serie (para seguir el consecutivo del mes). Vacío = ninguno
    ultimo_fc: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ultimo_ds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bodega: Mapped[str] = mapped_column(String(60), default="Principal")
    unidad: Mapped[str] = mapped_column(String(20), default="Und.")


class CtbFactura(BaseEmpresa):
    __tablename__ = "ctb_factura"

    id: Mapped[int] = mapped_column(primary_key=True)
    cufe: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    tipo: Mapped[str] = mapped_column(String(20), default="factura")  # factura | nota_credito | nota_debito
    # Cuenta de cobro (el documento viene titulado así): en el plano va como DS / DSS, con su propio consecutivo
    cuenta_cobro: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    estado: Mapped[str] = mapped_column(String(20), default=PENDIENTE, index=True)
    motivo_aparte: Mapped[str] = mapped_column(String(300), default="")
    # Cómo se leyó: xml (exacto) | ia (PDF o imagen leídos por la IA: verificar)
    leida_con: Mapped[str] = mapped_column(String(10), default="xml")
    # De dónde llegó (sin guardar el correo): remitente, asunto y fecha
    origen: Mapped[str] = mapped_column(String(20), default="correo")  # correo | carga
    correo_de: Mapped[str] = mapped_column(String(200), default="")
    correo_asunto: Mapped[str] = mapped_column(String(300), default="")
    correo_fecha: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Factura
    prefijo: Mapped[str] = mapped_column(String(20), default="")
    numero: Mapped[str] = mapped_column(String(40), default="")
    fecha_emision: Mapped[date | None] = mapped_column(Date, nullable=True)
    fecha_vencimiento: Mapped[date | None] = mapped_column(Date, nullable=True)
    forma_pago: Mapped[str] = mapped_column(String(20), default="Contado")
    moneda: Mapped[str] = mapped_column(String(5), default="COP")
    emisor_nit: Mapped[str] = mapped_column(String(20), default="", index=True)
    emisor_dv: Mapped[str] = mapped_column(String(2), default="")
    emisor_nombre: Mapped[str] = mapped_column(String(200), default="")
    comprador_nit: Mapped[str] = mapped_column(String(20), default="")
    comprador_nombre: Mapped[str] = mapped_column(String(200), default="")
    subtotal: Mapped[float] = mapped_column(Numeric(16, 2), default=0)
    iva: Mapped[float] = mapped_column(Numeric(16, 2), default=0)
    total: Mapped[float] = mapped_column(Numeric(16, 2), default=0)
    retenciones: Mapped[dict] = mapped_column(JSON, default=dict)  # informativo: rete fuente, IVA, ICA
    # Para el plano: nota del encabezado (la propone la IA) y avisos de la lectura
    nota: Mapped[str] = mapped_column(String(300), default="")
    avisos: Mapped[list] = mapped_column(JSON, default=list)
    # Contabilización: el número del documento (AAMM + consecutivo) y la fecha de cargue en World Office
    documento_numero: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fecha_contable: Mapped[date | None] = mapped_column(Date, nullable=True)
    contabilizada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    contabilizada_por: Mapped[int | None] = mapped_column(Integer, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lineas: Mapped[list["CtbLinea"]] = relationship(back_populates="factura", cascade="all, delete-orphan",
                                                    order_by="CtbLinea.orden", lazy="selectin")


class CtbLinea(BaseEmpresa):
    """Un producto de la factura = una línea del plano."""

    __tablename__ = "ctb_linea"

    id: Mapped[int] = mapped_column(primary_key=True)
    factura_id: Mapped[int] = mapped_column(ForeignKey("ctb_factura.id", ondelete="CASCADE"), index=True)
    orden: Mapped[int] = mapped_column(Integer, default=1)
    codigo_proveedor: Mapped[str] = mapped_column(String(60), default="")
    descripcion: Mapped[str] = mapped_column(String(500), default="")
    cantidad: Mapped[float] = mapped_column(Numeric(14, 4), default=1)
    valor_unitario: Mapped[float] = mapped_column(Numeric(16, 4), default=0)  # neto de descuentos
    subtotal: Mapped[float] = mapped_column(Numeric(16, 2), default=0)
    iva_pct: Mapped[float] = mapped_column(Numeric(6, 2), default=0)
    iva_valor: Mapped[float] = mapped_column(Numeric(16, 2), default=0)
    # Lo que va en World Office (lo propone la IA y lo revisa contabilidad)
    producto: Mapped[str] = mapped_column(String(40), default="")
    centro_costos: Mapped[str] = mapped_column(String(80), default="")
    nota: Mapped[str] = mapped_column(String(200), default="")
    # Lo que propuso el agente: si contabilidad lo cambia, el agente ofrece aprender la corrección
    producto_ia: Mapped[str] = mapped_column(String(40), default="", server_default="")

    factura: Mapped[CtbFactura] = relationship(back_populates="lineas")


class CtbRegla(BaseEmpresa):
    """Regla contable propia de la empresa que el agente aplica por encima de la norma general.
    P. ej. «En Speed los intereses de mora no van a la cuenta de intereses: van al costo (7) o al gasto (5)»."""

    __tablename__ = "ctb_regla"

    id: Mapped[int] = mapped_column(primary_key=True)
    texto: Mapped[str] = mapped_column(Text)
    cuentas: Mapped[str] = mapped_column(String(200), default="")  # cuentas que menciona (referencia)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    origen: Mapped[str] = mapped_column(String(20), default="manual")  # manual | correccion
    ejemplo: Mapped[str] = mapped_column(String(400), default="")  # la factura/línea de la que salió
    usos: Mapped[int] = mapped_column(Integer, default=0)  # veces que el agente dijo aplicarla
    creado_por: Mapped[int | None] = mapped_column(Integer, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CtbProducto(BaseEmpresa):
    """Catálogo de productos / cuentas de World Office (lo carga contabilidad)."""

    __tablename__ = "ctb_producto"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(40), unique=True)
    nombre: Mapped[str] = mapped_column(String(200), default="")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class CtbCentroCostos(BaseEmpresa):
    __tablename__ = "ctb_centro_costos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80), unique=True)  # como va en el plano (p. ej. «Administracion»)
    codigo: Mapped[str] = mapped_column(String(40), default="")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class CtbTercero(BaseEmpresa):
    """Proveedores creados en World Office (listado de terceros): para avisar si una factura es de uno que no existe."""

    __tablename__ = "ctb_tercero"

    id: Mapped[int] = mapped_column(primary_key=True)
    nit: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    dv: Mapped[str] = mapped_column(String(2), default="")
    nombre: Mapped[str] = mapped_column(String(200), default="")


class CtbPlano(BaseEmpresa):
    """Un plano descargado: qué facturas llevó y con qué número de documento (para marcarlas contabilizadas)."""

    __tablename__ = "ctb_plano"

    id: Mapped[int] = mapped_column(primary_key=True)
    fecha: Mapped[date] = mapped_column(Date)  # fecha de cargue en World Office (la digita contabilidad)
    items: Mapped[list] = mapped_column(JSON, default=list)  # [{"factura_id": 1, "documento": 2608001}]
    usuario_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CtbCorreo(BaseEmpresa):
    """Registro de cada correo leído (sin su contenido): para saber qué pasó con él."""

    __tablename__ = "ctb_correo"

    id: Mapped[int] = mapped_column(primary_key=True)
    mensaje_id: Mapped[str] = mapped_column(String(300), default="", index=True)
    de: Mapped[str] = mapped_column(String(200), default="")
    asunto: Mapped[str] = mapped_column(String(300), default="")
    fecha: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resultado: Mapped[str] = mapped_column(String(500), default="")
    facturas: Mapped[int] = mapped_column(Integer, default=0)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
