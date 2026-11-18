"""Validación de nómina: la decisión de una alerta guarda los valores con que se tomó; si al recalcular cambian, la
alerta vuelve a pendiente (y lo decidido queda en «anterior»).

Revision ID: 0051
Revises: 0050
Create Date: 2026-11-18
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        insp = sa.inspect(con)
        if not insp.has_table("nom_decision", schema=esquema):
            continue  # la crea el arranque con todas sus columnas
        columnas = {c["name"] for c in insp.get_columns("nom_decision", schema=esquema)}
        for col in ("valores", "anterior"):
            if col not in columnas:
                op.add_column("nom_decision", sa.Column(col, sa.JSON(), nullable=True), schema=esquema)
        # Las decisiones que ya existen toman como foto los valores de la alerta actual (la que se revisó)
        op.execute(f"""
            UPDATE "{esquema}".nom_decision d
               SET valores = json_build_object('esperado', round(a.esperado, 2)::float8, 'pagado', round(a.pagado, 2)::float8)
              FROM "{esquema}".nom_alerta a
             WHERE d.valores IS NULL AND d.estado <> 'pendiente' AND a.periodo_id = d.periodo_id AND a.nomina = d.nomina
               AND a.cedula = d.cedula AND a.tipo = d.tipo AND a.referencia = d.referencia
        """)


def downgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if sa.inspect(con).has_table("nom_decision", schema=esquema):
            op.drop_column("nom_decision", "anterior", schema=esquema)
            op.drop_column("nom_decision", "valores", schema=esquema)
