"""Liquidador: vacaciones (código marcado como vacaciones, días hábiles y saldo por empleado, promedio por periodo)

La tabla liq_vacacion_base la crea el arranque en el esquema de cada empresa.

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-28
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None

CODIGOS_VACACIONES = ("V", "VAC")


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if not sa.inspect(con).has_table("liq_turno", schema=esquema):
            continue  # el arranque crea las tablas con las columnas nuevas
        op.add_column("liq_turno", sa.Column("vacaciones", sa.Boolean(), nullable=False, server_default=sa.false()), schema=esquema)
        op.add_column("liq_empleado", sa.Column("dias_habiles", sa.String(7), nullable=False, server_default="012345"), schema=esquema)
        op.add_column("liq_empleado", sa.Column("fecha_ingreso", sa.Date(), nullable=True), schema=esquema)
        op.add_column("liq_empleado", sa.Column("vacaciones_previas", sa.Numeric(6, 2), nullable=False, server_default="0"), schema=esquema)
        con.execute(sa.text(f'update "{esquema}".liq_turno set vacaciones = true where not incapacidad and upper(codigo) in :codigos')
                    .bindparams(sa.bindparam("codigos", expanding=True)), {"codigos": list(CODIGOS_VACACIONES)})


def downgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if not sa.inspect(con).has_table("liq_turno", schema=esquema):
            continue
        for c in ("vacaciones_previas", "fecha_ingreso", "dias_habiles"):
            op.drop_column("liq_empleado", c, schema=esquema)
        op.drop_column("liq_turno", "vacaciones", schema=esquema)
