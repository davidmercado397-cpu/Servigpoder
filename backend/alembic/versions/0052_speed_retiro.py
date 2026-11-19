"""Nómina Speed: retiro del empleado registrado en la plataforma (fecha y motivo). Quien se retira no se liquida y la
importación del Listado no lo vuelve a activar.

Revision ID: 0052
Revises: 0051
Create Date: 2026-11-19
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        insp = sa.inspect(con)
        if not insp.has_table("spd_empleado", schema=esquema):
            continue  # la crea el arranque con todas sus columnas
        columnas = {c["name"] for c in insp.get_columns("spd_empleado", schema=esquema)}
        if "fecha_retiro" not in columnas:
            op.add_column("spd_empleado", sa.Column("fecha_retiro", sa.Date(), nullable=True), schema=esquema)
        if "motivo_retiro" not in columnas:
            op.add_column("spd_empleado", sa.Column("motivo_retiro", sa.String(200), nullable=False, server_default=""), schema=esquema)


def downgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if sa.inspect(con).has_table("spd_empleado", schema=esquema):
            op.drop_column("spd_empleado", "motivo_retiro", schema=esquema)
            op.drop_column("spd_empleado", "fecha_retiro", schema=esquema)
