"""Comprobantes de nómina (desprendibles de pago) en PDF: un comprobante por página con lo que se pagó en una nómina cerrada.

Mismo esquema del comprobante de Siigo: nombre arriba, título, logo y datos de la empresa a la izquierda, periodo y datos del
empleado a la derecha, ingresos y deducciones (concepto, cantidad y valor), neto a pagar y el pie «generado desde el
software SERA 360». Los valores salen tal cual de la nómina liquidada (solo aparecen los conceptos que tiene la persona).
Sin datos bancarios. Se genera en memoria y no se guarda.
"""

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.apps.liquidador.models import LiqPeriodo, LiqResultado
from app.apps.liquidador.services.exportar import ORDEN_CONCEPTOS, sufijo
from app.apps.liquidador.services.nomina import NOMBRES_HORAS
from app.models import Empresa
from app.models.marca import Marca, MarcaImagen

PDF = "application/pdf"
PIE = "Este comprobante de nómina fue generado desde el software SERA 360."
# Razón social y NIT por empresa (la marca solo tiene un nombre comercial)
DATOS_EMPRESA = {"sera": ("SERVICIOS EMPRESARIALES RESIDENCIALES Y AMBIENTALES SAS", "900889870")}
TIPOS_DESCUENTO = {"prestamo": "Préstamo", "embargo": "Embargo", "cuota": "Cuota"}
TIPOS_NOVEDAD = {"mayor_valor": "Mayor valor pagado", "menor_valor": "Menor valor pagado", "horas_extras": "Horas extras pendientes",
                 "recargos": "Recargos pendientes", "otro_devengo": "Otro devengo", "otra_deduccion": "Otra deducción"}

GRIS = colors.HexColor("#E5E7EB")
LINEA = colors.HexColor("#9CA3AF")
TEXTO = colors.HexColor("#1F2937")

_base = ParagraphStyle("base", fontName="Helvetica", fontSize=9, leading=11, textColor=TEXTO)
_titulo = ParagraphStyle("titulo", parent=_base, fontSize=16, leading=20, alignment=TA_CENTER)
_nombre_arriba = ParagraphStyle("arriba", parent=_base, fontSize=12, leading=15, alignment=TA_CENTER)
_derecha = ParagraphStyle("derecha", parent=_base, fontSize=10, leading=14, alignment=TA_RIGHT)
_empresa = ParagraphStyle("empresa", parent=_base, fontSize=9, leading=11, alignment=TA_CENTER)
_pie = ParagraphStyle("pie", parent=_base, fontSize=9, alignment=TA_CENTER)
_celda = ParagraphStyle("celda", parent=_base, fontSize=8.5, leading=10)


def pesos(v: float) -> str:
    """$ 711.750,00"""
    texto = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{'-' if v < 0 else ''}$ {texto}"


def cantidad(v) -> str:
    if v in (None, ""):
        return ""
    if isinstance(v, str):
        return v
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def ingresos(n: dict) -> list[tuple[str, object, float]]:
    """(concepto, cantidad, valor) de lo devengado, en el orden del comprobante."""
    filas: list[tuple[str, object, float]] = []
    if n.get("por_horas"):
        filas.append(("Sueldo (horas trabajadas)", n.get("horas_pagadas", 0), n.get("basico", 0)))
    elif n.get("basico"):
        filas.append(("Sueldo", n.get("dias_salario", 0), n["basico"]))
    if n.get("incapacidad"):
        filas.append(("Incapacidad", n.get("dias_incapacidad", 0), n["incapacidad"]))
    vac = n.get("vacaciones") or {}
    if vac.get("valor_habiles"):
        filas.append(("Vacaciones días hábiles", vac.get("dias_habiles", 0), vac["valor_habiles"]))
    if vac.get("valor_no_habiles"):
        filas.append(("Vacaciones días no hábiles", vac.get("dias_no_habiles", 0), vac["valor_no_habiles"]))
    for x in n.get("licencias") or []:
        filas.append((str(x.get("nombre") or x.get("codigo") or "Licencia").capitalize(), x.get("dias", 0), x.get("valor", 0)))
    for c in ORDEN_CONCEPTOS:
        valor = (n.get("valores") or {}).get(c.value)
        if valor:
            nombre = NOMBRES_HORAS.get(c.value, c.value)
            filas.append(((nombre if nombre.startswith("recargo") else f"hora {nombre}").capitalize(), (n.get("horas") or {}).get(c.value, 0), valor))
    for x in n.get("auxilios") or []:
        filas.append((x["descripcion"], "", x["valor"]))
    if n.get("auxilio"):
        filas.append(("Auxilio de transporte", n.get("dias_auxilio", 0), n["auxilio"]))
    for x in n.get("novedades") or []:
        if not x.get("deduccion"):
            filas.append((x["descripcion"] or TIPOS_NOVEDAD.get(x["tipo"], x["tipo"]), "", x["valor"]))
    return filas


