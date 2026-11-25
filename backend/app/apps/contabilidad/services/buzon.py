"""Lectura del buzón de Gmail por IMAP (con contraseña de aplicación).

Se leen los correos no leídos; de cada uno se toman los adjuntos (zip, XML, PDF) en memoria, se registran las
facturas y el correo queda marcado como leído. Ni el correo ni sus adjuntos se guardan: solo un registro de qué
pasó con él (remitente, asunto, resultado).
"""

import email
import imaplib
import logging
from datetime import datetime, timezone
from email import policy
from email.utils import parsedate_to_datetime

from sqlalchemy.orm import Session

from app.apps.contabilidad.models import CtbConfig, CtbCorreo
from app.apps.contabilidad.services import servicio
from app.core import ia
from app.core.security import descifrar_secreto

log = logging.getLogger("app.contabilidad")
SERVIDOR, PUERTO = "imap.gmail.com", 993
MAX_POR_LECTURA = 40
MAX_ADJUNTO = 25 * 1024 * 1024


class ErrorBuzon(Exception):
    pass


def conectar(c: CtbConfig) -> imaplib.IMAP4_SSL:
    clave = descifrar_secreto(c.clave_cifrada, "imap") if c.clave_cifrada else None
    if not c.correo or not clave:
        raise ErrorBuzon("Falta el correo o la contraseña de aplicación del buzón")
    try:
        imap = imaplib.IMAP4_SSL(SERVIDOR, PUERTO, timeout=60)
    except OSError as e:
        raise ErrorBuzon("No fue posible conectar con Gmail") from e
    try:
        imap.login(c.correo, clave)
    except imaplib.IMAP4.error as e:
        raise ErrorBuzon("Gmail rechazó el correo o la contraseña de aplicación (¿IMAP activo en Gmail?)") from e
    return imap


def probar(c: CtbConfig) -> int:
    """Conecta y devuelve cuántos correos sin leer hay en la carpeta."""
    imap = conectar(c)
    try:
        estado, _ = imap.select(c.carpeta or "INBOX", readonly=True)
        if estado != "OK":
            raise ErrorBuzon(f"No existe la carpeta «{c.carpeta}» en el buzón")
        _, datos = imap.search(None, "UNSEEN")
        return len(datos[0].split()) if datos and datos[0] else 0
    finally:
        imap.logout()


def _adjuntos(msg) -> list[tuple[str, bytes]]:
    out = []
    for parte in msg.walk():
        nombre = parte.get_filename()
        if not nombre or parte.get_content_maintype() == "multipart":
            continue
        datos = parte.get_payload(decode=True) or b""
        if len(datos) <= MAX_ADJUNTO and nombre.lower().endswith((".zip", ".xml", ".pdf")):
            out.append((nombre, datos))
    return out


def procesar_mensaje(db: Session, crudo: bytes) -> CtbCorreo:
    msg = email.message_from_bytes(crudo, policy=policy.default)
    try:
        fecha = parsedate_to_datetime(msg.get("date")) if msg.get("date") else None
    except (TypeError, ValueError):
        fecha = None
    de, asunto = str(msg.get("from") or "")[:200], str(msg.get("subject") or "")[:300]
    res = servicio.procesar_archivos(db, _adjuntos(msg), correo_de=de, correo_asunto=asunto, correo_fecha=fecha)
    registro = CtbCorreo(mensaje_id=str(msg.get("message-id") or "")[:300], de=de, asunto=asunto, fecha=fecha,
                         resultado=res.texto()[:500], facturas=len(res.nuevas))
    db.add(registro)
    return registro


def leer(db: Session) -> list[CtbCorreo]:
    """Lee los correos no leídos del buzón y registra sus facturas. Cada correo se confirma por separado."""
    c = servicio.config(db)
    ia.cargar(db)
    registros = []
    try:
        imap = conectar(c)
    except ErrorBuzon as e:
        c.ultimo_error, c.ultima_lectura = str(e), datetime.now(timezone.utc)
        db.commit()
        raise
    try:
        if imap.select(c.carpeta or "INBOX")[0] != "OK":
            raise ErrorBuzon(f"No existe la carpeta «{c.carpeta}» en el buzón")
        _, datos = imap.search(None, "UNSEEN")
        for num in (datos[0].split() if datos and datos[0] else [])[:MAX_POR_LECTURA]:
            _, partes = imap.fetch(num, "(BODY.PEEK[])")  # PEEK: no lo marca leído hasta procesarlo
            crudo = next((p[1] for p in partes if isinstance(p, tuple)), None)
            if not crudo:
                continue
            try:
                registros.append(procesar_mensaje(db, crudo))
                db.commit()
            except Exception as e:  # un correo malo no detiene los demás
                db.rollback()
                log.exception("Falló un correo del buzón de contabilidad")
                db.add(CtbCorreo(resultado=f"Error al procesar: {str(e)[:400]}"))
                db.commit()
            imap.store(num, "+FLAGS", "\\Seen")
        c = servicio.config(db)
        c.ultimo_error, c.ultima_lectura = "", datetime.now(timezone.utc)
        db.commit()
    except ErrorBuzon as e:
        c = servicio.config(db)
        c.ultimo_error, c.ultima_lectura = str(e), datetime.now(timezone.utc)
        db.commit()
        raise
    finally:
        try:
            imap.logout()
        except Exception:
            pass
    return registros
