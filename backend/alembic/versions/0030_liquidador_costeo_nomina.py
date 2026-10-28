"""Liquidador: costeo de nómina (costo empresa sin que cuente como pagado) y sus permisos

La tabla liq_costeo la crea el arranque en el esquema de cada empresa.

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-28
"""
import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

PERMISOS = (
    ("liquidador.costeo.ver", "Costeo de nómina", "Ver los costeos de nómina (costo empresa de un Excel de turnos, sin pagarlo)"),
    ("liquidador.costeo.gestionar", "Costeo de nómina", "Crear, recalcular y eliminar costeos de nómina"),
)


def upgrade() -> None:
    con = op.get_bind()
    for codigo, modulo, descripcion in PERMISOS:
        if not con.execute(sa.text("select 1 from permiso where codigo = :c"), {"c": codigo}).first():
            con.execute(sa.text("insert into permiso (codigo, modulo, descripcion) values (:c, :m, :d)"),
                        {"c": codigo, "m": modulo, "d": descripcion})
        # El rol Liquidador ya creado los recibe (el Administrador los recibe en el arranque)
        con.execute(sa.text("insert into rol_permiso (rol_id, permiso_codigo) select id, :c from rol where nombre = 'Liquidador' "
                            "and id not in (select rol_id from rol_permiso where permiso_codigo = :c)"), {"c": codigo})


def downgrade() -> None:
    con = op.get_bind()
    for codigo, _, _ in PERMISOS:
        con.execute(sa.text("delete from permiso where codigo = :c"), {"c": codigo})
