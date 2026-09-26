"""Liquidador de horas: turnos, festivos, quincenas y horas contadas

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-26
"""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "liq_parametros",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("hora_inicio_nocturna", sa.Integer(), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "liq_turno",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.String(length=8), nullable=False),
        sa.Column("nombre", sa.String(length=80), nullable=False),
        sa.Column("hora_inicio", sa.Time(), nullable=False),
        sa.Column("hora_fin", sa.Time(), nullable=False),
        sa.Column("horas_ordinarias", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("horas_extras", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("matriz", sa.JSON(), nullable=False),
        sa.Column("remunerado", sa.Boolean(), nullable=False),
        sa.Column("incapacidad", sa.Boolean(), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_liq_turno_codigo", "liq_turno", ["codigo"], unique=True)
    op.create_table(
        "liq_festivo_ajuste",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("es_festivo", sa.Boolean(), nullable=False),
        sa.Column("descripcion", sa.String(length=120), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_liq_festivo_ajuste_fecha", "liq_festivo_ajuste", ["fecha"], unique=True)
    op.create_table(
        "liq_empleado",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("documento", sa.String(length=32), nullable=False),
        sa.Column("nombre", sa.String(length=200), nullable=False),
        sa.Column("cargo", sa.String(length=80), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_liq_empleado_documento", "liq_empleado", ["documento"], unique=True)
    op.create_table(
        "liq_periodo",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("anio", sa.Integer(), nullable=False),
        sa.Column("mes", sa.Integer(), nullable=False),
        sa.Column("quincena", sa.Integer(), nullable=False),
        sa.Column("desde", sa.Date(), nullable=False),
        sa.Column("hasta", sa.Date(), nullable=False),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("archivo", sa.String(length=255), nullable=True),
        sa.Column("advertencias", sa.JSON(), nullable=False),
        sa.Column("cargado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("calculado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cerrado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cerrado_por", sa.Integer(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["cerrado_por"], ["usuario.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("anio", "mes", "quincena"),
    )
    op.create_index("ix_liq_periodo_anio", "liq_periodo", ["anio"])
    op.create_table(
        "liq_dia",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("periodo_id", sa.Integer(), nullable=False),
        sa.Column("empleado_id", sa.Integer(), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("turno_id", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.String(length=8), nullable=False),
        sa.Column("tipo_dia", sa.String(length=24), nullable=False),
        sa.Column("clase", sa.String(length=20), nullable=False),
        sa.Column("horas", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["empleado_id"], ["liq_empleado.id"]),
        sa.ForeignKeyConstraint(["periodo_id"], ["liq_periodo.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["turno_id"], ["liq_turno.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("periodo_id", "empleado_id", "fecha"),
    )
    op.create_index("ix_liq_dia_periodo_id", "liq_dia", ["periodo_id"])
    op.create_index("ix_liq_dia_empleado_id", "liq_dia", ["empleado_id"])
    op.create_table(
        "liq_resultado",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("periodo_id", sa.Integer(), nullable=False),
        sa.Column("empleado_id", sa.Integer(), nullable=False),
        sa.Column("horas", sa.JSON(), nullable=False),
        sa.Column("dias", sa.JSON(), nullable=False),
        sa.Column("total_horas", sa.Numeric(precision=7, scale=2), nullable=False),
        sa.ForeignKeyConstraint(["empleado_id"], ["liq_empleado.id"]),
        sa.ForeignKeyConstraint(["periodo_id"], ["liq_periodo.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("periodo_id", "empleado_id"),
    )
    op.create_index("ix_liq_resultado_periodo_id", "liq_resultado", ["periodo_id"])
    op.create_index("ix_liq_resultado_empleado_id", "liq_resultado", ["empleado_id"])


def downgrade() -> None:
    for tabla in ("liq_resultado", "liq_dia", "liq_periodo", "liq_empleado", "liq_festivo_ajuste", "liq_turno", "liq_parametros"):
        op.drop_table(tabla)
