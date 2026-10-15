from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.core.plataforma import App

PERMISOS: dict[str, tuple[str, str]] = {
    "planos.procesar": ("Planos", "Procesar planos de empleados y contratos y descargar el archivo listo para SIESA"),
    "planos.configurar": ("Configuración", "Editar alias, correcciones manuales, catálogos de entidades y el salario mínimo"),
}

ROLES_BASE: dict[str, tuple[str, list[str]]] = {
    "Planos SIESA": ("Planos SIESA: procesa los planos de empleados y contratos y mantiene sus alias y catálogos", list(PERMISOS)),
}


def _router() -> APIRouter:
    from app.apps.planos.routes import router

    return router


def _seed(db: Session) -> None:
    from app.apps.planos.services.configuracion import sembrar

    sembrar(db)


APP = App(
    codigo="planos",
    nombre="Planos SIESA",
    descripcion="Deja listos para cargar a SIESA los planos de empleados y contratos: convierte nombres a código, "
                "normaliza y reporta lo dudoso en una hoja de errores.",
    icono="file-spreadsheet",
    color="#7c3aed",
    permisos=PERMISOS,
    roles_base=ROLES_BASE,
    router=_router,
    seed=_seed,
)
