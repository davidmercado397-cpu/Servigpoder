"""Archivos que se descargan de una quincena.

- Liquidación ("Calendario + Liquidación" en la app original): el archivo que se sube al sistema de
  nómina. Conserva las 19 columnas y su orden; DIAS CON NOVEDAD se agrega al final.
- Plantilla: el calendario vacío que se llena y se vuelve a cargar.
"""

import io
from datetime import timedelta

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.apps.liquidador.dominio.tipos import HourConcept
from app.apps.liquidador.models import LiqPeriodo, LiqResultado
from app.apps.liquidador.services.calculo import AUSENCIA, DESCANSO_PAGO, INCAPACIDAD, LIBRE, NOVEDAD, TRABAJADO

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Mismo orden de la plantilla de referencia `Libro1.xlsx`
ENCABEZADOS: tuple[str, ...] = (
    "DOCUMENTO", "EMPLEADO",
    "DIURNAS ORDINARIA", "RECARGO NOCTURNO", "RECARGO FESTIVO DIURNO", "RECARGO FESTIVO NOCTURNO",
    "RECARGO DOMINICAL DIURNO", "RECARGO DOMINICAL NOCTURNO", "EXTRAS ORDINARIA DIURNAS", "EXTRAS ORDINARIA NOCTURNAS",
    "EXTRAS FESTIVAS DIURNAS", "EXTRAS FESTIVAS NOCTURNAS", "EXTRAS DOMINICALES DIURNAS", "EXTRAS DOMINICALES NOCTURNAS",
    "DIAS TRABAJADOS", "DESCANSOS PAGOS", "LIBRES", "AUSENCIAS", "INCAPACIDADES",
    "DIAS CON NOVEDAD",
)
ORDEN_CONCEPTOS: tuple[HourConcept, ...] = (
    HourConcept.ORDINARY_DAY, HourConcept.ORDINARY_NIGHT, HourConcept.HOLIDAY_DAY_SURCHARGE,
    HourConcept.HOLIDAY_NIGHT_SURCHARGE, HourConcept.SUNDAY_SURCHARGE, HourConcept.SUNDAY_NIGHT_SURCHARGE,
    HourConcept.OVERTIME_DAY, HourConcept.OVERTIME_NIGHT, HourConcept.HOLIDAY_OVERTIME_DAY,
    HourConcept.HOLIDAY_OVERTIME_NIGHT, HourConcept.SUNDAY_OVERTIME_DAY, HourConcept.SUNDAY_OVERTIME_NIGHT,
)
ORDEN_DIAS = (TRABAJADO, DESCANSO_PAGO, LIBRE, AUSENCIA, INCAPACIDAD, NOVEDAD)

_RELLENO = PatternFill(start_color="1E3A5F", end_color="1E3A5F", fill_type="solid")
_FUENTE = Font(bold=True, color="FFFFFF", size=10)
_CENTRO = Alignment(horizontal="center", vertical="center", wrap_text=True)
_DERECHA = Alignment(horizontal="right", vertical="center")
_MESES = ("", "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE",
          "NOVIEMBRE", "DICIEMBRE")


def _titulo(p: LiqPeriodo) -> str:
    return f"{p.anio}-{p.mes:02d}-{p.tipo}"


def fila_liquidacion(r: LiqResultado) -> list:
    return ([r.empleado.documento, r.empleado.nombre]
            + [float(r.horas.get(c.value, 0)) for c in ORDEN_CONCEPTOS]
            + [int(r.dias.get(k, 0)) for k in ORDEN_DIAS])


