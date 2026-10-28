"""Liquidador: permisos de salud del personal (incapacidades, restricciones médicas) y de tutelas y demandas, solo
para el rol «Gestión humana».

Las tablas liq_cie, liq_incapacidad, liq_restriccion, liq_caso, liq_caso_actuacion y liq_documento las crea el arranque
en el esquema de cada empresa.

Revision ID: 0034
Revises: 0033
Create Date: 2026-10-28
"""
import sqlalchemy as sa
from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None

PERMISOS = (
    ("liquidador.salud.ver", "Salud del personal", "Ver incapacidades (con su diagnóstico CIE), restricciones médicas y sus soportes"),
    ("liquidador.salud.gestionar", "Salud del personal",
     "Registrar incapacidades y restricciones médicas, adjuntar soportes e importar el formato de ausentismo"),
    ("liquidador.juridico.ver", "Tutelas y demandas", "Ver derechos de petición, tutelas, demandas y su seguimiento"),
    ("liquidador.juridico.gestionar", "Tutelas y demandas",
     "Registrar derechos de petición, tutelas y demandas, su seguimiento y sus soportes"),
)


def upgrade() -> None:
    con = op.get_bind()
    for codigo, modulo, descripcion in PERMISOS:
        if not con.execute(sa.text("select 1 from permiso where codigo = :c"), {"c": codigo}).first():
            con.execute(sa.text("insert into permiso (codigo, modulo, descripcion) values (:c, :m, :d)"),
                        {"c": codigo, "m": modulo, "d": descripcion})
        # Solo gestión humana (si el rol aún no existe, el arranque lo crea con estos permisos)
        con.execute(sa.text("insert into rol_permiso (rol_id, permiso_codigo) select id, cast(:c as varchar) from rol "
                            "where nombre = 'Gestión humana' and id not in "
                            "(select rol_id from rol_permiso where permiso_codigo = cast(:c as varchar))"), {"c": codigo})


def downgrade() -> None:
    con = op.get_bind()
    for codigo, _, _ in PERMISOS:
        con.execute(sa.text("delete from rol_permiso where permiso_codigo = :c"), {"c": codigo})
        con.execute(sa.text("delete from permiso where codigo = :c"), {"c": codigo})
