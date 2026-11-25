"""Contabilidad: las cuentas de cobro van con Tipo Documento DSS (no DS), igual que el prefijo.

Revision ID: 0060
Revises: 0059
Create Date: 2026-11-25
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if sa.inspect(con).has_table("ctb_config", schema=esquema):
            con.execute(sa.text(f"UPDATE \"{esquema}\".ctb_config SET tipo_documento_ds = 'DSS' WHERE tipo_documento_ds = 'DS'"))
            con.execute(sa.text(f"ALTER TABLE \"{esquema}\".ctb_config ALTER COLUMN tipo_documento_ds SET DEFAULT 'DSS'"))


def downgrade() -> None:
    pass
