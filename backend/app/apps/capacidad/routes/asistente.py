import re

from sqlalchemy.orm import Session

from app.core.asistente import router_asistente
from app.apps.capacidad.models import Puesto
from app.apps.capacidad.services import asistente as svc

PANTALLAS = {
    "/capacidad/cobertura": "el tablero de cobertura", "/capacidad/cubrimientos": "la bandeja de cubrimientos de nómina",
    "/capacidad/bolsas": "el reporte de personas en bolsa", "/capacidad/historico": "el histórico y comparación de cargas",
    "/capacidad/matriz": "la matriz comercial", "/capacidad/maestros": "los maestros y puestos por aclarar",
    "/capacidad/programacion": "la carga de programación de SIESA", "/capacidad": "el inicio con las alertas",
}


def _contexto_pantalla(db: Session, pantalla: str | None) -> str | None:
    if not pantalla:
        return None
    m = re.match(r"^/capacidad/cobertura/(\d+)", pantalla)
    if m:
        puesto = db.get(Puesto, int(m.group(1)))
        if puesto:
            return f"El usuario está viendo el calendario de cobertura del puesto {puesto.codigo} ({puesto.ubicacion.nombre})"
    nombre = PANTALLAS.get(pantalla.split("?")[0])
    return f"El usuario está en {nombre}" if nombre else None


# La función se resuelve en cada llamada para que las pruebas puedan sustituirla
router = router_asistente("capacidad", "capacidad.asistente.usar",
                          lambda db, usuario, mensajes: svc.responder(db, usuario, mensajes), _contexto_pantalla)
