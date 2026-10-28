"""Liquidador: clase de riesgo ARL por empleado y auxilio no prestacional del costeo

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-28
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        insp = sa.inspect(con)
        if insp.has_table("liq_empleado", schema=esquema):
            op.add_column("liq_empleado", sa.Column("arl_clase", sa.Integer(), nullable=True), schema=esquema)
        if insp.has_table("liq_costeo", schema=esquema):  # si no existe, el arranque la crea con la columna
            op.add_column("liq_costeo", sa.Column("auxilio_mensual", sa.Numeric(14, 2), nullable=False, server_default="0"), schema=esquema)


def downgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        insp = sa.inspect(con)
        if insp.has_table("liq_costeo", schema=esquema):
            op.drop_column("liq_costeo", "auxilio_mensual", schema=esquema)
        if insp.has_table("liq_empleado", schema=esquema):
            op.drop_column("liq_empleado", "arl_clase", schema=esquema)
