"""Costeo y MFP's: los ítems «Otros» de la MFP dicen cuál es (nombre escrito a mano).

Revision ID: 0042
Revises: 0041
Create Date: 2026-11-11
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        insp = sa.inspect(con)
        if insp.has_table("cst_mfp_item", schema=esquema) and \
                "nombre" not in {c["name"] for c in insp.get_columns("cst_mfp_item", schema=esquema)}:
            op.add_column("cst_mfp_item", sa.Column("nombre", sa.String(120), nullable=False, server_default=""), schema=esquema)


def downgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if sa.inspect(con).has_table("cst_mfp_item", schema=esquema):
            op.drop_column("cst_mfp_item", "nombre", schema=esquema)
