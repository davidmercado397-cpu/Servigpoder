"""Costeo y MFP's: el comprobante de egreso (CE) se reemplaza por PEL - Pago electrónico

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-27
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if not sa.inspect(con).has_table("cst_tipo_documento", schema=esquema):
            continue  # la siembra del arranque ya trae PEL
        con.execute(sa.text(f'insert into "{esquema}".cst_tipo_documento (codigo, nombre, activo) '
                            f"select 'PEL', 'Pago electrónico', true where not exists "
                            f'(select 1 from "{esquema}".cst_tipo_documento where codigo = \'PEL\')'))
        con.execute(sa.text(f"update \"{esquema}\".cst_movimiento set tipo_documento = 'PEL' where tipo_documento = 'CE'"))
        con.execute(sa.text(f"delete from \"{esquema}\".cst_tipo_documento where codigo = 'CE'"))


def downgrade() -> None:
    pass  # no se recupera el tipo CE: los movimientos quedan como PEL
