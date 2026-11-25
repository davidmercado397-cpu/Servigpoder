"""Contabilidad: modelo de IA propio del desarrollo (vacío = el general de la plataforma).

Revision ID: 0057
Revises: 0056
Create Date: 2026-11-25
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if sa.inspect(con).has_table("ctb_config", schema=esquema):
            con.execute(sa.text(f'ALTER TABLE "{esquema}".ctb_config ADD COLUMN IF NOT EXISTS modelo VARCHAR(150) NOT NULL DEFAULT \'\''))


def downgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if sa.inspect(con).has_table("ctb_config", schema=esquema):
            con.execute(sa.text(f'ALTER TABLE "{esquema}".ctb_config DROP COLUMN IF EXISTS modelo'))