def liquidacion(db: Session, periodo: LiqPeriodo) -> tuple[bytes, str, str]:
    # Orden por documento como texto (igual que la app original), sin depender de la intercalación de la base
    resultados = sorted(db.scalars(select(LiqResultado).where(LiqResultado.periodo_id == periodo.id)),
                        key=lambda r: r.empleado.documento)
    libro = Workbook()
    hoja = libro.active
    hoja.title = _titulo(periodo)
    hoja.append(list(ENCABEZADOS))
    for celda in hoja[1]:
        celda.fill, celda.font, celda.alignment = _RELLENO, _FUENTE, _CENTRO
    for r in resultados:
        hoja.append(fila_liquidacion(r))

    # Horas con un decimal (columnas 3 a 14); conteos como enteros
    for col in range(1, len(ENCABEZADOS) + 1):
        formato = "#,##0.0" if 3 <= col <= 14 else "#,##0"
        for (celda,) in hoja.iter_rows(min_row=2, min_col=col, max_col=col):
            celda.number_format, celda.alignment = formato, _DERECHA
    _autoajustar(hoja, minimo=10, maximo=22)
    hoja.freeze_panes = "C2"
    hoja.row_dimensions[1].height = 32
    return _guardar(libro), XLSX, f"liquidacion_{periodo.anio}_{periodo.mes:02d}_{periodo.tipo}.xlsx"


def plantilla(periodo: LiqPeriodo) -> tuple[bytes, str, str]:
    """documento | <MES AÑO> | día 1 | día 2 | … con una fila vacía para llenar."""
    dias, actual = [], periodo.desde
    while actual <= periodo.hasta:
        dias.append(actual.day)
        actual += timedelta(days=1)
    libro = Workbook()
    hoja = libro.active
    hoja.title = _titulo(periodo)
    encabezado = ["documento", f"{_MESES[periodo.mes]} {periodo.anio}", *dias]
    hoja.append(encabezado)
    for celda in hoja[1]:
        celda.fill, celda.font, celda.alignment = _RELLENO, _FUENTE, _CENTRO
    hoja.append([""] * len(encabezado))
    hoja.column_dimensions["A"].width = 16
    hoja.column_dimensions["B"].width = 28
    for i in range(len(dias)):
        hoja.column_dimensions[get_column_letter(3 + i)].width = 5
    hoja.freeze_panes = "C2"
    hoja.row_dimensions[1].height = 26
    return _guardar(libro), XLSX, f"plantilla_{periodo.anio}_{periodo.mes:02d}_{periodo.tipo}.xlsx"


def _autoajustar(hoja, *, minimo: int, maximo: int, margen: int = 2) -> None:
    for celdas in hoja.columns:
        largo = max((len(linea) for c in celdas if c.value is not None for linea in str(c.value).split("\n")), default=0)
        hoja.column_dimensions[celdas[0].column_letter].width = max(minimo, min(maximo, largo + margen))


def _guardar(libro: Workbook) -> bytes:
    buf = io.BytesIO()
    libro.save(buf)
    return buf.getvalue()


# --- Nómina ---

_CONCEPTOS_NOMINA = tuple((c.value, ENCABEZADOS[2 + i]) for i, c in enumerate(ORDEN_CONCEPTOS) if c != HourConcept.ORDINARY_DAY)
ENCABEZADOS_NOMINA: tuple[str, ...] = (
    "DOCUMENTO", "EMPLEADO", "SALARIO", "DIAS PAGADOS", "DIAS INCAPACIDAD", "DIAS SIN PAGO",
    "SUELDO BASICO", "INCAPACIDAD", *(f"VR {t}" for _, t in _CONCEPTOS_NOMINA), "AUXILIO DE TRANSPORTE",
    "TOTAL DEVENGADO", "SALUD", "PENSION", "EMBARGOS", "PRESTAMOS", "TOTAL DEDUCCIONES", "NETO A PAGAR",
)
_PRIMERA_MONEDA = 7  # columna G (SUELDO BASICO) en adelante son pesos


def fila_nomina(r: LiqResultado) -> list:
    n = r.nomina or {}
    v = n.get("valores", {})
    return [r.empleado.documento, r.empleado.nombre, n.get("salario", 0), n.get("dias_salario", 0), n.get("dias_incapacidad", 0),
            n.get("dias_sin_pago", 0), n.get("basico", 0), n.get("incapacidad", 0), *(v.get(c, 0) for c, _ in _CONCEPTOS_NOMINA),
            n.get("auxilio", 0), n.get("devengado", 0), n.get("salud", 0), n.get("pension", 0), n.get("embargos", 0),
            n.get("prestamos", 0), n.get("deducciones", 0), n.get("neto", 0)]


