"""PDF de la programación por ubicación y puesto (ReportLab).

- Portada con resumen e índice de ubicaciones (clicable, con número de página) y marcadores para navegar.
  Se arma en dos pasadas: la primera calcula en qué página queda cada ubicación y el total de páginas.
- Por ubicación: encabezado con código, nombre, ciudad y totales; por puesto: tabla con un día por
  columna. Un puesto no se parte entre páginas salvo que no quepa en una (entonces repite el encabezado).
- Domingos y festivos sombreados; novedades en color; descansos (Z, L) en gris; leyenda al final.
- Las columnas se ajustan al rango del archivo: quincena (15-16 días) o mes completo (28-31 días).
"""

import re
from collections import Counter
from datetime import date, datetime
from io import BytesIO
from zoneinfo import ZoneInfo

import holidays
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas as canvas_rl
from reportlab.platypus import (
    BaseDocTemplate, Frame, KeepTogether, NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer, Table,
    TableStyle,
)
from xml.sax.saxutils import escape

from app.apps.reporte.services.lector import Programacion, Puesto, Ubicacion, ordenada

ZONA = ZoneInfo("America/Bogota")
HOJA = landscape(LETTER)  # Carta horizontal
DIAS = ["Lu", "Ma", "Mi", "Ju", "Vi", "Sá", "Do"]
MESES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]

AZUL = colors.HexColor("#1F3A5F")
AZUL_CLARO = colors.HexColor("#E8EEF6")
GRIS_TEXTO = colors.HexColor("#64748B")
GRIS_FONDO = colors.HexColor("#F1F5F9")
BORDE = colors.HexColor("#CBD5E1")
RAYADO = colors.HexColor("#F8FAFC")
DOMINGO_ENC = colors.HexColor("#8A5A12")
DOMINGO_FONDO = colors.HexColor("#FFF6E5")
FESTIVO_ENC = colors.HexColor("#A32525")
FESTIVO_FONDO = colors.HexColor("#FDECEC")
NOVEDAD_FONDO = colors.HexColor("#EFE7FB")
NOVEDAD_TEXTO = colors.HexColor("#5B21B6")
INDUCCION_FONDO = colors.HexColor("#E0F2FE")

# Significado de los códigos conocidos (los demás se listan tal cual en la leyenda)
SIGNIFICADOS = {
    "Z": "Descanso", "L": "Libre", "VAC": "Vacaciones", "PRV": "Programado a vacaciones", "LNR": "Licencia no remunerada",
    "LRM": "Licencia remunerada", "LIC": "Licencia", "LUT": "Licencia por luto", "IEG": "Incapacidad por enfermedad general",
    "AT": "Accidente de trabajo", "AUS": "Ausencia", "IND": "Inducción", "IND NOCHE": "Inducción nocturna",
    "IND CORP": "Inducción corporativa", "PSA": "Permiso sindical", "PSB": "Permiso sindical",
}
_HORARIO = re.compile(r"^(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\s*(.*)$")

_E = {
    "titulo": ParagraphStyle("titulo", fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=AZUL),
    "sub": ParagraphStyle("sub", fontName="Helvetica", fontSize=10, leading=14, textColor=colors.HexColor("#334155")),
    "h_ubi": ParagraphStyle("h_ubi", fontName="Helvetica-Bold", fontSize=11.5, leading=15, textColor=colors.white,
                            backColor=AZUL, borderPadding=(5, 6, 5, 6), spaceBefore=12, spaceAfter=8),
    "h_puesto": ParagraphStyle("h_puesto", fontName="Helvetica-Bold", fontSize=9.5, leading=12, textColor=AZUL,
                               spaceBefore=6, spaceAfter=3),
    "total": ParagraphStyle("total", fontName="Helvetica", fontSize=7.5, leading=10, textColor=GRIS_TEXTO, spaceBefore=2, spaceAfter=6),
    "nombre": ParagraphStyle("nombre", fontName="Helvetica", fontSize=7, leading=8.4, alignment=TA_LEFT),
    "nota": ParagraphStyle("nota", fontName="Helvetica", fontSize=8, leading=11, textColor=GRIS_TEXTO),
    "indice": ParagraphStyle("indice", fontName="Helvetica", fontSize=7, leading=8.4),
    "h_indice": ParagraphStyle("h_indice", fontName="Helvetica-Bold", fontSize=12, leading=16, textColor=AZUL, spaceBefore=14, spaceAfter=6),
}