def deducciones(n: dict) -> list[tuple[str, object, float]]:
    filas: list[tuple[str, object, float]] = []
    if n.get("salud"):
        filas.append(("Fondo de salud", f"{cantidad(n.get('salud_pct', 0))} %", n["salud"]))
    if n.get("pension"):
        filas.append(("Fondo de pensión", f"{cantidad(n.get('pension_pct', 0))} %", n["pension"]))
    for x in n.get("descuentos") or []:
        if x.get("valor"):
            tipo = TIPOS_DESCUENTO.get(x["tipo"], x["tipo"])
            desc = x["descripcion"] or ""
            filas.append((desc if desc.lower().startswith(tipo.lower()) else f"{tipo}: {desc}", "", x["valor"]))
    for x in n.get("novedades") or []:
        if x.get("deduccion") and x.get("valor"):
            filas.append((x["descripcion"] or TIPOS_NOVEDAD.get(x["tipo"], x["tipo"]), "", x["valor"]))
    return filas


def _tabla(titulo: str, filas: list[tuple[str, object, float]], total_texto: str, total: float, alto: int) -> Table:
    datos = [[titulo, "", ""], ["Concepto", "Cantidad", "Valor"]]
    datos += [[Paragraph(escape(c), _celda), cantidad(q), pesos(v)] for c, q, v in filas]
    datos += [["", "", ""]] * max(alto - len(filas), 0)  # las dos tablas quedan del mismo alto
    datos.append([total_texto, "", pesos(total)])
    t = Table(datos, colWidths=[46 * mm, 17 * mm, 27 * mm])
    ultima = len(datos) - 1
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8.5),
        ("SPAN", (0, 0), (-1, 0)), ("ALIGN", (0, 0), (-1, 1), "CENTER"),
        ("FONT", (0, 0), (-1, 0), "Helvetica", 11), ("FONT", (0, 1), (-1, 1), "Helvetica-Bold", 8.5),
        ("BACKGROUND", (0, 0), (-1, 1), GRIS),
        ("ALIGN", (1, 2), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, ultima - 1), 0.4, LINEA), ("BOX", (0, 0), (-1, -1), 0.4, LINEA),
        ("SPAN", (0, ultima), (1, ultima)), ("ALIGN", (0, ultima), (1, ultima), "RIGHT"),
        ("FONT", (0, ultima), (-1, ultima), "Helvetica-Bold", 8.5), ("LINEABOVE", (0, ultima), (-1, ultima), 0.4, LINEA),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _logo(db: Session, empresa: Empresa | None):
    marca = db.scalar(select(Marca).where(Marca.empresa_id == empresa.id)) if empresa else None
    marca = marca or db.scalar(select(Marca).where(Marca.empresa_id.is_(None)))
    img = db.get(MarcaImagen, (marca.id, "logo")) if marca else None
    return marca, img


