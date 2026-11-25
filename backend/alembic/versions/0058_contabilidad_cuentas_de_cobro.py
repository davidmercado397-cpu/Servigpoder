"""Contabilidad: cuentas de cobro (Tipo DS, Prefijo DSS, con su propio consecutivo) y el último número usado en World Office
por serie. En Speed las facturas (FC) quedaron en 2608008: la siguiente de agosto es la 2608009.

Revision ID: 0058
Revises: 0057
Create Date: 2026-11-25
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        insp = sa.inspect(con)
        e = f'"{esquema}"'
        if insp.has_table("ctb_config", schema=esquema):
            con.execute(sa.text(f"ALTER TABLE {e}.ctb_config ADD COLUMN IF NOT EXISTS tipo_documento_ds VARCHAR(10) NOT NULL DEFAULT 'DS'"))
            con.execute(sa.text(f"ALTER TABLE {e}.ctb_config ADD COLUMN IF NOT EXISTS prefijo_ds VARCHAR(10) NOT NULL DEFAULT 'DSS'"))
            con.execute(sa.text(f"ALTER TABLE {e}.ctb_config ADD COLUMN IF NOT EXISTS ultimo_fc INTEGER"))
            con.execute(sa.text(f"ALTER TABLE {e}.ctb_config ADD COLUMN IF NOT EXISTS ultimo_ds INTEGER"))
            if esquema == "emp_speed":
                con.execute(sa.text(f"UPDATE {e}.ctb_config SET ultimo_fc = 2608008 WHERE ultimo_fc IS NULL"))
        if insp.has_table("ctb_factura", schema=esquema):
            con.execute(sa.text(f"ALTER TABLE {e}.ctb_factura ADD COLUMN IF NOT EXISTS cuenta_cobro BOOLEAN NOT NULL DEFAULT false"))


def downgrade() -> None:
    pass
