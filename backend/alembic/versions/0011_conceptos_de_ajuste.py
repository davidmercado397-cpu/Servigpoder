"""Validación de nómina: conceptos de ajuste (mayor/menor valor pagado) que no generan alertas

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-02
"""
import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("nom_parametros", sa.Column("conceptos_ajuste", sa.String(length=200), nullable=False, server_default="610,151"))


def downgrade() -> None:
    op.drop_column("nom_parametros", "conceptos_ajuste")
