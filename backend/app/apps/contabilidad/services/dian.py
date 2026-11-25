"""Lectura de la factura electrónica de la DIAN (UBL 2.1).

Los proveedores mandan un .zip con el PDF y el XML. El XML puede ser el «AttachedDocument» (el contenedor que
exige la DIAN, con la factura dentro como texto) o directamente la factura (Invoice, CreditNote, DebitNote).
Del XML salen los datos exactos; se busca por nombre local de los elementos para no depender de los prefijos.
"""

import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date
from xml.etree.ElementTree import Element

from defusedxml import ElementTree

MAX_ZIP = 40 * 1024 * 1024  # tamaño descomprimido máximo de un zip
TIPOS = {"Invoice": "factura", "CreditNote": "nota_credito", "DebitNote": "nota_debito"}
FORMAS_PAGO = {"1": "Contado", "2": "Credito"}


class FacturaInvalida(ValueError):
    pass


@dataclass
class Linea:
    orden: int
    codigo_proveedor: str
    descripcion: str
    cantidad: float
    valor_unitario: float  # neto: valor de la línea ÷ cantidad
    subtotal: float
    iva_pct: float
    iva_valor: float


@dataclass
class Factura:
    cufe: str
    tipo: str
    prefijo: str
    numero: str
    fecha_emision: date | None
    fecha_vencimiento: date | None
    forma_pago: str
    moneda: str
    emisor_nit: str
    emisor_dv: str
    emisor_nombre: str
    comprador_nit: str
    comprador_nombre: str
    subtotal: float
    iva: float
    total: float
    retenciones: dict = field(default_factory=dict)
    lineas: list[Linea] = field(default_factory=list)


@dataclass
class Adjunto:
    """Lo que trae un correo: XML de facturas y PDF (estos solo se leen si no vino el XML)."""

    xmls: list[tuple[str, bytes]] = field(default_factory=list)
    pdfs: list[tuple[str, bytes]] = field(default_factory=list)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _hijos(el: Element | None, nombre: str) -> list[Element]:
    return [h for h in el if _local(h.tag) == nombre] if el is not None else []


def _hijo(el: Element | None, ruta: str) -> Element | None:
    for parte in ruta.split("/"):
        if el is None:
            return None
        el = next(iter(_hijos(el, parte)), None)
    return el


def _texto(el: Element | None, ruta: str = "") -> str:
    x = _hijo(el, ruta) if ruta else el
    return (x.text or "").strip() if x is not None else ""


def _num(el: Element | None, ruta: str = "") -> float:
    t = _texto(el, ruta)
    try:
        return float(t) if t else 0.0
    except ValueError:
        return 0.0


def _fecha(t: str) -> date | None:
    try:
        return date.fromisoformat(t[:10]) if t else None
    except ValueError:
        return None


def _buscar(raiz: Element, nombre: str) -> Element | None:
    return next((e for e in raiz.iter() if _local(e.tag) == nombre), None)


def solo_nit(valor: str) -> str:
    """NIT sin dígito de verificación ni puntos: «900.474.794-1» → «900474794»."""
    t = re.sub(r"[.\s]", "", valor or "")
    return re.split(r"-", t)[0] if "-" in t else t


def _parte(party: Element | None) -> tuple[str, str, str]:
    """(NIT, DV, razón social) de AccountingSupplierParty / AccountingCustomerParty."""
    p = _hijo(party, "Party")
    esquema = _hijo(p, "PartyTaxScheme")
    legal = _hijo(p, "PartyLegalEntity")
    cid = _hijo(esquema, "CompanyID") if esquema is not None else None
    if cid is None or not (cid.text or "").strip():
        cid = _hijo(legal, "CompanyID")
    nit = solo_nit((cid.text or "") if cid is not None else "")
    dv = (cid.get("schemeID") or "") if cid is not None else ""
    nombre = _texto(esquema, "RegistrationName") or _texto(legal, "RegistrationName") or _texto(p, "PartyName/Name")
    return nit, dv[:2], nombre


def _iva(nodo: Element) -> tuple[float, float]:
    """(% de IVA, valor del IVA) de los TaxTotal de una línea (TaxScheme 01 = IVA)."""
    pct = valor = 0.0
    for total in _hijos(nodo, "TaxTotal"):
        for sub in _hijos(total, "TaxSubtotal"):
            categoria = _hijo(sub, "TaxCategory")
            if _texto(categoria, "TaxScheme/ID") in ("01", ""):
                pct = max(pct, _num(categoria, "Percent"))
                valor += _num(sub, "TaxAmount")
    return pct, valor


def _documento(raiz: Element) -> Element:
    """La factura: la raíz o, si es un AttachedDocument, la que viene dentro como texto."""
    if _local(raiz.tag) in TIPOS:
        return raiz
    if _local(raiz.tag) == "AttachedDocument":
        for desc in raiz.iter():
            if _local(desc.tag) == "Description" and desc.text and "<" in desc.text:
                interno = desc.text.strip()
                try:
                    doc = ElementTree.fromstring(interno.encode("utf-8"))
                except Exception:
                    continue
                if _local(doc.tag) in TIPOS:
                    return doc
    raise FacturaInvalida("El XML no es una factura electrónica (Invoice, CreditNote o AttachedDocument)")


