"""Validación de nómina: revisión de la 1.ª quincena (del 1 al 15), además de la 2.ª y la mensual

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-19
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if not sa.inspect(con).has_table("nom_periodo", schema=esquema):
            continue  # la crea el arranque con la estructura nueva
        # Las revisiones quincenales existentes son todas de la 2.ª quincena; la mensual lleva 0
        op.add_column("nom_periodo", sa.Column("quincena", sa.Integer(), nullable=False, server_default="2"), schema=esquema)
        con.execute(sa.text(f"update \"{esquema}\".nom_periodo set quincena = 0 where nomina = 'mensual'"))
        con.execute(sa.text(f'alter table "{esquema}".nom_periodo drop constraint if exists nom_periodo_anio_mes_nomina_key'))
        op.create_unique_constraint("uq_nom_periodo", "nom_periodo", ["anio", "mes", "nomina", "quincena"], schema=esquema)


def downgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if not sa.inspect(con).has_table("nom_periodo", schema=esquema):
            continue
        con.execute(sa.text(f'delete from "{esquema}".nom_periodo where quincena = 1'))
        op.drop_constraint("uq_nom_periodo", "nom_periodo", schema=esquema)
        op.create_unique_constraint("nom_periodo_anio_mes_nomina_key", "nom_periodo", ["anio", "mes", "nomina"], schema=esquema)
        op.drop_column("nom_periodo", "quincena", schema=esquema)
