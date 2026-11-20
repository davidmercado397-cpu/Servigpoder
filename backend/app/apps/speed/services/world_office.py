"""Archivo plano de novedades para World Office (Speed).

Una fila por persona, por día y por novedad, sacada de los códigos de la programación de la quincena. Solo van las
novedades (turnos adicionales, ausencias, licencias, incapacidades…), no el salario, las horas extras ni los auxilios.

Columnas del modelo de cargue de World Office que usa Speed (Cargue_Novedades_2QOCTUBRE_2026, hoja GENERAL; 2026-11-20):
Encab: Empresa («SPEED SECURITY LTDA»), Encab: Tipo Documento (NNO), Encab: Prefijo (NOVNO), Encab: Documento Número (el
consecutivo que se pide al descargar), Detalle: Empleado (la cédula, como número), Concepto, Fecha (el día, mm-dd-yy),
Cantidad (1: una fila por día; las incapacidades van en una fila por tramo y concepto, con la fecha del primer
día y la cantidad de días, 2026-11-20), Valor (el día de salario; en los turnos adicionales, el valor del turno), Unidad Medida (D),
Centro Costos (Produccion si se liquida por programación; Administrativo si no), Nota («NOVEDADES 1RA QUINCENA
NOVIEMBRE2026-3 NOV: …»), Proceso (vacío), Pasa a Nómina y Aprobado (-1), Usuario Aprueba y Código Centro Costos (vacíos).
"""

import io
from dataclasses import dataclass
from datetime import date, datetime

import xlsxwriter

from app.apps.speed.services.programacion import NOMBRES

# Código → (concepto en World Office, se incluye). Los conceptos se pueden cambiar en Parámetros.
# Los que no estaban en el ejemplo de World Office quedan con un nombre propuesto para confirmar.
CONCEPTOS: dict[str, tuple[str, bool, str]] = {
    "TAD": ("Auxilio de Compensacion por descanso Diurno", True, "Turno adicional diurno (valor del turno en Parámetros)"),
    "TAN": ("Auxilio de compensacion por descanso Nocturno", True, "Turno adicional nocturno (valor del turno en Parámetros)"),
    "AUS": ("Ausencias", True, "Ausencia"),
    "PNR": ("Licencia No remunerada", True, "Permiso no remunerado"),
    "SUS": ("SUSPENSIÓN", True, "Suspensión"),
    "DESPR": ("Licencia No remunerada", True, "Desprogramado"),
    "RUN": ("Licencia No remunerada", False, "Renuncia (normalmente se retira en World Office)"),
    "PR": ("Licencia Remunerada", True, "Permiso remunerado"),
    "LUT": ("LICENCIA POR LUTO", True, "Licencia de luto"),
    "CD": ("Licencia Remunerada", True, "Calamidad doméstica"),
    "DDF": ("Licencia Remunerada", True, "Día de la familia"),
    "LYM": ("Licencia de Paternidad", True, "Ley María"),
    "VAC": ("Vacaciones", False, "Vacaciones (normalmente se liquidan en World Office)"),
    "INC180": ("Incapacidad mayor a 180 dias", False, "Incapacidad de más de 180 días (no la paga la empresa)"),
    "INC_EMPRESA": ("incapacidades Empresa 100%", True, "Incapacidad: primeros días al 100 % (los paga la empresa)"),
    "INC_EPS": ("Incapacidades EPS 66.67%", True, "Incapacidad: desde el 3.er día al 66,67 %"),
    "INC_EPS_MINIMO": ("Incapacidades EPS 100%", True, "Incapacidad desde el 3.er día cuando el 66,67 % no llega al mínimo (se paga el día completo)"),
}

ENCABEZADO = ["Encab: Empresa", "Encab: Tipo Documento", "Encab: Prefijo", "Encab: Documento Número", "Detalle: Empleado",
              "Detalle: Concepto", "Detalle: Fecha", "Detalle: Cantidad", "Detalle: Valor", "Detalle: Unidad Medida",
              "Detalle: Centro Costos", "Detalle: Nota", "Detalle: Proceso ", "Detalle: Pasa a Nómina", "Detalle: Aprobado",
              "Detalle: Usuario Aprueba", "Detalle: Código Centro Costos"]
EMPRESA = "SPEED SECURITY LTDA"
TIPO_DOCUMENTO = "NNO"
PREFIJO = "NOVNO"
MESES = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]
MESES_CORTOS = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"]
NOMBRE_NOTA = {"INC_EMPRESA": "Incapacidad", "INC_EPS": "Incapacidad", "INC_EPS_MINIMO": "Incapacidad"}


@dataclass
class Fila:
    nombre: str
    cedula: str
    concepto: str
    fecha: date
    valor: float
    centro: str
    nota: str
    cantidad: int = 1
    clave: str = ""
    hasta: int = 0  # último día (para juntar los días seguidos de una incapacidad)


