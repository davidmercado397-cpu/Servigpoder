"""Liquidador: SERA no tiene vigilantes; quienes quedaron con el cargo por defecto «Vigilante» pasan a «Operario de aseo».
Los descuentos admiten el tipo «cuota» (plan exequial, pólizas…): la columna tipo ya es texto, no requiere cambios.

Revision ID: 0033
Revises: 0032
Create Date: 2026-10-28
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if sa.inspect(con).has_table("liq_empleado", schema=esquema):
            con.execute(sa.text(f'update "{esquema}".liq_empleado set cargo = \'Operario de aseo\' where cargo = \'Vigilante\''))


def downgrade() -> None:
    pass  # no se puede saber quién era vigilante de verdad
