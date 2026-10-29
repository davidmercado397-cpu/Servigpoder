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

_TIPOS_DESCUENTO = {"prestamo": "Préstamo", "embargo": "Embargo", "cuota": "Cuota"}

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


def sufijo(p) -> str:
    """Nombre de la nómina para el archivo (vacío para la nómina General)."""
    nombre = getattr(p, "nombre", "General") or "General"
    if nombre == "General":
        return ""
    limpio = "".join(c if c.isalnum() else "_" for c in nombre).strip("_")
    return f"_{limpio[:40]}" if limpio else ""


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
    return _guardar(libro), XLSX, f"liquidacion_{periodo.anio}_{periodo.mes:02d}_{periodo.tipo}{sufijo(periodo)}.xlsx"


def plantilla(periodo: LiqPeriodo, con_arl: bool = False) -> tuple[bytes, str, str]:
    """documento | <MES AÑO> | día 1 | día 2 | … con una fila vacía para llenar. La del costeo lleva además la
    columna "arl" (clase de riesgo 1 a 5)."""
    dias, actual = [], periodo.desde
    while actual <= periodo.hasta:
        dias.append(actual.day)
        actual += timedelta(days=1)
    libro = Workbook()
    hoja = libro.active
    hoja.title = _titulo(periodo)
    encabezado = ["documento", f"{_MESES[periodo.mes]} {periodo.anio}", *(["arl"] if con_arl else []), *dias]
    hoja.append(encabezado)
    for celda in hoja[1]:
        celda.fill, celda.font, celda.alignment = _RELLENO, _FUENTE, _CENTRO
    hoja.append([""] * len(encabezado))
    hoja.column_dimensions["A"].width = 16
    hoja.column_dimensions["B"].width = 28
    primera = 4 if con_arl else 3
    if con_arl:
        hoja.column_dimensions["C"].width = 6
    for i in range(len(dias)):
        hoja.column_dimensions[get_column_letter(primera + i)].width = 5
    hoja.freeze_panes = f"{get_column_letter(primera)}2"
    hoja.row_dimensions[1].height = 26
    return _guardar(libro), XLSX, f"plantilla_{periodo.anio}_{periodo.mes:02d}_{periodo.tipo}{sufijo(periodo)}.xlsx"


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
    "SUELDO BASICO", "INCAPACIDAD", "VACACIONES DIAS HABILES", "VACACIONES DIAS NO HABILES", *(f"VR {t}" for _, t in _CONCEPTOS_NOMINA), "AUXILIOS NO PRESTACIONALES", "AUXILIO DE TRANSPORTE",
    "NOVEDADES DEVENGO", "TOTAL DEVENGADO", "SALUD", "PENSION", "EMBARGOS", "PRESTAMOS", "CUOTAS", "NOVEDADES DEDUCCION",
    "TOTAL DEDUCCIONES", "NETO A PAGAR", "DIAS COD 180", "PROVISION SEG SOCIAL COD 180",
)
_PRIMERA_MONEDA = 7  # columna G (SUELDO BASICO) en adelante son pesos


def fila_nomina(r: LiqResultado) -> list:
    n = r.nomina or {}
    v = n.get("valores", {})
    return [r.empleado.documento, r.empleado.nombre, n.get("salario", 0), n.get("dias_salario", 0), n.get("dias_incapacidad", 0),
            n.get("dias_sin_pago", 0), n.get("basico", 0), n.get("incapacidad", 0),
            (n.get("vacaciones") or {}).get("valor_habiles", 0), (n.get("vacaciones") or {}).get("valor_no_habiles", 0),
            *(v.get(c, 0) for c, _ in _CONCEPTOS_NOMINA),
            n.get("auxilios_no_prestacionales", 0), n.get("auxilio", 0), n.get("novedades_devengo", 0), n.get("devengado", 0), n.get("salud", 0),
            n.get("pension", 0), n.get("embargos", 0), n.get("prestamos", 0), n.get("cuotas", 0), n.get("novedades_deduccion", 0),
            n.get("deducciones", 0), n.get("neto", 0), (n.get("seguridad_social_180") or {}).get("dias", 0), n.get("provision_ss_180", 0)]


