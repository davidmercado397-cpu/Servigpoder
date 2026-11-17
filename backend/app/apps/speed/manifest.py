from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.core.plataforma import App

PERMISOS: dict[str, tuple[str, str]] = {
    "speed.ver": ("Nómina Speed", "Ver empleados, quincenas, liquidaciones y descuentos"),
    "speed.liquidar": ("Nómina Speed", "Importar el Listado, crear quincenas, cargar novedades, liquidar y cerrar"),
    "speed.descuentos": ("Nómina Speed", "Registrar préstamos, embargos, cuotas y pagos adicionales"),
    "speed.configurar": ("Nómina Speed", "Cambiar los parámetros de la nómina (salario mínimo, auxilio, % de salud y pensión…)"),
}

ROLES_BASE: dict[str, tuple[str, list[str]]] = {
    "Nómina Speed": ("Nómina Speed: importa el Listado, liquida las quincenas y maneja los descuentos", list(PERMISOS)),
}


def _router() -> APIRouter:
    from app.apps.speed.routes import router

    return router


def _seed(db: Session) -> None:
    from app.apps.speed.services.servicio import sembrar

    sembrar(db)


APP = App(
    codigo="speed",
    nombre="Nómina Speed",
    descripcion="Liquida la nómina quincenal de Speed desde el Listado de colaboradores y la programación: devengado, deducciones y neto.",
    icono="calculator",
    color="#0e7490",
    permisos=PERMISOS,
    roles_base=ROLES_BASE,
    router=_router,
    seed=_seed,
)
