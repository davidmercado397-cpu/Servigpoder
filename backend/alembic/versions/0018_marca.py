"""Marca de la plataforma: nombre, colores, logo, favicon y fondo de ingreso

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-14
"""
import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "marca",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(80), nullable=False),
        sa.Column("subtitulo", sa.String(80), nullable=False),
        sa.Column("color_primario", sa.String(7), nullable=False),
        sa.Column("color_acento", sa.String(7), nullable=False),
        sa.Column("color_barra", sa.String(7), nullable=False),
        sa.Column("color_barra_fin", sa.String(7), nullable=False),
        sa.Column("login_fondo", sa.String(20), nullable=False),
        sa.Column("login_color", sa.String(7), nullable=False),
        sa.Column("login_oscurecer", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("actualizado_por", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["actualizado_por"], ["usuario.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "marca_imagen",
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("contenido", sa.LargeBinary(), nullable=False),
        sa.Column("mime", sa.String(40), nullable=False),
        sa.Column("ancho", sa.Integer(), nullable=False),
        sa.Column("alto", sa.Integer(), nullable=False),
        sa.Column("bytes", sa.Integer(), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("tipo"),
    )


def downgrade() -> None:
    op.drop_table("marca_imagen")
    op.drop_table("marca")
