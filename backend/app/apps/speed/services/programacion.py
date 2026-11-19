"""Lectura del archivo de programación de Speed (hojas «PROGRAMACION GENERAL», «SEÑORA SANDRA»…).

Cada hoja tiene bloques por puesto: una fila con los días de la semana, otra con el número del día y debajo una fila por persona
(PUESTO, APELLIDOS Y NOMBRES, DOCUMENTO…) con un código por día. Se leen todas las hojas que tengan la columna «DOCUMENTO» y la
fila de días; las demás (caja menor, ejemplos) se ignoran. El archivo se procesa en memoria y no se guarda.

Traslados: una persona puede salir en varios puestos. Donde no trabaja ese día hay una celda combinada con un texto
(«TRASLADO A HEROES 80») o vacía, y los turnos de esos días están en la fila del otro puesto. Por eso se juntan los días de
todas las filas de la misma cédula. Si dos filas traen códigos distintos el mismo día, manda el que más afecta el pago
(ver PRIORIDAD) y se avisa.

Códigos (hoja 2 del archivo y reglas acordadas con el usuario el 2026-11-18):
- Turnos trabajados: D, N, A, B, C, IND, INN, TMA, DISP. Descanso: X.
- TAD / TAN: turno adicional diurno / nocturno. Es un día trabajado y además se paga aparte (valor por turno en Parámetros).
- PNR, AUS, SUS: descuentan salario, auxilio de transporte y variables (licencia no remunerada, ausencia, suspensión).
- RUN (renuncia) y DESPR (desprogramado): también descuentan salario, auxilio y variables.
- PR, CD, LUT, DDF, LYM: licencias remuneradas; pagan salario pero descuentan auxilio y variables.
- VAC: vacaciones; pagan salario pero descuentan auxilio y variables.
- INC: incapacidad (2 días al 100 % y desde el 3.º al 66,67 %); descuenta auxilio y variables.
- Día vacío (sin código en ninguna fila): sin programación; descuenta las variables de quien aplica a la regla.
- INC 180: incapacidad de más de 180 días (2026-11-19). Esos días no se pagan (ni salario, ni auxilio, ni variables: la
  incapacidad ya no la reconoce la empresa). Si toda la quincena es INC 180 (o INC 180 y descansos), la persona no se
  liquida ni sale en la nómina: se muestra aparte en la pestaña de alertas.
- Quien sale en la programación sin ningún turno en toda la quincena (p. ej. en el puesto INCAPACITADO sin días) no se
  paga: esos días se toman como desprogramados (2026-11-19). Lo ideal es programarlo con INC.
"""

import io
import re
import unicodedata
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date

from openpyxl import load_workbook


class ProgramacionInvalida(ValueError):
    pass


TRABAJO = {"D", "N", "A", "B", "C", "IND", "INN", "TMA", "DISP"}
DESCANSO = {"X"}
ADICIONAL = {"TAD", "TAN"}
# Código → campo de la novedad donde se cuenta el día
NOVEDAD = {
    "AUS": "ausencias", "PNR": "licencias", "SUS": "suspensiones", "RUN": "desprogramados", "DESPR": "desprogramados",
    "PR": "permisos_remunerados", "CD": "permisos_remunerados", "LUT": "permisos_remunerados", "DDF": "permisos_remunerados",
    "LYM": "permisos_remunerados", "VAC": "vacaciones", "INC": "incapacidad", "INC180": "desprogramados",
}
ALIAS = {"DESP": "DESPR"}
INC180 = "INC180"
CODIGOS = TRABAJO | DESCANSO | ADICIONAL | set(NOVEDAD)
NOMBRES = {
    "D": "Turno diurno", "N": "Turno nocturno", "A": "Turno 06:00 a 14:00", "B": "Turno 14:00 a 22:00", "C": "Turno 22:00 a 06:00",
    "IND": "Inducción diurno", "INN": "Inducción nocturno", "TMA": "Turno mutuo acuerdo", "DISP": "Disponible", "X": "Descanso",
    "TAD": "Turno adicional diurno", "TAN": "Turno adicional nocturno", "AUS": "Ausencia", "PNR": "Permiso no remunerado",
    "SUS": "Suspensión", "RUN": "Renuncia", "DESPR": "Desprogramado", "PR": "Permiso remunerado", "CD": "Calamidad doméstica",
    "LUT": "Licencia de luto", "DDF": "Día de la familia", "LYM": "Ley María", "VAC": "Vacaciones", "INC": "Incapacidad",
    "INC180": "Incapacidad de más de 180 días",
}
# Si dos filas de la misma persona traen códigos distintos el mismo día, gana el de mayor prioridad
PRIORIDAD = {**{c: 6 for c in ("RUN", "DESPR", "AUS", "PNR", "SUS", "INC180")}, "INC": 5, "VAC": 4,
             **{c: 3 for c in ("PR", "CD", "LUT", "DDF", "LYM")}, "TAD": 2, "TAN": 2, **{c: 1 for c in TRABAJO}, "X": 0}


