"""Liquidador: en la nómina por horas una persona puede tener varias líneas el mismo día (varios puestos); el día guarda
los turnos adicionales y el código combinado («H4+H4»).

Revision ID: 0039
Revises: 0038
Create Date: 2026-10-29
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if not sa.inspect(con).has_table("liq_dia", schema=esquema):
            continue
        op.add_column("liq_dia", sa.Column("turnos_extra", sa.JSON(), nullable=False, server_default=sa.text("'[]'")), schema=esquema)
        op.alter_column("liq_dia", "codigo", type_=sa.String(40), existing_type=sa.String(8), schema=esquema)


def downgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if sa.inspect(con).has_table("liq_dia", schema=esquema):
            op.drop_column("liq_dia", "turnos_extra", schema=esquema)
