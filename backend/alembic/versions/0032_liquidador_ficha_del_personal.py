"""Liquidador: ficha del personal (datos de gestión humana), historial de contratos y de vacaciones, y sus permisos

Las tablas liq_contrato y liq_vacacion_salida las crea el arranque en el esquema de cada empresa.

Revision ID: 0032
Revises: 0031
Create Date: 2026-10-28
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None

TEXTOS = {"puesto": 200, "tipo_contrato": 40, "rh": 5, "pais_nacimiento": 80, "depto_nacimiento": 80, "ciudad_nacimiento": 80,
          "pais_expedicion": 80, "depto_expedicion": 80, "ciudad_expedicion": 80, "celular": 30, "correo": 150, "direccion": 200,
          "barrio": 120, "ciudad": 80, "eps": 80, "fondo_pensiones": 80, "fondo_cesantias": 80, "caja_compensacion": 80,
          "plan_exequial": 80, "numero_cuenta": 40, "nivel_educativo": 60, "tipo_personal": 20}
FECHAS = ("vacaciones_corte", "fecha_retiro", "fecha_nacimiento", "fecha_expedicion")
PERMISOS = (
    ("liquidador.personal.ver", "Ficha del personal",
     "Ver los datos personales de la ficha (contacto, identificación, seguridad social, cuenta) y los historiales"),
    ("liquidador.personal.gestionar", "Ficha del personal",
     "Editar los datos personales, registrar contratos y vacaciones e importar la base de personal y el libro de vacaciones"),
)


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if not sa.inspect(con).has_table("liq_empleado", schema=esquema):
            continue  # el arranque crea la tabla con las columnas nuevas
        for nombre, largo in TEXTOS.items():
            op.add_column("liq_empleado", sa.Column(nombre, sa.String(largo), nullable=True), schema=esquema)
        for nombre in FECHAS:
            op.add_column("liq_empleado", sa.Column(nombre, sa.Date(), nullable=True), schema=esquema)
        op.add_column("liq_empleado", sa.Column("estado", sa.String(10), nullable=False, server_default="activo"), schema=esquema)
        op.add_column("liq_empleado", sa.Column("sexo", sa.String(1), nullable=True), schema=esquema)
        op.add_column("liq_empleado", sa.Column("estado_civil", sa.Integer(), nullable=True), schema=esquema)
        op.add_column("liq_empleado", sa.Column("extranjero", sa.Boolean(), nullable=False, server_default=sa.false()), schema=esquema)
        op.add_column("liq_empleado", sa.Column("pensionado", sa.Boolean(), nullable=False, server_default=sa.false()), schema=esquema)
        op.add_column("liq_empleado", sa.Column("cursos", sa.Text(), nullable=True), schema=esquema)
    for codigo, modulo, descripcion in PERMISOS:
        if not con.execute(sa.text("select 1 from permiso where codigo = :c"), {"c": codigo}).first():
            con.execute(sa.text("insert into permiso (codigo, modulo, descripcion) values (:c, :m, :d)"),
                        {"c": codigo, "m": modulo, "d": descripcion})
        # Nómina (rol Liquidador) también ve y edita la ficha; el rol «Gestión humana» lo crea el arranque
        con.execute(sa.text("insert into rol_permiso (rol_id, permiso_codigo) select id, cast(:c as varchar) from rol "
                            "where nombre = 'Liquidador' and id not in "
                            "(select rol_id from rol_permiso where permiso_codigo = cast(:c as varchar))"), {"c": codigo})


def downgrade() -> None:
    con = op.get_bind()
    for codigo, _, _ in PERMISOS:
        con.execute(sa.text("delete from permiso where codigo = :c"), {"c": codigo})
    for esquema in esquemas(con):
        if not sa.inspect(con).has_table("liq_empleado", schema=esquema):
            continue
        for nombre in (*TEXTOS, *FECHAS, "estado", "sexo", "estado_civil", "extranjero", "pensionado", "cursos"):
            op.drop_column("liq_empleado", nombre, schema=esquema)
