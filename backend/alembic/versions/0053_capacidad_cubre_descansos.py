"""Capacidad operativa: cada puesto dice si el descanso de sus titulares se cubre con un relevo (todos sí, de entrada).

Revision ID: 0053
Revises: 0052
Create Date: 2026-11-25
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        insp = sa.inspect(con)
        if insp.has_table("puesto", schema=esquema) and \
                "cubre_descansos" not in {c["name"] for c in insp.get_columns("puesto", schema=esquema)}:
            op.add_column("puesto", sa.Column("cubre_descansos", sa.Boolean(), nullable=False, server_default="true"), schema=esquema)


def downgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if sa.inspect(con).has_table("puesto", schema=esquema):
            op.drop_column("puesto", "cubre_descansos", schema=esquema)
