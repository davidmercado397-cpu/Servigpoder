"""Empresas del holding y acceso de cada usuario a los desarrollos de cada empresa.

Los usuarios y los roles son compartidos (mismo rol en todas las empresas). Cada empresa tiene sus propios
datos en su esquema (emp_<codigo>) y habilita los desarrollos que usa; a cada usuario se le marca a qué
desarrollos entra en cada empresa.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Empresa(Base):
    __tablename__ = "empresa"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True, index=True)  # sera, servigpoder…
    nombre: Mapped[str] = mapped_column(String(120))
    esquema: Mapped[str] = mapped_column(String(40), unique=True)  # emp_<codigo>
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    apps: Mapped[list["EmpresaApp"]] = relationship(cascade="all, delete-orphan", lazy="selectin")

    @property
    def codigos_apps(self) -> list[str]:
        return sorted(a.app for a in self.apps)


class EmpresaApp(Base):
    """Desarrollo habilitado para la empresa."""

    __tablename__ = "empresa_app"

    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id", ondelete="CASCADE"), primary_key=True)
    app: Mapped[str] = mapped_column(String(40), primary_key=True)


class UsuarioEmpresaApp(Base):
    """El usuario entra a este desarrollo de esta empresa (lo que puede hacer allí lo definen sus roles)."""

    __tablename__ = "usuario_empresa_app"

    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"), primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id", ondelete="CASCADE"), primary_key=True)
    app: Mapped[str] = mapped_column(String(40), primary_key=True)
    empresa: Mapped[Empresa] = relationship(lazy="joined")
