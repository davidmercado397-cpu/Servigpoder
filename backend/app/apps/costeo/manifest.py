from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.core.plataforma import App

PERMISOS: dict[str, tuple[str, str]] = {
    "costeo.ver": ("Consulta", "Ver MFP, bolsas, costeos y totales; descargar el Excel"),
    "costeo.movimientos": ("MFP", "Registrar pagos, aplicaciones y solicitudes de horas de las MFP (programación y comercial)"),
    "costeo.mfp": ("MFP", "Crear y editar MFP y sus ítems, importar el Excel, terminar contratos, aprobar costeos y crear la MFP"),
    "costeo.autorizar": ("MFP", "Autorizar movimientos que superan lo pactado o la bolsa de horas"),
    "costeo.costear": ("Costeo", "Crear, editar y versionar costeos"),
    "costeo.configurar": ("Configuración", "Editar parámetros, comisiones, servicios, catálogos de costos y tipos de ítem"),
    "costeo.precios": ("Configuración", "Actualizar los precios de dotación y otros costos directos (compras y contabilidad)"),
}

ROLES_BASE: dict[str, tuple[str, list[str]]] = {
    "Comercial costeo": ("Costeo y MFP's: hace costeos y registra la ejecución de las MFP", ["costeo.ver", "costeo.movimientos", "costeo.costear"]),
    "Programador MFP": ("Costeo y MFP's: consulta las MFP y registra las solicitudes de horas", ["costeo.ver", "costeo.movimientos"]),
    "Precios costeo": ("Costeo y MFP's: compras y contabilidad actualizan los precios de dotación y otros costos", ["costeo.ver", "costeo.precios"]),
    "Administrador costeo": ("Costeo y MFP's: todo, incluida la autorización para superar topes", list(PERMISOS)),
}


def _router() -> APIRouter:
    from app.apps.costeo.routes import router

    return router


def _seed(db: Session) -> None:
    from app.apps.costeo.services.configuracion import sembrar

    sembrar(db)


APP = App(
    codigo="costeo",
    nombre="Costeo y MFP's",
    descripcion="Costeo de servicios con parámetros editables y control de las MFP por cliente, ítem y totales: "
                "lo pactado, lo ejecutado, bolsas de horas y reembolsos.",
    icono="hand-coins",
    color="#be185d",
    permisos=PERMISOS,
    roles_base=ROLES_BASE,
    router=_router,
    seed=_seed,
)
