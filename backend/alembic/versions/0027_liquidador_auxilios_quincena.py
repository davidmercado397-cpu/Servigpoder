"""Liquidador: auxilios no prestacionales por empleado y quincena en que aplica cada préstamo, embargo o auxilio

La tabla liq_auxilio la crea el arranque en el esquema de cada empresa.

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-28
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if not sa.inspect(con).has_table("liq_descuento", schema=esquema):
            continue  # el arranque la crea con la columna nueva
        op.add_column("liq_descuento", sa.Column("quincena", sa.String(10), nullable=False, server_default="ambas"), schema=esquema)


def downgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if sa.inspect(con).has_table("liq_descuento", schema=esquema):
            op.drop_column("liq_descuento", "quincena", schema=esquema)
