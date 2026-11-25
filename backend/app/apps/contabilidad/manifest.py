from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.core.plataforma import App

PERMISOS: dict[str, tuple[str, str]] = {
    "contabilidad.ver": ("Contabilidad", "Ver las facturas recibidas, los planos y los correos leídos"),
    "contabilidad.revisar": ("Contabilidad", "Revisar facturas, cargarlas a mano, descargar el plano y marcar lo contabilizado"),
    "contabilidad.configurar": ("Contabilidad", "Configurar el buzón de Gmail, los datos del plano y los catálogos (cuentas, centros, terceros)"),
}

ROLES_BASE: dict[str, tuple[str, list[str]]] = {
    "Contabilidad": ("Contabilidad: revisa las facturas recibidas y descarga el plano de World Office", list(PERMISOS)),
}


def _router() -> APIRouter:
    from app.apps.contabilidad.routes import router

    return router


def _seed(db: Session) -> None:
    from app.apps.contabilidad.services.servicio import sembrar

    sembrar(db)


APP = App(
    codigo="contabilidad",
    nombre="Contabilidad",
    descripcion="Lee las facturas de compra que llegan al correo (XML de la DIAN) y arma el plano para World Office.",
    icono="file-spreadsheet",
    color="#7c3aed",
    permisos=PERMISOS,
    roles_base=ROLES_BASE,
    router=_router,
    seed=_seed,
)
