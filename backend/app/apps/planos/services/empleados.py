"""Plano de empleados SIESA (63 columnas, A–BK).

Modo "completo": normaliza y valida todas las columnas de la regla. Modo "codigos": solo cédula, fechas y lugares
(K–Q); no toca nombres, nivel educativo, género, estado civil ni extranjero.
Regla de oro: un dato se convierte con una regla o se reporta en la hoja de errores; nunca se inventa.
"""

from collections import defaultdict

from app.apps.planos.services.comun import (
    PlanoInvalido, Resultado, abrir, col, fila_vacia, formato_texto, guardar, hoja_de_datos, limpiar_id, meses_entre,
    normalizar, normalizar_fecha, ordenar, quitar_filas, texto, ultima_fila,
)
from app.apps.planos.services.dane import COLOMBIA, ResolverDane

FIJOS = {"F": "001", "G": "001", "H": "1", "AH": "1", "AI": "0"}
EDAD_MIN_INGRESO = 16
MESES_MIN_EXPEDICION = 17 * 12 + 6  # 17 años y 6 meses
TIPOS_ID = {"C", "E", "M", "N", "O", "P", "Q", "R", "S", "T", "X", "Z"}
NIVELES = ["SIN DEFINIR", "PREESCOLAR", "BASICA PRIMARIA", "BASICA SECUNDARIA", "MEDIA", "TECNICO LABORAL", "TÉCNICO",
           "TECNOLOGICA", "PROFESIONAL", "ESPECIALIZACION", "MAESTRÍA", "DOCTORADO", "OTROS"]
GENERO = {"MASCULINO": "0", "M": "0", "FEMENINO": "1", "F": "1", "NO BINARIO": "2"}
ESTADO_CIVIL = {"NINGUNO": "0", "SOLTERO": "1", "SOLTERA": "1", "CASADO": "2", "CASADA": "2", "VIUDO": "3", "VIUDA": "3",
                "DIVORCIADO": "4", "DIVORCIADA": "4", "UNION LIBRE": "5"}
FECHAS = {"I": "Fecha de ingreso", "J": "Fecha de nacimiento", "N": "Fecha de expedición"}
LUGARES = [("K", "L", "M", "Nacimiento"), ("O", "P", "Q", "Expedición")]
COLUMNAS_TEXTO = ["A", "B", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "S", "T", "U", "AH", "AI"]
COLUMNAS_CODIGOS = {"A", "I", "J", "N", "K", "L", "M", "O", "P", "Q"}


def limpiar_nombre(v, conservar_enie: bool = False) -> str:
    """Mayúsculas, sin tildes, comas ni espacios sobrantes. La Ñ pasa a N salvo que SIESA la acepte (conservar_enie)."""
    return normalizar(texto(v).replace(",", " "), enie=not conservar_enie)


def convertir_nivel_educativo(v) -> tuple[str, bool]:
    n = normalizar(v)
    if not n:
        return "", True
    oficial = next((o for o in NIVELES if normalizar(o) == n), None)
    return (oficial, True) if oficial else (texto(v), False)


def convertir_genero(v) -> tuple[str, bool]:
    s = normalizar(v)
    if s in ("", "0", "1", "2"):
        return s, True
    return (GENERO[s], True) if s in GENERO else (texto(v), False)


def convertir_estado_civil(v) -> tuple[str, bool]:
    s = normalizar(v)
    if s in ("", "0", "1", "2", "3", "4", "5"):
        return s, True
    return (ESTADO_CIVIL[s], True) if s in ESTADO_CIVIL else (texto(v), False)


def es_plano_empleados(ws) -> bool:
    return texto(ws.cell(1, 1).value).upper().startswith("ID DEL TERCERO")


