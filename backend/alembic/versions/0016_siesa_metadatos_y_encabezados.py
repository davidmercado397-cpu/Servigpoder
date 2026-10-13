"""Instructivos SIESA: metadatos (módulo, fecha, sección) y encabezado de contexto en cada fragmento

La búsqueda pasa a indexar encabezado + texto. Los fragmentos ya cargados toman como encabezado el título de
su documento (su sección queda vacía hasta volver a cargar el PDF).

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-14
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if not sa.inspect(con).has_table("siesa_fragmento", schema=esquema):
            continue  # la crea el arranque con la estructura nueva (el índice por módulo también lo crea el arranque)
        op.add_column("siesa_documento", sa.Column("modulo", sa.String(80), nullable=False, server_default=""), schema=esquema)
        op.add_column("siesa_documento", sa.Column("fecha", sa.Date(), nullable=True), schema=esquema)
        op.add_column("siesa_fragmento", sa.Column("seccion", sa.String(300), nullable=False, server_default=""), schema=esquema)
        op.add_column("siesa_fragmento", sa.Column("encabezado", sa.String(500), nullable=False, server_default=""), schema=esquema)
        con.execute(sa.text(f'update "{esquema}".siesa_fragmento f set encabezado = left(d.titulo, 500) '
                            f'from "{esquema}".siesa_documento d where d.id = f.documento_id'))
        con.execute(sa.text(f'drop index if exists "{esquema}".ix_siesa_fragmento_texto'))
        con.execute(sa.text(f'create index ix_siesa_fragmento_texto on "{esquema}".siesa_fragmento '
                            "using gin (to_tsvector('spanish'::regconfig, (encabezado || ' ' || texto)))"))


def downgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if not sa.inspect(con).has_table("siesa_fragmento", schema=esquema):
            continue
        con.execute(sa.text(f'drop index if exists "{esquema}".ix_siesa_fragmento_texto'))
        con.execute(sa.text(f'create index ix_siesa_fragmento_texto on "{esquema}".siesa_fragmento '
                            "using gin (to_tsvector('spanish'::regconfig, texto))"))
        op.drop_column("siesa_fragmento", "encabezado", schema=esquema)
        op.drop_column("siesa_fragmento", "seccion", schema=esquema)
        op.drop_column("siesa_documento", "fecha", schema=esquema)
        op.drop_column("siesa_documento", "modulo", schema=esquema)
