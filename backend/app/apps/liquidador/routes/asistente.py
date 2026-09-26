import re

from sqlalchemy.orm import Session

from app.core.asistente import router_asistente
from app.apps.liquidador.models import LiqPeriodo
from app.apps.liquidador.services import asistente as svc

PANTALLAS = {
    "/liquidador": "la lista de quincenas", "/liquidador/turnos": "la configuración de turnos",
    "/liquidador/festivos": "los festivos", "/liquidador/empleados": "la lista de empleados",
}


def _contexto_pantalla(db: Session, pantalla: str | None) -> str | None:
    if not pantalla:
        return None
    m = re.match(r"^/liquidador/quincenas/(\d+)", pantalla)
    if m:
        p = db.get(LiqPeriodo, int(m.group(1)))
        if p:
            return f"El usuario está viendo la quincena {p.anio}-{p.mes:02d} Q{p.quincena} (estado {p.estado})"
    nombre = PANTALLAS.get(pantalla.split("?")[0])
    return f"El usuario está en {nombre}" if nombre else None


router = router_asistente("liquidador", "liquidador.asistente.usar",
                          lambda db, usuario, mensajes: svc.responder(db, usuario, mensajes), _contexto_pantalla)
