"""Liquidador: el rol «Administrador SERA» (creado en la plataforma) recibe todo lo de gestión humana: ver y modificar la
ficha del personal (histórico de vacaciones y cuotas pendientes incluidos), incapacidades y restricciones médicas, y
tutelas y demandas. Si el rol no existe, no hace nada.

Revision ID: 0036
Revises: 0035
Create Date: 2026-10-28
"""
import sqlalchemy as sa
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None

PERMISOS = ("liquidador.periodos.ver", "liquidador.personal.ver", "liquidador.personal.gestionar", "liquidador.salud.ver",
            "liquidador.salud.gestionar", "liquidador.juridico.ver", "liquidador.juridico.gestionar")
ROLES = "select id from rol where lower(regexp_replace(trim(nombre), '\\s+', ' ', 'g')) in ('administrador sera', 'admin sera')"


def upgrade() -> None:
    con = op.get_bind()
    for codigo in PERMISOS:
        # El permiso ya existe (migraciones 0032 y 0034); se asigna solo si el rol aún no lo tiene
        con.execute(sa.text(f"insert into rol_permiso (rol_id, permiso_codigo) select id, cast(:c as varchar) from ({ROLES}) r "
                            "where exists (select 1 from permiso where codigo = cast(:c as varchar)) and id not in "
                            "(select rol_id from rol_permiso where permiso_codigo = cast(:c as varchar))"), {"c": codigo})


def downgrade() -> None:
    pass  # no se sabe cuáles de estos permisos tenía el rol antes
