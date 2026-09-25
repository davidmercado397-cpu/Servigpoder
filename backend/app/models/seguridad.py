from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Table, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

rol_permiso = Table(
    "rol_permiso",
    Base.metadata,
    Column("rol_id", ForeignKey("rol.id", ondelete="CASCADE"), primary_key=True),
    Column("permiso_codigo", ForeignKey("permiso.codigo", ondelete="CASCADE"), primary_key=True),
)

usuario_rol = Table(
    "usuario_rol",
    Base.metadata,
    Column("usuario_id", ForeignKey("usuario.id", ondelete="CASCADE"), primary_key=True),
    Column("rol_id", ForeignKey("rol.id", ondelete="CASCADE"), primary_key=True),
)


class Permiso(Base):
    __tablename__ = "permiso"

    codigo: Mapped[str] = mapped_column(String(60), primary_key=True)
    modulo: Mapped[str] = mapped_column(String(60))
    descripcion: Mapped[str] = mapped_column(String(200))


class Rol(Base):
    __tablename__ = "rol"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(60), unique=True)
    descripcion: Mapped[str] = mapped_column(String(200), default="")
    permisos: Mapped[list[Permiso]] = relationship(secondary=rol_permiso, lazy="selectin")


class Usuario(Base):
    __tablename__ = "usuario"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(160), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    roles: Mapped[list[Rol]] = relationship(secondary=usuario_rol, lazy="selectin")

    @property
    def permisos(self) -> set[str]:
        return {p.codigo for r in self.roles for p in r.permisos}
