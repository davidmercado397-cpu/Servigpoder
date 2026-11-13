"""Configuración del agente de IA (OpenRouter) hecha desde el panel de administración.

Una sola fila (id 1) para toda la plataforma. La clave de la API se guarda cifrada y nunca se devuelve completa.
Lo que esté vacío aquí se toma de las variables del servidor (IA_API_KEY, IA_MODELO).
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class IAConfig(Base):
    __tablename__ = "ia_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    api_key_cifrada: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Últimos 4 caracteres de la clave, para reconocerla sin mostrarla
    api_key_final: Mapped[str | None] = mapped_column(String(8), nullable=True)
    modelo: Mapped[str | None] = mapped_column(String(150), nullable=True)
    # Modelo para llenar costeos desde archivos (vacío = el general)
    modelo_costeo: Mapped[str | None] = mapped_column(String(150), nullable=True)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    actualizado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True)
