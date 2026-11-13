"""Instructivos SIESA: enlace de OneDrive/SharePoint de cada instructivo (el chat lo entrega con la respuesta) y modelo
de IA propio del chat, elegido en Administración → Inteligencia artificial

Revision ID: 0047
Revises: 0046
Create Date: 2026-11-13
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    insp = sa.inspect(con)
    if insp.has_table("ia_config") and "modelo_siesa" not in {c["name"] for c in insp.get_columns("ia_config")}:
        op.add_column("ia_config", sa.Column("modelo_siesa", sa.String(150), nullable=True))
    for esquema in esquemas(con):
        insp = sa.inspect(con)
        if insp.has_table("siesa_documento", schema=esquema) and \
                "enlace" not in {c["name"] for c in insp.get_columns("siesa_documento", schema=esquema)}:
            op.add_column("siesa_documento", sa.Column("enlace", sa.String(1000), nullable=False, server_default=""), schema=esquema)


def downgrade() -> None:
    con = op.get_bind()
    op.drop_column("ia_config", "modelo_siesa")
    for esquema in esquemas(con):
        if sa.inspect(con).has_table("siesa_documento", schema=esquema):
            op.drop_column("siesa_documento", "enlace", schema=esquema)
