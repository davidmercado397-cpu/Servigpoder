"""Lectura de los archivos que se cargan cada mes (todos exportados de SIESA).

Cada lector valida el formato y devuelve datos simples (dicts/listas) que se guardan como JSON por periodo:
el archivo no se conserva.
"""

import re
from collections import defaultdict
from datetime import date, datetime

from app.apps.reporte.services import lector as lector_programacion
from app.core.excel import leer_filas, texto


class ErrorArchivo(ValueError):
    pass


def norm(valor: object) -> str:
    """Texto comparable: sin espacios repetidos, en mayúsculas."""
    return re.sub(r"\s+", " ", texto(valor)).upper()


def codigo_programacion(valor: str) -> str:
    """'[VAC]' → 'VAC'; espacios colapsados (los horarios quedan tal cual)."""
    c = re.sub(r"\s+", " ", valor.strip())
    return c[1:-1].strip() if c.startswith("[") and c.endswith("]") else c


def num(valor: object) -> float:
    if valor is None or valor == "":
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    try:
        return float(str(valor).replace(",", ""))
    except ValueError:
        return 0.0


def _encabezado(filas: list[list[object]], requeridas: set[str], nombre: str) -> tuple[int, dict[str, int]]:
    for i, f in enumerate(filas[:10]):
        cols = {norm(c): j for j, c in enumerate(f) if texto(c)}
        if requeridas <= set(cols):
            return i, cols
    faltan = ", ".join(sorted(requeridas))
    raise ErrorArchivo(f"El archivo no parece ser {nombre}: se esperaban las columnas {faltan}")


def _fila(f: list[object], i: int) -> object:
    return f[i] if i < len(f) else None


# --- Maestro de modalidades ------------------------------------------------------------------

def modalidades(contenido: bytes) -> dict:
    """{codigo: {"descripcion", "conceptos": {concepto: {"descripcion", "valor"}}}} (valor por día)."""
    filas = leer_filas(contenido)
    i, c = _encabezado(filas, {"CÓDIGO", "DESCRIPCIÓN", "CONCEPTO ADICIONAL", "VALOR CONCEPTO ADICIONAL"}, "el maestro de modalidades")
    res: dict[str, dict] = {}
    for f in filas[i + 1:]:
        cod = norm(_fila(f, c["CÓDIGO"]))
        if not cod:
            continue
        m = res.setdefault(cod, {"descripcion": "", "conceptos": {}})
        desc = norm(_fila(f, c["DESCRIPCIÓN"]))
        if desc:
            m["descripcion"] = desc
        concepto = texto(_fila(f, c["CONCEPTO ADICIONAL"]))
        if concepto:
            m["conceptos"][concepto] = {
                "descripcion": texto(_fila(f, c.get("DESCRIPCIÓN CONCEPTO ADICIONAL", -1))) if "DESCRIPCIÓN CONCEPTO ADICIONAL" in c else "",
                "valor": num(_fila(f, c["VALOR CONCEPTO ADICIONAL"])),
            }
    if not res:
        raise ErrorArchivo("El maestro de modalidades no tiene filas")
    return res


# --- Maestro de ubicaciones y puestos con modalidad ----------------------------------------------

def ubicaciones(contenido: bytes) -> list[dict]:
    filas = leer_filas(contenido)
    i, c = _encabezado(filas, {"CÓDIGO", "MODALIDAD DE PAGO", "CODIGO PUESTO", "MODALIDAD PAGO"}, "el maestro de ubicaciones con modalidad")
    res = []
    for f in filas[i + 1:]:
        puesto = norm(_fila(f, c["CODIGO PUESTO"]))
        ubicacion = norm(_fila(f, c["CÓDIGO"]))
        if not puesto or not ubicacion:
            continue
        res.append({
            "ubicacion": ubicacion,
            "ubicacion_nombre": norm(_fila(f, c.get("DESCRIPCIÓN", -1))) if "DESCRIPCIÓN" in c else "",
            "modalidad_ubicacion": norm(_fila(f, c["MODALIDAD DE PAGO"])),  # viene el CÓDIGO
            "puesto": puesto,
            "puesto_nombre": norm(_fila(f, c.get("DESCRIPCIÓN PUESTO", -1))) if "DESCRIPCIÓN PUESTO" in c else "",
            "centro_costos": norm(_fila(f, c.get("CÓDIGO C.COSTO", -1))) if "CÓDIGO C.COSTO" in c else "",
            "modalidad_puesto": norm(_fila(f, c["MODALIDAD PAGO"])),  # viene la DESCRIPCIÓN
        })
    if not res:
        raise ErrorArchivo("El maestro de ubicaciones no tiene puestos")
    return res


