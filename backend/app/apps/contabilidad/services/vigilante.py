"""Revisión automática del buzón de Contabilidad: cada minuto mira, en cada empresa con el desarrollo habilitado,
si ya pasaron los minutos configurados desde la última lectura y, si el buzón está activo, lo lee."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal, engine, traduccion
from app.models import Empresa, EmpresaApp

log = logging.getLogger("app.contabilidad")
APP = "contabilidad"
_corriendo = asyncio.Lock()


def _revisar_todas() -> None:
    from app.apps.contabilidad.services import buzon, servicio

    with SessionLocal() as db:
        esquemas = list(db.scalars(select(Empresa.esquema).join(EmpresaApp, EmpresaApp.empresa_id == Empresa.id)
                                   .where(EmpresaApp.app == APP, Empresa.activa.is_(True))))
    for esquema in esquemas:
        with Session(bind=engine.execution_options(**traduccion(esquema)), autoflush=False,
                     expire_on_commit=False) as db:
            try:
                c = servicio.config(db)
                db.commit()
                if not c.activo or not c.correo:
                    continue
                ultima = c.ultima_lectura
                if ultima and ultima.tzinfo is None:
                    ultima = ultima.replace(tzinfo=timezone.utc)
                if ultima and datetime.now(timezone.utc) - ultima < timedelta(minutes=max(1, c.minutos or 5)):
                    continue
                buzon.leer(db)
            except Exception:
                log.exception("Falló la lectura automática del buzón de contabilidad (%s)", esquema)


async def bucle() -> None:
    while True:
        await asyncio.sleep(60)
        if _corriendo.locked():
            continue
        async with _corriendo:
            try:
                await asyncio.to_thread(_revisar_todas)
            except Exception:
                log.exception("Falló la revisión automática de buzones")
