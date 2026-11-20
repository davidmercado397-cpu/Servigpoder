"""Cruce de la nómina que liquida World Office contra la que calcula la plataforma (Speed, 2026-11-20).

Se sube el Excel que exporta World Office («ExportarAExcel»: Puesto Trabajo, Cuenta No, Nombre del Trabajador «NOMBRES CC
CÉDULA», Sueldo Básico, Días Trab, Sueldo Devengado, Valor Incapac, Horas Extras, Auxilio Transporte, Recargo Nocturno, Otros
Devengados, Total Devengado, Aporte Salud, Aporte Pensión, Retención en la Fuente, Fondo Solidar, Valor Préstamos,
OtrosDeducidos, Total Descuento, Neto a Pagar). Se lee en memoria y no se guarda el archivo: solo los valores por persona.

Se compara concepto por concepto. Una diferencia de dinero cuenta desde 1.000 pesos, hacia arriba o hacia abajo (−999 a 999 no
es diferencia; −1.100 sí). Los días cuentan desde medio día. Cada diferencia se puede justificar (cuál valor está bien y por
qué); si después la diferencia cambia, la justificación ya no aplica y vuelve a quedar pendiente.
"""

import io
import re
import unicodedata
from dataclasses import dataclass

from openpyxl import load_workbook

TOLERANCIA = 1000.0
TOLERANCIA_DIAS = 0.5


class ArchivoInvalido(ValueError):
    pass


