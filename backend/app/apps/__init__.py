"""Registro de los desarrollos de la plataforma.

Para agregar un desarrollo nuevo:
1. Crear `app/apps/<codigo>/` con `manifest.py` (APP = App(...)), models, routes y services.
2. Agregarlo a la lista `APPS` de abajo.
3. Sus modelos heredan de `BaseEmpresa` (app.core.db): sus tablas existen en el esquema de cada empresa
   y las crea el arranque. Para cambiar tablas ya existentes, la migración de Alembic se aplica en cada
   esquema (`for esquema in esquemas(op.get_bind()): op.add_column(..., schema=esquema)`).
4. Crear sus pantallas en `frontend/src/app/(plataforma)/<codigo>/` y registrarla en el portal.
"""

from app.apps.capacidad.manifest import APP as CAPACIDAD
from app.apps.liquidador.manifest import APP as LIQUIDADOR
from app.apps.nomina.manifest import APP as NOMINA
from app.apps.reporte.manifest import APP as REPORTE
from app.core.plataforma import App

APPS: list[App] = [CAPACIDAD, LIQUIDADOR, REPORTE, NOMINA]


def por_codigo(codigo: str) -> App | None:
    return next((a for a in APPS if a.codigo == codigo), None)
