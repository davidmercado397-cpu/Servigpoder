"""La IA en Contabilidad: propone el producto (cuenta), el centro de costos y las notas de cada factura, y lee las
facturas que llegan solo en PDF o escaneadas (sin XML). Los documentos no se guardan."""

import base64
import json
import logging
from datetime import date

from app.apps.contabilidad.services.dian import Factura, FacturaInvalida, Linea, solo_nit
from app.core import ia

log = logging.getLogger("app.contabilidad")

INSTRUCCIONES_PROPONER = """Eres el auxiliar contable de una empresa colombiana de vigilancia. Para registrar una factura de
compra en World Office propones, para CADA producto de la factura:
- "producto": el código del CATÁLOGO DE CUENTAS que corresponde al gasto, costo o activo (usa solo códigos del catálogo);
- "centro_costos": uno de los CENTROS DE COSTOS (exacto);
- "nota": una nota corta en minúsculas de lo que se compró (p. ej. "compra de vuelos").
Y para la factura, "nota": una nota corta en MAYÚSCULAS (p. ej. "COMPRA DE VUELO").
Si el HISTORIAL muestra cómo se registró antes este proveedor, síguelo salvo que el producto sea claramente distinto.
Si dudas, escoge lo más probable y explícalo en "dudas". Responde SOLO un JSON:
{"nota": "…", "lineas": [{"n": 1, "producto": "código", "centro_costos": "nombre", "nota": "…"}], "dudas": ["…"]}"""

INSTRUCCIONES_LEER = """Lees una factura electrónica colombiana (PDF o imagen) y devuelves sus datos EXACTOS como aparecen.
No inventes: si un dato no aparece, null. Valores como números (sin $ ni puntos de miles; decimales con punto).
Responde SOLO un JSON:
{"cufe": "…", "tipo": "factura|nota_credito|nota_debito", "prefijo": "…", "numero": "…", "fecha_emision": "AAAA-MM-DD",
 "fecha_vencimiento": "AAAA-MM-DD", "forma_pago": "Contado|Credito", "emisor_nit": "sin DV", "emisor_dv": "…",
 "emisor_nombre": "…", "comprador_nit": "sin DV", "comprador_nombre": "…", "subtotal": 0, "iva": 0, "total": 0,
 "lineas": [{"codigo": "…", "descripcion": "…", "cantidad": 1, "valor_unitario": 0, "subtotal": 0, "iva_pct": 19, "iva_valor": 0}]}"""


def _json(texto: str) -> dict:
    i, j = texto.find("{"), texto.rfind("}")
    if i < 0 or j <= i:
        raise ia.IAError(502, "La IA no devolvió una respuesta legible")
    try:
        datos = json.loads(texto[i:j + 1])
    except ValueError as e:
        raise ia.IAError(502, "La IA no devolvió una respuesta legible") from e
    if not isinstance(datos, dict):
        raise ia.IAError(502, "La IA no devolvió una respuesta legible")
    return datos


def proponer(factura: dict, productos: list[tuple[str, str]], centros: list[str], historial: list[dict]) -> dict:
    """factura: {"proveedor", "nit", "lineas": [{"n", "descripcion", "cantidad", "valor", "iva_pct"}]}"""
    contexto = ("CATÁLOGO DE CUENTAS (código nombre):\n" + "\n".join(f"{c} {n}" for c, n in productos)
                + "\n\nCENTROS DE COSTOS: " + json.dumps(centros, ensure_ascii=False)
                + "\n\nHISTORIAL DE ESTE PROVEEDOR (cómo se registró antes):\n" + json.dumps(historial[:30], ensure_ascii=False))
    r = ia.completar(INSTRUCCIONES_PROPONER + "\n\n" + contexto,
                     [{"role": "user", "content": "FACTURA:\n" + json.dumps(factura, ensure_ascii=False)}], max_tokens=4000)
    return _json(r.texto)


def _n(v) -> float:
    try:
        return float(str(v).replace(",", "")) if v not in (None, "") else 0.0
    except ValueError:
        return 0.0


def _fecha(v) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def leer_pdf(nombre: str, contenido: bytes) -> Factura:
    """Factura sin XML: la IA lee el PDF. Se marca para verificar."""
    parte = {"type": "file", "file": {"filename": nombre, "file_data": "data:application/pdf;base64," + base64.b64encode(contenido).decode()}}
    r = ia.completar(INSTRUCCIONES_LEER, [{"role": "user", "content": [{"type": "text", "text": f"Archivo: {nombre}"}, parte]}],
                     max_tokens=6000)
    d = _json(r.texto)
    lineas = []
    for i, x in enumerate(d.get("lineas") or [], start=1):
        if not isinstance(x, dict):
            continue
        cantidad = _n(x.get("cantidad")) or 1.0
        subtotal = _n(x.get("subtotal")) or _n(x.get("valor_unitario")) * cantidad
        lineas.append(Linea(i, str(x.get("codigo") or "")[:60], str(x.get("descripcion") or "")[:500], cantidad,
                            round(subtotal / cantidad, 4), subtotal, _n(x.get("iva_pct")), _n(x.get("iva_valor"))))
    if not lineas or not d.get("emisor_nit"):
        raise FacturaInvalida(f"La IA no encontró una factura en «{nombre}»")
    numero = str(d.get("numero") or "")
    return Factura(
        cufe=str(d.get("cufe") or "").strip() or f"{solo_nit(str(d.get('emisor_nit')))}-{d.get('prefijo') or ''}{numero}",
        tipo=d.get("tipo") if d.get("tipo") in ("factura", "nota_credito", "nota_debito") else "factura",
        prefijo=str(d.get("prefijo") or "")[:20], numero=numero[:40], fecha_emision=_fecha(d.get("fecha_emision")),
        fecha_vencimiento=_fecha(d.get("fecha_vencimiento")) or _fecha(d.get("fecha_emision")),
        forma_pago="Credito" if str(d.get("forma_pago") or "").lower().startswith("cr") else "Contado", moneda="COP",
        emisor_nit=solo_nit(str(d.get("emisor_nit"))), emisor_dv=str(d.get("emisor_dv") or "")[:2],
        emisor_nombre=str(d.get("emisor_nombre") or "")[:200], comprador_nit=solo_nit(str(d.get("comprador_nit") or "")),
        comprador_nombre=str(d.get("comprador_nombre") or "")[:200], subtotal=_n(d.get("subtotal")), iva=_n(d.get("iva")),
        total=_n(d.get("total")), lineas=lineas,
    )
