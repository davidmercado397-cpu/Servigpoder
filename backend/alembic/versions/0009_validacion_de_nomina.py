"""Validación de nómina: periodos, archivos, resultados, alertas, decisiones y catálogos

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-01
"""
import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "nom_periodo",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("anio", sa.Integer(), nullable=False),
        sa.Column("mes", sa.Integer(), nullable=False),
        sa.Column("nomina", sa.String(length=10), nullable=False),
        sa.Column("historial", sa.JSON(), nullable=False),
        sa.Column("resumen", sa.JSON(), nullable=False),
        sa.Column("calculado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("anio", "mes", "nomina"),
    )
    op.create_table(
        "nom_archivo",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("periodo_id", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("nombre", sa.String(length=255), nullable=False),
        sa.Column("registros", sa.Integer(), nullable=False),
        sa.Column("datos", sa.JSON(), nullable=False),
        sa.Column("cargado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("cargado_por", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["periodo_id"], ["nom_periodo.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cargado_por"], ["usuario.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("periodo_id", "tipo"),
    )
    op.create_index("ix_nom_archivo_periodo_id", "nom_archivo", ["periodo_id"])
    op.create_table(
        "nom_persona",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("periodo_id", sa.Integer(), nullable=False),
        sa.Column("nomina", sa.String(length=10), nullable=False),
        sa.Column("cedula", sa.String(length=30), nullable=False),
        sa.Column("nombre", sa.String(length=200), nullable=False),
        sa.Column("grupo", sa.String(length=80), nullable=False),
        sa.Column("alertas", sa.Integer(), nullable=False),
        sa.Column("detalle", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["periodo_id"], ["nom_periodo.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("periodo_id", "nomina", "cedula"),
    )
    op.create_index("ix_nom_persona_periodo_id", "nom_persona", ["periodo_id"])
    op.create_index("ix_nom_persona_cedula", "nom_persona", ["cedula"])
    op.create_table(
        "nom_alerta",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("periodo_id", sa.Integer(), nullable=False),
        sa.Column("nomina", sa.String(length=10), nullable=False),
        sa.Column("cedula", sa.String(length=30), nullable=False),
        sa.Column("nombre", sa.String(length=200), nullable=False),
        sa.Column("tipo", sa.String(length=40), nullable=False),
        sa.Column("referencia", sa.String(length=40), nullable=False),
        sa.Column("severidad", sa.String(length=10), nullable=False),
        sa.Column("mensaje", sa.Text(), nullable=False),
        sa.Column("esperado", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("pagado", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("nueva", sa.Boolean(), nullable=False),
        sa.Column("datos", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["periodo_id"], ["nom_periodo.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_nom_alerta_periodo_id", "nom_alerta", ["periodo_id"])
    op.create_index("ix_nom_alerta_cedula", "nom_alerta", ["cedula"])
    op.create_index("ix_nom_alerta_tipo", "nom_alerta", ["tipo"])
    op.create_table(
        "nom_decision",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("periodo_id", sa.Integer(), nullable=False),
        sa.Column("nomina", sa.String(length=10), nullable=False),
        sa.Column("cedula", sa.String(length=30), nullable=False),
        sa.Column("tipo", sa.String(length=40), nullable=False),
        sa.Column("referencia", sa.String(length=40), nullable=False),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("comentario", sa.Text(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("decidido_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["periodo_id"], ["nom_periodo.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("periodo_id", "nomina", "cedula", "tipo", "referencia"),
    )
    op.create_index("ix_nom_decision_periodo_id", "nom_decision", ["periodo_id"])
    op.create_table(
        "nom_codigo",
        sa.Column("codigo", sa.String(length=40), nullable=False),
        sa.Column("descripcion", sa.String(length=120), nullable=False),
        sa.Column("descuenta", sa.Boolean(), nullable=False),
        sa.Column("vacaciones", sa.Boolean(), nullable=False),
        sa.Column("revisado", sa.Boolean(), nullable=False),
        sa.Column("visto_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("codigo"),
    )
    op.create_table(
        "nom_grupo",
        sa.Column("nombre", sa.String(length=80), nullable=False),
        sa.Column("tratamiento", sa.String(length=20), nullable=False),
        sa.Column("revisado", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("nombre"),
    )
    op.create_table(
        "nom_puesto_decision",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ubicacion", sa.String(length=40), nullable=False),
        sa.Column("puesto", sa.String(length=40), nullable=False),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("comentario", sa.Text(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("decidido_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ubicacion", "puesto"),
    )
    op.create_table(
        "nom_parametros",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tolerancia", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("smlmv", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("auxilio_transporte", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("horas_dia", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("solo_primera_quincena", sa.String(length=200), nullable=False),
        sa.Column("excluidos_base_embargo", sa.String(length=200), nullable=False),
        sa.Column("embargos_sin_minimo", sa.String(length=200), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    for tabla in ("nom_parametros", "nom_puesto_decision", "nom_grupo", "nom_codigo", "nom_decision", "nom_alerta",
                  "nom_persona", "nom_archivo", "nom_periodo"):
        op.drop_table(tabla)