def celda(codigo: str) -> str:
    """'06:00 - 18:00*' → '06:00\\n18:00*'; 'IND CORP' → 'IND\\nCORP'; el resto igual."""
    m = _HORARIO.match(codigo)
    if m:
        inicio, fin, resto = m.groups()
        # '*' y '**' van pegados a la salida; otro texto (p. ej. 'ECO') en una tercera línea
        return f"{inicio}\n{fin}{resto}" if not resto or resto.startswith("*") else f"{inicio}\n{fin}\n{resto}"
    if " " in codigo and len(codigo) > 6:
        return codigo.replace(" ", "\n", 1)
    return codigo


def _sin_corchetes(codigo: str) -> str:
    return codigo[1:-1].strip() if codigo.startswith("[") and codigo.endswith("]") else codigo


def _es_novedad(codigo: str) -> bool:
    return codigo.startswith("[")


def _es_descanso(codigo: str) -> bool:
    return codigo in ("Z", "L")


def _es_induccion(codigo: str) -> bool:
    return codigo.upper().startswith("IND")


def _clave(*partes: str) -> str:
    """Nombre de destino interno del PDF (sin espacios ni símbolos)."""
    return "-".join(re.sub(r"[^A-Za-z0-9]+", "_", x) for x in partes)


def _n(valor: int) -> str:
    return f"{valor:,}".replace(",", ".")


def _rango_texto(desde: date, hasta: date) -> str:
    return f"Del {desde.day} al {hasta.day} de {MESES[desde.month]} de {desde.year}"


class _Encabezado(Paragraph):
    """Encabezado de ubicación: registra el marcador del PDF y la entrada del índice."""

    def __init__(self, texto: str, entrada: str, clave: str):
        super().__init__(texto, _E["h_ubi"])
        self.entrada, self.clave = entrada, clave


class _TituloPuesto(Paragraph):
    def __init__(self, texto: str, entrada: str, clave: str):
        super().__init__(texto, _E["h_puesto"])
        self.entrada, self.clave = entrada, clave


class _Documento(BaseDocTemplate):
    def __init__(self, buf: BytesIO, hoja: tuple[float, float], prog: Programacion, generado: datetime, total_paginas: int):
        super().__init__(buf, pagesize=hoja, leftMargin=24, rightMargin=24, topMargin=34, bottomMargin=28,
                         title=f"Programación {_rango_texto(prog.desde, prog.hasta)}", author=prog.compania,
                         subject="Listado de asignación por ubicación y puesto", creator="Plataforma Servigpoder")
        self.prog, self.generado, self.total_paginas = prog, generado, total_paginas
        self.paginas: dict[str, int] = {}  # clave de ubicación → página donde empieza
        marco = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="normal")
        self.addPageTemplates([PageTemplate("portada", [marco], onPage=self._pie),
                               PageTemplate("cuerpo", [marco], onPage=self._decorar)])

    def _pie(self, c: canvas_rl.Canvas, doc) -> None:
        c.saveState()
        c.setFont("Helvetica", 7)
        c.setFillColor(GRIS_TEXTO)
        c.drawString(self.leftMargin, 14, f"Generado el {self.generado:%d/%m/%Y %H:%M} · Plataforma Servigpoder · Uso interno")
        total = f" de {self.total_paginas}" if self.total_paginas else ""
        c.drawRightString(self.pagesize[0] - self.rightMargin, 14, f"Página {doc.page}{total}")
        c.restoreState()

    def _decorar(self, c: canvas_rl.Canvas, doc) -> None:
        self._pie(c, doc)
        ancho, alto = self.pagesize
        c.saveState()
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(AZUL)
        c.drawString(self.leftMargin, alto - 22, f"Programación de personal · {_rango_texto(self.prog.desde, self.prog.hasta)}")
        c.setFont("Helvetica", 7.5)
        c.setFillColor(GRIS_TEXTO)
        c.drawRightString(ancho - self.rightMargin, alto - 22, self.prog.compania[:95])
        c.setStrokeColor(BORDE)
        c.setLineWidth(0.5)
        c.line(self.leftMargin, alto - 26, ancho - self.rightMargin, alto - 26)
        c.restoreState()

    def afterFlowable(self, flowable) -> None:
        if isinstance(flowable, _Encabezado):
            self.canv.bookmarkPage(flowable.clave)
            self.canv.addOutlineEntry(flowable.entrada, flowable.clave, level=0, closed=True)
            self.paginas[flowable.clave] = self.page
        elif isinstance(flowable, _TituloPuesto):
            self.canv.bookmarkPage(flowable.clave)
            self.canv.addOutlineEntry(flowable.entrada, flowable.clave, level=1)


