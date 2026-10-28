"""Liquidador: varias nóminas con nombre dentro de cada periodo

Las existentes quedan como la nómina «General» de su periodo.

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-28
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        insp = sa.inspect(con)
        if not insp.has_table("liq_periodo", schema=esquema):
            continue  # el arranque crea la tabla con la columna nueva
        op.add_column("liq_periodo", sa.Column("nombre", sa.String(80), nullable=False, server_default="General"), schema=esquema)
        for uc in insp.get_unique_constraints("liq_periodo", schema=esquema):
            if sorted(uc["column_names"]) == ["anio", "mes", "quincena"]:
                op.drop_constraint(uc["name"], "liq_periodo", type_="unique", schema=esquema)
        op.create_unique_constraint("uq_liq_periodo_nomina", "liq_periodo", ["anio", "mes", "quincena", "nombre"], schema=esquema)


def downgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if not sa.inspect(con).has_table("liq_periodo", schema=esquema):
            continue
        op.drop_constraint("uq_liq_periodo_nomina", "liq_periodo", type_="unique", schema=esquema)
        op.drop_column("liq_periodo", "nombre", schema=esquema)
        op.create_unique_constraint(None, "liq_periodo", ["anio", "mes", "quincena"], schema=esquema)