def filas_persona(nombre: str, cedula: str, salario: float, produccion: bool, dias: dict[int, str], incapacidad_previos: float,
                  anio: int, mes: int, quincena: int, p: dict, conceptos: dict[str, tuple[str, bool]]) -> list[Fila]:
    """Las filas de una persona según sus códigos por día en la quincena."""
    desde, hasta = (1, 15) if quincena == 1 else (16, 31)
    diario = salario / 30
    minimo_diario = float(p.get("salario_minimo") or 0) / 30
    al_pct = diario * float(p.get("pct_incapacidad") or 0) / 100
    dias_100 = float(p.get("dias_incapacidad_100") or 0)
    centro = "Produccion" if produccion else "Administrativo"
    encabezado = f"NOVEDADES {'1RA' if quincena == 1 else '2DA'} QUINCENA {MESES[mes - 1]}{anio}"
    salida: list[Fila] = []
    racha = 0  # días seguidos de la incapacidad actual (la primera puede venir de la quincena anterior)
    previos = incapacidad_previos if dias.get(desde) == "INC" else 0
    for dia in range(desde, hasta + 1):
        c = dias.get(dia)
        if c != "INC":
            racha = 0
            previos = 0
        if c is None or (dia == 31 and c not in ("TAD", "TAN")):  # del 31 solo cuentan los turnos adicionales
            continue
        try:
            fecha = date(anio, mes, dia)
        except ValueError:
            continue
        if c == "INC":
            racha += 1
            if racha + previos <= dias_100:
                clave, valor = "INC_EMPRESA", diario
            elif al_pct < minimo_diario:
                clave, valor = "INC_EPS_MINIMO", minimo_diario
            else:
                clave, valor = "INC_EPS", al_pct
        elif c == "TAD":
            clave, valor = "TAD", float(p.get("valor_tad") or 0)
        elif c == "TAN":
            clave, valor = "TAN", float(p.get("valor_tan") or 0)
        elif c in conceptos:
            clave, valor = c, diario
        else:
            continue  # turnos normales y descansos no son novedad
        concepto, incluir = conceptos.get(clave, (clave, False))
        if not incluir:
            continue
        texto = NOMBRE_NOTA.get(clave) or NOMBRES.get(c, c)
        previa = salida[-1] if salida else None
        if c == "INC" and previa is not None and previa.clave == clave and previa.hasta == dia - 1:
            # Incapacidad: los días seguidos del mismo concepto van en una sola fila
            previa.cantidad += 1
            previa.hasta = dia
            previa.nota = (f"{encabezado}-{previa.fecha.day} al {dia} {MESES_CORTOS[mes - 1]}: {texto} {previa.cantidad} días")
            continue
        nota = f"{encabezado}-{dia} {MESES_CORTOS[mes - 1]}: {texto}" + (" 1 día" if c == "INC" else "")
        salida.append(Fila(nombre, cedula, concepto, fecha, round(valor, 2), centro, nota, 1, clave, dia))
    return salida


def excel(filas: list[Fila], documento: int) -> bytes:
    """El plano con el modelo de cargue de World Office (hoja GENERAL)."""
    buf = io.BytesIO()
    libro = xlsxwriter.Workbook(buf, {"in_memory": True})
    hoja = libro.add_worksheet("GENERAL")
    titulo = libro.add_format({"bold": True, "bg_color": "#FFFF00"})
    fecha = libro.add_format({"num_format": "mm-dd-yy"})
    numero = libro.add_format({"num_format": "0"})
    plata = libro.add_format({"num_format": '_(* #,##0_);_(* \\(#,##0\\);_(* "-"??_);_(@_)'})
    hoja.write_row(0, 0, ENCABEZADO, titulo)
    for i, f in enumerate(sorted(filas, key=lambda x: (x.nombre, x.fecha, x.concepto)), start=1):
        hoja.write_row(i, 0, [EMPRESA, TIPO_DOCUMENTO, PREFIJO, documento])
        if f.cedula.isdigit():
            hoja.write_number(i, 4, int(f.cedula), numero)
        else:
            hoja.write_string(i, 4, f.cedula)
        hoja.write_string(i, 5, f.concepto)
        hoja.write_datetime(i, 6, datetime(f.fecha.year, f.fecha.month, f.fecha.day), fecha)
        hoja.write_number(i, 7, f.cantidad)
        hoja.write_number(i, 8, f.valor, plata)
        hoja.write_string(i, 9, "D")
        hoja.write_string(i, 10, f.centro)
        hoja.write_string(i, 11, f.nota)
        hoja.write_row(i, 13, [-1, -1])
    for col, ancho in enumerate((22.6, 22, 13.1, 25.4, 17.4, 41.1, 13.6, 16.4, 13.1, 22.4, 20.9, 70, 15.9, 21.6, 17.3, 23.6, 27.9)):
        hoja.set_column(col, col, ancho)
    libro.close()
    return buf.getvalue()
