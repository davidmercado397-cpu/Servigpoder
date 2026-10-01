from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.core.plataforma import App

PERMISOS: dict[str, tuple[str, str]] = {
    "nomina.ver": ("Validación de nómina", "Ver periodos, alertas, personas e informes"),
    "nomina.cargar": ("Validación de nómina", "Crear periodos, cargar archivos y recalcular"),
    "nomina.revisar": ("Validación de nómina", "Marcar alertas como revisadas, justificadas o error y decidir puestos sin modalidad"),
    "nomina.configurar": ("Validación de nómina", "Configurar códigos que descuentan, grupos de empleados y parámetros"),
}

ROLES_BASE: dict[str, tuple[str, list[str]]] = {
    "Analista de nómina": ("Validación de nómina: carga los archivos del mes, revisa las alertas y configura las reglas", list(PERMISOS)),
}


def _router() -> APIRouter:
    from app.apps.nomina.routes import router

    return router


def _seed(db: Session) -> None:
    from app.apps.nomina.services.servicio import sembrar

    sembrar(db)


APP = App(
    codigo="nomina",
    nombre="Validación de nómina",
    descripcion="Revisa la nómina de las modalidades fijas contra la programación, los maestros y las cuotas, y genera alertas.",
    icono="badge-check",
    color="#b45309",
    permisos=PERMISOS,
    roles_base=ROLES_BASE,
    router=_router,
    seed=_seed,
)