def efecto(c: str) -> str:
    """Lo que el código hace en el pago: trabajar y descansar son iguales; cada campo de novedad es distinto."""
    return NOVEDAD.get(c) or ("adicional" if c in ADICIONAL else "normal")


CAMPOS = ("ausencias", "licencias", "suspensiones", "desprogramados", "permisos_remunerados", "vacaciones", "incapacidad")


def _normal(t) -> str:
    t = "".join(c for c in unicodedata.normalize("NFD", str(t or "").lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def _cedula(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return re.sub(r"\D", "", str(v))


def codigo(v) -> str | None:
    """El código de una celda, o None si está vacía o es un texto (traslado, nota)."""
    if v is None:
        return None
    t = re.sub(r"[\s\-_.>+]+", "", str(v)).upper()  # «INC 180», «INC-180» → INC180
    t = ALIAS.get(t, t)
    return t if t in CODIGOS else None


@dataclass
class Persona:
    cedula: str
    nombre: str
    puestos: list[str] = field(default_factory=list)
    dias: dict[int, str] = field(default_factory=dict)  # día del mes → código
    conflictos: list[tuple[int, str]] = field(default_factory=list)  # (día, detalle)


def _dias_de_fila(fila: tuple, desde: int) -> dict[int, int]:
    """Columna → día del mes si la fila es la de los números de día (1, 2, 3… seguidos)."""
    mapa: dict[int, int] = {}
    anterior = None
    for j in range(desde, len(fila)):
        v = fila[j]
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        if not isinstance(v, int) or not 1 <= v <= 31:
            if mapa:
                break
            continue
        if anterior is not None and v != anterior + 1:
            break
        mapa[j] = v
        anterior = v
    return mapa if len(mapa) >= 7 else {}


def _letras(fila: tuple, mapa: dict[int, int]) -> dict[int, str]:
    return {dia: _normal(fila[j]).upper() for j, dia in mapa.items() if j < len(fila) and fila[j] is not None}


def leer(contenido: bytes) -> tuple[dict[str, Persona], list[str], dict]:
    """Personas (por cédula) con sus códigos por día del mes, advertencias e información del archivo."""
    try:
        libro = load_workbook(io.BytesIO(contenido), data_only=True)
    except Exception as e:
        raise ProgramacionInvalida("No se pudo abrir el Excel") from e
    personas: dict[str, Persona] = {}
    advertencias: list[str] = []
    sin_documento: list[str] = []
    hojas: list[str] = []
    semana: dict[int, str] = {}
    try:
        for hoja in libro.worksheets:
            # Las celdas combinadas guardan el valor solo en la primera: se replica en todo el rango
            combinadas: dict[tuple[int, int], object] = {}
            for rango in hoja.merged_cells.ranges:
                valor = hoja.cell(rango.min_row, rango.min_col).value
                for r in range(rango.min_row, rango.max_row + 1):
                    for c in range(rango.min_col, rango.max_col + 1):
                        combinadas[(r - 1, c - 1)] = valor
            filas = [tuple(f) for f in hoja.iter_rows(values_only=True)]
            col_doc = col_nombre = col_puesto = None
            for fila in filas[:40]:
                normales = [_normal(v) for v in fila]
                if "documento" in normales and any(n.startswith("apellidos") for n in normales):
                    col_doc = normales.index("documento")
                    col_nombre = next(j for j, n in enumerate(normales) if n.startswith("apellidos"))
                    col_puesto = normales.index("puesto") if "puesto" in normales else None
                    break
            if col_doc is None:
                continue
            desde = max(col_doc, col_nombre) + 1
            mapa: dict[int, int] = {}
            leida = False
            for i, fila in enumerate(filas):
                nuevo = _dias_de_fila(fila, desde)
                if nuevo:
                    mapa = nuevo
                    if i > 0 and not semana:
                        semana = _letras(filas[i - 1], mapa)
                    continue
                if not mapa:
                    continue
                cedula = _cedula(fila[col_doc] if col_doc < len(fila) else None)
                nombre = re.sub(r"\s+", " ", str(fila[col_nombre] or "")).strip() if col_nombre < len(fila) else ""
                codigos = {dia: codigo(combinadas.get((i, j), fila[j] if j < len(fila) else None)) for j, dia in mapa.items()}
                if not cedula:
                    # Sin documento: se intenta cruzar después por el nombre (clave «nombre:…»)
                    con_datos = any(codigos.values()) or any("horas" in _normal(v) for v in fila if isinstance(v, str))
                    if not nombre or len(nombre) < 6 or not con_datos:
                        continue
                    cedula = "nombre:" + _normal(nombre)
                    sin_documento.append(f"{hoja.title} fila {i + 1}: {nombre[:60]}")
                leida = True
                p = personas.setdefault(cedula, Persona("" if cedula.startswith("nombre:") else cedula, nombre))
                puesto = re.sub(r"\s+", " ", str(fila[col_puesto] or "")).strip() if col_puesto is not None and col_puesto < len(fila) else ""
                if puesto and puesto not in p.puestos:
                    p.puestos.append(puesto)
                for dia, c in codigos.items():
                    if c is None:
                        continue
                    actual = p.dias.get(dia)
                    if actual is None or actual == c:
                        p.dias[dia] = c
                        continue
                    gana = c if PRIORIDAD[c] > PRIORIDAD[actual] else actual
                    if efecto(c) != efecto(actual):
                        p.conflictos.append((dia, f"día {dia}: {actual} y {c} (se tomó {gana})"))
                    p.dias[dia] = gana
            if leida:
                hojas.append(hoja.title)
    finally:
        libro.close()
    if not personas:
        raise ProgramacionInvalida("No se encontró la programación: el archivo debe tener la columna «DOCUMENTO» y la fila con los números de día")
    return personas, advertencias, {"hojas": hojas, "semana": semana, "sin_documento": sin_documento}


# Letra del día de la semana como la usa el archivo (lunes = 0)
LETRA_SEMANA = ("L", "M", "MM", "J", "V", "S", "D")


def revisar_mes(semana: dict[int, str], anio: int, mes: int) -> str | None:
    """Avisa si los días de la semana del archivo no corresponden al mes de la quincena."""
    ultimo = monthrange(anio, mes)[1]
    revisados = [(d, s) for d, s in semana.items() if d <= ultimo and s in LETRA_SEMANA]
    if len(revisados) < 5:
        return None
    errados = sum(1 for d, s in revisados if LETRA_SEMANA[date(anio, mes, d).weekday()] != s)
    if errados > len(revisados) / 2:
        return f"Los días de la semana del archivo no coinciden con {mes:02d}/{anio}: revise que la programación sea de este mes"
    return None


def novedad(p: Persona, anio: int, mes: int, quincena: int, ingreso: date | None) -> dict:
    """Los días de la quincena de una persona según su programación (para la novedad y la liquidación).

    Quincena comercial: 1–15 y 16–30. Del 31 solo cuentan los turnos adicionales. En febrero, los días 29 y 30 que no
    existen no cuentan como vacíos.
    """
    desde, hasta = (1, 15) if quincena == 1 else (16, 30)
    ultimo = monthrange(anio, mes)[1]
    inicio = desde
    if ingreso and (ingreso.year, ingreso.month) == (anio, mes):
        inicio = max(desde, min(ingreso.day, 30))
    conteo = {c: 0 for c in CAMPOS}
    sin_programacion = 0
    tad = tan = 0
    tramos: list[int] = []  # días seguidos de cada incapacidad (en orden)
    inc_desde_inicio = False
    en_inc = False
    for dia in range(desde, hasta + 1):
        if dia < inicio or dia > ultimo:
            en_inc = False
            continue
        c = p.dias.get(dia)
        if c == "TAD":
            tad += 1
        elif c == "TAN":
            tan += 1
        if c is None:
            sin_programacion += 1
        elif c in NOVEDAD:
            conteo[NOVEDAD[c]] += 1
        if c == "INC":
            if en_inc:
                tramos[-1] += 1
            else:
                tramos.append(1)
                inc_desde_inicio = inc_desde_inicio or (dia == inicio and inicio == desde)
            en_inc = True
        else:
            en_inc = False
    if quincena == 2 and ultimo == 31:
        tad += p.dias.get(31) == "TAD"
        tan += p.dias.get(31) == "TAN"
    fin_inc = 0  # incapacidad que sigue al cierre de la quincena (para la siguiente)
    for dia in range(min(hasta, ultimo), inicio - 1, -1):
        if p.dias.get(dia) != "INC":
            break
        fin_inc += 1
    contrato = max(0, hasta - inicio + 1) if not (ingreso and (ingreso.year, ingreso.month) > (anio, mes)) else 0
    # Sin ningún código en toda la quincena: no se paga (desprogramado), con aviso
    sin_turnos = contrato > 0 and sin_programacion >= contrato
    # INC 180: si en la quincena no hay otro código que pague (solo INC 180 y descansos), no se liquida ni sale en la nómina
    del_rango = [p.dias.get(d) for d in range(inicio, min(hasta, ultimo) + 1)]
    inc180 = sum(1 for c in del_rango if c == INC180)
    inc180_toda = inc180 > 0 and all(c in (INC180, "X", None) for c in del_rango)
    if sin_turnos:
        conteo["desprogramados"] += sin_programacion
        sin_programacion = 0
    return {
        **conteo,
        "dias_programados": max(0, contrato - sin_programacion),
        "sin_programacion": sin_programacion,
        "turnos_tad": tad,
        "turnos_tan": tan,
        "programacion": {
            "dias": {str(d): p.dias[d] for d in sorted(p.dias) if desde <= d <= max(hasta, 31 if quincena == 2 else hasta)},
            "puestos": p.puestos[:6],
            "tramos_incapacidad": tramos,
            "incapacidad_desde_inicio": inc_desde_inicio,
            "incapacidad_al_cierre": fin_inc,
            "conflictos": [t for d, t in p.conflictos if desde <= d <= hasta][:10],
            "sin_turnos": sin_turnos,
            "inc180": inc180,
            "inc180_toda": inc180_toda,
        },
    }
