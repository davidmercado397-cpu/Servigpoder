"""Liquidador: umbral semanal de horas por periodo (opcional al liquidar) y novedades que lo justifican

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-27
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None

# Novedades que se marcan como justificadas de entrada (editable en Turnos)
JUSTIFICADAS = ("V", "VAC", "LR", "LM", "LP", "LL", "LUT", "LIC", "IEG", "INC")


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        insp = sa.inspect(con)
        if not insp.has_table("liq_periodo", schema=esquema):
            continue  # el arranque crea las tablas con las columnas nuevas
        op.add_column("liq_turno", sa.Column("justifica_umbral", sa.Boolean(), nullable=False, server_default=sa.false()), schema=esquema)
        op.add_column("liq_periodo", sa.Column("umbral_activo", sa.Boolean(), nullable=False, server_default=sa.false()), schema=esquema)
        op.add_column("liq_periodo", sa.Column("umbral_horas", sa.Numeric(5, 2), nullable=False, server_default="42"), schema=esquema)
        op.add_column("liq_periodo", sa.Column("umbral_horas_novedad", sa.Numeric(4, 2), nullable=False, server_default="7"), schema=esquema)
        op.add_column("liq_resultado", sa.Column("umbral_semanas", sa.JSON(), nullable=True), schema=esquema)
        con.execute(sa.text(f'update "{esquema}".liq_turno set justifica_umbral = true '
                            f"where incapacidad or upper(codigo) in :codigos").bindparams(sa.bindparam("codigos", expanding=True)),
                    {"codigos": list(JUSTIFICADAS)})


def downgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if not sa.inspect(con).has_table("liq_periodo", schema=esquema):
            continue
        op.drop_column("liq_resultado", "umbral_semanas", schema=esquema)
        for c in ("umbral_horas_novedad", "umbral_horas", "umbral_activo"):
            op.drop_column("liq_periodo", c, schema=esquema)
        op.drop_column("liq_turno", "justifica_umbral", schema=esquema)
