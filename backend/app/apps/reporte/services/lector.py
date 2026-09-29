"""Lectura del Excel 'ReporteAsignacionResumido' de SIESA para el reporte en PDF.

Filas 1-3: Compañía / Desde / Hasta. Luego la fila de encabezados (C.C. Empleado, NOMBRE EMPLEADO,
UBICACION, DESCRIPCION UBICACION, PUESTO, DESCRIPCION PUESTO, 1 … 31, …) y una fila por empleado y
puesto. Las columnas 1 a 31 son los días del mes; solo se usan las del rango Desde–Hasta, así que sirve
igual para una quincena (1-15, 16-fin de mes) o el mes completo.
"""

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.core.excel import a_fecha, leer_filas, texto


class ErrorReporte(ValueError):
    pass


@dataclass
class Empleado:
    cedula: str
    nombre: str
    dias: dict[date, str]  # código tal como viene de SIESA (sin espacios sobrantes)


@dataclass
class Puesto:
    codigo: str
    descripcion: str
    empleados: list[Empleado] = field(default_factory=list)


@dataclass
class Ubicacion:
    codigo: str
    nombre: str
    ciudad: str
    puestos: dict[str, Puesto] = field(default_factory=dict)

    @property
    def empleados(self) -> int:
        return sum(len(p.empleados) for p in self.puestos.values())


@dataclass
class Programacion:
    compania: str
    desde: date
    hasta: date
    ubicaciones: dict[str, Ubicacion]

    @property
    def fechas(self) -> list[date]:
        return [self.desde + timedelta(days=i) for i in range((self.hasta - self.desde).days + 1)]

    @property
    def filas(self) -> int:
        return sum(u.empleados for u in self.ubicaciones.values())

    @property
    def puestos(self) -> int:
        return sum(len(u.puestos) for u in self.ubicaciones.values())

    def ciudades(self) -> list[str]:
        return sorted({u.ciudad for u in self.ubicaciones.values() if u.ciudad})


def clave_natural(codigo: str) -> tuple:
    """'2' < '10' < '100'; '12-1' < '12-2' < '12-10'; letras al final de cada parte ('2843-7G')."""
    partes = re.split(r"(\d+)", codigo.upper())
    return tuple((0, int(p), "") if p.isdigit() else (1, 0, p.strip(" -")) for p in partes if p.strip(" -"))


def _espacios(valor: object) -> str:
    return re.sub(r"\s+", " ", texto(valor))


def _buscar(filas: list[list[object]], etiqueta: str) -> object:
    for f in filas[:6]:
        if f and texto(f[0]).lower().startswith(etiqueta):
            return f[1] if len(f) > 1 else None
    raise ErrorReporte(f"No se encontró '{etiqueta.capitalize()}' en el encabezado del archivo. ¿Es el reporte de asignación de SIESA?")


def leer(contenido: bytes) -> Programacion:
    filas = leer_filas(contenido)
    if len(filas) < 5:
        raise ErrorReporte("El archivo no tiene el formato del reporte de asignación de SIESA")
    compania = _espacios(_buscar(filas, "compa"))
    try:
        desde, hasta = a_fecha(_buscar(filas, "desde")), a_fecha(_buscar(filas, "hasta"))
    except ValueError as e:
        raise ErrorReporte("Las fechas Desde/Hasta del archivo no son válidas") from e
    if desde > hasta or (desde.year, desde.month) != (hasta.year, hasta.month):
        raise ErrorReporte("El rango Desde/Hasta debe estar dentro de un mismo mes (p. ej. del 1 al 15, del 16 al 30 o el mes completo)")

    i_enc = next((i for i, f in enumerate(filas[:12]) if f and "empleado" in texto(f[0]).lower()), None)
    if i_enc is None:
        raise ErrorReporte("No se encontró la fila de encabezados (C.C. Empleado)")
    enc = [texto(c).upper() for c in filas[i_enc]]
    col = {nombre: i for i, nombre in enumerate(enc)}
    try:
        i_dia1 = enc.index("1")
        i_nombre, i_ubi, i_desc_ubi = col["NOMBRE EMPLEADO"], col["UBICACION"], col["DESCRIPCION UBICACION"]
        i_puesto, i_desc_puesto = col["PUESTO"], col["DESCRIPCION PUESTO"]
    except (KeyError, ValueError) as e:
        raise ErrorReporte(f"Falta la columna {e} en el archivo") from e
    i_ciudad = col.get("DESCRIPCION CENTRO DE OPERACION")

    fechas = [desde + timedelta(days=i) for i in range((hasta - desde).days + 1)]
    ubicaciones: dict[str, Ubicacion] = {}
    for f in filas[i_enc + 1:]:
        cedula = texto(f[0]) if f else ""
        if not cedula:
            continue
        f = list(f) + [None] * (len(enc) - len(f))
        cod_ubi = _espacios(f[i_ubi]) or "SIN UBICACIÓN"
        ubi = ubicaciones.get(cod_ubi)
        if ubi is None:
            ubi = ubicaciones[cod_ubi] = Ubicacion(cod_ubi, _espacios(f[i_desc_ubi]), _espacios(f[i_ciudad]) if i_ciudad is not None else "")
        cod_puesto = _espacios(f[i_puesto]) or cod_ubi
        puesto = ubi.puestos.get(cod_puesto)
        if puesto is None:
            puesto = ubi.puestos[cod_puesto] = Puesto(cod_puesto, _espacios(f[i_desc_puesto]))
        dias = {}
        for d in fechas:
            valor = _espacios(f[i_dia1 + d.day - 1])
            if valor:
                dias[d] = valor
        puesto.empleados.append(Empleado(cedula, _espacios(f[i_nombre]), dias))

    if not ubicaciones:
        raise ErrorReporte("El archivo no tiene filas de empleados")
    return Programacion(compania, desde, hasta, ubicaciones)


def filtrar(prog: Programacion, ciudades: list[str], ubicaciones: list[str]) -> Programacion:
    seleccion = {c: u for c, u in prog.ubicaciones.items()
                 if (not ciudades or u.ciudad in ciudades) and (not ubicaciones or c in ubicaciones)}
    if not seleccion:
        raise ErrorReporte("Ninguna ubicación coincide con los filtros elegidos")
    return Programacion(prog.compania, prog.desde, prog.hasta, seleccion)


def ordenada(prog: Programacion) -> list[Ubicacion]:
    """Ubicaciones por código y, dentro de cada una, puestos por código y empleados por nombre."""
    resultado = []
    for u in sorted(prog.ubicaciones.values(), key=lambda u: clave_natural(u.codigo)):
        for p in u.puestos.values():
            p.empleados.sort(key=lambda e: e.nombre)
        u.puestos = dict(sorted(u.puestos.items(), key=lambda kv: clave_natural(kv[0])))
        resultado.append(u)
    return resultado
