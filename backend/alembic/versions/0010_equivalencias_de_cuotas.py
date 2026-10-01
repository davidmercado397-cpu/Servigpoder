"""Validación de nómina: cuotas que se pagan con otro concepto (152 RODAMIENTO_ADM → 129 RODAMIENTO)

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-01
"""
import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("nom_parametros", sa.Column("equivalencias_cuotas", sa.String(length=200), nullable=False, server_default="152=129"))


def downgrade() -> None:
    op.drop_column("nom_parametros", "equivalencias_cuotas")
