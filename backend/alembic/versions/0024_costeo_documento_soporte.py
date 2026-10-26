"""Costeo y MFP's: documento contable (tipo y número) en cada movimiento y archivo del soporte

Las tablas nuevas (cst_tipo_documento, cst_soporte) las crea el arranque en el esquema de cada empresa.

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-26
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if not sa.inspect(con).has_table("cst_movimiento", schema=esquema):
            continue  # la crea el arranque con las columnas nuevas
        op.add_column("cst_movimiento", sa.Column("tipo_documento", sa.String(20), nullable=False, server_default=""), schema=esquema)
        op.add_column("cst_movimiento", sa.Column("numero_documento", sa.String(40), nullable=False, server_default=""), schema=esquema)


def downgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if sa.inspect(con).has_table("cst_movimiento", schema=esquema):
            op.drop_column("cst_movimiento", "numero_documento", schema=esquema)
            op.drop_column("cst_movimiento", "tipo_documento", schema=esquema)
