"""Base de conocimiento de instructivos de SIESA: solo el texto extraído de cada PDF, por fragmentos.

El PDF no se guarda: se lee en memoria, se extrae el texto por página y se descarta.
"""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, func, literal_column, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import BaseEmpresa as Base
from app.models import Usuario


class SiesaDocumento(Base):
    __tablename__ = "siesa_documento"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(255))  # nombre del archivo
    titulo: Mapped[str] = mapped_column(String(255))
    # Metadatos para filtrar antes de buscar y para dar contexto: módulo de SIESA (Nómina, Contabilidad…) y
    # fecha del instructivo (la del PDF, editable)
    modulo: Mapped[str] = mapped_column(String(80), default="", server_default="", index=True)
    fecha: Mapped[date | None] = mapped_column(Date, nullable=True)
    huella: Mapped[str] = mapped_column(String(64), unique=True)  # SHA-256 del PDF: evita cargar dos veces el mismo
    paginas: Mapped[int] = mapped_column(Integer, default=0)
    paginas_sin_texto: Mapped[int] = mapped_column(Integer, default=0)  # escaneadas (imagen): no se pueden consultar
    fragmentos: Mapped[int] = mapped_column(Integer, default=0)
    caracteres: Mapped[int] = mapped_column(Integer, default=0)
    cargado_por: Mapped[int | None] = mapped_column(ForeignKey(Usuario.id, ondelete="SET NULL"), nullable=True)
    cargado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    partes: Mapped[list["SiesaFragmento"]] = relationship(back_populates="documento", cascade="all, delete-orphan", passive_deletes=True)


class SiesaFragmento(Base):
    __tablename__ = "siesa_fragmento"
    # Búsqueda de texto completo en español (PostgreSQL); en las pruebas (SQLite) se busca en Python
    __table_args__ = (
        Index("ix_siesa_fragmento_texto", func.to_tsvector(literal_column("'spanish'::regconfig"), text("(encabezado || ' ' || texto)")),
              postgresql_using="gin").ddl_if(dialect="postgresql"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    documento_id: Mapped[int] = mapped_column(ForeignKey("siesa_documento.id", ondelete="CASCADE"), index=True)
    pagina: Mapped[int] = mapped_column(Integer)
    orden: Mapped[int] = mapped_column(Integer)
    seccion: Mapped[str] = mapped_column(String(300), default="", server_default="")  # "Solicitud > Plazos"
    # Contexto del fragmento: "Nómina · Manual de vacaciones > Solicitud > Plazos" (entra en la búsqueda)
    encabezado: Mapped[str] = mapped_column(String(500), default="", server_default="")
    texto: Mapped[str] = mapped_column(Text)

    documento: Mapped[SiesaDocumento] = relationship(back_populates="partes", lazy="joined")
