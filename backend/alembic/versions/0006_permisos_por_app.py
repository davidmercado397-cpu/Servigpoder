"""Plataforma multi-app: los permisos de Capacidad Operativa pasan a tener el prefijo 'capacidad.'

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-25
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

RENOMBRAR = [
    "maestros.ver", "maestros.gestionar", "matriz.ver", "matriz.gestionar", "programacion.cargar",
    "analisis.ver", "cubrimientos.aprobar", "parametros.gestionar", "asistente.usar",
]


def _mover(conn, desde: str, hacia: str) -> None:
    fila = conn.execute(sa.text("select modulo, descripcion from permiso where codigo = :c"), {"c": desde}).first()
    if fila is None:
        return
    if not conn.execute(sa.text("select 1 from permiso where codigo = :c"), {"c": hacia}).first():
        conn.execute(sa.text("insert into permiso (codigo, modulo, descripcion) values (:c, :m, :d)"),
                     {"c": hacia, "m": fila.modulo, "d": fila.descripcion})
    # Los roles conservan sus permisos con el código nuevo
    conn.execute(sa.text(
        "insert into rol_permiso (rol_id, permiso_codigo) select rol_id, cast(:hacia as varchar) from rol_permiso "
        "where permiso_codigo = cast(:desde as varchar) and rol_id not in "
        "(select rol_id from rol_permiso where permiso_codigo = cast(:hacia as varchar))"
    ), {"desde": desde, "hacia": hacia})
    conn.execute(sa.text("delete from rol_permiso where permiso_codigo = :c"), {"c": desde})
    conn.execute(sa.text("delete from permiso where codigo = :c"), {"c": desde})


def upgrade() -> None:
    conn = op.get_bind()
    for codigo in RENOMBRAR:
        _mover(conn, codigo, f"capacidad.{codigo}")


def downgrade() -> None:
    conn = op.get_bind()
    for codigo in RENOMBRAR:
        _mover(conn, f"capacidad.{codigo}", codigo)
