"""Liquidador: modificar la ficha del personal queda solo para el rol «Gestión humana»; el rol «Liquidador» (nómina)
la consulta pero no la modifica ni importa la base de personal o el libro de vacaciones.

Revision ID: 0035
Revises: 0034
Create Date: 2026-10-28
"""
import sqlalchemy as sa
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().execute(sa.text(
        "delete from rol_permiso where permiso_codigo = 'liquidador.personal.gestionar' "
        "and rol_id in (select id from rol where nombre = 'Liquidador')"))


def downgrade() -> None:
    op.get_bind().execute(sa.text(
        "insert into rol_permiso (rol_id, permiso_codigo) select id, 'liquidador.personal.gestionar' from rol "
        "where nombre = 'Liquidador' and id not in "
        "(select rol_id from rol_permiso where permiso_codigo = 'liquidador.personal.gestionar')"))