TIPOS_NOVEDAD = {"auxilio_variable": "Auxilio no prestacional variable", "mayor_valor": "Mayor valor pagado", "menor_valor": "Menor valor pagado", "horas_extras": "Horas extras pendientes",
                 "recargos": "Recargos pendientes", "otro_devengo": "Otro devengo", "otra_deduccion": "Otra deducción"}


def _hoja_novedades(libro, filas: list[tuple[str | None, LiqResultado]]) -> None:
    """Detalle de las novedades manuales (con la nómina de cada persona si es el archivo del periodo completo)."""
    con_nomina = any(n is not None for n, _ in filas)
    hoja = libro.create_sheet("Novedades")
    hoja.append([*(["NOMINA"] if con_nomina else []), "DOCUMENTO", "EMPLEADO", "TIPO", "DESCRIPCION", "NOMINA DE ORIGEN", "EFECTO",
                 "CALCULO", "VALOR", "OBSERVACION"])
    for nombre, r in filas:
        for x in (r.nomina or {}).get("novedades", []):
            efecto = "Deducción" if x["deduccion"] else ("Devengo salarial" if x["salarial"] else "Devengo no salarial")
            hoja.append([*([nombre] if con_nomina else []), r.empleado.documento, r.empleado.nombre, TIPOS_NOVEDAD.get(x["tipo"], x["tipo"]),
                         x["descripcion"], x.get("nomina_origen") or "", efecto, x["calculo"], x["valor"], x.get("observacion", "")])
    for celda in hoja[1]:
        celda.fill, celda.font, celda.alignment = _RELLENO, _FUENTE, _CENTRO
    col_valor = 9 if con_nomina else 8
    for (celda,) in hoja.iter_rows(min_row=2, min_col=col_valor, max_col=col_valor):
        celda.number_format = "$ #,##0"
    _autoajustar(hoja, minimo=10, maximo=50)


def _formato_nomina(hoja, primera_moneda: int, ultima_col: int) -> None:
    for celda in hoja[1]:
        celda.fill, celda.font, celda.alignment = _RELLENO, _FUENTE, _CENTRO
    for col in range(primera_moneda, ultima_col + 1):
        for (celda,) in hoja.iter_rows(min_row=2, min_col=col, max_col=col):
            celda.number_format, celda.alignment = "$ #,##0", _DERECHA
    _autoajustar(hoja, minimo=11, maximo=24)
    hoja.row_dimensions[1].height = 42