def leer_xml(contenido: bytes) -> Factura:
    try:
        raiz = ElementTree.fromstring(contenido)
    except Exception as e:
        raise FacturaInvalida("El XML está dañado") from e
    doc = _documento(raiz)
    tipo = TIPOS[_local(doc.tag)]
    numero_completo = _texto(doc, "ID")
    pref_el = _buscar(doc, "Prefix")
    prefijo = (pref_el.text or "").strip() if pref_el is not None else ""
    if prefijo and numero_completo.upper().startswith(prefijo.upper()):
        numero = numero_completo[len(prefijo):]
    else:
        m = re.fullmatch(r"(.*?)(\d+)", numero_completo)
        prefijo, numero = (m.group(1), m.group(2)) if m else ("", numero_completo)
    emisor = _parte(_hijo(doc, "AccountingSupplierParty"))
    comprador = _parte(_hijo(doc, "AccountingCustomerParty"))
    medio = _hijo(doc, "PaymentMeans")
    vence = _fecha(_texto(doc, "DueDate")) or _fecha(_texto(medio, "PaymentDueDate"))
    totales = _hijo(doc, "LegalMonetaryTotal")
    if totales is None:
        totales = _hijo(doc, "RequestedMonetaryTotal")
    iva = sum(_num(sub, "TaxAmount") for t in _hijos(doc, "TaxTotal") for sub in _hijos(t, "TaxSubtotal")
              if _texto(sub, "TaxCategory/TaxScheme/ID") in ("01", ""))
    retenciones: dict[str, float] = {}
    for t in _hijos(doc, "WithholdingTaxTotal"):
        for sub in _hijos(t, "TaxSubtotal"):
            nombre = {"05": "rete_iva", "06": "rete_fuente", "07": "rete_ica"}.get(_texto(sub, "TaxCategory/TaxScheme/ID"), "otra")
            retenciones[nombre] = retenciones.get(nombre, 0.0) + _num(sub, "TaxAmount")

    lineas = []
    nombre_linea = {"factura": "InvoiceLine", "nota_credito": "CreditNoteLine", "nota_debito": "DebitNoteLine"}[tipo]
    cantidad_tag = {"factura": "InvoicedQuantity", "nota_credito": "CreditedQuantity", "nota_debito": "DebitedQuantity"}[tipo]
    for i, ln in enumerate(_hijos(doc, nombre_linea), start=1):
        cantidad = _num(ln, cantidad_tag) or 1.0
        subtotal = _num(ln, "LineExtensionAmount")
        pct, valor_iva = _iva(ln)
        item = _hijo(ln, "Item")
        descripcion = " ".join(_texto(d) for d in _hijos(item, "Description")).strip() or _texto(item, "Name")
        codigo = _texto(item, "SellersItemIdentification/ID") or _texto(item, "StandardItemIdentification/ID")
        lineas.append(Linea(i, codigo[:60], re.sub(r"\s+", " ", descripcion)[:500], cantidad,
                            round(subtotal / cantidad, 4) if cantidad else subtotal, subtotal, pct, valor_iva))
    if not lineas:
        raise FacturaInvalida("La factura no trae productos")
    return Factura(
        cufe=_texto(doc, "UUID") or f"{emisor[0]}-{numero_completo}", tipo=tipo, prefijo=prefijo[:20], numero=numero[:40],
        fecha_emision=_fecha(_texto(doc, "IssueDate")), fecha_vencimiento=vence or _fecha(_texto(doc, "IssueDate")),
        forma_pago=FORMAS_PAGO.get(_texto(medio, "ID"), "Contado"), moneda=_texto(doc, "DocumentCurrencyCode") or "COP",
        emisor_nit=emisor[0], emisor_dv=emisor[1], emisor_nombre=emisor[2][:200],
        comprador_nit=comprador[0], comprador_nombre=comprador[2][:200],
        subtotal=_num(totales, "LineExtensionAmount"), iva=round(iva, 2),
        total=_num(totales, "PayableAmount") or _num(totales, "TaxInclusiveAmount"),
        retenciones={k: round(v, 2) for k, v in retenciones.items()}, lineas=lineas,
    )


def abrir_adjuntos(archivos: list[tuple[str, bytes]]) -> Adjunto:
    """Separa XML y PDF; abre los .zip (también un zip dentro de otro). Todo en memoria."""
    out = Adjunto()

    def agregar(nombre: str, datos: bytes, nivel: int = 0) -> None:
        n = nombre.lower()
        if n.endswith(".zip") and nivel < 2:
            try:
                with zipfile.ZipFile(io.BytesIO(datos)) as z:
                    if sum(i.file_size for i in z.infolist()) > MAX_ZIP:
                        raise FacturaInvalida(f"«{nombre}» es demasiado grande")
                    for info in z.infolist():
                        if not info.is_dir():
                            agregar(info.filename.rsplit("/", 1)[-1], z.read(info), nivel + 1)
            except zipfile.BadZipFile as e:
                raise FacturaInvalida(f"«{nombre}» no es un zip válido") from e
        elif n.endswith(".xml"):
            out.xmls.append((nombre, datos))
        elif n.endswith(".pdf"):
            out.pdfs.append((nombre, datos))

    for nombre, datos in archivos:
        agregar(nombre, datos)
    return out
