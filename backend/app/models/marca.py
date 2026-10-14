"""Marca de la plataforma: nombre, colores, logo, favicon y fondo de la pantalla de ingreso.

Una sola fila (id = 1). Las imágenes se guardan en la base (ya validadas, recortadas a su tamaño y sin
metadatos), nunca como archivos en el servidor.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

# Valores de fábrica (la marca actual de la plataforma)
MARCA_INICIAL = {
    "nombre": "Plataforma Servigpoder",
    "subtitulo": "Desarrollos internos",
    "color_primario": "#1d5fbf",
    "color_acento": "#38bdf8",
    "color_barra": "#0f2d5c",
    "color_barra_fin": "#081a38",
    "login_fondo": "degradado",  # degradado | color | imagen
    "login_color": "#0f2d5c",
    "login_oscurecer": 45,  # % de oscuridad sobre la imagen de fondo, para que el texto se lea
}


class Marca(Base):
    __tablename__ = "marca"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    nombre: Mapped[str] = mapped_column(String(80), default=MARCA_INICIAL["nombre"])
    subtitulo: Mapped[str] = mapped_column(String(80), default=MARCA_INICIAL["subtitulo"])
    color_primario: Mapped[str] = mapped_column(String(7), default=MARCA_INICIAL["color_primario"])
    color_acento: Mapped[str] = mapped_column(String(7), default=MARCA_INICIAL["color_acento"])
    color_barra: Mapped[str] = mapped_column(String(7), default=MARCA_INICIAL["color_barra"])
    color_barra_fin: Mapped[str] = mapped_column(String(7), default=MARCA_INICIAL["color_barra_fin"])
    login_fondo: Mapped[str] = mapped_column(String(20), default=MARCA_INICIAL["login_fondo"])
    login_color: Mapped[str] = mapped_column(String(7), default=MARCA_INICIAL["login_color"])
    login_oscurecer: Mapped[int] = mapped_column(Integer, default=MARCA_INICIAL["login_oscurecer"])
    # Sube con cada cambio: las imágenes se piden con ?v= para que el navegador no muestre una vieja
    version: Mapped[int] = mapped_column(Integer, default=1)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    actualizado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True)


class MarcaImagen(Base):
    """logo | favicon | fondo (de la pantalla de ingreso)."""

    __tablename__ = "marca_imagen"

    tipo: Mapped[str] = mapped_column(String(20), primary_key=True)
    contenido: Mapped[bytes] = mapped_column(LargeBinary)
    mime: Mapped[str] = mapped_column(String(40))
    ancho: Mapped[int] = mapped_column(Integer)
    alto: Mapped[int] = mapped_column(Integer)
    bytes: Mapped[int] = mapped_column(Integer)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
