from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.core.plataforma import App

PERMISOS: dict[str, tuple[str, str]] = {
    "capacidad.maestros.ver": ("Maestros", "Ver ubicaciones, puestos, catálogos y equivalencias"),
    "capacidad.maestros.gestionar": ("Maestros", "Editar ubicaciones, puestos, catálogos y equivalencias"),
    "capacidad.matriz.ver": ("Matriz comercial", "Ver la matriz comercial"),
    "capacidad.matriz.gestionar": ("Matriz comercial", "Editar, proyectar y aprobar la matriz comercial"),
    "capacidad.programacion.cargar": ("Programación", "Cargar el Excel de programación de SIESA"),
    "capacidad.analisis.ver": ("Análisis", "Ver tablero, cobertura, hallazgos y reportes"),
    "capacidad.cubrimientos.aprobar": ("Nómina", "Aprobar o rechazar cubrimientos y turnos adicionales"),
    "capacidad.parametros.gestionar": ("Configuración", "Configurar umbrales de alertas"),
    "capacidad.asistente.usar": ("Asistente IA", "Hacer preguntas al asistente sobre los datos que su rol puede ver"),
}

ROLES_BASE: dict[str, tuple[str, list[str]]] = {
    "Programador": (
        "Capacidad Operativa: carga la programación, mantiene la matriz y analiza la cobertura",
        ["capacidad.maestros.ver", "capacidad.maestros.gestionar", "capacidad.matriz.ver", "capacidad.matriz.gestionar",
         "capacidad.programacion.cargar", "capacidad.analisis.ver", "capacidad.asistente.usar"],
    ),
    "Nómina": (
        "Capacidad Operativa: revisa y aprueba cubrimientos y turnos adicionales",
        ["capacidad.maestros.ver", "capacidad.matriz.ver", "capacidad.analisis.ver", "capacidad.cubrimientos.aprobar",
         "capacidad.asistente.usar"],
    ),
}


def _router() -> APIRouter:
    from app.apps.capacidad.routes import (
        analisis, asistente, catalogos, cubrimientos, maestros, matriz, programacion, seguimiento,
    )

    router = APIRouter(prefix="/capacidad")
    for modulo in (catalogos, maestros, matriz, programacion, analisis, cubrimientos, seguimiento, asistente):
        router.include_router(modulo.router)
    return router


def _seed(db: Session) -> None:
    from app.apps.capacidad.services.alertas import sembrar_parametros
    from app.apps.capacidad.services.catalogos import sembrar_novedades

    sembrar_novedades(db)
    sembrar_parametros(db)


APP = App(
    codigo="capacidad",
    nombre="Capacidad Operativa",
    descripcion="Programación de personal de SIESA contra lo vendido: cobertura, cubrimientos, bolsas y alertas.",
    icono="shield-check",
    color="#1d5fbf",
    permisos=PERMISOS,
    roles_base=ROLES_BASE,
    router=_router,
    seed=_seed,
)
