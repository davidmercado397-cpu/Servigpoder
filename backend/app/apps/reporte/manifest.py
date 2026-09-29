from fastapi import APIRouter

from app.core.plataforma import App

PERMISOS: dict[str, tuple[str, str]] = {
    "reporte.generar": ("Reporte de programación", "Cargar el Excel de programación de SIESA y descargar el PDF por ubicación y puesto"),
}

ROLES_BASE: dict[str, tuple[str, list[str]]] = {
    "Consulta de programación": ("Reporte de programación: genera el PDF de la programación por ubicación y puesto", list(PERMISOS)),
}


def _router() -> APIRouter:
    from app.apps.reporte.routes import router

    return router


APP = App(
    codigo="reporte",
    nombre="Reporte de programación",
    descripcion="Convierte el Excel de programación de SIESA en un PDF ordenado por ubicación y puesto, listo para imprimir.",
    icono="file-text",
    color="#7c3aed",
    permisos=PERMISOS,
    roles_base=ROLES_BASE,
    router=_router,
)
