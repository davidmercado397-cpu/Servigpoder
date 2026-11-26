"""Contabilidad: toda línea negativa queda fuera del plano y su valor se resta de los otros productos de la factura
(también en las facturas ya leídas que no están contabilizadas).

Revision ID: 0066
Revises: 0065
Create Date: 2026-11-26
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if not sa.inspect(con).has_table("ctb_linea", schema=esquema):
            continue
        e = f'"{esquema}"'
        con.execute(sa.text(
            f"UPDATE {e}.ctb_linea l SET excluida = true FROM {e}.ctb_factura f "
            f"WHERE l.factura_id = f.id AND f.estado <> 'contabilizada' AND (l.subtotal < 0 OR l.valor_unitario < 0)"))


def downgrade() -> None:
    pass
