"""Permiso del asistente de IA para los roles existentes

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-25
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    existe = conn.execute(sa.text("select 1 from permiso where codigo = 'asistente.usar'")).first()
    if not existe:
        conn.execute(sa.text(
            "insert into permiso (codigo, modulo, descripcion) values "
            "('asistente.usar', 'Asistente IA', 'Hacer preguntas al asistente sobre los datos que su rol puede ver')"
        ))
    # Los roles base ya creados reciben el permiso (el Administrador lo recibe en el seed)
    conn.execute(sa.text(
        "insert into rol_permiso (rol_id, permiso_codigo) "
        "select id, 'asistente.usar' from rol where nombre in ('Programador', 'Nómina') "
        "and id not in (select rol_id from rol_permiso where permiso_codigo = 'asistente.usar')"
    ))


def downgrade() -> None:
    op.get_bind().execute(sa.text("delete from permiso where codigo = 'asistente.usar'"))
