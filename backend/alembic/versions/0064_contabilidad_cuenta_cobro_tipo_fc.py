"""Contabilidad: las cuentas de cobro van con Tipo Documento FC (columna B) y Prefijo DSS (columna C).

Revision ID: 0064
Revises: 0063
Create Date: 2026-11-26
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if sa.inspect(con).has_table("ctb_config", schema=esquema):
            con.execute(sa.text(f"UPDATE \"{esquema}\".ctb_config SET tipo_documento_ds = 'FC' WHERE tipo_documento_ds IN ('DS', 'DSS')"))
            con.execute(sa.text(f"ALTER TABLE \"{esquema}\".ctb_config ALTER COLUMN tipo_documento_ds SET DEFAULT 'FC'"))


def downgrade() -> None:
    pass
