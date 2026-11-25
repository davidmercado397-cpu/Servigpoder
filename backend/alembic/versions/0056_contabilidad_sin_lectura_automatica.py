"""Contabilidad: el correo se revisa solo con el botón «Revisar correo»; se quitan las columnas de la lectura automática.

Revision ID: 0056
Revises: 0055
Create Date: 2026-11-25
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if sa.inspect(con).has_table("ctb_config", schema=esquema):
            con.execute(sa.text(f'ALTER TABLE "{esquema}".ctb_config DROP COLUMN IF EXISTS activo'))
            con.execute(sa.text(f'ALTER TABLE "{esquema}".ctb_config DROP COLUMN IF EXISTS minutos'))


def downgrade() -> None:
    pass
