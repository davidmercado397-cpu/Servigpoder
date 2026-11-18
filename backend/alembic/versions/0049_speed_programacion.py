"""Nómina Speed: la novedad de la quincena guarda lo que trae el archivo de programación (vacaciones, licencias
remuneradas, renuncia/desprogramado, turnos adicionales TAD/TAN, días sin programación y los códigos por día).

Revision ID: 0049
Revises: 0048
Create Date: 2026-11-18
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None

COLUMNAS = (
    ("desprogramados", sa.Numeric(5, 2), "0"),
    ("permisos_remunerados", sa.Numeric(5, 2), "0"),
    ("vacaciones", sa.Numeric(5, 2), "0"),
    ("turnos_tad", sa.Integer(), "0"),
    ("turnos_tan", sa.Integer(), "0"),
    ("sin_programacion", sa.Numeric(5, 2), "0"),
)


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        insp = sa.inspect(con)
        if not insp.has_table("spd_novedad", schema=esquema):
            continue  # la crea el arranque con todas sus columnas
        existentes = {c["name"] for c in insp.get_columns("spd_novedad", schema=esquema)}
        for nombre, tipo, defecto in COLUMNAS:
            if nombre not in existentes:
                op.add_column("spd_novedad", sa.Column(nombre, tipo, nullable=False, server_default=defecto), schema=esquema)
        if "programacion" not in existentes:
            op.add_column("spd_novedad", sa.Column("programacion", sa.JSON(), nullable=True), schema=esquema)


def downgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if sa.inspect(con).has_table("spd_novedad", schema=esquema):
            for nombre in ("programacion", *(c[0] for c in COLUMNAS)):
                op.drop_column("spd_novedad", nombre, schema=esquema)
