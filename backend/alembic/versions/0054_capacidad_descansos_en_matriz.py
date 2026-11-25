"""Capacidad operativa: «los descansos se cubren» pasa del puesto (maestros) a la matriz comercial de cada mes.

Lo que ya se haya desmarcado en un puesto queda desmarcado en sus filas de la matriz.

Revision ID: 0054
Revises: 0053
Create Date: 2026-11-25
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        insp = sa.inspect(con)
        if not insp.has_table("matriz_puesto", schema=esquema):
            continue
        if "cubre_descansos" not in {c["name"] for c in insp.get_columns("matriz_puesto", schema=esquema)}:
            op.add_column("matriz_puesto", sa.Column("cubre_descansos", sa.Boolean(), nullable=False, server_default="true"),
                          schema=esquema)
        if insp.has_table("puesto", schema=esquema) and \
                "cubre_descansos" in {c["name"] for c in insp.get_columns("puesto", schema=esquema)}:
            con.execute(sa.text(f'update "{esquema}".matriz_puesto set cubre_descansos = false where puesto_id in '
                                f'(select id from "{esquema}".puesto where cubre_descansos = false)'))
            op.drop_column("puesto", "cubre_descansos", schema=esquema)


def downgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        insp = sa.inspect(con)
        if insp.has_table("matriz_puesto", schema=esquema):
            op.drop_column("matriz_puesto", "cubre_descansos", schema=esquema)
        if insp.has_table("puesto", schema=esquema):
            op.add_column("puesto", sa.Column("cubre_descansos", sa.Boolean(), nullable=False, server_default="true"), schema=esquema)