# --- Contratos ------------------------------------------------------------------------------------

def contratos(contenido: bytes) -> dict[str, dict]:
    filas = leer_filas(contenido)
    i, c = _encabezado(filas, {"EMPLEADO", "DESCRIPCION ESTADO", "DESCRIPCION TIPO DE NOMINA", "DESCRIPCION GRUPO EMPLEADOS"},
                       "el listado de contratos")
    res: dict[str, dict] = {}
    for f in filas[i + 1:]:
        ced = texto(_fila(f, c["EMPLEADO"]))
        if not ced:
            continue
        ingreso = _fila(f, c.get("FECHA INGRESO", -1)) if "FECHA INGRESO" in c else None
        if isinstance(ingreso, datetime):
            ingreso = ingreso.date()
        nuevo = {
            "nombre": norm(_fila(f, c.get("NOMBRE DEL EMPLEADO", -1))) if "NOMBRE DEL EMPLEADO" in c else "",
            "activo": norm(_fila(f, c["DESCRIPCION ESTADO"])) == "ACTIVO",
            "cargo": norm(_fila(f, c.get("DESCRIPCION DEL CARGO", -1))) if "DESCRIPCION DEL CARGO" in c else "",
            "centro_costos": norm(_fila(f, c.get("DESCRIPCION CCOSTO", -1))) if "DESCRIPCION CCOSTO" in c else "",
            "tipo_nomina": norm(_fila(f, c["DESCRIPCION TIPO DE NOMINA"])),
            "grupo": norm(_fila(f, c["DESCRIPCION GRUPO EMPLEADOS"])),
            "ingreso": ingreso.isoformat() if isinstance(ingreso, date) else None,
        }
        # Una persona puede tener un contrato retirado y otro activo: manda el activo
        if ced not in res or (nuevo["activo"] and not res[ced]["activo"]):
            res[ced] = nuevo
    if not res:
        raise ErrorArchivo("El listado de contratos no tiene filas")
    return res


# --- Cuotas ---------------------------------------------------------------------------------------

def cuotas(contenido: bytes) -> list[dict]:
    filas = leer_filas(contenido)
    i, c = _encabezado(filas, {"EMPLEADO", "CPTO", "VALOR MÁXIMO", "VALOR ACUMULADO", "VALOR DEVENGO", "VALOR DEDUCCIÓN", "TASA", "ESTADO"},
                       "el maestro de cuotas")
    res = []
    for n, f in enumerate(filas[i + 1:], start=1):
        ced = texto(_fila(f, c["EMPLEADO"]))
        if not ced:
            continue
        res.append({
            "id": n,
            "cedula": ced,
            "nombre": norm(_fila(f, c.get("NOMBRE", -1))) if "NOMBRE" in c else "",
            "concepto": texto(_fila(f, c["CPTO"])),
            "descripcion": texto(_fila(f, c.get("DESCRIPCIÓN CPTO", -1))) if "DESCRIPCIÓN CPTO" in c else "",
            "cuotas_descontadas": int(num(_fila(f, c.get("CUOTAS", -1)))) if "CUOTAS" in c else 0,
            "maximo": num(_fila(f, c["VALOR MÁXIMO"])),
            "acumulado": num(_fila(f, c["VALOR ACUMULADO"])),
            "devengo": num(_fila(f, c["VALOR DEVENGO"])),
            "deduccion": num(_fila(f, c["VALOR DEDUCCIÓN"])),
            "tasa": num(_fila(f, c["TASA"])),
            "estado": norm(_fila(f, c["ESTADO"])),
        })
    return res


# --- Programación (Excel de asignación de SIESA) -------------------------------------------------

