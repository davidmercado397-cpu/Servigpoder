"""Contabilidad: las cuentas de cobro (DS / DSS) llevan un número seguido que no reinicia con el mes. En Speed van por la
345: la siguiente es la 346.

Revision ID: 0059
Revises: 0058
Create Date: 2026-11-25
"""
import sqlalchemy as sa
from alembic import op

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    if sa.inspect(con).has_table("ctb_config", schema="emp_speed"):
        con.execute(sa.text('UPDATE "emp_speed".ctb_config SET ultimo_ds = 345 WHERE ultimo_ds IS NULL'))


def downgrade() -> None:
    pass
