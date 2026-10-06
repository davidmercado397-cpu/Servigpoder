"""Liquidador: cálculo de la nómina (tarifas por vigencia, salario por empleado, préstamos y embargos)

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-06
"""
import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

PERMISOS = (
    ("liquidador.nomina.ver", "Nómina", "Ver la nómina calculada (devengado, deducciones y neto), salarios, recargos y descuentos"),
    ("liquidador.nomina.gestionar", "Nómina", "Editar los % de recargos, el salario mínimo, el salario de cada empleado, préstamos y embargos"),
)


def upgrade() -> None:
    op.add_column("liq_empleado", sa.Column("salario", sa.Numeric(14, 2), nullable=True))
    op.add_column("liq_resultado", sa.Column("nomina", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("liq_resultado", sa.Column("devengado", sa.Numeric(14, 2), nullable=False, server_default="0"))
    op.add_column("liq_resultado", sa.Column("neto", sa.Numeric(14, 2), nullable=False, server_default="0"))
    op.create_table(
        "liq_tarifa",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("vigente_desde", sa.Date(), nullable=False),
        sa.Column("smlmv", sa.Numeric(14, 2), nullable=False),
        sa.Column("auxilio_transporte", sa.Numeric(14, 2), nullable=False),
        sa.Column("horas_mes", sa.Integer(), nullable=False),
        sa.Column("salud_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("pension_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("porcentajes", sa.JSON(), nullable=False),
        sa.Column("nota", sa.String(length=300), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_liq_tarifa_vigente_desde", "liq_tarifa", ["vigente_desde"], unique=True)
    op.create_table(
        "liq_descuento",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("empleado_id", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("descripcion", sa.String(length=200), nullable=False),
        sa.Column("valor_mensual", sa.Numeric(14, 2), nullable=True),
        sa.Column("porcentaje", sa.Numeric(5, 2), nullable=True),
        sa.Column("monto_total", sa.Numeric(14, 2), nullable=True),
        sa.Column("desde", sa.Date(), nullable=False),
        sa.Column("hasta", sa.Date(), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["empleado_id"], ["liq_empleado.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_liq_descuento_empleado_id", "liq_descuento", ["empleado_id"])

    # Los permisos nuevos los recibe el rol Liquidador ya creado (el Administrador los recibe en el seed)
    con = op.get_bind()
    for codigo, modulo, descripcion in PERMISOS:
        if not con.execute(sa.text("select 1 from permiso where codigo = :c"), {"c": codigo}).first():
            con.execute(sa.text("insert into permiso (codigo, modulo, descripcion) values (:c, :m, :d)"),
                        {"c": codigo, "m": modulo, "d": descripcion})
        con.execute(sa.text(
            "insert into rol_permiso (rol_id, permiso_codigo) select id, cast(:c as varchar) from rol where nombre = 'Liquidador' "
            "and id not in (select rol_id from rol_permiso where permiso_codigo = cast(:c as varchar))"), {"c": codigo})


def downgrade() -> None:
    op.drop_table("liq_descuento")
    op.drop_table("liq_tarifa")
    op.drop_column("liq_resultado", "neto")
    op.drop_column("liq_resultado", "devengado")
    op.drop_column("liq_resultado", "nomina")
    op.drop_column("liq_empleado", "salario")
    op.get_bind().execute(sa.text("delete from permiso where codigo like 'liquidador.nomina.%'"))
