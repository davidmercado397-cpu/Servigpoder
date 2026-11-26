"""Contabilidad: el agente contable aprende las reglas de la empresa. Se guarda la cuenta que propuso el agente en
cada línea (para ofrecer aprender la corrección). La tabla de reglas (ctb_regla) la crea la aplicación al arrancar.

Revision ID: 0061
Revises: 0060
Create Date: 2026-11-26
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        insp = sa.inspect(con)
        if insp.has_table("ctb_linea", schema=esquema) and "producto_ia" not in {c["name"] for c in insp.get_columns("ctb_linea", schema=esquema)}:
            op.add_column("ctb_linea", sa.Column("producto_ia", sa.String(40), nullable=False, server_default=""), schema=esquema)


def downgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if sa.inspect(con).has_table("ctb_linea", schema=esquema):
            op.drop_column("ctb_linea", "producto_ia", schema=esquema)
