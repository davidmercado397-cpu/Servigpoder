"""Instructivos SIESA: habilitado en Servigpoder para quienes administran la plataforma

Las tablas (siesa_documento, siesa_fragmento) las crea el arranque en el esquema de cada empresa.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-13
"""
import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    empresa = con.execute(sa.text("select id from empresa where codigo = 'servigpoder'")).scalar()
    if empresa is None:
        return
    con.execute(sa.text("insert into empresa_app (empresa_id, app) select :e, 'siesa' "
                        "where not exists (select 1 from empresa_app where empresa_id = :e and app = 'siesa')"), {"e": empresa})
    # Los administradores entran para cargar los instructivos; a los demás se les da acceso desde Usuarios
    con.execute(sa.text(
        "insert into usuario_empresa_app (usuario_id, empresa_id, app) "
        "select distinct ur.usuario_id, :e, 'siesa' from usuario_rol ur join rol r on r.id = ur.rol_id "
        "where r.nombre = 'Administrador' and not exists (select 1 from usuario_empresa_app x "
        "where x.usuario_id = ur.usuario_id and x.empresa_id = :e and x.app = 'siesa')"), {"e": empresa})


def downgrade() -> None:
    con = op.get_bind()
    con.execute(sa.text("delete from usuario_empresa_app where app = 'siesa'"))
    con.execute(sa.text("delete from empresa_app where app = 'siesa'"))
