"""Empresa Speed con su desarrollo «Nómina Speed». El esquema y sus tablas los crea el arranque; los administradores
quedan con acceso.

Revision ID: 0048
Revises: 0047
Create Date: 2026-11-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    empresa_id = con.execute(sa.text("select id from empresa where codigo = 'speed'")).scalar()
    if empresa_id is None:
        con.execute(sa.text('CREATE SCHEMA IF NOT EXISTS "emp_speed"'))
        empresa_id = con.execute(sa.text(
            "insert into empresa (codigo, nombre, esquema, activa) values ('speed', 'Speed', 'emp_speed', true) returning id")).scalar()
    if not con.execute(sa.text("select 1 from empresa_app where empresa_id = :e and app = 'speed'"), {"e": empresa_id}).scalar():
        con.execute(sa.text("insert into empresa_app (empresa_id, app) values (:e, 'speed')"), {"e": empresa_id})
    # Los administradores entran al desarrollo (a los demás se les da acceso desde Usuarios)
    con.execute(sa.text(
        "insert into usuario_empresa_app (usuario_id, empresa_id, app) "
        "select distinct ur.usuario_id, :e, 'speed' from usuario_rol ur join rol r on r.id = ur.rol_id "
        "where r.nombre = 'Administrador' and not exists (select 1 from usuario_empresa_app x "
        "where x.usuario_id = ur.usuario_id and x.empresa_id = :e and x.app = 'speed')"), {"e": empresa_id})


def downgrade() -> None:
    con = op.get_bind()
    con.execute(sa.text("delete from usuario_empresa_app where app = 'speed'"))
    con.execute(sa.text("delete from empresa_app where app = 'speed'"))
