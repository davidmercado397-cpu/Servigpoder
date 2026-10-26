"""Costeo y MFP's: habilitado en Servigpoder para quienes administran la plataforma

Las tablas (cst_*) las crea el arranque en el esquema de cada empresa.

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-26
"""
import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    empresa = con.execute(sa.text("select id from empresa where codigo = 'servigpoder'")).scalar()
    if empresa is None:
        return
    con.execute(sa.text("insert into empresa_app (empresa_id, app) select :e, 'costeo' "
                        "where not exists (select 1 from empresa_app where empresa_id = :e and app = 'costeo')"), {"e": empresa})
    # Los administradores entran para configurar el desarrollo; a los demás se les da acceso desde Usuarios
    con.execute(sa.text(
        "insert into usuario_empresa_app (usuario_id, empresa_id, app) "
        "select distinct ur.usuario_id, :e, 'costeo' from usuario_rol ur join rol r on r.id = ur.rol_id "
        "where r.nombre = 'Administrador' and not exists (select 1 from usuario_empresa_app x "
        "where x.usuario_id = ur.usuario_id and x.empresa_id = :e and x.app = 'costeo')"), {"e": empresa})


def downgrade() -> None:
    con = op.get_bind()
    con.execute(sa.text("delete from usuario_empresa_app where app = 'costeo'"))
    con.execute(sa.text("delete from empresa_app where app = 'costeo'"))
