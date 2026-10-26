"""Validación de nómina: cuotas que solo se pagan en la 2.ª quincena (135 auxilio de movilidad administrativo)

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-26
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if not sa.inspect(con).has_table("nom_parametros", schema=esquema):
            continue  # la crea el arranque con la columna nueva
        op.add_column("nom_parametros", sa.Column("solo_segunda_quincena", sa.String(200), nullable=False, server_default="135"),
                      schema=esquema)


def downgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if sa.inspect(con).has_table("nom_parametros", schema=esquema):
            op.drop_column("nom_parametros", "solo_segunda_quincena", schema=esquema)
