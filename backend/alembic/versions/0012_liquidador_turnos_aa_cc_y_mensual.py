"""Liquidador: turnos AA y CC (12 h diurno y nocturno) y periodos mensuales

Los periodos mensuales usan quincena = 0 (no cambia el esquema). AA y CC se agregan a las bases que ya
tienen turnos; en una base nueva los siembra la configuración inicial.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-06
"""
import json
from datetime import time
from decimal import Decimal

import sqlalchemy as sa
from alembic import op

from app.apps.liquidador.dominio.matriz import build_shift_matrix

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

TURNOS = (
    ("AA", "06 a 18 (12 h)", time(6), time(18)),
    ("CC", "18 a 06 (12 h)", time(18), time(6)),
)


def upgrade() -> None:
    con = op.get_bind()
    if con.execute(sa.text("SELECT count(*) FROM liq_turno")).scalar() == 0:
        return  # base nueva: los siembra la configuración inicial
    nocturna = con.execute(sa.text("SELECT hora_inicio_nocturna FROM liq_parametros ORDER BY id LIMIT 1")).scalar() or 19
    for codigo, nombre, inicio, fin in TURNOS:
        if con.execute(sa.text("SELECT 1 FROM liq_turno WHERE upper(codigo) = :c"), {"c": codigo}).first():
            continue
        matriz = build_shift_matrix(Decimal("12"), Decimal("0"), inicio, nocturna)
        con.execute(sa.text(
            "INSERT INTO liq_turno (codigo, nombre, hora_inicio, hora_fin, horas_ordinarias, horas_extras, matriz, "
            "remunerado, incapacidad, activo) VALUES (:c, :n, :i, :f, 12, 0, CAST(:m AS json), true, false, true)"),
            {"c": codigo, "n": nombre, "i": inicio, "f": fin, "m": json.dumps(matriz)})


def downgrade() -> None:
    pass  # los turnos pueden estar en uso: no se borran
