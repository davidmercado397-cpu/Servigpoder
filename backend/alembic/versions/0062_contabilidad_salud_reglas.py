"""Contabilidad: salud de las reglas del agente (cuántas veces se corrigió una factura donde se aplicó) y qué reglas
aplicó el agente en cada factura.

Revision ID: 0062
Revises: 0061
Create Date: 2026-11-26
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        insp = sa.inspect(con)
        if insp.has_table("ctb_regla", schema=esquema) and "corregida" not in {c["name"] for c in insp.get_columns("ctb_regla", schema=esquema)}:
            op.add_column("ctb_regla", sa.Column("corregida", sa.Integer(), nullable=False, server_default="0"), schema=esquema)
        if insp.has_table("ctb_factura", schema=esquema) and "reglas_aplicadas" not in {c["name"] for c in insp.get_columns("ctb_factura", schema=esquema)}:
            op.add_column("ctb_factura", sa.Column("reglas_aplicadas", sa.JSON(), nullable=True), schema=esquema)


def downgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        insp = sa.inspect(con)
        if insp.has_table("ctb_factura", schema=esquema):
            op.drop_column("ctb_factura", "reglas_aplicadas", schema=esquema)
        if insp.has_table("ctb_regla", schema=esquema):
            op.drop_column("ctb_regla", "corregida", schema=esquema)
