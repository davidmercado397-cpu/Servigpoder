"""Lectura del Excel de colaboradores de Speed (hoja «LISTADO») y de la plantilla de novedades de la quincena.

El archivo se procesa en memoria y no se guarda. Del Listado se toman los datos de trabajo y los valores; la dirección y
el teléfono no se guardan (no hacen falta para liquidar).
"""

import io
import re
import unicodedata
from datetime import date, datetime

from openpyxl import load_workbook


class ListadoInvalido(ValueError):
    pass


def _normal(t) -> str:
    t = "".join(c for c in unicodedata.normalize("NFD", str(t or "").lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def _num(v) -> float:
    if v in (None, ""):
        return 0.0
    if isinstance(v, (int, float)):
        return round(float(v), 2)
    t = str(v).replace("$", "").replace(" ", "")
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})+(,\d+)?", t):
        t = t.replace(".", "").replace(",", ".")
    try:
        return round(float(t.replace(",", ".")), 2)
    except ValueError:
        return 0.0


def _cedula(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return re.sub(r"\D", "", str(v))


def _fecha(v) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(v.strip(), formato).date()
            except ValueError:
                continue
    return None


def _texto(v, largo: int) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:largo]


# Encabezado normalizado → campo. Los dos «Rodamiento»: el primero es el valor y el segundo la nota de texto.
COLUMNAS = {
    "identificacion": "cedula", "apellidos y nombres": "nombre", "fecha de ingreso": "fecha_ingreso",
    "tipo de contrato": "tipo_contrato", "tipo de nomina": "grupo", "cargo": "cargo", "area": "area", "puesto": "puesto",
    "cliente": "cliente", "tipo de turno": "tipo_turno", "salario": "salario", "auxilio de transporte": "auxilio_listado",
    "horas extras": "horas_extras", "comisiones": "comisiones", "ley 2466": "ley_2466", "bonificaciones": "bonificaciones",
    "rodamiento": "rodamiento", "regla de programacion": "aplica_programacion",
}
OBLIGATORIAS = ("cedula", "nombre", "salario", "aplica_programacion")


def leer_listado(contenido: bytes) -> tuple[list[dict], list[str]]:
    """Empleados del Listado (una fila por cédula) y advertencias."""
    try:
        libro = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    except Exception as e:
        raise ListadoInvalido("No se pudo abrir el Excel") from e
    try:
        hoja = next((h for h in libro.worksheets if _normal(h.title) == "listado"), None)
        if hoja is None:
            raise ListadoInvalido("El Excel no tiene la hoja «LISTADO»")
        filas = list(hoja.iter_rows(values_only=True))
    finally:
        libro.close()

    encabezado = None
    for i, fila in enumerate(filas[:30]):
        if any(_normal(v).startswith("identificacion") for v in fila):
            encabezado = i
            break
    if encabezado is None:
        raise ListadoInvalido("No se encontró la fila de encabezados (la que tiene «Identificación»)")
    columnas: dict[str, int] = {}
    for j, v in enumerate(filas[encabezado]):
        clave = _normal(v)
        campo = next((c for k, c in COLUMNAS.items() if clave == k or clave.startswith(k)), None)
        if campo == "rodamiento" and "rodamiento" in columnas:
            columnas["nota"] = j  # el segundo «Rodamiento» es el texto que explica el auxilio
        elif campo and campo not in columnas:
            columnas[campo] = j
    faltan = [c for c in OBLIGATORIAS if c not in columnas]
    if faltan:
        raise ListadoInvalido("Faltan columnas en el Listado: " + ", ".join(faltan))

    empleados: dict[str, dict] = {}
    advertencias: list[str] = []
    for i, fila in enumerate(filas[encabezado + 1:], start=encabezado + 2):
        def val(campo):
            j = columnas.get(campo)
            return fila[j] if j is not None and j < len(fila) else None

        cedula = _cedula(val("cedula"))
        if not cedula:
            continue  # filas vacías y de totales
        regla = _normal(val("aplica_programacion"))
        if regla not in ("si aplica", "no aplica", "si", "no"):
            advertencias.append(f"Fila {i}: la regla de programación dice «{_texto(val('aplica_programacion'), 30)}»; se tomó «SI APLICA»")
        nota = val("nota")
        e = {
            "cedula": cedula, "nombre": _texto(val("nombre"), 160), "fecha_ingreso": _fecha(val("fecha_ingreso")),
            "tipo_contrato": _texto(val("tipo_contrato"), 40), "grupo": _texto(val("grupo"), 40), "cargo": _texto(val("cargo"), 120),
            "area": _texto(val("area"), 80), "puesto": _texto(val("puesto"), 120), "cliente": _texto(val("cliente"), 160),
            "tipo_turno": _texto(val("tipo_turno"), 120),
            **{c: _num(val(c)) for c in ("salario", "auxilio_listado", "horas_extras", "comisiones", "ley_2466", "bonificaciones", "rodamiento")},
            "nota": "" if nota in (None, 0, "0") else _texto(nota, 300),
            "aplica_programacion": not regla.startswith("no"),
        }
        if not e["salario"]:
            advertencias.append(f"Fila {i} ({cedula}): sin salario")
        if cedula in empleados:
            advertencias.append(f"Fila {i}: la cédula {cedula} está repetida; se tomó la última")
        empleados[cedula] = e
    if not empleados:
        raise ListadoInvalido("El Listado no tiene empleados")
    return list(empleados.values()), advertencias


# --- Plantilla de novedades de la quincena ------------------------------------------------------------------

COLUMNAS_NOVEDAD = [("cedula", "Cédula"), ("nombre", "Nombre"), ("dias_programados", "Días programados"), ("ausencias", "Ausencias"),
                    ("licencias", "Licencias no remuneradas"), ("suspensiones", "Suspensiones"), ("incapacidad", "Días de incapacidad"),
                    ("incapacidad_previos", "Días previos de la misma incapacidad"), ("observacion", "Observación")]


def leer_novedades(contenido: bytes) -> tuple[list[dict], list[str]]:
    try:
        libro = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    except Exception as e:
        raise ListadoInvalido("No se pudo abrir el Excel") from e
    try:
        filas = list(libro.worksheets[0].iter_rows(values_only=True))
    finally:
        libro.close()
    if not filas:
        raise ListadoInvalido("La plantilla está vacía")
    titulos = {_normal(t): c for c, t in COLUMNAS_NOVEDAD}
    columnas = {titulos[_normal(v)]: j for j, v in enumerate(filas[0]) if _normal(v) in titulos}
    if "cedula" not in columnas:
        raise ListadoInvalido("La plantilla no tiene la columna «Cédula»")
    salida, advertencias = [], []
    for i, fila in enumerate(filas[1:], start=2):
        def val(campo):
            j = columnas.get(campo)
            return fila[j] if j is not None and j < len(fila) else None

        cedula = _cedula(val("cedula"))
        if not cedula:
            continue
        n = {"cedula": cedula, "observacion": _texto(val("observacion"), 300)}
        prog = val("dias_programados")
        n["dias_programados"] = None if prog in (None, "") else _num(prog)
        for c in ("ausencias", "licencias", "suspensiones", "incapacidad", "incapacidad_previos"):
            n[c] = _num(val(c))
            if n[c] < 0 or n[c] > 15 and c != "incapacidad_previos":
                advertencias.append(f"Fila {i} ({cedula}): {c} = {n[c]:g} fuera de rango; se ignoró la fila")
                break
        else:
            salida.append(n)
    return salida, advertencias
