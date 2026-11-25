"""Desarrollo «Contabilidad» para Speed (facturas de compra por correo → plano de World Office). Sus tablas las crea el
arranque; los administradores quedan con acceso.

Revision ID: 0055
Revises: 0054
Create Date: 2026-11-25
"""
import sqlalchemy as sa
from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    empresa_id = con.execute(sa.text("select id from empresa where codigo = 'speed'")).scalar()
    if empresa_id is None:
        return
    if not con.execute(sa.text("select 1 from empresa_app where empresa_id = :e and app = 'contabilidad'"), {"e": empresa_id}).scalar():
        con.execute(sa.text("insert into empresa_app (empresa_id, app) values (:e, 'contabilidad')"), {"e": empresa_id})
    con.execute(sa.text(
        "insert into usuario_empresa_app (usuario_id, empresa_id, app) "
        "select distinct ur.usuario_id, :e, 'contabilidad' from usuario_rol ur join rol r on r.id = ur.rol_id "
        "where r.nombre = 'Administrador' and not exists (select 1 from usuario_empresa_app x "
        "where x.usuario_id = ur.usuario_id and x.empresa_id = :e and x.app = 'contabilidad')"), {"e": empresa_id})


def downgrade() -> None:
    con = op.get_bind()
    con.execute(sa.text("delete from usuario_empresa_app where app = 'contabilidad'"))
    con.execute(sa.text("delete from empresa_app where app = 'contabilidad'"))