def _tabla_puesto(puesto: Puesto, fechas: list[date], festivos: dict[date, str], ancho: float) -> Table:
    n = len(fechas)
    ancho_nombre = min(165.0, max(120.0, ancho * 0.19))
    ancho_dia = (ancho - ancho_nombre) / n
    fuente = 6.8 if n <= 16 else 5.6

    encabezado = ["Empleado"] + [f"{DIAS[d.weekday()]}\n{d.day}" for d in fechas]
    datos = [encabezado]
    estilo = [
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", fuente + 0.4),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("FONT", (1, 1), (-1, -1), "Helvetica", fuente),
        ("LEADING", (0, 0), (-1, -1), fuente + 1.4),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDE),
        ("BOX", (0, 0), (-1, -1), 0.6, AZUL),
        ("TOPPADDING", (0, 0), (-1, -1), 1.6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]
    # Domingos y festivos: encabezado de color y columna sombreada
    for j, d in enumerate(fechas, start=1):
        if d in festivos:
            estilo += [("BACKGROUND", (j, 0), (j, 0), FESTIVO_ENC), ("BACKGROUND", (j, 1), (j, -1), FESTIVO_FONDO)]
        elif d.weekday() == 6:
            estilo += [("BACKGROUND", (j, 0), (j, 0), DOMINGO_ENC), ("BACKGROUND", (j, 1), (j, -1), DOMINGO_FONDO)]

    for i, e in enumerate(puesto.empleados, start=1):
        fila = [Paragraph(escape(e.nombre), _E["nombre"])]
        if i % 2 == 0:
            estilo.append(("BACKGROUND", (0, i), (0, i), RAYADO))
        for j, d in enumerate(fechas, start=1):
            codigo = e.dias.get(d, "")
            fila.append(celda(codigo))
            if not codigo:
                continue
            if _es_novedad(codigo):
                estilo += [("BACKGROUND", (j, i), (j, i), NOVEDAD_FONDO), ("TEXTCOLOR", (j, i), (j, i), NOVEDAD_TEXTO),
                           ("FONT", (j, i), (j, i), "Helvetica-Bold", fuente)]
            elif _es_descanso(codigo):
                estilo += [("TEXTCOLOR", (j, i), (j, i), GRIS_TEXTO), ("BACKGROUND", (j, i), (j, i), GRIS_FONDO)]
            elif _es_induccion(codigo):
                estilo.append(("BACKGROUND", (j, i), (j, i), INDUCCION_FONDO))
        datos.append(fila)

    tabla = Table(datos, colWidths=[ancho_nombre] + [ancho_dia] * n, repeatRows=1)
    tabla.setStyle(TableStyle(estilo))
    return tabla


