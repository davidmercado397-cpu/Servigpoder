"""Liquidador: código de turno 180 (incapacidad de más de 180 días). No se paga en nómina (lo paga el fondo de pensiones
o nadie), cuenta como tiempo no laborado y SERA provisiona la seguridad social de esos días. Se crea el turno en cada
empresa que tenga el liquidador y aún no lo tenga.

Revision ID: 0037
Revises: 0036
Create Date: 2026-10-29
"""
import json
from datetime import time
from decimal import Decimal

import sqlalchemy as sa
from alembic import op

from app.apps.liquidador.dominio.matriz import build_shift_matrix
from app.core.empresas import esquemas

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    matriz = json.dumps(build_shift_matrix(Decimal("0"), Decimal("0"), time(0, 0), 19), default=float)
    for esquema in esquemas(con):
        if not sa.inspect(con).has_table("liq_turno", schema=esquema):
            continue
        if con.execute(sa.text(f'select 1 from "{esquema}".liq_turno where upper(codigo) = \'180\'')).first():
            continue
        con.execute(sa.text(
            f'insert into "{esquema}".liq_turno (codigo, nombre, hora_inicio, hora_fin, horas_ordinarias, horas_extras, matriz, remunerado, '
            "incapacidad, justifica_umbral, vacaciones, activo, creado_en) values ('180', 'incapacidad de mas de 180 dias', '00:00', '00:00', "
            "0, 0, cast(:m as json), false, false, true, false, true, now())"), {"m": matriz})


def downgrade() -> None:
    pass  # puede haber días cargados con el código