def _normal(t) -> str:
    t = "".join(c for c in unicodedata.normalize("NFD", str(t or "").lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "", t)


# Encabezado de World Office (normalizado) → campo
COLUMNAS = {
    "puestotrabajo": "area", "nombredeltrabajador": "nombre", "sueldobasico": "sueldo_basico", "diastrab": "dias",
    "sueldodevengado": "sueldo", "valorincapac": "incapacidad", "horasextras": "horas_extras",
    "auxiliotransporteyconectividad": "auxilio", "auxiliotransporte": "auxilio", "recargonocturno": "recargo",
    "otrosdevengados": "otros_devengados", "totaldevengado": "total_devengado", "aportesalud": "salud",
    "aportepension": "pension", "retencionenlafuente": "retencion", "fondosolidar": "fondo_solidaridad",
    "valorprestamos": "prestamos", "otrosdeducidos": "otros_deducidos", "totaldescuento": "total_descuento",
    "netoapagar": "neto",
}
OBLIGATORIAS = ("nombre", "neto", "total_devengado")
NUMERICOS = ("sueldo_basico", "dias", "sueldo", "incapacidad", "horas_extras", "auxilio", "recargo", "otros_devengados",
             "total_devengado", "salud", "pension", "retencion", "fondo_solidaridad", "prestamos", "otros_deducidos",
             "total_descuento", "neto")


def _numero(v) -> float:
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    t = re.sub(r"[^\d,.\-]", "", str(v))
    # El separador que va de último con 1 o 2 decimales es el decimal; los demás son de miles
    m = re.search(r"[.,](\d{1,2})$", t)
    entero, decimales = (t[:m.start()], m.group(1)) if m else (t, "")
    t = re.sub(r"[.,]", "", entero) + (f".{decimales}" if decimales else "")
    try:
        return float(t)
    except ValueError:
        return 0.0


def separar_nombre(texto: str) -> tuple[str, str]:
    """«ADRIANA CASTILLO GUTIERREZ CC 1018455843» → (nombre, cédula). La cédula son los dígitos del final."""
    t = re.sub(r"\s+", " ", str(texto or "")).strip()
    m = re.search(r"(?:\b(?:CC|C\.C\.?|CE|TI|PEP|PPT|NIT|PA)\s*)?([0-9][0-9.\-]{4,})\s*$", t, re.IGNORECASE)
    if not m:
        return t, ""
    return t[:m.start()].strip(" -"), re.sub(r"\D", "", m.group(1))


def leer(contenido: bytes) -> tuple[list[dict], dict]:
    """Las personas del Excel de nómina de World Office y la información del encabezado (documento y periodo)."""
    try:
        libro = load_workbook(io.BytesIO(contenido), data_only=True, read_only=True)
    except Exception as e:
        raise ArchivoInvalido("No se pudo abrir el Excel") from e
    personas: list[dict] = []
    info: dict = {"titulo": "", "desde": None, "hasta": None, "hoja": ""}
    try:
        for hoja in libro.worksheets:
            filas = [tuple(f) for f in hoja.iter_rows(values_only=True)]
            mapa: dict[str, int] = {}
            inicio = 0
            for i, fila in enumerate(filas[:30]):
                cols = {COLUMNAS[_normal(v)]: j for j, v in enumerate(fila) if _normal(v) in COLUMNAS}
                if all(c in cols for c in OBLIGATORIAS):
                    mapa, inicio = cols, i + 1
                    break
                texto = " ".join(str(v) for v in fila if v is not None)
                if "nomina" in _normal(texto) and not info["titulo"]:
                    info["titulo"] = texto.strip()[:200]
                    fechas = re.findall(r"(\d{1,2})/(\d{1,2})/(\d{4})", texto)
                    if len(fechas) >= 2:
                        info["desde"] = "-".join((fechas[0][2], fechas[0][1].zfill(2), fechas[0][0].zfill(2)))
                        info["hasta"] = "-".join((fechas[1][2], fechas[1][1].zfill(2), fechas[1][0].zfill(2)))
            if not mapa:
                continue
            info["hoja"] = hoja.title
            for fila in filas[inicio:]:
                valor = lambda campo: fila[mapa[campo]] if campo in mapa and mapa[campo] < len(fila) else None  # noqa: E731
                area = str(valor("area") or "").strip()
                crudo = str(valor("nombre") or "").strip()
                if not crudo or area.lower().startswith("total") or crudo.lower().startswith("total"):
                    continue
                nombre, cedula = separar_nombre(crudo)
                personas.append({"cedula": cedula, "nombre": nombre, "area": area,
                                 **{c: _numero(valor(c)) for c in NUMERICOS}})
            break
    finally:
        libro.close()
    if not personas:
        raise ArchivoInvalido("No se encontró la nómina de World Office: el archivo debe tener las columnas «Nombre del Trabajador», "
                              "«Total Devengado» y «Neto a Pagar»")
    return personas, info


@dataclass(frozen=True)
class Concepto:
    clave: str
    nombre: str
    dias: bool = False


CONCEPTOS = (
    Concepto("dias", "Días trabajados", dias=True),
    Concepto("sueldo", "Sueldo devengado (salario y vacaciones)"),
    Concepto("incapacidad", "Incapacidad"),
    Concepto("horas_extras", "Horas extras y recargos"),
    Concepto("auxilio", "Auxilio de transporte"),
    Concepto("otros_devengados", "Otros devengados (Ley 2466, bonificaciones, rodamiento, comisiones, turnos adicionales, pagos adicionales)"),
    Concepto("total_devengado", "Total devengado"),
    Concepto("salud", "Aporte salud"),
    Concepto("pension", "Aporte pensión"),
    Concepto("otros_descuentos", "Otros descuentos (préstamos, embargos, cuotas, retención, fondo de solidaridad)"),
    Concepto("total_descuento", "Total descuentos"),
    Concepto("neto", "Neto a pagar"),
)
NOMBRES = {c.clave: c.nombre for c in CONCEPTOS} | {"persona": "Persona"}


def valores_wo(w: dict) -> dict[str, float]:
    return {
        "dias": w["dias"], "sueldo": w["sueldo"], "incapacidad": w["incapacidad"], "horas_extras": w["horas_extras"] + w["recargo"],
        "auxilio": w["auxilio"], "otros_devengados": w["otros_devengados"], "total_devengado": w["total_devengado"],
        "salud": w["salud"], "pension": w["pension"],
        "otros_descuentos": w["retencion"] + w["fondo_solidaridad"] + w["prestamos"] + w["otros_deducidos"],
        "total_descuento": w["total_descuento"], "neto": w["neto"],
    }


def valores_nuestros(liq: dict) -> dict[str, float]:
    """liq: devengado, deducciones, neto, conceptos y dias (como se guardan en la liquidación)."""
    c = {k: float(v or 0) for k, v in (liq.get("conceptos") or {}).items()}
    g = lambda *k: sum(c.get(x, 0.0) for x in k)  # noqa: E731
    return {
        "dias": float((liq.get("dias") or {}).get("trabajados") or 0), "sueldo": g("salario", "vacaciones"), "incapacidad": g("incapacidad"),
        "horas_extras": g("horas_extras"), "auxilio": g("auxilio_transporte"),
        "otros_devengados": g("comisiones", "ley_2466", "bonificaciones", "rodamiento", "turnos_adicionales", "pago_adicional"),
        "total_devengado": float(liq.get("devengado") or 0), "salud": g("salud"), "pension": g("pension"),
        "otros_descuentos": g("embargos", "prestamos", "cuotas"), "total_descuento": float(liq.get("deducciones") or 0),
        "neto": float(liq.get("neto") or 0),
    }


def es_diferencia(clave: str, diferencia: float) -> bool:
    """Desde 1.000 pesos (en positivo o negativo); los días, desde medio día."""
    if clave == "dias":
        return abs(diferencia) >= TOLERANCIA_DIAS
    return abs(round(diferencia, 2)) >= TOLERANCIA


def comparar(nuestro: dict[str, float], wo: dict[str, float]) -> list[dict]:
    salida = []
    for c in CONCEPTOS:
        dif = round(wo[c.clave] - nuestro[c.clave], 2)
        if es_diferencia(c.clave, dif):
            salida.append({"concepto": c.clave, "nombre": c.nombre, "nuestro": nuestro[c.clave], "wo": wo[c.clave], "diferencia": dif})
    return salida


def misma_diferencia(clave: str, justificada: float, actual: float) -> bool:
    """La justificación sigue aplicando si la diferencia no cambió (dentro de la tolerancia)."""
    return not es_diferencia(clave, actual - justificada)
