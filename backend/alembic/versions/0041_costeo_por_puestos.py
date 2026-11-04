"""Costeo y MFP's: costeo por puestos. La dotación de la tarifa dice a qué puestos aplica (gala, overol, arma…) y
cuántos lleva cada hombre o puesto; se crean el arma de fogeo y el servicio de 12 horas de lunes a viernes (1 hombre).

Revision ID: 0041
Revises: 0040
Create Date: 2026-11-04
"""
import sqlalchemy as sa
from alembic import op

from app.core.empresas import esquemas

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None

APLICA = {
    "PANTALÓN": "gala", "CAMISA": "gala", "CORBATA": "gala", "GOLEANA": "gala", "CORREA": "gala", "APELLIDOS (PAR)": "gala",
    "CALZADO HOMBRE": "gala", "OVEROL": "overol", "BOTAS PUNTERA": "overol",
    "CAPA IMPERMEABLE": "todos", "RADIO KENWOOD": "todos", "PORTA RADIOS": "todos", "CARGADOR DE RADIO": "todos",
    "TONFA CON PORTA TONFA": "todos", "MINUTAS": "todos", "EXÁMENES MÉDICOS (OSTEOMUSCULAR, AUDIOMETRÍA Y VISIOMETRÍA)": "todos",
    "PRUEBAS DE SPA": "todos", "CHAPUZA EXTERNA": "arma", "ARMA DE FUEGO": "fuego", "ARMA DE FOGEO": "fogeo",
    "ARMA TRAUMÁTICA": "traumatica",
}
SERVICIO_LV = "Servicio de vigilancia 12 horas de lunes a viernes"


def upgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        insp = sa.inspect(con)
        if not insp.has_table("cst_catalogo_costo", schema=esquema):
            continue
        columnas = {c["name"] for c in insp.get_columns("cst_catalogo_costo", schema=esquema)}
        if "aplica" not in columnas:
            op.add_column("cst_catalogo_costo", sa.Column("aplica", sa.String(20), nullable=False, server_default=""), schema=esquema)
        if "cantidad" not in columnas:
            op.add_column("cst_catalogo_costo", sa.Column("cantidad", sa.Numeric(8, 2), nullable=False, server_default="1"), schema=esquema)
        tabla = f'"{esquema}".cst_catalogo_costo'
        con.execute(sa.text(
            f"insert into {tabla} (grupo, nombre, valor_unitario, vida_util_meses, entregas_anio, por_hombre, activo, fuente, aplica, cantidad) "
            f"select 'dotacion_tarifa', 'ARMA DE FOGEO', 0, 60, null, false, true, '', 'fogeo', 1 "
            f"where not exists (select 1 from {tabla} where grupo = 'dotacion_tarifa' and nombre = 'ARMA DE FOGEO')"))
        for nombre, aplica in APLICA.items():
            con.execute(sa.text(f"update {tabla} set aplica = :aplica where grupo = 'dotacion_tarifa' and nombre = :nombre and aplica = ''"),
                        {"aplica": aplica, "nombre": nombre})
        if insp.has_table("cst_servicio", schema=esquema):
            servicio = f'"{esquema}".cst_servicio'
            con.execute(sa.text(
                f"insert into {servicio} (descripcion, tarifa, hombres, activo) select cast(:d as varchar), 0, 1, true "
                f"where not exists (select 1 from {servicio} where lower(descripcion) like '%lunes a viernes%')"), {"d": SERVICIO_LV})


def downgrade() -> None:
    con = op.get_bind()
    for esquema in esquemas(con):
        if sa.inspect(con).has_table("cst_catalogo_costo", schema=esquema):
            op.drop_column("cst_catalogo_costo", "cantidad", schema=esquema)
            op.drop_column("cst_catalogo_costo", "aplica", schema=esquema)
