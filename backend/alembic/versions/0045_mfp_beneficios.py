"""MFP: beneficios (cantidad por año de contrato o por todo el contrato, con valor unitario) que se controlan por consumo

Revision ID: 0045
Revises: 0044
Create Date: 2026-11-13
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        insp = sa.inspect(con)
        if not insp.has_table("cst_mfp_item", schema=esquema):
            continue
        columnas = {c["name"] for c in insp.get_columns("cst_mfp_item", schema=esquema)}
        if "periodo" not in columnas:
            op.add_column("cst_mfp_item", sa.Column("periodo", sa.String(10), nullable=False, server_default="anio"), schema=esquema)
        if "valor_unitario" not in columnas:
            op.add_column("cst_mfp_item", sa.Column("valor_unitario", sa.Numeric(16, 2), nullable=False, server_default="0"), schema=esquema)


def downgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if sa.inspect(con).has_table("cst_mfp_item", schema=esquema):
            op.drop_column("cst_mfp_item", "valor_unitario", schema=esquema)
            op.drop_column("cst_mfp_item", "periodo", schema=esquema)
