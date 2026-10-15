"""Marca por empresa: cada empresa puede tener su logo, favicon, fondo y colores; la general queda para el ingreso

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-15
"""
import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("marca", sa.Column("empresa_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_marca_empresa", "marca", "empresa", ["empresa_id"], ["id"], ondelete="CASCADE")
    op.create_unique_constraint("uq_marca_empresa", "marca", ["empresa_id"])
    # El id de la marca pasa a ser autoincremental (la general sigue siendo la 1)
    op.execute("create sequence if not exists marca_id_seq owned by marca.id")
    op.execute("select setval('marca_id_seq', greatest((select max(id) from marca), 1))")
    op.execute("alter table marca alter column id set default nextval('marca_id_seq')")
    # Las imágenes existentes son de la marca general
    op.add_column("marca_imagen", sa.Column("marca_id", sa.Integer(), nullable=False, server_default="1"))
    op.alter_column("marca_imagen", "marca_id", server_default=None)
    op.execute("insert into marca (id, nombre, subtitulo, color_primario, color_acento, color_barra, color_barra_fin, login_fondo, "
               "login_color, login_oscurecer, version) select 1, 'Plataforma Servigpoder', 'Desarrollos internos', '#1d5fbf', '#38bdf8', "
               "'#0f2d5c', '#081a38', 'degradado', '#0f2d5c', 45, 1 where exists (select 1 from marca_imagen) "
               "and not exists (select 1 from marca where id = 1)")
    op.create_foreign_key("fk_marca_imagen_marca", "marca_imagen", "marca", ["marca_id"], ["id"], ondelete="CASCADE")
    op.drop_constraint("marca_imagen_pkey", "marca_imagen", type_="primary")
    op.create_primary_key("marca_imagen_pkey", "marca_imagen", ["marca_id", "tipo"])


def downgrade() -> None:
    op.execute("delete from marca_imagen where marca_id <> 1")
    op.drop_constraint("marca_imagen_pkey", "marca_imagen", type_="primary")
    op.drop_constraint("fk_marca_imagen_marca", "marca_imagen", type_="foreignkey")
    op.drop_column("marca_imagen", "marca_id")
    op.create_primary_key("marca_imagen_pkey", "marca_imagen", ["tipo"])
    op.execute("delete from marca where empresa_id is not null")
    op.drop_constraint("uq_marca_empresa", "marca", type_="unique")
    op.drop_constraint("fk_marca_empresa", "marca", type_="foreignkey")
    op.drop_column("marca", "empresa_id")
