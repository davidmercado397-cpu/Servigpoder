"""Comparación con la nómina de Siigo: el reporte de netos (una hoja por nómina con NOMBRE, CEDULA, NETO A PAGAR y, si vienen,
INGRESOS y DEDUCCIONES; sin ellas se compara solo el neto) contra lo liquidado aquí en todas las nóminas del mismo periodo. Se cruza persona por persona sumando
sus nóminas en cada lado, para que no importe cómo se repartieron. El archivo se procesa y se descarta.

Los datos leídos (no el archivo) quedan 24 horas por periodo para volver a comparar contra la nómina actual sin subirlo
otra vez; después se borran solos.

Las posibles causas son pistas: se busca qué concepto liquidado aquí explica la diferencia (recargos, extras, auxilio de
transporte, auxilios no prestacionales, vacaciones, incapacidad, novedades, días de salario, descuentos).
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.apps.liquidador.models import LiqPeriodo, LiqResultado, LiqSiigoCarga
from app.apps.liquidador.services.exportar import XLSX, _CENTRO, _FUENTE, _RELLENO, _autoajustar, _guardar
from app.apps.liquidador.services.personal import ErrorArchivo, Indice, _abrir, _norm, _texto, documento

CAMPOS_SISTEMA = ("basico", "incapacidad", "vacaciones_valor", "recargos", "extras", "auxilios_no_prestacionales", "auxilio",
                  "novedades_devengo", "devengado", "salud", "pension", "embargos", "prestamos", "cuotas", "novedades_deduccion",
                  "deducciones", "neto")
# Conceptos que pueden explicar una diferencia de ingresos o de deducciones
PISTAS_INGRESOS = (("recargos", "los recargos"), ("extras", "las horas extras"), ("auxilio", "el auxilio de transporte"),
                   ("auxilios_no_prestacionales", "los auxilios no prestacionales"), ("vacaciones_valor", "las vacaciones"),
                   ("incapacidad", "la incapacidad"), ("novedades_devengo", "las novedades (devengo)"))
PISTAS_DEDUCCIONES = (("prestamos", "los préstamos"), ("cuotas", "las cuotas"), ("embargos", "los embargos"),
                      ("novedades_deduccion", "las novedades (deducción)"))


@dataclass
class PersonaSiigo:
    documento: str
    nombre: str
    hojas: list[str] = field(default_factory=list)
    ingresos: float | None = 0.0  # None: alguna de sus hojas no trae la columna
    deducciones: float | None = 0.0
    neto: float = 0.0
    detalle: list[dict] = field(default_factory=list)  # una entrada por hoja (nómina de Siigo) donde aparece


def _num(v) -> float | None:
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace("$", "").replace(".", "").replace(",", ".").strip()) if v not in (None, "") else None
    except ValueError:
        return None


VIGENCIA = timedelta(hours=24)


def leer(contenido: bytes) -> tuple[dict[str, PersonaSiigo], list[dict]]:
    """(personas por documento, hallazgos)."""
    libro = _abrir(contenido)
    personas: dict[str, PersonaSiigo] = {}
    hallazgos = []
    for hoja in libro.worksheets:
        cols: dict[str, int] = {}
        for num, fila in enumerate(hoja.iter_rows(values_only=True), start=1):
            if not cols:
                claves = [_norm(c) for c in fila]
                if "CEDULA" in claves and any(c.startswith("NETO") for c in claves):
                    for i, c in enumerate(claves):
                        for clave, campo in (("NOMBRE", "nombre"), ("CEDULA", "documento"), ("INGRESO", "ingresos"), ("DEVENGAD", "ingresos"),
                                             ("DEDUCCION", "deducciones"), ("NETO", "neto")):
                            if clave in c and campo not in cols:
                                cols[campo] = i
                continue
            v = lambda campo: fila[cols[campo]] if campo in cols and cols[campo] < len(fila) else None  # noqa: E731
            doc, _ = documento(v("documento"))
            if doc is None:
                continue  # filas de total o vacías
            neto = _num(v("neto"))
            if neto is None:
                hallazgos.append({"hoja": hoja.title, "fila": num, "documento": doc, "detalle": "Sin neto a pagar: no se comparó"})
                continue
            p = personas.setdefault(doc, PersonaSiigo(doc, _texto(v("nombre"), 200) or doc))
            # Sin la columna en la hoja no se sabe (None); con la columna y la celda vacía es 0
            ingresos = (_num(v("ingresos")) or 0.0) if "ingresos" in cols else None
            deducciones = (_num(v("deducciones")) or 0.0) if "deducciones" in cols else None
            p.hojas.append(hoja.title)
            p.detalle.append({"hoja": hoja.title, "ingresos": ingresos, "deducciones": deducciones, "neto": neto})
            p.ingresos = None if p.ingresos is None or ingresos is None else p.ingresos + ingresos
            p.deducciones = None if p.deducciones is None or deducciones is None else p.deducciones + deducciones
            p.neto += neto
    if not personas:
        raise ErrorArchivo("No se encontraron filas con CEDULA y NETO A PAGAR. Use el reporte de netos de nómina de Siigo.")
    return personas, hallazgos


def purgar(db: Session) -> None:
    db.execute(delete(LiqSiigoCarga).where(LiqSiigoCarga.vence_en < datetime.now(timezone.utc)))


def guardar(db: Session, anio: int, mes: int, quincena: int, contenido: bytes, archivo: str, usuario_id: int | None) -> LiqSiigoCarga:
    """Lee el reporte y deja sus datos 24 horas para el periodo (reemplaza los anteriores)."""
    personas, hallazgos = leer(contenido)
    purgar(db)
    db.execute(delete(LiqSiigoCarga).where(LiqSiigoCarga.anio == anio, LiqSiigoCarga.mes == mes, LiqSiigoCarga.quincena == quincena))
    ahora = datetime.now(timezone.utc)
    c = LiqSiigoCarga(anio=anio, mes=mes, quincena=quincena, archivo=archivo[:255], hallazgos=hallazgos, cargado_por=usuario_id,
                      cargado_en=ahora, vence_en=ahora + VIGENCIA,
                      personas=[{"documento": p.documento, "nombre": p.nombre, "hojas": p.detalle} for p in personas.values()])
    db.add(c)
    db.flush()
    return c


def vigente(db: Session, anio: int, mes: int, quincena: int) -> LiqSiigoCarga | None:
    purgar(db)
    return db.scalar(select(LiqSiigoCarga).where(LiqSiigoCarga.anio == anio, LiqSiigoCarga.mes == mes, LiqSiigoCarga.quincena == quincena))


def _personas(c: LiqSiigoCarga) -> dict[str, PersonaSiigo]:
    out = {}
    for x in c.personas:
        p = PersonaSiigo(x["documento"], x["nombre"], [h["hoja"] for h in x["hojas"]], detalle=x["hojas"])
        p.ingresos = None if any(h["ingresos"] is None for h in x["hojas"]) else sum(h["ingresos"] for h in x["hojas"])
        p.deducciones = None if any(h["deducciones"] is None for h in x["hojas"]) else sum(h["deducciones"] for h in x["hojas"])
        p.neto = sum(h["neto"] for h in x["hojas"])
        out[p.documento] = p
    return out


def _pistas(dif: float, componentes: dict[str, float], lista, tolerancia: float, verbo: str) -> list[str]:
    """Conceptos de aquí cuyo valor coincide con la diferencia (solo si aquí hay más: de Siigo no hay detalle)."""
    if dif <= 0:
        return []
    margen = max(tolerancia, 100.0)
    return [f"Aquí se {verbo} {texto} ({valor:,.0f}) y la diferencia es igual: revise si Siigo los tiene"
            for campo, texto in lista if (valor := componentes.get(campo, 0.0)) and abs(dif - valor) <= margen]


def comparar(db: Session, carga: LiqSiigoCarga, tolerancia: float = 1000.0) -> dict:
    """Compara los datos de Siigo guardados con lo liquidado ahora en todas las nóminas del periodo."""
    anio, mes, quincena = carga.anio, carga.mes, carga.quincena
    siigo, hallazgos = _personas(carga), carga.hallazgos
    por_hoja: dict[str, float] = {}
    for s in siigo.values():
        for h in s.detalle:
            por_hoja[h["hoja"]] = por_hoja.get(h["hoja"], 0.0) + h["neto"]
    nominas = list(db.scalars(select(LiqPeriodo).where(LiqPeriodo.anio == anio, LiqPeriodo.mes == mes, LiqPeriodo.quincena == quincena)
                              .order_by(LiqPeriodo.id)))
    if not nominas:
        raise ErrorArchivo("No hay nóminas liquidadas en ese periodo")
    nuestras: dict[str, dict] = {}
    empleados = {}
    por_nomina = {}
    for p in nominas:
        total = 0.0
        for r in db.scalars(select(LiqResultado).where(LiqResultado.periodo_id == p.id)):
            n = r.nomina or {}
            if not n:
                continue
            e = r.empleado
            empleados[e.documento] = e
            x = nuestras.setdefault(e.documento, {"nombre": e.nombre, "empleado_id": e.id, "nominas": [], **{c: 0.0 for c in CAMPOS_SISTEMA},
                                                  "salario": float(n.get("salario", 0))})
            x["nominas"].append({"periodo_id": p.id, "nombre": p.nombre, "estado": p.estado})
            for c in CAMPOS_SISTEMA:
                x[c] += float(n.get(c, 0) or 0)
            total += float(n.get("neto", 0) or 0)
        por_nomina[p.nombre] = total
    indice = Indice(empleados.values())

    def resta(a: float | None, b: float | None) -> float | None:
        return None if a is None or b is None else round(a - b, 2)

    filas, vistos = [], set()
    for doc, s in siigo.items():
        e = indice.buscar(doc)
        propio = nuestras.get(e.documento) if e else None
        datos_siigo = {"ingresos": s.ingresos, "deducciones": s.deducciones, "neto": s.neto, "hojas": s.detalle}
        if propio is None:
            filas.append({"documento": doc, "nombre": s.nombre, "estado": "solo_siigo", "hojas_siigo": s.hojas, "nominas": [],
                          "siigo": datos_siigo, "sistema": None,
                          "diferencia": {"ingresos": resta(0, s.ingresos), "deducciones": resta(0, s.deducciones), "neto": -s.neto},
                          "pistas": ["No está liquidado aquí en este periodo"]})
            continue
        vistos.add(e.documento)
        # Diferencia = aquí − Siigo; ingresos y deducciones solo si el reporte los trae
        dif = {"ingresos": resta(propio["devengado"], s.ingresos), "deducciones": resta(propio["deducciones"], s.deducciones),
               "neto": round(propio["neto"] - s.neto, 2)}
        cuadra = all(abs(v) <= tolerancia for v in dif.values() if v is not None)
        pistas = []
        valor_dia = propio["salario"] / 30 if propio["salario"] else 0
        if not cuadra:
            if dif["ingresos"] is None:  # solo neto: más aquí puede ser un pago; menos aquí, un descuento
                if dif["neto"] > tolerancia:
                    pistas += _pistas(dif["neto"], propio, PISTAS_INGRESOS, tolerancia, "pagan")
                elif dif["neto"] < -tolerancia:
                    pistas += _pistas(-dif["neto"], propio, PISTAS_DEDUCCIONES, tolerancia, "descuentan")
                if valor_dia and not pistas:
                    dias = dif["neto"] / (valor_dia * 0.92)  # un día de salario menos su 8 % de salud y pensión
                    if abs(dias - round(dias)) < 0.05 and round(dias):
                        pistas.append(f"La diferencia del neto equivale a {abs(round(dias))} día(s) de salario (menos salud y pensión), "
                                      f"{'más' if dias > 0 else 'menos'} aquí")
            elif abs(dif["ingresos"]) > tolerancia:
                pistas += _pistas(dif["ingresos"], propio, PISTAS_INGRESOS, tolerancia, "pagan")
                if valor_dia and not pistas:
                    dias = dif["ingresos"] / valor_dia
                    if abs(dias - round(dias)) < 0.05 and round(dias):
                        pistas.append(f"La diferencia de ingresos equivale a {abs(round(dias))} día(s) de salario "
                                      f"({'más' if dias > 0 else 'menos'} aquí)")
            if dif["deducciones"] is not None and abs(dif["deducciones"]) > tolerancia:
                dp = _pistas(dif["deducciones"], propio, PISTAS_DEDUCCIONES, tolerancia, "descuentan")
                if not dp and dif["ingresos"] is not None and abs(dif["ingresos"]) > tolerancia \
                        and abs(dif["deducciones"] - 0.08 * dif["ingresos"]) <= max(tolerancia, 100):
                    dp.append("La diferencia de deducciones es el 8 % (salud y pensión) de la diferencia de ingresos")
                pistas += dp
        filas.append({"documento": e.documento, "nombre": propio["nombre"], "empleado_id": propio["empleado_id"],
                      "estado": "cuadra" if cuadra else "diferencia", "hojas_siigo": s.hojas, "nominas": propio["nominas"],
                      "siigo": datos_siigo, "sistema": {c: round(propio[c], 2) for c in CAMPOS_SISTEMA}, "diferencia": dif,
                      "pistas": pistas})
    for doc, propio in nuestras.items():
        if doc not in vistos:
            filas.append({"documento": doc, "nombre": propio["nombre"], "empleado_id": propio["empleado_id"], "estado": "solo_sistema",
                          "hojas_siigo": [], "nominas": propio["nominas"], "siigo": None,
                          "sistema": {c: round(propio[c], 2) for c in CAMPOS_SISTEMA},
                          "diferencia": {"ingresos": propio["devengado"], "deducciones": propio["deducciones"], "neto": propio["neto"]},
                          "pistas": ["No está en el archivo de Siigo"]})
    orden = {"diferencia": 0, "solo_siigo": 1, "solo_sistema": 2, "cuadra": 3}
    filas.sort(key=lambda f: (orden[f["estado"]], -abs(f["diferencia"]["neto"]), f["nombre"]))
    neto_siigo = sum(s.neto for s in siigo.values())
    neto_sistema = sum(x["neto"] for x in nuestras.values())
    conteo = defaultdict(int)
    for f in filas:
        conteo[f["estado"]] += 1
    return {
        "resumen": {"personas_siigo": len(siigo), "personas_sistema": len(nuestras), "cuadran": conteo["cuadra"],
                    "con_diferencia": conteo["diferencia"], "solo_siigo": conteo["solo_siigo"], "solo_sistema": conteo["solo_sistema"],
                    "neto_siigo": round(neto_siigo, 2), "neto_sistema": round(neto_sistema, 2),
                    "solo_neto": all(x.ingresos is None and x.deducciones is None for x in siigo.values()),
                    "diferencia_neto": round(neto_sistema - neto_siigo, 2), "tolerancia": tolerancia},
        "hojas_siigo": {k: round(v, 2) for k, v in por_hoja.items()},
        "nominas_sistema": {k: round(v, 2) for k, v in por_nomina.items()},
        "filas": filas, "hallazgos": hallazgos,
        "carga": {"archivo": carga.archivo, "cargado_en": carga.cargado_en.isoformat(), "vence_en": carga.vence_en.isoformat()},
    }


ESTADOS = {"cuadra": "Cuadra", "diferencia": "Con diferencia", "solo_siigo": "Solo en Siigo", "solo_sistema": "Solo en el sistema"}


def excel(res: dict, etiqueta: str) -> tuple[bytes, str, str]:
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Comparacion"
    hoja.append(["DOCUMENTO", "EMPLEADO", "ESTADO", "HOJAS SIIGO", "NOMINAS SISTEMA", "INGRESOS SIIGO", "INGRESOS SISTEMA", "DIF INGRESOS",
                 "DEDUCCIONES SIIGO", "DEDUCCIONES SISTEMA", "DIF DEDUCCIONES", "NETO SIIGO", "NETO SISTEMA", "DIF NETO",
                 "BASICO", "INCAPACIDAD", "VACACIONES", "RECARGOS", "EXTRAS", "AUX. NO PRESTACIONALES", "AUX. TRANSPORTE",
                 "NOVEDADES DEVENGO", "SALUD", "PENSION", "EMBARGOS", "PRESTAMOS", "CUOTAS", "NOVEDADES DEDUCCION", "POSIBLES CAUSAS"])
    for f in res["filas"]:
        s, n, d = f["siigo"] or {}, f["sistema"] or {}, f["diferencia"]
        hoja.append([f["documento"], f["nombre"], ESTADOS[f["estado"]], " · ".join(f["hojas_siigo"]),
                     " · ".join(x["nombre"] for x in f["nominas"]),
                     s.get("ingresos"), n.get("devengado"), d["ingresos"], s.get("deducciones"), n.get("deducciones"), d["deducciones"],
                     s.get("neto"), n.get("neto"), d["neto"],
                     *(n.get(c) for c in ("basico", "incapacidad", "vacaciones_valor", "recargos", "extras", "auxilios_no_prestacionales",
                                          "auxilio", "novedades_devengo", "salud", "pension", "embargos", "prestamos", "cuotas",
                                          "novedades_deduccion")),
                     " | ".join(f["pistas"])])
    for celda in hoja[1]:
        celda.fill, celda.font, celda.alignment = _RELLENO, _FUENTE, _CENTRO
    for col in range(6, 29):
        for (celda,) in hoja.iter_rows(min_row=2, min_col=col, max_col=col):
            celda.number_format = "$ #,##0.00"
    _autoajustar(hoja, minimo=10, maximo=40)
    hoja.freeze_panes = "C2"
    hoja.auto_filter.ref = hoja.dimensions
    hoja.row_dimensions[1].height = 42

    r = res["resumen"]
    resumen = libro.create_sheet("Resumen")
    for fila in (["Personas en Siigo", r["personas_siigo"]], ["Personas en el sistema", r["personas_sistema"]], ["Cuadran", r["cuadran"]],
                 ["Con diferencia", r["con_diferencia"]], ["Solo en Siigo", r["solo_siigo"]], ["Solo en el sistema", r["solo_sistema"]],
                 ["Neto Siigo", r["neto_siigo"]], ["Neto sistema", r["neto_sistema"]], ["Diferencia (sistema − Siigo)", r["diferencia_neto"]],
                 ["Tolerancia por persona", r["tolerancia"]], [], ["NETO POR HOJA DE SIIGO", ""],
                 *([k, v] for k, v in res["hojas_siigo"].items()), [], ["NETO POR NOMINA DEL SISTEMA", ""],
                 *([k, v] for k, v in res["nominas_sistema"].items())):
        resumen.append(fila)
    for celda in resumen["A"]:
        celda.font = Font(bold=True)
    _autoajustar(resumen, minimo=12, maximo=45)
    return _guardar(libro), XLSX, f"comparacion_siigo_{etiqueta}.xlsx"
