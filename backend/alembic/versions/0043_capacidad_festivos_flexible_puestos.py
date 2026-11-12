"""Capacidad operativa: horario de festivos (aplica en cualquier festivo), horario flexible (horas por día sin hora fija)
y puestos corregidos a mano (ciudad y nombre que la importación no pisa).

Revision ID: 0043
Revises: 0042
Create Date: 2026-11-12
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None

COLUMNAS = {
    "puesto": [("ciudad_manual", sa.String(80), None), ("descripcion_manual", sa.Boolean(), "false")],
    "matriz_puesto": [("horario_flexible", sa.Boolean(), "false")],
    "matriz_franja": [("festivos", sa.Boolean(), "false")],
}


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        insp = sa.inspect(con)
        for tabla, columnas in COLUMNAS.items():
            if not insp.has_table(tabla, schema=esquema):
                continue
            existentes = {c["name"] for c in insp.get_columns(tabla, schema=esquema)}
            for nombre, tipo, defecto in columnas:
                if nombre not in existentes:
                    op.add_column(tabla, sa.Column(nombre, tipo, nullable=defecto is None, server_default=defecto), schema=esquema)


def downgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        insp = sa.inspect(con)
        for tabla, columnas in COLUMNAS.items():
            if insp.has_table(tabla, schema=esquema):
                for nombre, _, _ in columnas:
                    op.drop_column(tabla, nombre, schema=esquema)
