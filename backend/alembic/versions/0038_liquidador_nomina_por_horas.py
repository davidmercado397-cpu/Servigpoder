"""Liquidador: nómina por horas (tipo de nómina y si descuenta salud y/o pensión).

Revision ID: 0038
Revises: 0037
Create Date: 2026-10-29
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if not sa.inspect(con).has_table("liq_periodo", schema=esquema):
            continue
        op.add_column("liq_periodo", sa.Column("tipo_nomina", sa.String(10), nullable=False, server_default="normal"), schema=esquema)
        op.add_column("liq_periodo", sa.Column("descuenta_salud", sa.Boolean(), nullable=False, server_default=sa.true()), schema=esquema)
        op.add_column("liq_periodo", sa.Column("descuenta_pension", sa.Boolean(), nullable=False, server_default=sa.true()), schema=esquema)


def downgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if sa.inspect(con).has_table("liq_periodo", schema=esquema):
            for c in ("descuenta_pension", "descuenta_salud", "tipo_nomina"):
                op.drop_column("liq_periodo", c, schema=esquema)
