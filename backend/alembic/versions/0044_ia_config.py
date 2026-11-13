"""Configuración del agente de IA desde el panel de administración (clave cifrada y modelos); costeo: arma no letal
como opción del puesto (el ARMA NO LETAL del catálogo entra sola en esos puestos)

Revision ID: 0044
Revises: 0043
Create Date: 2026-11-13
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        insp = sa.inspect(con)
        if insp.has_table("cst_catalogo_costo", schema=esquema) and \
                "aplica" in {c["name"] for c in insp.get_columns("cst_catalogo_costo", schema=esquema)}:
            con.execute(sa.text(f'''update "{esquema}".cst_catalogo_costo set aplica = 'noletal' '''
                                "where grupo = 'dotacion_tarifa' and nombre = 'ARMA NO LETAL' and aplica = ''"))
    if sa.inspect(con).has_table("ia_config"):
        return
    op.create_table(
        "ia_config",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("api_key_cifrada", sa.Text(), nullable=True),
        sa.Column("api_key_final", sa.String(8), nullable=True),
        sa.Column("modelo", sa.String(150), nullable=True),
        sa.Column("modelo_costeo", sa.String(150), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("actualizado_por", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["actualizado_por"], ["usuario.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("ia_config")