def periodo_completo(db: Session, anio: int, mes: int, quincena: int) -> tuple[bytes, str, str] | None:
    """Todas las nóminas de un periodo (quincena o mes) en un archivo: una fila por persona y nómina con todo lo
    liquidado, el consolidado por persona, los descuentos y las novedades. Para cruces externos."""
    from openpyxl.styles import Border, Side

    nominas = list(db.scalars(select(LiqPeriodo).where(LiqPeriodo.anio == anio, LiqPeriodo.mes == mes, LiqPeriodo.quincena == quincena)
                              .order_by(LiqPeriodo.id)))
    if not nominas:
        return None
    filas: list[tuple[str, LiqResultado]] = []
    for p in nominas:
        for r in sorted(db.scalars(select(LiqResultado).where(LiqResultado.periodo_id == p.id)), key=lambda r: r.empleado.documento):
            if r.nomina:
                filas.append((f"{p.nombre} ({'cerrada' if p.estado == 'cerrada' else 'abierta'})", r))
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Nomina"
    hoja.append(["NOMINA", *ENCABEZADOS_NOMINA])
    for nombre, r in filas:
        hoja.append([nombre, *fila_nomina(r)])
    ultima = hoja.max_row
    linea = Side(style="thin", color="1E3A5F")
    if filas:
        total = ["TOTAL", None, f"{len(filas)} filas", None]
        for col in range(5, len(ENCABEZADOS_NOMINA) + 2):
            letra = get_column_letter(col)
            total.append(f"=SUM({letra}2:{letra}{ultima})")
        hoja.append(total)
        for celda in hoja[hoja.max_row]:
            celda.font, celda.border = Font(bold=True), Border(top=linea)
    _formato_nomina(hoja, _PRIMERA_MONEDA + 1, len(ENCABEZADOS_NOMINA) + 1)
    for col in (4, 5, 6, 7):  # salario es pesos; días, número
        for (celda,) in hoja.iter_rows(min_row=2, min_col=col, max_col=col):
            celda.number_format = "$ #,##0" if col == 4 else "#,##0"
    hoja.freeze_panes = "D2"

    # Consolidado por persona: suma de sus nóminas del periodo
    por_persona: dict[str, dict] = {}
    numericas = list(range(3, len(ENCABEZADOS_NOMINA)))  # desde SALARIO hasta NETO (índices de fila_nomina)
    for nombre, r in filas:
        f = fila_nomina(r)
        x = por_persona.setdefault(f[0], {"nombre": f[1], "nominas": [], "valores": [0.0] * len(ENCABEZADOS_NOMINA)})
        x["nominas"].append(nombre)
        for i in numericas:
            x["valores"][i] += float(f[i] or 0)
    con = libro.create_sheet("Por persona")
    columnas = [i for i in numericas if i >= 3]
    con.append(["DOCUMENTO", "EMPLEADO", "NOMINAS", *(ENCABEZADOS_NOMINA[i] for i in columnas)])
    for doc, x in sorted(por_persona.items(), key=lambda t: t[1]["nombre"]):
        con.append([doc, x["nombre"], " · ".join(x["nominas"]), *(round(x["valores"][i], 2) for i in columnas)])
    _formato_nomina(con, 4 + columnas.index(_PRIMERA_MONEDA - 1), len(columnas) + 3)
    con.freeze_panes = "D2"

    desc = libro.create_sheet("Descuentos")
    desc.append(["NOMINA", "DOCUMENTO", "EMPLEADO", "TIPO", "DESCRIPCION", "CALCULO", "VALOR DESCONTADO", "OBSERVACION"])
    for nombre, r in filas:
        for x in (r.nomina or {}).get("descuentos", []):
            desc.append([nombre, r.empleado.documento, r.empleado.nombre, _TIPOS_DESCUENTO.get(x["tipo"], x["tipo"]), x["descripcion"],
                         x["calculo"], x["valor"], x.get("observacion", "")])
    for celda in desc[1]:
        celda.fill, celda.font, celda.alignment = _RELLENO, _FUENTE, _CENTRO
    for (celda,) in desc.iter_rows(min_row=2, min_col=7, max_col=7):
        celda.number_format = "$ #,##0"
    _autoajustar(desc, minimo=10, maximo=50)
    _hoja_novedades(libro, filas)
    etiqueta = f"{anio}_{mes:02d}_{'MES' if quincena == 0 else f'Q{quincena}'}"
    return _guardar(libro), XLSX, f"nomina_periodo_{etiqueta}.xlsx"


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

    desc = libro.create_sheet("Prestamos embargos y cuotas")
    desc.append(["DOCUMENTO", "EMPLEADO", "TIPO", "DESCRIPCION", "CALCULO", "VALOR DESCONTADO", "OBSERVACION"])
    for r in resultados:
        for x in (r.nomina or {}).get("descuentos", []):
            desc.append([r.empleado.documento, r.empleado.nombre, _TIPOS_DESCUENTO.get(x["tipo"], x["tipo"]),
                         x["descripcion"], x["calculo"], x["valor"], x.get("observacion", "")])
    for celda in desc[1]:
        celda.fill, celda.font, celda.alignment = _RELLENO, _FUENTE, _CENTRO
    for (celda,) in desc.iter_rows(min_row=2, min_col=6, max_col=6):
        celda.number_format = "$ #,##0"
    _autoajustar(desc, minimo=10, maximo=50)
    _hoja_novedades(libro, [(None, r) for r in resultados])

    vac = libro.create_sheet("Vacaciones")
    vac.append(["DOCUMENTO", "EMPLEADO", "DIAS HABILES DEL EMPLEADO", "DIAS HABILES", "DIAS NO HABILES", "SALARIO",
                "PROMEDIO VARIABLE", "ORIGEN DEL PROMEDIO", "BASE MENSUAL", "VALOR DIA", "VALOR DIAS HABILES",
                "VALOR DIAS NO HABILES", "TOTAL VACACIONES", "SALDO PENDIENTE"])
    for r in resultados:
        x = (r.nomina or {}).get("vacaciones")
        if not x:
            continue
        origen = "Fijado por nómina" if x["promedio_manual"] else f"Sugerido ({x['meses_promedio']:g} meses de recargo nocturno)"
        vac.append([r.empleado.documento, r.empleado.nombre, x["dias_habiles_empleado"], x["dias_habiles"], x["dias_no_habiles"],
                    x["salario"], x["promedio"], origen, x["base"], x["valor_dia"], x["valor_habiles"], x["valor_no_habiles"],
                    x["valor"], x["saldo"]["pendientes"] if x.get("saldo") else "Sin fecha de ingreso"])
    for celda in vac[1]:
        celda.fill, celda.font, celda.alignment = _RELLENO, _FUENTE, _CENTRO
    for col in (6, 7, 9, 10, 11, 12, 13):
        for (celda,) in vac.iter_rows(min_row=2, min_col=col, max_col=col):
            celda.number_format = "$ #,##0"
    _autoajustar(vac, minimo=10, maximo=40)

    aux = libro.create_sheet("Auxilios no prestacionales")
    aux.append(["DOCUMENTO", "EMPLEADO", "DESCRIPCION", "CALCULO", "VALOR PAGADO", "EXCESO DEL 40 % EN LA BASE DE APORTES"])
    for r in resultados:
        n = r.nomina or {}
        for i, x in enumerate(n.get("auxilios", [])):
            aux.append([r.empleado.documento, r.empleado.nombre, x["descripcion"], x["calculo"], x["valor"],
                        n.get("exceso_no_salarial", 0) if i == 0 else None])
    for celda in aux[1]:
        celda.fill, celda.font, celda.alignment = _RELLENO, _FUENTE, _CENTRO
    for col in (5, 6):
        for (celda,) in aux.iter_rows(min_row=2, min_col=col, max_col=col):
            celda.number_format = "$ #,##0"
    _autoajustar(aux, minimo=10, maximo=50)

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

    if periodo.umbral_activo:
        um = libro.create_sheet("Umbral semanal")
        um.append([f"Umbral semanal de {float(periodo.umbral_horas):g} h (semanas partidas en proporción; "
                   f"{float(periodo.umbral_horas_novedad):g} h menos por día con novedad justificada)"])
        um.append(["DOCUMENTO", "EMPLEADO", "SEMANA DESDE", "SEMANA HASTA", "DIAS EN EL PERIODO", "NOVEDADES JUSTIFICADAS",
                   "UMBRAL", "HORAS TRABAJADAS", "EXTRAS GENERADAS", "EXTRAS PAGADAS", "EXTRAS DESCONTADAS"])
        for r in resultados:
            for s in r.umbral_semanas or []:
                um.append([r.empleado.documento, r.empleado.nombre, s["desde"], s["hasta"], s["dias_periodo"], s["justificados"],
                           s["umbral"], s["trabajadas"], s["extras"], s["pagadas"], s["descontadas"]])
        for celda in um[2]:
            celda.fill, celda.font, celda.alignment = _RELLENO, _FUENTE, _CENTRO
        for col in range(7, 12):
            for (celda,) in um.iter_rows(min_row=3, min_col=col, max_col=col):
                celda.number_format = "#,##0.00"
        _autoajustar(um, minimo=10, maximo=22)
        um.column_dimensions["A"].width = 14
        um.freeze_panes = "C3"
        um.row_dimensions[2].height = 32
    return _guardar(libro), XLSX, f"nomina_{periodo.anio}_{periodo.mes:02d}_{periodo.tipo}{sufijo(periodo)}.xlsx"
