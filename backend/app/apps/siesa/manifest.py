from fastapi import APIRouter

from app.core.plataforma import App

PERMISOS: dict[str, tuple[str, str]] = {
    "siesa.consultar": ("Chat", "Hacer preguntas sobre los instructivos de SIESA cargados"),
    "siesa.gestionar": ("Base de conocimiento", "Cargar y eliminar los PDF de instructivos de SIESA"),
}

ROLES_BASE: dict[str, tuple[str, list[str]]] = {
    "Consulta instructivos SIESA": ("Instructivos SIESA: preguntas al chat de instructivos", ["siesa.consultar"]),
}


def _router() -> APIRouter:
    from app.apps.siesa.routes import router

    return router


APP = App(
    codigo="siesa",
    nombre="Instructivos SIESA",
    descripcion="Chat que responde solo con lo que dicen los instructivos de SIESA cargados, citando el documento y la página.",
    icono="book-open",
    color="#b45309",
    permisos=PERMISOS,
    roles_base=ROLES_BASE,
    router=_router,
)
