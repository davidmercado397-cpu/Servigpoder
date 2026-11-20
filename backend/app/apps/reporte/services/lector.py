"""Lectura del Excel 'ReporteAsignacionResumido' de SIESA para el reporte en PDF.

Filas 1-3: Compañía / Desde / Hasta. Luego la fila de encabezados (C.C. Empleado, NOMBRE EMPLEADO,
UBICACION, DESCRIPCION UBICACION, PUESTO, DESCRIPCION PUESTO, 1 … 31, …) y una fila por empleado y
puesto. Las columnas de días son el número del día (1 … 31) o la fecha; se recorren en orden desde el
Desde, así que sirve para una quincena, el mes completo o un rango que cruce de mes (del 15 al 15).
Se pueden juntar varios archivos (p. ej. dos meses) y recortar el rango (una semana, tres semanas…).
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from app.core.excel import a_fecha, leer_filas, texto


class ErrorReporte(ValueError):
    pass


MAX_DIAS = 35  # días por PDF: más columnas ya no se leen en la hoja Carta


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
    if desde > hasta:
        raise ErrorReporte("La fecha Desde del archivo es posterior a la fecha Hasta")
    if (hasta - desde).days > 62:
        raise ErrorReporte("El archivo cubre más de dos meses: expórtelo de SIESA por meses")

    i_enc = next((i for i, f in enumerate(filas[:12]) if f and "empleado" in texto(f[0]).lower()), None)
    if i_enc is None:
        raise ErrorReporte("No se encontró la fila de encabezados (C.C. Empleado)")
    enc = [texto(c).upper() for c in filas[i_enc]]
    col = {nombre: i for i, nombre in enumerate(enc)}
    try:
        i_nombre, i_ubi, i_desc_ubi = col["NOMBRE EMPLEADO"], col["UBICACION"], col["DESCRIPCION UBICACION"]
        i_puesto, i_desc_puesto = col["PUESTO"], col["DESCRIPCION PUESTO"]
    except (KeyError, ValueError) as e:
        raise ErrorReporte(f"Falta la columna {e} en el archivo") from e
    i_ciudad = col.get("DESCRIPCION CENTRO DE OPERACION")

    fechas = [desde + timedelta(days=i) for i in range((hasta - desde).days + 1)]
    columnas = _columnas_dias(filas[i_enc], fechas)
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
        for d, i_col in columnas.items():
            valor = _espacios(f[i_col]) if i_col < len(f) else ""
            if valor:
                dias[d] = valor
        puesto.empleados.append(Empleado(cedula, _espacios(f[i_nombre]), dias))

    if not ubicaciones:
        raise ErrorReporte("El archivo no tiene filas de empleados")
    return Programacion(compania, desde, hasta, ubicaciones)


def _columnas_dias(encabezado: list[object], fechas: list[date]) -> dict[date, int]:
    """Columna de cada fecha del rango. El encabezado trae el número del día (1 … 31) o la fecha; se recorre en orden,
    así un rango que cruza de mes (15 … 31, 1 … 14) queda en su fecha correcta."""
    dias: list[tuple[int, int | None, date | None]] = []  # (columna, número de día, fecha)
    for i, celda in enumerate(encabezado):
        if isinstance(celda, (date, datetime)):
            dias.append((i, None, a_fecha(celda)))
            continue
        t = texto(celda)
        if re.fullmatch(r"\d{1,2}(\.0)?", t) and 1 <= int(float(t)) <= 31:
            dias.append((i, int(float(t)), None))
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", t):
            dias.append((i, None, a_fecha(t)))
    if not dias:
        raise ErrorReporte("No se encontraron las columnas de los días (1 … 31) en el archivo")
    if all(x[2] is not None for x in dias):  # encabezados con la fecha completa
        por_fecha = {x[2]: x[0] for x in dias}
        return {d: por_fecha[d] for d in fechas if d in por_fecha}
    columnas: dict[date, int] = {}
    numeros = [(i, n) for i, n, _ in dias if n is not None]
    if [n for _, n in numeros] == list(range(1, len(numeros) + 1)):
        # Formato de siempre: 1 … 31. Si el rango cruza de mes, cada día va en la columna de su número
        # (sin ambigüedad mientras ningún número de día se repita en el rango)
        if len({d.day for d in fechas}) != len(fechas):
            repetidos = sorted({d.day for d in fechas if sum(1 for x in fechas if x.day == d.day) > 1})
            dias = ", ".join(str(x) for x in repetidos)
            raise ErrorReporte(
                f"El Excel de SIESA tiene una sola columna por número de día y este archivo trae dos veces el día {dias} "
                f"({fechas[0]:%d/%m} a {fechas[-1]:%d/%m}), así que no se sabe de qué mes es. Expórtelo de SIESA en dos archivos "
                f"(p. ej. del {fechas[0]:%d/%m} al fin de mes y del 1 al {fechas[-1]:%d/%m}) y cárguelos juntos, o expórtelo hasta "
                f"el {(fechas[-1] - timedelta(days=len(repetidos))):%d/%m}.")
        por_dia = {n: i for i, n in numeros}
        return {d: por_dia[d.day] for d in fechas if d.day in por_dia}
    j = 0
    for d in fechas:  # rango que cruza de mes: las columnas van en el orden de las fechas
        while j < len(numeros) and numeros[j][1] != d.day:
            j += 1
        if j == len(numeros):
            raise ErrorReporte(f"No se encontró la columna del día {d.day}/{d.month} en el archivo")
        columnas[d] = numeros[j][0]
        j += 1
    return columnas


def unir(programaciones: list[Programacion]) -> Programacion:
    """Junta varios archivos (p. ej. octubre y noviembre) en un solo rango: mismo empleado en el mismo puesto = una fila."""
    if len(programaciones) == 1:
        return programaciones[0]
    ordenadas = sorted(programaciones, key=lambda p: p.desde)
    for a, b in zip(ordenadas, ordenadas[1:]):
        if b.desde > a.hasta + timedelta(days=1):
            raise ErrorReporte(f"Entre los archivos faltan días: uno termina el {a.hasta:%d/%m/%Y} y el siguiente empieza el {b.desde:%d/%m/%Y}")
    ubicaciones: dict[str, Ubicacion] = {}
    for p in ordenadas:
        for cod, u in p.ubicaciones.items():
            destino = ubicaciones.setdefault(cod, Ubicacion(u.codigo, u.nombre, u.ciudad))
            for cod_p, puesto in u.puestos.items():
                dp = destino.puestos.setdefault(cod_p, Puesto(puesto.codigo, puesto.descripcion))
                por_cedula = {e.cedula: e for e in dp.empleados}
                for e in puesto.empleados:
                    if e.cedula in por_cedula:
                        por_cedula[e.cedula].dias.update(e.dias)
                    else:
                        nuevo = Empleado(e.cedula, e.nombre, dict(e.dias))
                        dp.empleados.append(nuevo)
                        por_cedula[e.cedula] = nuevo
    return Programacion(ordenadas[0].compania, ordenadas[0].desde, max(p.hasta for p in ordenadas), ubicaciones)


def recortar(prog: Programacion, desde: date | None, hasta: date | None) -> Programacion:
    """El rango del PDF (una semana, tres semanas, del 15 al 15…) dentro de lo que traen los archivos."""
    desde, hasta = desde or prog.desde, hasta or prog.hasta
    if desde > hasta:
        raise ErrorReporte("La fecha Desde es posterior a la fecha Hasta")
    if desde < prog.desde or hasta > prog.hasta:
        raise ErrorReporte(f"El rango debe estar entre el {prog.desde:%d/%m/%Y} y el {prog.hasta:%d/%m/%Y} (lo que traen los archivos)")
    if (hasta - desde).days + 1 > MAX_DIAS:
        raise ErrorReporte(f"El PDF admite hasta {MAX_DIAS} días: elija un rango más corto")
    if (desde, hasta) == (prog.desde, prog.hasta):
        return prog
    ubicaciones: dict[str, Ubicacion] = {}
    for cod, u in prog.ubicaciones.items():
        puestos = {}
        for cod_p, p in u.puestos.items():
            # Quien no tiene nada programado en el rango no sale (p. ej. solo estaba en el otro mes)
            empleados = [Empleado(e.cedula, e.nombre, {d: v for d, v in e.dias.items() if desde <= d <= hasta}) for e in p.empleados]
            empleados = [e for e in empleados if e.dias]
            if empleados:
                puestos[cod_p] = Puesto(p.codigo, p.descripcion, empleados)
        if puestos:
            ubicaciones[cod] = Ubicacion(u.codigo, u.nombre, u.ciudad, puestos)
    if not ubicaciones:
        raise ErrorReporte("No hay programación en el rango elegido")
    return Programacion(prog.compania, desde, hasta, ubicaciones)


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