def _leyenda(prog: Programacion, festivos: dict[date, str]) -> list:
    usados = Counter(c for u in prog.ubicaciones.values() for p in u.puestos.values() for e in p.empleados for c in e.dias.values())
    novedades, otros = [], []
    for codigo, veces in sorted(usados.items()):
        if _HORARIO.match(codigo):
            continue
        base = _sin_corchetes(codigo)
        significado = SIGNIFICADOS.get(base, "")
        (novedades if _es_novedad(codigo) or _es_descanso(codigo) or significado else otros).append((codigo, significado, veces))

    elementos: list = [PageBreak(), Paragraph("Convenciones", _E["h_indice"]),
                       Paragraph("Horarios en dos líneas: entrada arriba y salida abajo (un turno que cruza la medianoche, "
                                 "como 18:00 a 06:00, sale el día que empieza). Los sufijos * y ** se muestran tal como vienen "
                                 "de SIESA. Celda vacía: sin programación ese día.", _E["nota"]), Spacer(1, 6)]
    muestra = [["", "Significado"],
               ["Do", "Domingo (columna sombreada)"], ["Fest.", "Festivo (columna sombreada en rojo)"],
               ["[VAC]", "Novedad (en morado)"], ["Z / L", "Descanso / libre (en gris)"]]
    t = Table(muestra, colWidths=[50, 260])
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8), ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDE), ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("BACKGROUND", (0, 1), (0, 1), DOMINGO_ENC), ("TEXTCOLOR", (0, 1), (0, 1), colors.white),
        ("BACKGROUND", (0, 2), (0, 2), FESTIVO_ENC), ("TEXTCOLOR", (0, 2), (0, 2), colors.white),
        ("BACKGROUND", (0, 3), (0, 3), NOVEDAD_FONDO), ("TEXTCOLOR", (0, 3), (0, 3), NOVEDAD_TEXTO),
        ("BACKGROUND", (0, 4), (0, 4), GRIS_FONDO), ("TEXTCOLOR", (0, 4), (0, 4), GRIS_TEXTO),
    ]))
    elementos += [t, Spacer(1, 10)]

    filas = [["Código", "Significado", "Veces en el reporte"]]
    filas += [[c, s or "Código de SIESA", f"{v:,}".replace(",", ".")] for c, s, v in novedades + otros]
    t = Table(filas, colWidths=[90, 260, 100], repeatRows=1)
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8), ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
        ("BACKGROUND", (0, 0), (-1, 0), AZUL_CLARO), ("GRID", (0, 0), (-1, -1), 0.4, BORDE), ("ALIGN", (2, 0), (2, -1), "RIGHT"),
    ]))
    elementos.append(t)
    if festivos:
        elementos += [Spacer(1, 10), Paragraph("Festivos del periodo: " + "; ".join(
            f"{d.day} de {MESES[d.month]} ({escape(n)})" for d, n in sorted(festivos.items())), _E["nota"])]
    return elementos


def _indice(ubicaciones: list[Ubicacion], paginas: dict[str, int], ancho: float) -> Table:
    """Índice en dos columnas; cada nombre es un enlace a su ubicación."""
    celdas = []
    for u in ubicaciones:
        clave = _clave("u", u.codigo)
        lugar = f" · {u.ciudad}" if u.ciudad else ""
        texto = f'<a href="#{escape(clave)}" color="#1F3A5F"><b>{escape(u.codigo)}</b> · {escape(u.nombre)}{escape(lugar)}</a>'
        celdas.append([Paragraph(texto, _E["indice"]), f"{u.empleados}", str(paginas.get(clave, ""))])
    mitad = -(-len(celdas) // 2)
    izquierda, derecha = celdas[:mitad], celdas[mitad:] + [["", "", ""]] * (mitad - len(celdas[mitad:]))
    filas = [["Ubicación", "Emp.", "Pág.", "", "Ubicación", "Emp.", "Pág."]]
    filas += [a + [""] + b for a, b in zip(izquierda, derecha)]
    col = (ancho - 16) / 2
    t = Table(filas, colWidths=[col - 62, 28, 34, 16, col - 62, 28, 34], repeatRows=1)
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 7), ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7),
        ("TEXTCOLOR", (0, 0), (-1, 0), GRIS_TEXTO), ("LINEBELOW", (0, 0), (2, 0), 0.6, AZUL), ("LINEBELOW", (4, 0), (6, 0), 0.6, AZUL),
        ("ALIGN", (1, 0), (2, -1), "RIGHT"), ("ALIGN", (5, 0), (6, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]))
    return t


