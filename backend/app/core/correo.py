"""Envío de correos por SMTP (Gmail / Google Workspace: smtp.gmail.com:587 con STARTTLS y contraseña de aplicación).

Las credenciales van en variables de entorno (SMTP_USUARIO, SMTP_CLAVE…); sin ellas no se envía nada y quien llama
lo registra como «correo no configurado».
"""

import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from html import escape

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings


@dataclass
class Mensaje:
    para: list[str]
    asunto: str
    html: str
    texto: str = ""
    # Imágenes dentro del correo: {cid: (contenido, mime)}; en el HTML se usan como src="cid:<cid>"
    imagenes: dict[str, tuple[bytes, str]] = field(default_factory=dict)


def plantilla(db: Session, titulo: str, cuerpo: str, empresa: str | None = None) -> tuple[str, dict[str, tuple[bytes, str]]]:
    """Correo con la marca de la plataforma (logo, nombre y colores de la empresa o de la general).
    Devuelve el HTML y las imágenes para Mensaje.imagenes. Hecho con tablas y estilos en línea, como lo leen Gmail y Outlook."""
    from app.models import Empresa
    from app.models.marca import MARCA_INICIAL, Marca, MarcaImagen

    general = db.scalar(select(Marca).where(Marca.empresa_id.is_(None)))
    e = db.scalar(select(Empresa).where(Empresa.codigo == empresa)) if empresa else None
    propia = db.scalar(select(Marca).where(Marca.empresa_id == e.id)) if e else None
    m = propia or general
    datos = {k: getattr(m, k) if m else v for k, v in MARCA_INICIAL.items()}
    logo = next((i for i in (db.get(MarcaImagen, (x.id, "logo")) for x in (propia, general) if x) if i), None)
    imagenes = {"logo": (logo.contenido, logo.mime)} if logo else {}
    barra, acento, primario = datos["color_barra"], datos["color_acento"], datos["color_primario"]
    alto = 44
    ancho = round(logo.ancho * alto / logo.alto) if logo and logo.alto else 0
    img = (f'<td style="padding-right:14px;vertical-align:middle"><img src="cid:logo" alt="" width="{ancho}" height="{alto}" '
           f'style="display:block;border:0;height:{alto}px;width:{ancho}px"></td>') if logo else ""
    sub = (f'<div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:{acento};margin-top:2px">'
           f'{escape(datos["subtitulo"])}</div>') if datos["subtitulo"] else ""
    html = f"""<!doctype html><html><body style="margin:0;padding:0;background:#eef2f7">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#eef2f7;padding:24px 12px">
<tr><td align="center">
<table role="presentation" width="640" cellpadding="0" cellspacing="0" style="max-width:640px;width:100%;background:#ffffff;border-radius:10px;overflow:hidden;font-family:Segoe UI,Helvetica,Arial,sans-serif;color:#1f2937">
<tr><td style="background:{barra};padding:18px 24px">
<table role="presentation" cellpadding="0" cellspacing="0"><tr>{img}<td style="vertical-align:middle">
<div style="font-size:18px;font-weight:bold;color:#ffffff">{escape(datos["nombre"])}</div>{sub}</td></tr></table></td></tr>
<tr><td style="height:4px;background:{acento};font-size:0;line-height:0">&nbsp;</td></tr>
<tr><td style="padding:24px 24px 8px">
<h1 style="margin:0 0 12px;font-size:20px;color:{primario}">{escape(titulo)}</h1>
<div style="font-size:14px;line-height:1.55">{cuerpo}</div></td></tr>
<tr><td style="padding:16px 24px 22px;font-size:12px;color:#6b7280;border-top:1px solid #edf0f4">
Correo automático de {escape(datos["nombre"])}. No responda a este mensaje.</td></tr>
</table></td></tr></table></body></html>"""
    return html, imagenes


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
            if m.imagenes:
                parte_html = msg.get_payload()[-1]
                for cid, (contenido, mime) in m.imagenes.items():
                    tipo, _, subtipo = mime.partition("/")
                    parte_html.add_related(contenido, maintype=tipo, subtype=subtipo or "png", cid=f"<{cid}>")
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
