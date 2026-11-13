"""MFP: la bolsa de publicidad y la reserva de representación son gastos del costeo, no de la MFP. Se quitan de las MFP
(las que no tienen movimientos) y sus tipos dejan de ofrecerse.

Revision ID: 0046
Revises: 0045
Create Date: 2026-11-13
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None

CODIGOS = "('PUBLICIDAD', 'REPRESENTACION')"


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        insp = sa.inspect(con)
        if not (insp.has_table("cst_mfp_item", schema=esquema) and insp.has_table("cst_tipo_item", schema=esquema)):
            continue
        e = f'"{esquema}"'
        con.execute(sa.text(
            f"delete from {e}.cst_mfp_item i using {e}.cst_tipo_item t where i.tipo_id = t.id and t.codigo in {CODIGOS} "
            f"and not exists (select 1 from {e}.cst_movimiento m where m.item_id = i.id)"))
        con.execute(sa.text(f"update {e}.cst_tipo_item set activo = false where codigo in {CODIGOS}"))


def downgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if sa.inspect(con).has_table("cst_tipo_item", schema=esquema):
            con.execute(sa.text(f'update "{esquema}".cst_tipo_item set activo = true where codigo in {CODIGOS}'))