def _historia(prog: Programacion, ubicaciones: list[Ubicacion], festivos: dict[date, str], generado: datetime,
              filtros: str, paginas: dict[str, int], ancho: float) -> list:
    fechas = prog.fechas
    historia: list = [
        Paragraph("Listado de asignación por ubicación y puesto", _E["titulo"]),
        Spacer(1, 4),
        Paragraph(escape(prog.compania), _E["sub"]),
        Paragraph(f"<b>{_rango_texto(prog.desde, prog.hasta)}</b> ({len(fechas)} días) · Generado el {generado:%d/%m/%Y %H:%M}", _E["sub"]),
    ]
    if filtros:
        historia.append(Paragraph(f"Filtros: {escape(filtros)}", _E["sub"]))
    resumen = Table([["Ubicaciones", "Puestos", "Filas de empleados", "Festivos en el periodo"],
                     [_n(len(ubicaciones)), _n(sum(len(u.puestos) for u in ubicaciones)),
                      _n(sum(u.empleados for u in ubicaciones)), str(len(festivos))]],
                    colWidths=[ancho / 4] * 4)
    resumen.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica", 8), ("TEXTCOLOR", (0, 0), (-1, 0), GRIS_TEXTO),
        ("FONT", (0, 1), (-1, 1), "Helvetica-Bold", 16), ("TEXTCOLOR", (0, 1), (-1, 1), AZUL),
        ("BACKGROUND", (0, 0), (-1, -1), AZUL_CLARO), ("BOX", (0, 0), (-1, -1), 0.6, BORDE),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("LEFTPADDING", (0, 0), (-1, -1), 10),
    ]))
    historia += [Spacer(1, 10), resumen, Paragraph("Índice de ubicaciones", _E["h_indice"]),
                 _indice(ubicaciones, paginas, ancho), NextPageTemplate("cuerpo"), PageBreak()]

    for u in ubicaciones:
        n_p, n_e = len(u.puestos), u.empleados
        lugar = f" · {u.ciudad}" if u.ciudad else ""
        cabecera = (f"Ubicación {escape(u.codigo)} · {escape(u.nombre)}{escape(lugar)}"
                    f"<font size=8.5>   —   {n_p} puesto{'s' if n_p != 1 else ''} · {n_e} empleado{'s' if n_e != 1 else ''}</font>")
        entrada = f"{u.codigo} · {u.nombre}{lugar} ({n_p} p. · {n_e} emp.)"
        for k, p in enumerate(u.puestos.values()):
            titulo = _TituloPuesto(f"Puesto {escape(p.codigo)} · {escape(p.descripcion)}",
                                   f"{p.codigo} · {p.descripcion}", _clave("p", u.codigo, p.codigo))
            total = Paragraph(f"Total puesto {escape(p.codigo)}: {len(p.empleados)} empleado{'s' if len(p.empleados) != 1 else ''}", _E["total"])
            bloque = [titulo, _tabla_puesto(p, fechas, festivos, ancho), total]
            if k == 0:
                # El encabezado de la ubicación siempre queda junto a su primer puesto
                bloque.insert(0, _Encabezado(cabecera, entrada, _clave("u", u.codigo)))
            historia.append(KeepTogether(bloque))

    historia += _leyenda(prog, festivos)
    return historia


def generar(prog: Programacion, filtros: str = "") -> bytes:
    return construir(prog, filtros)[0]


def construir(prog: Programacion, filtros: str = "") -> tuple[bytes, dict[str, int], int]:
    """PDF, página donde empieza cada ubicación (por clave) y total de páginas."""
    generado = datetime.now(ZONA)
    festivos = {d: n for d, n in holidays.Colombia(years=prog.desde.year).items() if prog.desde <= d <= prog.hasta}
    ubicaciones = ordenada(prog)

    paginas: dict[str, int] = {}
    total = 0
    for _ in range(2):  # 1.ª pasada: páginas de cada ubicación y total; 2.ª: índice y numeración definitivos
        buf = BytesIO()
        doc = _Documento(buf, HOJA, prog, generado, total)
        doc.build(_historia(prog, ubicaciones, festivos, generado, filtros, paginas, doc.width))
        paginas, total = doc.paginas, doc.page
    return buf.getvalue(), paginas, total
