"""Usuarios, roles y permisos

Revision ID: 0001
Revises:
Create Date: 2026-09-25
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "permiso",
        sa.Column("codigo", sa.String(60), primary_key=True),
        sa.Column("modulo", sa.String(60), nullable=False),
        sa.Column("descripcion", sa.String(200), nullable=False),
    )
    op.create_table(
        "rol",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("nombre", sa.String(60), nullable=False, unique=True),
        sa.Column("descripcion", sa.String(200), nullable=False),
    )
    op.create_table(
        "usuario",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String(60), nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("email", sa.String(160), nullable=True),
        sa.Column("password_hash", sa.String(200), nullable=False),
        sa.Column("activo", sa.Boolean, nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_usuario_username", "usuario", ["username"], unique=True)
    op.create_table(
        "rol_permiso",
        sa.Column("rol_id", sa.Integer, sa.ForeignKey("rol.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("permiso_codigo", sa.String(60), sa.ForeignKey("permiso.codigo", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "usuario_rol",
        sa.Column("usuario_id", sa.Integer, sa.ForeignKey("usuario.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("rol_id", sa.Integer, sa.ForeignKey("rol.id", ondelete="CASCADE"), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("usuario_rol")
    op.drop_table("rol_permiso")
    op.drop_index("ix_usuario_username", table_name="usuario")
    op.drop_table("usuario")
    op.drop_table("rol")
    op.drop_table("permiso")
