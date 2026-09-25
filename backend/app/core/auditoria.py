import logging
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.rate_limit import ip_cliente
from app.core.respuestas import request_id_ctx
from app.models import Auditoria

log = logging.getLogger("app.auditoria")


def auditar(db: Session, request: Request, accion: str, usuario_id: int | None = None, **detalle: Any) -> None:
    """Registra el evento en la bitácora. Nunca incluir contraseñas ni tokens en `detalle`.

    Se agrega a la sesión actual: queda guardado con el commit de la operación.
    """
    ip = ip_cliente(request)
    db.add(Auditoria(usuario_id=usuario_id, accion=accion, detalle=detalle, ip=ip, request_id=request_id_ctx.get()))
    log.info("auditoria accion=%s usuario=%s ip=%s detalle=%s", accion, usuario_id, ip, detalle)
