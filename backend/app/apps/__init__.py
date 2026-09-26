"""Registro de los desarrollos de la plataforma.

Para agregar un desarrollo nuevo:
1. Crear `app/apps/<codigo>/` con `manifest.py` (APP = App(...)), models, routes y services.
2. Agregarlo a la lista `APPS` de abajo.
3. Crear su migración de Alembic (`alembic revision --autogenerate`).
4. Crear sus pantallas en `frontend/src/app/(plataforma)/<codigo>/` y registrarla en el portal.
"""

from app.apps.capacidad.manifest import APP as CAPACIDAD
from app.core.plataforma import App

APPS: list[App] = [CAPACIDAD]


def por_codigo(codigo: str) -> App | None:
    return next((a for a in APPS if a.codigo == codigo), None)
