"""Liquidador: el tipo de novedad admite 30 caracteres («auxilio_intermunicipal» no cabía en 20) y se corrigen los
afiliados a Colpensiones que la importación de la base marcó como pensionados (por contener «PENSION»).

Los mal marcados quedaron sin fondo de pensiones; los pensionados reales («PENSIONADO VEJEZ - COLPENSIONES») tienen el
fondo. Quien venía como «PENSIONADA VEJEZ» (sin fondo) vuelve a quedar marcado al importar de nuevo la base.

Revision ID: 0040
Revises: 0039
Create Date: 2026-10-29
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        insp = sa.inspect(con)
        if insp.has_table("liq_novedad", schema=esquema):
            op.alter_column("liq_novedad", "tipo", type_=sa.String(30), existing_type=sa.String(20), schema=esquema)
        if insp.has_table("liq_empleado", schema=esquema):
            con.execute(sa.text(f'update "{esquema}".liq_empleado set pensionado = false where pensionado and fondo_pensiones is null'))


def downgrade() -> None:
    pass
