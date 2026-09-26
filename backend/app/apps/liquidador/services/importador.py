"""Carga del Excel de turnos de una quincena (mismo formato que la app original).

Fila 1: `documento` | nombre (o el mes, p. ej. MAYO) | [salario] [cargo] | 1 | 2 | … (o fechas completas)
Filas siguientes: documento, nombre y el código del turno de cada día (vacío = sin turno).
El archivo se procesa en memoria y no se guarda en el servidor.
"""

import io
from dataclasses import dataclass, field
from datetime import date, datetime

from openpyxl import load_workbook
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.apps.liquidador.models import LiqDia, LiqEmpleado, LiqPeriodo
from app.apps.liquidador.services.turnos import por_codigo

_ALIAS = {
    "documento": "documento", "document_id": "documento",
    "nombre_completo": "nombre", "nombres_apellidos": "nombre", "nombre": "nombre", "full_name": "nombre",
    # El salario ya no se usa (solo se cuentan horas): la columna se reconoce para no leerla como día
    "salario": "salario", "salario_basico": "salario", "salario_base": "salario", "base_salary": "salario",
    "cargo": "cargo", "position": "cargo",
}
_MESES = ("", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
          "noviembre", "diciembre")


class ErrorImportacion(ValueError):
    pass


@dataclass
class FilaResumen:
    documento: str
    nombre: str
    dias: int
    turnos: str  # p. ej. "D×8, N×2"


@dataclass
class Resumen:
    empleados: int = 0
    dias: int = 0
    fechas: int = 0
    advertencias: list[str] = field(default_factory=list)
    detalle: list[FilaResumen] = field(default_factory=list)


def _normalizar(valor: object) -> str:
    clave = str(valor).strip().lower().replace(" ", "_")
    return _ALIAS.get(clave, clave)


def _rango(desde: date, hasta: date) -> str:
    if (desde.year, desde.month) == (hasta.year, hasta.month):
        return f"{desde.day} al {hasta.day} de {_MESES[desde.month]} de {desde.year}"
    if desde.year == hasta.year:
        return f"{desde.day} de {_MESES[desde.month]} al {hasta.day} de {_MESES[hasta.month]} de {desde.year}"
    return f"{desde.day} de {_MESES[desde.month]} de {desde.year} al {hasta.day} de {_MESES[hasta.month]} de {hasta.year}"


def _fecha_encabezado(valor: object, periodo: LiqPeriodo) -> date | None:
    """Número de día (1-31) del mes de la quincena o fecha completa."""
    if valor is None or str(valor).strip() == "":
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor).strip()
    if isinstance(valor, (int, float)) or texto.isdigit():
        try:
            dia = int(float(valor)) if isinstance(valor, (int, float)) else int(texto)
            return date(periodo.anio, periodo.mes, dia) if 1 <= dia <= 31 else None
        except ValueError:
            return None  # día inexistente en el mes (p. ej. 30 de febrero)
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


def importar(db: Session, periodo: LiqPeriodo, contenido: bytes) -> Resumen:
    try:
        libro = load_workbook(io.BytesIO(contenido), data_only=True, read_only=True)
    except Exception as e:  # archivo dañado: no se expone el detalle técnico
        raise ErrorImportacion("No se pudo leer el archivo Excel. Verifica que sea un .xlsx válido.") from e
    hoja = libro.active
    hoja.reset_dimensions()
    filas = list(hoja.iter_rows(values_only=True))
    libro.close()
    if len(filas) < 2:
        raise ErrorImportacion("El archivo no contiene filas de datos. Asegúrate de incluir al menos un empleado.")

    encabezado = list(filas[0])
    if not encabezado or encabezado[0] is None or _normalizar(encabezado[0]) != "documento":
        raise ErrorImportacion("La primera columna debe llamarse 'documento'. Revisa el encabezado del Excel.")

    columnas_fecha: list[tuple[int, date]] = []
    col_cargo: int | None = None
    for i, celda in enumerate(encabezado[2:], start=2):
        if celda is None:
            continue
        clave = _normalizar(celda)
        if clave == "salario":
            continue
        if clave == "cargo":
            col_cargo = i
            continue
        fecha = _fecha_encabezado(celda, periodo)
        if fecha is not None:
            columnas_fecha.append((i, fecha))
    if not columnas_fecha:
        raise ErrorImportacion("No se encontraron columnas de fecha. A partir de la tercera columna, cada encabezado "
                               "debe ser un número de día (1 al 31) o una fecha completa.")

    if any(f < periodo.desde or f > periodo.hasta for _, f in columnas_fecha):
        fechas = [f for _, f in columnas_fecha]
        raise ErrorImportacion(
            f"El archivo cargado contiene fechas del {_rango(min(fechas), max(fechas))}, pero la quincena seleccionada es "
            f"{_rango(periodo.desde, periodo.hasta)}. Verifica que estás trabajando sobre la quincena correcta, o ajusta "
            f"los encabezados del Excel para que coincidan.")

    turnos = por_codigo(db)
    empleados = {e.documento: e for e in db.scalars(select(LiqEmpleado))}
    db.execute(delete(LiqDia).where(LiqDia.periodo_id == periodo.id))

    res = Resumen(fechas=len(columnas_fecha))
    vistos: set[tuple[str, date]] = set()
    for num, fila in enumerate(filas[1:], start=2):
        if not fila or fila[0] is None or str(fila[0]).strip() == "":
            continue
        documento = _texto_documento(fila[0])
        nombre = str((fila[1] if len(fila) > 1 else None) or "").strip() or documento
        cargo = "Vigilante"
        if col_cargo is not None and col_cargo < len(fila) and fila[col_cargo]:
            cargo = str(fila[col_cargo]).strip() or "Vigilante"

        emp = empleados.get(documento)
        if emp is None:
            emp = LiqEmpleado(documento=documento, nombre=nombre[:200], cargo=cargo[:80])
            db.add(emp)
            empleados[documento] = emp
        else:
            emp.nombre, emp.cargo = nombre[:200], cargo[:80]
        db.flush()
        res.empleados += 1

        por_turno: dict[str, int] = {}
        for col, fecha in columnas_fecha:
            if col >= len(fila) or fila[col] is None or str(fila[col]).strip() == "":
                continue
            codigo = str(fila[col]).strip().upper()
            turno = turnos.get(codigo)
            if turno is None:
                res.advertencias.append(f"Fila {num}, {fecha.isoformat()}: el turno '{codigo}' no existe — se omitió")
                continue
            if (documento, fecha) in vistos:
                res.advertencias.append(f"Fila {num}, {fecha.isoformat()}: el documento {documento} ya tiene turno ese día — se omitió")
                continue
            vistos.add((documento, fecha))
            db.add(LiqDia(periodo_id=periodo.id, empleado_id=emp.id, fecha=fecha, turno_id=turno.id, codigo=turno.codigo))
            res.dias += 1
            por_turno[codigo] = por_turno.get(codigo, 0) + 1
        res.detalle.append(FilaResumen(documento, nombre, sum(por_turno.values()),
                                       ", ".join(f"{c}×{n}" for c, n in sorted(por_turno.items())) or "—"))

    if res.dias == 0:
        raise ErrorImportacion("No se importó ningún día de trabajo. Verifica que las celdas de cada día contengan un "
                               "código de turno válido (D, N, Z, L, AUS, INC…).")
    db.flush()
    return res


def _texto_documento(valor: object) -> str:
    """Cédulas que Excel guarda como número (1144127973.0) se leen sin decimales."""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()
