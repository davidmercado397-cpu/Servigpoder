"""Contabilidad: líneas fuera del plano (las quita contabilidad o son negativos mínimos de hasta $200). Las facturas ya
leídas que no están contabilizadas dejan fuera sus negativos mínimos.

Revision ID: 0065
Revises: 0064
Create Date: 2026-11-26
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        insp = sa.inspect(con)
        if not insp.has_table("ctb_linea", schema=esquema):
            continue
        e = f'"{esquema}"'
        con.execute(sa.text(f"ALTER TABLE {e}.ctb_linea ADD COLUMN IF NOT EXISTS excluida BOOLEAN NOT NULL DEFAULT false"))
        con.execute(sa.text(
            f"UPDATE {e}.ctb_linea l SET excluida = true FROM {e}.ctb_factura f "
            f"WHERE l.factura_id = f.id AND f.estado <> 'contabilizada' "
            f"AND (l.subtotal < 0 OR l.valor_unitario < 0) AND abs(CASE WHEN l.subtotal <> 0 THEN l.subtotal "
            f"ELSE l.valor_unitario * l.cantidad END) <= 200"))


def downgrade() -> None:
    pass
