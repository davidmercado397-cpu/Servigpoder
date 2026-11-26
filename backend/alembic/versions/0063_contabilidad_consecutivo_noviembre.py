"""Contabilidad (Speed): las facturas de noviembre de 2026 van en la 2611008 en World Office; la siguiente es la 2611009.

Revision ID: 0063
Revises: 0062
Create Date: 2026-11-26
"""
import sqlalchemy as sa
from alembic import op

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    if sa.inspect(con).has_table("ctb_config", schema="emp_speed"):
        con.execute(sa.text('UPDATE "emp_speed".ctb_config SET ultimo_fc = 2611008 WHERE ultimo_fc IS NULL OR ultimo_fc < 2611008'))


def downgrade() -> None:
    pass
