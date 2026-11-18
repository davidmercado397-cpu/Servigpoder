"""Nómina Speed: la quincena guarda el resultado de la última programación importada (para resolver después a quienes
no están en el Listado: crearlos, asignarlos a un empleado o descartarlos).

Revision ID: 0050
Revises: 0049
Create Date: 2026-11-18
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        insp = sa.inspect(con)
        if not insp.has_table("spd_periodo", schema=esquema):
            continue  # la crea el arranque con todas sus columnas
        if "programacion_resultado" not in {c["name"] for c in insp.get_columns("spd_periodo", schema=esquema)}:
            op.add_column("spd_periodo", sa.Column("programacion_resultado", sa.JSON(), nullable=True), schema=esquema)


def downgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if sa.inspect(con).has_table("spd_periodo", schema=esquema):
            op.drop_column("spd_periodo", "programacion_resultado", schema=esquema)