def procesar(contenido: bytes, dane: ResolverDane, modo: str = "completo", correcciones: dict[tuple[str, str], str] | None = None,
             fila_ejemplo: int | None = None, conservar_enie: bool = False) -> tuple[bytes, Resultado, dict[str, str]]:
    """Devuelve (libro listo para SIESA con hoja Errores, resultado, {cédula: fecha de ingreso} para el cruce)."""
    if modo not in ("completo", "codigos"):
        raise PlanoInvalido("Modo desconocido")
    wb = abrir(contenido)
    ws = hoja_de_datos(wb)
    if not es_plano_empleados(ws):
        raise PlanoInvalido("La hoja no parece un plano de empleados: la columna A debe ser «ID DEL TERCERO»")
    res = Resultado()
    correcciones = correcciones or {}
    filas_por_cedula: dict[str, list[int]] = defaultdict(list)
    cruce: dict[str, str] = {}
    ultima = ultima_fila(ws)
    borrar: list[int] = []

    for f in range(2, ultima + 1):
        if f == fila_ejemplo or fila_vacia(ws, f):
            borrar.append(f)
            continue
        res.sumar("filas")
        cel = lambda c: ws.cell(f, col(c))  # noqa: E731

        ced, problema = limpiar_id(cel("A").value)
        cel("A").value = ced
        if problema:
            res.agregar(f, ced, "A", problema)
        else:
            filas_por_cedula[ced].append(f)
        for (c_ced, c_col), valor in correcciones.items():
            if c_ced == ced and (modo == "completo" or c_col in COLUMNAS_CODIGOS):
                cel(c_col).value = valor
                res.sumar("correcciones")

        fechas: dict[str, str] = {}
        for c, nombre in FECHAS.items():
            v, ok = normalizar_fecha(cel(c).value)
            cel(c).value = v or None
            if ok:
                fechas[c] = v
            else:
                res.agregar(f, ced, c, f"{nombre} inválida o vacía: '{v}'" if v else f"{nombre} vacía")

        pais_nacimiento = None
        for cp, cd, cc, lugar in LUGARES:
            r = dane.resolver(cel(cp).value, cel(cd).value, cel(cc).value)
            for tipo, msg, alias in r.problemas:
                res.agregar(f, ced, f"{cp}-{cc}", f"{lugar}: {msg}", tipo, alias)
            for c, v in ((cp, r.pais), (cd, r.depto), (cc, r.ciudad)):
                if v:
                    cel(c).value = v
            if r.completo and not any(p[0] == "Error" for p in r.problemas):
                res.sumar("lugares_codificados")
            if cp == "K":
                pais_nacimiento = r.pais

        if modo == "completo":
            b = texto(cel("B").value).upper()
            cel("B").value = b or None
            if b not in TIPOS_ID:
                res.agregar(f, ced, "B", f"Tipo de identificación fuera del catálogo: '{b}'" if b else "Tipo de identificación vacío")
            for c in ("C", "D", "E"):
                cel(c).value = limpiar_nombre(cel(c).value, conservar_enie) or None
            for c, convertir, nombre in (("R", convertir_nivel_educativo, "Nivel educativo"), ("S", convertir_genero, "Género"),
                                         ("T", convertir_estado_civil, "Estado civil")):
                v, ok = convertir(cel(c).value)
                cel(c).value = v or None
                if not ok:
                    res.agregar(f, ced, c, f"{nombre} no reconocido: '{v}'")
            for c, v in FIJOS.items():
                cel(c).value = v
            if pais_nacimiento:
                cel("U").value = "0" if pais_nacimiento == COLOMBIA else "1"

        # Coherencia: el dato es una fecha real pero no cuadra
        i, j, n = fechas.get("I"), fechas.get("J"), fechas.get("N")
        if i and j:
            if i <= j:
                res.agregar(f, ced, "I/J", f"Fecha de ingreso ({i}) igual o anterior a la de nacimiento ({j})", "Advertencia")
            elif meses_entre(j, i) < EDAD_MIN_INGRESO * 12:
                res.agregar(f, ced, "I/J", f"Menor de {EDAD_MIN_INGRESO} años al ingresar (nac {j}, ingreso {i})", "Advertencia")
        if j and n and meses_entre(j, n) < MESES_MIN_EXPEDICION:
            res.agregar(f, ced, "J/N", f"Documento expedido antes de los 17 años y 6 meses (nac {j}, exp {n})", "Advertencia")
        if ced and not problema:
            cruce[ced] = i or ""

    for ced, filas in filas_por_cedula.items():
        if len(filas) > 1:
            for f in filas:
                res.agregar(f, ced, "A", f"Cédula repetida en el plano (filas {', '.join(map(str, filas))})")

    formato_texto(ws, COLUMNAS_TEXTO, ultima)
    quitar_filas(ws, ultima, borrar)
    res.resumen["filas_eliminadas"] = len(borrar)
    res.hallazgos = ordenar(res.hallazgos)
    return guardar(wb, res.hallazgos), res, cruce
