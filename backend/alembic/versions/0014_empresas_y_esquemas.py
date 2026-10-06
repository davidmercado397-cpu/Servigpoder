"""Empresas: cada una con sus datos en su propio esquema

- Tablas del núcleo nuevas: empresa, empresa_app, usuario_empresa_app y auditoria.empresa.
- Las tablas de los desarrollos salen de public: las del Liquidador de horas (liq_*) a emp_sera y el resto
  (capacidad operativa, validación de nómina) a emp_servigpoder. ALTER TABLE … SET SCHEMA conserva datos,
  índices, secuencias y llaves.
- Las tablas que le faltan a cada esquema las crea el arranque (preparar_esquema), con la estructura vigente.
- Cada usuario conserva lo que veía: entra a los desarrollos de los que su rol tiene algún permiso, en la
  empresa donde quedaron esos datos.

Migraciones futuras de tablas de un desarrollo: aplicarlas en cada esquema, p. ej.
    for esquema in esquemas(op.get_bind()):
        op.add_column("liq_turno", sa.Column(...), schema=esquema)

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-06
"""
import sqlalchemy as sa
from alembic import op

from app.core.db import BaseEmpresa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

EMPRESAS = (
    ("servigpoder", "Servigpoder", ("capacidad", "nomina", "reporte")),
    ("sera", "SERA", ("liquidador",)),
)


def _esquema_de_tabla(nombre: str) -> str:
    return "emp_sera" if nombre.startswith("liq_") else "emp_servigpoder"


def upgrade() -> None:
    import app.apps.capacidad.models  # noqa: F401  (registra las tablas de cada desarrollo)
    import app.apps.liquidador.models  # noqa: F401
    import app.apps.nomina.models  # noqa: F401

    op.create_table(
        "empresa",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.String(length=20), nullable=False),
        sa.Column("nombre", sa.String(length=120), nullable=False),
        sa.Column("esquema", sa.String(length=40), nullable=False),
        sa.Column("activa", sa.Boolean(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("esquema"),
    )
    op.create_index("ix_empresa_codigo", "empresa", ["codigo"], unique=True)
    op.create_table(
        "empresa_app",
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column("app", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresa.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("empresa_id", "app"),
    )
    op.create_table(
        "usuario_empresa_app",
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column("app", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresa.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("usuario_id", "empresa_id", "app"),
    )
    op.add_column("auditoria", sa.Column("empresa", sa.String(length=20), nullable=True))
    op.create_index("ix_auditoria_empresa", "auditoria", ["empresa"])

    con = op.get_bind()
    for codigo, nombre, apps in EMPRESAS:
        con.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "emp_{codigo}"'))
        empresa_id = con.execute(sa.text(
            "insert into empresa (codigo, nombre, esquema, activa) values (:c, :n, :e, true) returning id"),
            {"c": codigo, "n": nombre, "e": f"emp_{codigo}"}).scalar()
        for a in apps:
            con.execute(sa.text("insert into empresa_app (empresa_id, app) values (:e, :a)"), {"e": empresa_id, "a": a})

    # Mover los datos existentes a su empresa
    publicas = set(sa.inspect(con).get_table_names(schema="public"))
    for tabla in BaseEmpresa.metadata.tables.values():
        if tabla.name in publicas:
            con.execute(sa.text(f'ALTER TABLE public."{tabla.name}" SET SCHEMA "{_esquema_de_tabla(tabla.name)}"'))

    # Cada usuario entra a lo que ya veía (algún permiso del desarrollo), en la empresa que lo tiene habilitado
    con.execute(sa.text(
        "insert into usuario_empresa_app (usuario_id, empresa_id, app) "
        "select distinct ur.usuario_id, ea.empresa_id, ea.app from usuario_rol ur "
        "join rol_permiso rp on rp.rol_id = ur.rol_id "
        "join empresa_app ea on rp.permiso_codigo like ea.app || '.%'"))


def downgrade() -> None:
    import app.apps.capacidad.models  # noqa: F401
    import app.apps.liquidador.models  # noqa: F401
    import app.apps.nomina.models  # noqa: F401

    con = op.get_bind()
    for tabla in BaseEmpresa.metadata.tables.values():
        origen = _esquema_de_tabla(tabla.name)
        if tabla.name in set(sa.inspect(con).get_table_names(schema=origen)):
            con.execute(sa.text(f'ALTER TABLE "{origen}"."{tabla.name}" SET SCHEMA public'))
    op.drop_index("ix_auditoria_empresa", table_name="auditoria")
    op.drop_column("auditoria", "empresa")
    op.drop_table("usuario_empresa_app")
    op.drop_table("empresa_app")
    op.drop_table("empresa")
    # Los esquemas de las empresas se conservan (pueden tener tablas creadas al arrancar)