def nomina(db: Session, periodo: LiqPeriodo) -> tuple[bytes, str, str]:
    """Valor por concepto, total devengado, deducciones y neto por persona, con el detalle de descuentos y
    las tarifas usadas. Archivo aparte: el de liquidación (horas) no cambia."""
    from openpyxl.styles import Border, Side

    from app.apps.liquidador.models import LiqTarifa

    resultados = sorted(db.scalars(select(LiqResultado).where(LiqResultado.periodo_id == periodo.id)),
                        key=lambda r: r.empleado.documento)
    libro = Workbook()
    hoja = libro.active
    hoja.title = f"Nomina {_titulo(periodo)}"
    hoja.append(list(ENCABEZADOS_NOMINA))
    for r in resultados:
        hoja.append(fila_nomina(r))
    ultima = hoja.max_row
    if resultados:
        total = ["TOTAL", f"{len(resultados)} empleados", None]
        for col in range(4, len(ENCABEZADOS_NOMINA) + 1):
            letra = get_column_letter(col)
            total.append(f"=SUM({letra}2:{letra}{ultima})")
        hoja.append(total)
        linea = Side(style="thin", color="1E3A5F")
        for celda in hoja[hoja.max_row]:
            celda.font, celda.border = Font(bold=True), Border(top=linea)
    for celda in hoja[1]:
        celda.fill, celda.font, celda.alignment = _RELLENO, _FUENTE, _CENTRO
    for col in range(3, len(ENCABEZADOS_NOMINA) + 1):
        formato = "$ #,##0" if col == 3 or col >= _PRIMERA_MONEDA else "#,##0"
        for (celda,) in hoja.iter_rows(min_row=2, min_col=col, max_col=col):
            celda.number_format, celda.alignment = formato, _DERECHA
    _autoajustar(hoja, minimo=11, maximo=24)
    hoja.freeze_panes = "C2"
    hoja.row_dimensions[1].height = 42

    desc = libro.create_sheet("Prestamos y embargos")
    desc.append(["DOCUMENTO", "EMPLEADO", "TIPO", "DESCRIPCION", "CALCULO", "VALOR DESCONTADO", "OBSERVACION"])
    for r in resultados:
        for x in (r.nomina or {}).get("descuentos", []):
            desc.append([r.empleado.documento, r.empleado.nombre, "Embargo" if x["tipo"] == "embargo" else "Préstamo",
                         x["descripcion"], x["calculo"], x["valor"], x.get("observacion", "")])
    for celda in desc[1]:
        celda.fill, celda.font, celda.alignment = _RELLENO, _FUENTE, _CENTRO
    for (celda,) in desc.iter_rows(min_row=2, min_col=6, max_col=6):
        celda.number_format = "$ #,##0"
    _autoajustar(desc, minimo=10, maximo=50)

    usadas = sorted({f for r in resultados for f in (r.nomina or {}).get("tarifas", [])})
    tar = libro.create_sheet("Tarifas usadas")
    tar.append(["VIGENTE DESDE", "SALARIO MINIMO", "AUXILIO TRANSPORTE", "HORAS MES", "SALUD %", "PENSION %",
                *(f"% {t}" for _, t in _CONCEPTOS_NOMINA), "NOTA"])
    for t in db.scalars(select(LiqTarifa).order_by(LiqTarifa.vigente_desde)):
        if t.vigente_desde.isoformat() in usadas:
            tar.append([t.vigente_desde, float(t.smlmv), float(t.auxilio_transporte), t.horas_mes, float(t.salud_pct),
                        float(t.pension_pct), *(t.porcentajes.get(c, 0) for c, _ in _CONCEPTOS_NOMINA), t.nota])
    for celda in tar[1]:
        celda.fill, celda.font, celda.alignment = _RELLENO, _FUENTE, _CENTRO
    for (celda,) in tar.iter_rows(min_row=2, min_col=1, max_col=1):
        celda.number_format = "dd/mm/yyyy"
    _autoajustar(tar, minimo=10, maximo=40)
    tar.row_dimensions[1].height = 42
    return _guardar(libro), XLSX, f"nomina_{periodo.anio}_{periodo.mes:02d}_{periodo.tipo}.xlsx"