def programacion(contenido: bytes) -> dict:
    try:
        prog = lector_programacion.leer(contenido)
    except lector_programacion.ErrorReporte as e:
        raise ErrorArchivo(str(e)) from e
    filas = []
    for u in prog.ubicaciones.values():
        for p in u.puestos.values():
            for e in p.empleados:
                filas.append({
                    "cedula": e.cedula, "nombre": norm(e.nombre), "ubicacion": norm(u.codigo), "ubicacion_nombre": norm(u.nombre),
                    "puesto": norm(p.codigo), "puesto_nombre": norm(p.descripcion),
                    # Se conservan los corchetes: indican novedad y sirven para clasificar códigos nuevos
                    "dias": {d.isoformat(): re.sub(r"\s+", " ", c.strip()) for d, c in e.dias.items()},
                })
    return {"desde": prog.desde.isoformat(), "hasta": prog.hasta.isoformat(), "filas": filas}


# --- Nómina liquidada (quincenal o mensual) ------------------------------------------------------

_COLUMNA = re.compile(r"^(HORAS|DEVENGO|DEDUCCION)_(\d+)$")


def nomina(contenido: bytes) -> dict:
    """{"conceptos": {codigo: descripcion}, "personas": {cedula: {...}}} sumando las filas de cada persona."""
    filas = leer_filas(contenido)
    i_enc = next((i for i, f in enumerate(filas[:6]) if any(texto(c).upper() == "TERCERO" for c in f)), None)
    if i_enc is None:
        raise ErrorArchivo("El archivo no parece ser una nómina liquidada de SIESA: falta la columna Tercero")
    enc = [texto(c).upper() for c in filas[i_enc]]
    if not any(_COLUMNA.match(c) for c in enc):
        raise ErrorArchivo("El archivo de nómina no tiene columnas HORAS_/DEVENGO_/DEDUCCION_")
    # Fila de títulos ("100-SALARIO BASICO"): el título va en la primera columna de cada concepto
    conceptos: dict[str, str] = {}
    if i_enc > 0:
        for t in filas[i_enc - 1]:
            m = re.match(r"^\s*(\d+)\s*-\s*(.+)$", texto(t))
            if m:
                conceptos[m.group(1)] = re.sub(r"\s+", " ", m.group(2)).strip()
    col = {c: j for j, c in enumerate(enc)}
    personas: dict[str, dict] = {}
    for f in filas[i_enc + 1:]:
        ced = texto(_fila(f, col["TERCERO"]))
        if not ced:
            continue
        p = personas.setdefault(ced, {
            "nombre": norm(_fila(f, col.get("DESCRIPCIÓN", -1))) if "DESCRIPCIÓN" in col else "",
            "cargo": norm(_fila(f, col.get("DESCRIPCIÓN DEL CARGO", -1))) if "DESCRIPCIÓN DEL CARGO" in col else "",
            "salario": num(_fila(f, col.get("SALARIO BÁSICO", -1))) if "SALARIO BÁSICO" in col else 0.0,
            "centros_costos": [], "filas": 0, "horas": defaultdict(float), "devengos": defaultdict(float),
            "deducciones": defaultdict(float), "neto": 0.0,
        })
        p["filas"] += 1
        cc = texto(_fila(f, col.get("CENTRO COSTOS", -1))) if "CENTRO COSTOS" in col else ""
        if cc and cc not in p["centros_costos"]:
            p["centros_costos"].append(cc)
        for nombre, j in col.items():
            m = _COLUMNA.match(nombre)
            if m:
                valor = num(_fila(f, j))
                if valor:
                    destino = {"HORAS": "horas", "DEVENGO": "devengos", "DEDUCCION": "deducciones"}[m.group(1)]
                    p[destino][m.group(2)] += valor
        if "NETO" in col:
            p["neto"] += num(_fila(f, col["NETO"]))
    if not personas:
        raise ErrorArchivo("El archivo de nómina no tiene personas")
    for p in personas.values():
        for k in ("horas", "devengos", "deducciones"):
            p[k] = {c: round(v, 2) for c, v in p[k].items()}
    return {"conceptos": conceptos, "personas": personas}