def generar(db: Session, periodo: LiqPeriodo, empresa_codigo: str | None) -> tuple[bytes, str, str]:
    empresa = db.scalar(select(Empresa).where(Empresa.codigo == empresa_codigo)) if empresa_codigo else None
    marca, img = _logo(db, empresa)
    razon, nit = DATOS_EMPRESA.get(empresa_codigo or "", ((marca.nombre if marca else "") or (empresa.nombre if empresa else ""), ""))
    resultados = sorted((r for r in db.scalars(select(LiqResultado).where(LiqResultado.periodo_id == periodo.id)) if r.nomina),
                        key=lambda r: r.empleado.nombre)

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=18 * mm, bottomMargin=15 * mm,
                            title=f"Comprobantes de nómina {periodo.etiqueta} {periodo.nombre}", author="SERA 360")
    historia = []
    for i, r in enumerate(resultados):
        n, e = r.nomina, r.empleado
        if i:
            historia.append(PageBreak())
        historia += [Paragraph(escape(e.nombre), _nombre_arriba), Spacer(1, 10 * mm), Paragraph("Comprobante de Nómina", _titulo), Spacer(1, 6 * mm)]

        izquierda = []
        if img is not None:
            ancho = 42 * mm
            alto = ancho * img.alto / img.ancho if img.ancho else 20 * mm
            if alto > 24 * mm:
                ancho, alto = ancho * 24 * mm / alto, 24 * mm
            izquierda.append(Image(ImageReader(BytesIO(img.contenido)), width=ancho, height=alto))
        izquierda.append(Paragraph(escape(razon), _empresa))
        if nit:
            izquierda.append(Paragraph(f"Nit {escape(nit)}", _empresa))
        salario = n.get("salario", 0)
        derecha = Paragraph(
            f"Periodo de Pago: <b>{periodo.desde:%Y/%m/%d} - {periodo.hasta:%Y/%m/%d}</b><br/>"
            f"Comprobante Número: <b>{r.id}</b><br/><br/>"
            f"Nombre: <b>{escape(e.nombre)}</b><br/>Identificación: <b>{escape(e.documento)}</b><br/>"
            f"Cargo: <b>{escape(e.cargo or '')}</b><br/>Salario básico: <b>{pesos(salario)}</b>", _derecha)
        cabecera = Table([[izquierda, derecha]], colWidths=[80 * mm, 105 * mm])
        cabecera.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (0, 0), "CENTER")]))
        historia += [cabecera, Spacer(1, 8 * mm)]

        ing, ded = ingresos(n), deducciones(n)
        alto = max(len(ing), len(ded))
        tablas = Table([[_tabla("INGRESOS", ing, "Total Ingresos", n.get("devengado", 0), alto),
                         _tabla("DEDUCCIONES", ded, "Total Deducciones", n.get("deducciones", 0), alto)]],
                       colWidths=[92 * mm, 92 * mm])
        tablas.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        neto = Table([["NETO A PAGAR", pesos(n.get("neto", 0))]], colWidths=[45 * mm, 38 * mm], hAlign="RIGHT")
        neto.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, -1), "Helvetica-Bold", 10), ("BACKGROUND", (0, 0), (0, 0), GRIS), ("BOX", (0, 0), (-1, -1), 0.4, LINEA),
            ("INNERGRID", (0, 0), (-1, -1), 0.4, LINEA), ("ALIGN", (0, 0), (0, 0), "CENTER"), ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        historia += [tablas, Spacer(1, 6 * mm), neto, Spacer(1, 10 * mm), Paragraph(PIE, _pie)]
    if not historia:
        historia.append(Paragraph("La nómina no tiene personas liquidadas.", _base))
    doc.build(historia)
    return buf.getvalue(), PDF, f"comprobantes_{periodo.anio}_{periodo.mes:02d}_{periodo.tipo}{sufijo(periodo)}.pdf"
