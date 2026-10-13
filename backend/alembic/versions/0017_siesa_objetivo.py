"""Instructivos SIESA: objetivo de cada instructivo (contexto para la IA)

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-14
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if sa.inspect(con).has_table("siesa_documento", schema=esquema):
            op.add_column("siesa_documento", sa.Column("objetivo", sa.Text(), nullable=False, server_default=""), schema=esquema)


def downgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if sa.inspect(con).has_table("siesa_documento", schema=esquema):
            op.drop_column("siesa_documento", "objetivo", schema=esquema)
