"""Envío de correos por SMTP (Microsoft 365: smtp.office365.com:587 con STARTTLS).

Las credenciales van en variables de entorno (SMTP_USUARIO, SMTP_CLAVE…); sin ellas no se envía nada y quien llama
lo registra como «correo no configurado».
"""

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from app.core.config import get_settings


@dataclass
class Mensaje:
    para: list[str]
    asunto: str
    html: str
    texto: str = ""


def configurado() -> bool:
    s = get_settings()
    return bool(s.smtp_host and s.smtp_usuario and s.smtp_clave)


def enviar(mensajes: list[Mensaje]) -> list[str | None]:
    """Envía los mensajes por una sola conexión. Devuelve, por mensaje, None si salió o el error."""
    s = get_settings()
    if not configurado():
        return ["El correo de la plataforma no está configurado (SMTP_USUARIO y SMTP_CLAVE)"] * len(mensajes)
    remitente = s.smtp_remitente or s.smtp_usuario
    try:
        servidor = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20)
        servidor.starttls()
        servidor.login(s.smtp_usuario, s.smtp_clave)
    except (OSError, smtplib.SMTPException) as e:
        return [f"No se pudo conectar al correo: {e.__class__.__name__}: {str(e)[:200]}"] * len(mensajes)
    errores: list[str | None] = []
    try:
        for m in mensajes:
            msg = EmailMessage()
            msg["From"], msg["To"], msg["Subject"] = remitente, ", ".join(m.para), m.asunto
            msg["Date"], msg["Message-ID"] = formatdate(localtime=True), make_msgid()
            msg.set_content(m.texto or "Este correo se ve mejor en un cliente que muestre HTML.")
            msg.add_alternative(m.html, subtype="html")
            try:
                servidor.send_message(msg)
                errores.append(None)
            except (OSError, smtplib.SMTPException) as e:
                errores.append(f"{e.__class__.__name__}: {str(e)[:200]}")
    finally:
        try:
            servidor.quit()
        except (OSError, smtplib.SMTPException):
            pass
    return errores
