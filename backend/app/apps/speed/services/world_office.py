"""Archivo plano de novedades para World Office (Speed).

Una fila por persona, por día y por novedad, sacada de los códigos de la programación de la quincena. Solo van las
novedades (turnos adicionales, ausencias, licencias, incapacidades…), no el salario, las horas extras ni los auxilios.

Columnas (como la plantilla que usa Speed): Empleado («APELLIDOS NOMBRES - CÉDULA»), Tipo (concepto de World Office),
Fecha (el día, a las 0:00), Cantidad (1), Valor (el día de salario; en los turnos adicionales, el valor del turno),
Unidad de medida («Día»), Centro de Costos (Produccion si se liquida por programación; Administrativo si no), Nota,
Proceso (vacío) y Pasa a Nómina / Aprobado / Procesado (-1).
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
    "SUS": ("Suspension", True, "Suspensión"),
    "DESPR": ("Licencia No remunerada", True, "Desprogramado"),
    "RUN": ("Licencia No remunerada", False, "Renuncia (normalmente se retira en World Office)"),
    "PR": ("Licencia Remunerada", True, "Permiso remunerado"),
    "LUT": ("LICENCIA POR LUTO", True, "Licencia de luto"),
    "CD": ("Licencia Remunerada", True, "Calamidad doméstica"),
    "DDF": ("Licencia Remunerada", True, "Día de la familia"),
    "LYM": ("Licencia de Paternidad", True, "Ley María"),
    "VAC": ("Vacaciones", False, "Vacaciones (normalmente se liquidan en World Office)"),
    "INC_EMPRESA": ("incapacidades Empresa 100%", True, "Incapacidad: primeros días al 100 % (los paga la empresa)"),
    "INC_EPS": ("Incapacidades EPS 66.67%", True, "Incapacidad: desde el 3.er día al 66,67 %"),
    "INC_EPS_MINIMO": ("Incapacidades EPS 100%", True, "Incapacidad desde el 3.er día cuando el 66,67 % no llega al mínimo (se paga el día completo)"),
}

ENCABEZADO = ["Empleado", "Tipo", "Fecha", "Cantidad", "Valor", "Unidad de medida", "Centro de Costos", "Nota", "Proceso",
              "Pasa a Nómina", "Aprobado", "Procesado"]
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


def filas_persona(nombre: str, cedula: str, salario: float, produccion: bool, dias: dict[int, str], incapacidad_previos: float,
                  anio: int, mes: int, quincena: int, p: dict, conceptos: dict[str, tuple[str, bool]]) -> list[Fila]:
    """Las filas de una persona según sus códigos por día en la quincena."""
    desde, hasta = (1, 15) if quincena == 1 else (16, 31)
    diario = salario / 30
    minimo_diario = float(p.get("salario_minimo") or 0) / 30
    al_pct = diario * float(p.get("pct_incapacidad") or 0) / 100
    dias_100 = float(p.get("dias_incapacidad_100") or 0)
    centro = "Produccion" if produccion else "Administrativo"
    encabezado = f"NOVEDADES {'1RA' if quincena == 1 else '2DA'} QUINCENA DE {MESES[mes - 1]} {anio}"
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
        nota = f"{encabezado}-{dia:02d} {MESES_CORTOS[mes - 1]}: {texto}"
        salida.append(Fila(nombre, cedula, concepto, fecha, round(valor, 2), centro, nota))
    return salida


def excel(filas: list[Fila]) -> bytes:
    buf = io.BytesIO()
    libro = xlsxwriter.Workbook(buf, {"in_memory": True})
    hoja = libro.add_worksheet("Hoja1")
    fecha = libro.add_format({"num_format": "m/d/yy h:mm"})
    plata = libro.add_format({"num_format": "#,##0.00"})
    hoja.write_row(0, 0, ENCABEZADO)
    for i, f in enumerate(sorted(filas, key=lambda x: (x.nombre, x.fecha, x.concepto)), start=1):
        hoja.write_string(i, 0, f"{f.nombre} - {f.cedula}")
        hoja.write_string(i, 1, f.concepto)
        hoja.write_datetime(i, 2, datetime(f.fecha.year, f.fecha.month, f.fecha.day), fecha)
        hoja.write_number(i, 3, 1)
        hoja.write_number(i, 4, f.valor, plata)
        hoja.write_string(i, 5, "Día")
        hoja.write_string(i, 6, f.centro)
        hoja.write_string(i, 7, f.nota)
        hoja.write_string(i, 8, "")
        hoja.write_row(i, 9, [-1, -1, -1])
    hoja.set_column(0, 0, 45)
    hoja.set_column(1, 1, 44)
    hoja.set_column(2, 2, 14)
    hoja.set_column(3, 6, 12)
    hoja.set_column(7, 7, 70)
    libro.close()
    return buf.getvalue()
