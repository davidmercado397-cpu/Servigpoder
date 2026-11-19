"""Servicios de la nómina de Speed: parámetros, importación del Listado y de la programación, liquidación y Excel."""

import copy
from calendar import monthrange
import io
from difflib import SequenceMatcher
import re
import unicodedata
from datetime import date, datetime, timezone

import xlsxwriter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.apps.speed.models import (
    ABIERTO, ADICIONAL, TIPOS_DESCUENTO, SpdConceptoWO, SpdDescuento, SpdDescuentoAplicado, SpdEmpleado, SpdLiquidacion, SpdNovedad, SpdParametro,
    SpdPeriodo,
)
from app.apps.speed.services import calculo, programacion, world_office

CAMPOS_EMPLEADO = ("nombre", "fecha_ingreso", "tipo_contrato", "grupo", "cargo", "area", "puesto", "cliente", "tipo_turno", "salario",
                   "auxilio_listado", "horas_extras", "comisiones", "ley_2466", "bonificaciones", "rodamiento", "nota", "aplica_programacion")


# --- Nóminas: la general y la de los puestos de la señora Sandra («TIPO DE NOMINA» del Listado) -----------------

GRUPOS = ("general", "sandra", "todos")


def nomina_de(e: SpdEmpleado) -> str:
    return "sandra" if "sandra" in (e.grupo or "").lower() else "general"


def en_nomina(e: SpdEmpleado, grupo: str) -> bool:
    """La general no incluye los puestos de la señora Sandra; esos se ven solo si se eligen (o «todos»)."""
    return grupo == "todos" or nomina_de(e) == grupo


def sembrar(db: Session) -> None:
    existentes = {p.clave for p in db.scalars(select(SpdParametro))}
    for orden, (clave, (valor, nombre, ayuda)) in enumerate(calculo.PARAMETROS.items()):
        if clave not in existentes:
            db.add(SpdParametro(clave=clave, valor=valor, nombre=nombre, ayuda=ayuda, orden=orden))
    conceptos = {c.codigo for c in db.scalars(select(SpdConceptoWO))}
    for orden, (codigo, (concepto, incluir, descripcion)) in enumerate(world_office.CONCEPTOS.items()):
        if codigo not in conceptos:
            db.add(SpdConceptoWO(codigo=codigo, concepto=concepto, incluir=incluir, descripcion=descripcion, orden=orden))


def conceptos_wo(db: Session) -> dict[str, tuple[str, bool]]:
    c = {k: (v[0], v[1]) for k, v in world_office.CONCEPTOS.items()}
    c.update({x.codigo: (x.concepto, x.incluir) for x in db.scalars(select(SpdConceptoWO))})
    return c


def _tramos(dias: dict[int, str], codigo: str) -> list[tuple[int, int]]:
    """Días seguidos con el código: [(desde, hasta), …]."""
    salida: list[tuple[int, int]] = []
    for d in sorted(k for k, v in dias.items() if v == codigo):
        if salida and salida[-1][1] == d - 1:
            salida[-1] = (salida[-1][0], d)
        else:
            salida.append((d, d))
    return salida


def vacaciones_y_retiros(db: Session, periodo: SpdPeriodo, grupo: str = "general") -> dict:
    """Quién tiene vacaciones y quién se retira en la quincena, con las fechas (para cargarlo en World Office)."""
    desde, hasta = (1, 15) if periodo.quincena == 1 else (16, 30)
    fecha = lambda d: date(periodo.anio, periodo.mes, d).isoformat()  # noqa: E731
    vacaciones: list[dict] = []
    retiros: list[dict] = []
    novedades = [n for n in db.scalars(select(SpdNovedad).where(SpdNovedad.periodo_id == periodo.id)) if en_nomina(n.empleado, grupo)]
    for n in novedades:
        e = n.empleado
        base = {"empleado_id": e.id, "cedula": e.cedula, "nombre": e.nombre, "cargo": e.cargo, "puesto": e.puesto,
                "centro": "Produccion" if e.aplica_programacion else "Administrativo"}
        dias = {int(k): v for k, v in ((n.programacion or {}).get("dias") or {}).items() if desde <= int(k) <= hasta}
        if float(n.vacaciones or 0):
            tramos = _tramos(dias, "VAC")
            vacaciones.append({**base, "dias": float(n.vacaciones), "tramos": [[fecha(a), fecha(b)] for a, b in tramos],
                               "desde_antes": bool(tramos) and tramos[0][0] == desde, "sigue": bool(tramos) and tramos[-1][1] == hasta,
                               "sin_fechas": not tramos})
        run = _tramos(dias, "RUN")
        if run:
            trabajados = [d for d, c in dias.items() if d < run[0][0] and c not in ("RUN", "DESPR")]
            retiros.append({**base, "primer_dia_retiro": fecha(run[0][0]), "ultimo_dia": fecha(max(trabajados)) if trabajados else None,
                            "dias_retiro": sum(b - a + 1 for a, b in run), "motivo": "Renuncia (RUN en la programación)"})
    con_retiro = {r["empleado_id"] for r in retiros}
    # Retirados en la plataforma: con novedad en la quincena o con la fecha de retiro dentro de ella
    inicio, fin = date(periodo.anio, periodo.mes, desde), date(periodo.anio, periodo.mes, min(hasta, monthrange(periodo.anio, periodo.mes)[1]))
    con_novedad = {n.empleado_id for n in novedades}
    for e in db.scalars(select(SpdEmpleado).where(SpdEmpleado.fecha_retiro.is_not(None))):
        if e.id in con_retiro or not en_nomina(e, grupo) or not (e.id in con_novedad or inicio <= e.fecha_retiro <= fin):
            continue
        con_retiro.add(e.id)
        retiros.append({"empleado_id": e.id, "cedula": e.cedula, "nombre": e.nombre, "cargo": e.cargo, "puesto": e.puesto,
                        "centro": "Produccion" if e.aplica_programacion else "Administrativo", "primer_dia_retiro": None,
                        "ultimo_dia": e.fecha_retiro.isoformat(), "dias_retiro": 0,
                        "motivo": "Retirado en la plataforma" + (f": {e.motivo_retiro}" if e.motivo_retiro else "")})
    # Quien tiene novedad en la quincena pero ya no viene en el Listado (inactivo): posible retiro
    for n in novedades:
        e = n.empleado
        if not e.activo and e.id not in con_retiro:
            retiros.append({"empleado_id": e.id, "cedula": e.cedula, "nombre": e.nombre, "cargo": e.cargo, "puesto": e.puesto,
                            "centro": "Produccion" if e.aplica_programacion else "Administrativo", "primer_dia_retiro": None,
                            "ultimo_dia": None, "dias_retiro": 0, "motivo": "Ya no viene en el Listado (inactivo)"})
    # Si ya se retiró en la plataforma (para no ofrecer «Retirar» otra vez)
    ids = [r["empleado_id"] for r in retiros]
    por_id = {e.id: e for e in db.scalars(select(SpdEmpleado).where(SpdEmpleado.id.in_(ids or [0])))}
    for r in retiros:
        e = por_id.get(r["empleado_id"])
        r["retirado"] = e.fecha_retiro.isoformat() if e is not None and e.fecha_retiro else None
    vacaciones.sort(key=lambda x: x["nombre"])
    retiros.sort(key=lambda x: x["nombre"])
    return {"vacaciones": vacaciones, "retiros": retiros}


def excel_vacaciones_retiros(periodo: SpdPeriodo, datos: dict) -> bytes:
    buf = io.BytesIO()
    libro = xlsxwriter.Workbook(buf, {"in_memory": True})
    negrita = libro.add_format({"bold": True, "bg_color": "#e2e8f0", "border": 1})
    hoja = libro.add_worksheet("Vacaciones")
    hoja.write_row(0, 0, ["CÉDULA", "NOMBRE", "CARGO", "PUESTO", "CENTRO DE COSTOS", "DÍAS EN LA QUINCENA", "FECHAS", "OBSERVACIÓN"], negrita)
    for i, v in enumerate(datos["vacaciones"], start=1):
        obs = "; ".join(t for t, si in (("viene de la quincena anterior", v["desde_antes"]), ("sigue en la próxima quincena", v["sigue"]),
                                        ("digitadas a mano, sin fechas", v["sin_fechas"])) if si)
        hoja.write_string(i, 0, v["cedula"])
        hoja.write_row(i, 1, [v["nombre"], v["cargo"], v["puesto"], v["centro"], v["dias"],
                              ", ".join(f"{a} a {b}" if a != b else a for a, b in v["tramos"]), obs])
    hoja.set_column(0, 0, 13)
    hoja.set_column(1, 1, 36)
    hoja.set_column(2, 4, 20)
    hoja.set_column(6, 7, 40)
    hoja = libro.add_worksheet("Retiros")
    hoja.write_row(0, 0, ["CÉDULA", "NOMBRE", "CARGO", "PUESTO", "CENTRO DE COSTOS", "ÚLTIMO DÍA CON TURNO", "DESDE (RUN)", "MOTIVO"], negrita)
    for i, r in enumerate(datos["retiros"], start=1):
        hoja.write_string(i, 0, r["cedula"])
        hoja.write_row(i, 1, [r["nombre"], r["cargo"], r["puesto"], r["centro"], r["ultimo_dia"] or "", r["primer_dia_retiro"] or "", r["motivo"]])
    hoja.set_column(0, 0, 13)
    hoja.set_column(1, 1, 36)
    hoja.set_column(2, 6, 20)
    hoja.set_column(7, 7, 40)
    libro.close()
    return buf.getvalue()


def plano_world_office(db: Session, periodo: SpdPeriodo, grupo: str = "general") -> tuple[bytes, int, list[str]]:
    """Archivo plano de novedades de la quincena para World Office (desde los códigos de la programación)."""
    p = periodo.parametros if periodo.estado != ABIERTO and periodo.parametros else parametros(db)
    conceptos = conceptos_wo(db)
    filas: list[world_office.Fila] = []
    avisos: list[str] = []
    for n in db.scalars(select(SpdNovedad).where(SpdNovedad.periodo_id == periodo.id)):
        e = n.empleado
        if not en_nomina(e, grupo) or motivo_exclusion(e, n):
            continue
        dias = {int(k): v for k, v in ((n.programacion or {}).get("dias") or {}).items()}
        if (n.programacion or {}).get("sin_turnos") and n.origen == "programacion":
            # Sin ningún turno en la quincena: cada día de contrato va como desprogramado (no se paga)
            desde, hasta = (1, 15) if periodo.quincena == 1 else (16, 30)
            inicio = e.fecha_ingreso.day if e.fecha_ingreso and (e.fecha_ingreso.year, e.fecha_ingreso.month) == (periodo.anio, periodo.mes) else desde
            dias = {d: "DESPR" for d in range(max(desde, inicio), hasta + 1)}
        if not dias:
            if any(float(getattr(n, c) or 0) for c in DIAS_NOVEDAD if c not in ("incapacidad_previos", "sin_programacion")):
                avisos.append(f"{e.nombre} ({e.cedula}): sus novedades se digitaron sin programación (no hay fechas); no van en el plano")
            continue
        filas += world_office.filas_persona(e.nombre, e.cedula, float(e.salario or 0), e.aplica_programacion, dias,
                                            float(n.incapacidad_previos or 0), periodo.anio, periodo.mes, periodo.quincena, p, conceptos)
    if any(f.concepto == conceptos["TAD"][0] for f in filas) and not float(p.get("valor_tad") or 0):
        avisos.append("Hay turnos TAD pero su valor está en 0 (Parámetros)")
    if any(f.concepto == conceptos["TAN"][0] for f in filas) and not float(p.get("valor_tan") or 0):
        avisos.append("Hay turnos TAN pero su valor está en 0 (Parámetros)")
    return world_office.excel(filas), len(filas), avisos


def parametros(db: Session) -> dict[str, float]:
    p = calculo.parametros_por_defecto()
    p.update({x.clave: float(x.valor) for x in db.scalars(select(SpdParametro))})
    return p


def _igual(a, b) -> bool:
    if isinstance(a, (int, float)) or isinstance(b, (int, float)):
        try:
            return abs(float(a or 0) - float(b or 0)) < 0.005
        except (TypeError, ValueError):
            return False
    return (a or "") == (b or "")


def importar_listado(db: Session, empleados: list[dict]) -> dict:
    """Crea o actualiza por cédula. Quien no viene en el archivo queda inactivo (vuelve a activarse si aparece)."""
    actuales = {e.cedula: e for e in db.scalars(select(SpdEmpleado))}
    nuevos = actualizados = sin_cambios = reactivados = 0
    cambios: list[dict] = []
    retirados: list[dict] = []
    for d in empleados:
        e = actuales.get(d["cedula"])
        if e is not None and e.fecha_retiro:
            retirados.append({"cedula": e.cedula, "nombre": e.nombre, "fecha_retiro": e.fecha_retiro.isoformat()})
            continue
        if e is None:
            db.add(SpdEmpleado(cedula=d["cedula"], **{c: d[c] for c in CAMPOS_EMPLEADO}, activo=True))
            nuevos += 1
            continue
        distintos = [c for c in CAMPOS_EMPLEADO if not _igual(getattr(e, c), d[c])]
        if not e.activo:
            e.activo = True
            reactivados += 1
        if distintos:
            for c in ("salario", "horas_extras", "ley_2466", "bonificaciones", "rodamiento", "aplica_programacion"):
                if c in distintos:
                    cambios.append({"cedula": e.cedula, "nombre": e.nombre, "campo": c, "antes": _valor(getattr(e, c)), "ahora": _valor(d[c])})
            for c in distintos:
                setattr(e, c, d[c])
            actualizados += 1
        else:
            sin_cambios += 1
    vienen = {d["cedula"] for d in empleados}
    inactivados = [e for c, e in actuales.items() if c not in vienen and e.activo]
    for e in inactivados:
        e.activo = False
    db.flush()
    return {"nuevos": nuevos, "actualizados": actualizados, "sin_cambios": sin_cambios, "reactivados": reactivados,
            "inactivados": [{"cedula": e.cedula, "nombre": e.nombre} for e in inactivados], "cambios": cambios[:300],
            "retirados_en_archivo": retirados}


def _valor(v):
    return float(v) if isinstance(v, (int, float)) or hasattr(v, "as_integer_ratio") else v


def _empleado_dict(e: SpdEmpleado) -> dict:
    return {"salario": float(e.salario or 0), "horas_extras": float(e.horas_extras or 0), "comisiones": float(e.comisiones or 0),
            "ley_2466": float(e.ley_2466 or 0), "bonificaciones": float(e.bonificaciones or 0), "rodamiento": float(e.rodamiento or 0),
            "auxilio_listado": float(e.auxilio_listado or 0), "aplica_programacion": e.aplica_programacion, "fecha_ingreso": e.fecha_ingreso}


DIAS_NOVEDAD = ("ausencias", "licencias", "suspensiones", "desprogramados", "permisos_remunerados", "vacaciones", "incapacidad",
                "incapacidad_previos", "turnos_tad", "turnos_tan", "sin_programacion")


def _novedad_dict(n: SpdNovedad | None) -> dict | None:
    if n is None:
        return None
    d = {"dias_programados": None if n.dias_programados is None else float(n.dias_programados),
         **{c: float(getattr(n, c) or 0) for c in DIAS_NOVEDAD}}
    d["incapacidad_tramos"] = (n.programacion or {}).get("tramos_incapacidad")
    d["sin_turnos"] = bool((n.programacion or {}).get("sin_turnos")) and n.origen == "programacion"
    return d


# --- Archivo de programación ----------------------------------------------------------------------------------

def _clave_nombre(t: str) -> str:
    t = "".join(c for c in unicodedata.normalize("NFD", (t or "").lower()) if unicodedata.category(c) != "Mn")
    return " ".join(sorted(re.findall(r"[a-z0-9]+", t)))


def _mismo_nombre(a: str, b: str) -> bool:
    """El mismo nombre aunque esté escrito un poco distinto (JHON / JOHN) o le falte un nombre o apellido.

    Pide al menos 3 palabras en el más corto, 2 iguales y a lo sumo 1 parecida (≥ 75 % de letras en común)."""
    x, y = _clave_nombre(a).split(), _clave_nombre(b).split()
    corto, largo = (x, y) if len(x) <= len(y) else (y, x)
    if len(corto) < 3:
        return False
    restantes, exactos, parecidos = list(largo), 0, 0
    for t in corto:
        if t in restantes:
            restantes.remove(t)
            exactos += 1
            continue
        mejor = max(restantes, key=lambda r: SequenceMatcher(None, t, r).ratio(), default=None)
        if mejor is None or SequenceMatcher(None, t, mejor).ratio() < 0.75:
            return False
        restantes.remove(mejor)
        parecidos += 1
    return exactos >= 2 and parecidos <= 1


def _parecidos(nombre: str, empleados: list[SpdEmpleado]) -> list[SpdEmpleado]:
    return [e for e in empleados if _mismo_nombre(nombre, e.nombre)]


def _anterior(db: Session, periodo: SpdPeriodo) -> SpdPeriodo | None:
    if periodo.quincena == 2:
        anio, mes, q = periodo.anio, periodo.mes, 1
    else:
        anio, mes, q = (periodo.anio - 1, 12, 2) if periodo.mes == 1 else (periodo.anio, periodo.mes - 1, 2)
    return db.scalar(select(SpdPeriodo).where(SpdPeriodo.anio == anio, SpdPeriodo.mes == mes, SpdPeriodo.quincena == q))


def _previos(nueva: dict, anterior: SpdNovedad | None) -> float:
    """Días que ya llevaba la incapacidad que sigue desde la quincena anterior (para no pagar otra vez 2 días al 100 %)."""
    if not nueva["programacion"]["incapacidad_desde_inicio"] or anterior is None:
        return 0.0
    prog = anterior.programacion or {}
    al_cierre = float(prog.get("incapacidad_al_cierre") or 0)
    if not al_cierre:
        return 0.0
    # Si toda la incapacidad de la anterior venía de antes, se suman también esos días
    viene = prog.get("incapacidad_desde_inicio") and (prog.get("tramos_incapacidad") or []) == [al_cierre]
    return al_cierre + (float(anterior.incapacidad_previos or 0) if viene else 0.0)


def _cargar_novedad(db: Session, periodo: SpdPeriodo, e: SpdEmpleado, per: "programacion.Persona", n: SpdNovedad | None,
                    previa: SpdNovedad | None) -> dict:
    """Escribe en la novedad de la quincena lo que dice la programación de la persona."""
    d = programacion.novedad(per, periodo.anio, periodo.mes, periodo.quincena, e.fecha_ingreso)
    if n is None:
        n = SpdNovedad(periodo_id=periodo.id, empleado_id=e.id, observacion="")
        db.add(n)
    for c in ("ausencias", "licencias", "suspensiones", "desprogramados", "permisos_remunerados", "vacaciones", "incapacidad",
              "turnos_tad", "turnos_tan", "sin_programacion", "dias_programados", "programacion"):
        setattr(n, c, d[c])
    n.incapacidad_previos = _previos(d, previa)
    n.origen = "programacion"
    return d


def _pendiente(clave: str, per: "programacion.Persona", periodo: SpdPeriodo, sugeridos: list[SpdEmpleado]) -> dict:
    """Persona de la programación que no está en el Listado: se guardan sus códigos para poder crearla o asignarla después."""
    dias = sorted(per.dias)
    ingreso = None
    if dias and dias[0] > 1:  # empezó a trabajar en el mes: se sugiere ese día como fecha de ingreso
        ingreso = date(periodo.anio, periodo.mes, dias[0]).isoformat()
    return {"clave": clave, "cedula": per.cedula, "nombre": per.nombre, "puestos": per.puestos[:3],
            "dias": {str(d): per.dias[d] for d in dias}, "ingreso_sugerido": ingreso, "estado": "pendiente",
            # Empleados del Listado con un nombre parecido (para «Es un empleado del Listado»)
            "sugeridos": [{"cedula": e.cedula, "nombre": e.nombre} for e in sugeridos[:3]]}


def resolver_pendiente(db: Session, periodo: SpdPeriodo, clave: str, accion: str, empleado: SpdEmpleado | None) -> dict:
    """Crear / asignar: carga la programación de la persona en la novedad de ese empleado. Descartar: solo la marca."""
    resultado = copy.deepcopy(periodo.programacion_resultado or {})
    item = next((x for x in resultado.get("no_encontrados", []) if x.get("clave") == clave), None)
    if item is None:
        raise ValueError("La persona ya no está en el resultado de la programación (vuelva a subir el archivo)")
    if item.get("estado") != "pendiente":
        raise ValueError("Esa persona ya se resolvió")
    if accion != "descartar":
        assert empleado is not None
        per = programacion.Persona(empleado.cedula, item["nombre"], list(item.get("puestos") or []),
                                   {int(k): v for k, v in (item.get("dias") or {}).items()})
        existente = db.scalar(select(SpdNovedad).where(SpdNovedad.periodo_id == periodo.id, SpdNovedad.empleado_id == empleado.id))
        anterior = _anterior(db, periodo)
        previa = (db.scalar(select(SpdNovedad).where(SpdNovedad.periodo_id == anterior.id, SpdNovedad.empleado_id == empleado.id))
                  if anterior else None)
        _cargar_novedad(db, periodo, empleado, per, existente, previa)
        item["empleado"] = {"cedula": empleado.cedula, "nombre": empleado.nombre}
        resultado["cargadas"] = int(resultado.get("cargadas") or 0) + 1
    item["estado"] = {"crear": "creado", "asignar": "asignado"}.get(accion, "descartado")
    periodo.programacion_resultado = resultado
    db.flush()
    return item


def importar_programacion(db: Session, periodo: SpdPeriodo, personas: dict[str, "programacion.Persona"], info: dict) -> dict:
    """Llena la novedad de la quincena de cada persona con lo que dice la programación (reemplaza lo cargado antes desde
    la programación; las novedades digitadas a mano de quien no viene en el archivo se conservan)."""
    empleados = list(db.scalars(select(SpdEmpleado)))
    por_cedula = {e.cedula: e for e in empleados}
    por_nombre: dict[str, list[SpdEmpleado]] = {}
    for e in empleados:
        por_nombre.setdefault(_clave_nombre(e.nombre), []).append(e)
    existentes = {n.empleado_id: n for n in db.scalars(select(SpdNovedad).where(SpdNovedad.periodo_id == periodo.id))}
    anterior = _anterior(db, periodo)
    previas = ({n.empleado_id: n for n in db.scalars(select(SpdNovedad).where(SpdNovedad.periodo_id == anterior.id))}
               if anterior else {})

    cargados: set[int] = set()
    no_encontrados: list[dict] = []
    sin_turnos: list[dict] = []
    por_nombre_cruzados: list[dict] = []
    conflictos: list[dict] = []
    resumen = {"vacaciones": 0, "incapacidad": 0, "no_laborados": 0, "remunerados": 0, "turnos_tad": 0, "turnos_tan": 0, "sin_programacion": 0}
    for clave, per in personas.items():
        e = por_cedula.get(clave)
        parecidos: list[SpdEmpleado] = []
        if e is None:
            candidatos = por_nombre.get(_clave_nombre(per.nombre), [])
            if len(candidatos) == 1:
                e = candidatos[0]
                por_nombre_cruzados.append({"nombre": per.nombre, "cedula": e.cedula, "en_archivo": per.cedula or "sin documento",
                                            "nombre_listado": e.nombre})
            else:
                parecidos = _parecidos(per.nombre, [x for x in empleados if x.cedula not in personas])
                # Sin documento en la programación y un solo nombre parecido en el Listado: se cruza (y se muestra para revisar)
                if not per.cedula and len(parecidos) == 1:
                    e = parecidos[0]
                    por_nombre_cruzados.append({"nombre": per.nombre, "cedula": e.cedula, "en_archivo": "sin documento",
                                                "nombre_listado": e.nombre, "parecido": True})
        if e is None:
            no_encontrados.append(_pendiente(clave, per, periodo, parecidos))
            continue
        if e.id in cargados:
            conflictos.append({"cedula": e.cedula, "nombre": e.nombre, "detalle": ["aparece con dos documentos o nombres distintos; se tomó el primero"]})
            continue
        d = _cargar_novedad(db, periodo, e, per, existentes.get(e.id), previas.get(e.id))
        cargados.add(e.id)
        if d["programacion"]["sin_turnos"]:
            sin_turnos.append({"cedula": e.cedula, "nombre": e.nombre, "puestos": per.puestos[:3]})
        if d["programacion"]["conflictos"]:
            conflictos.append({"cedula": e.cedula, "nombre": e.nombre, "detalle": d["programacion"]["conflictos"]})
        resumen["vacaciones"] += d["vacaciones"]
        resumen["incapacidad"] += d["incapacidad"]
        resumen["no_laborados"] += d["ausencias"] + d["licencias"] + d["suspensiones"] + d["desprogramados"]
        resumen["remunerados"] += d["permisos_remunerados"]
        resumen["turnos_tad"] += d["turnos_tad"]
        resumen["turnos_tan"] += d["turnos_tan"]
        resumen["sin_programacion"] += d["sin_programacion"] if e.aplica_programacion else 0
    # Lo que se había cargado desde una programación anterior y ya no viene en el archivo
    quitadas = 0
    for empleado_id, n in existentes.items():
        if n.origen == "programacion" and empleado_id not in cargados:
            db.delete(n)
            quitadas += 1
    sin_programacion = [{"cedula": e.cedula, "nombre": e.nombre, "cargo": e.cargo} for e in sorted(empleados, key=lambda x: x.nombre)
                        if e.activo and e.aplica_programacion and e.id not in cargados]
    avisos: list[str] = []
    aviso_mes = programacion.revisar_mes(info.get("semana") or {}, periodo.anio, periodo.mes)
    if aviso_mes:
        avisos.append(aviso_mes)
    db.flush()
    return {"hojas": info.get("hojas", []), "personas": len(personas), "cargadas": len(cargados), "quitadas": quitadas,
            "no_encontrados": no_encontrados, "sin_turnos": sin_turnos, "por_nombre": por_nombre_cruzados, "sin_programacion": sin_programacion,
            "conflictos": conflictos[:200], "resumen": resumen, "avisos": avisos}


def descuentos_para(db: Session, periodo: SpdPeriodo, empleado_id: int | None = None) -> dict[int, list[calculo.Descuento]]:
    """Descuentos activos con su saldo antes de esta quincena (lo aplicado en las otras quincenas)."""
    q = select(SpdDescuento).where(SpdDescuento.activo.is_(True))
    if empleado_id:
        q = q.where(SpdDescuento.empleado_id == empleado_id)
    lista = list(db.scalars(q.order_by(SpdDescuento.id)))
    usados = dict(db.execute(select(SpdDescuentoAplicado.descuento_id, func.sum(SpdDescuentoAplicado.valor))
                             .where(SpdDescuentoAplicado.periodo_id != periodo.id).group_by(SpdDescuentoAplicado.descuento_id)).all())
    salida: dict[int, list[calculo.Descuento]] = {}
    for d in lista:
        saldo = None if d.valor_total is None else max(0.0, float(d.valor_total) - float(usados.get(d.id) or 0))
        if saldo is not None and saldo <= 0:
            continue
        salida.setdefault(d.empleado_id, []).append(calculo.Descuento(d.id, d.tipo, d.descripcion or TIPOS_DESCUENTO[d.tipo],
                                                                      float(d.cuota), saldo, d.salarial))
    return salida


def motivo_exclusion(e: SpdEmpleado, n: SpdNovedad | None) -> str | None:
    """Quién no se liquida en esta nómina porque va en otra (2026-11-19): vacaciones, retiro o inactivo."""
    if e.fecha_retiro:
        return "retiro"
    if not e.activo:
        return "inactivo"
    if n is not None:
        if float(n.vacaciones or 0):
            return "vacaciones"
        if "RUN" in ((n.programacion or {}).get("dias") or {}).values():
            return "retiro"
    return None


def liquidar_periodo(db: Session, periodo: SpdPeriodo) -> dict:
    """Liquida a los empleados activos. Quien tiene vacaciones o retiro en la quincena no se liquida: va en otra nómina
    y se muestra en «Vacaciones y retiros». Rehace lo de la quincena."""
    p = parametros(db)
    db.query(SpdLiquidacion).filter(SpdLiquidacion.periodo_id == periodo.id).delete()
    db.query(SpdDescuentoAplicado).filter(SpdDescuentoAplicado.periodo_id == periodo.id).delete()
    db.flush()
    novedades = {n.empleado_id: n for n in db.scalars(select(SpdNovedad).where(SpdNovedad.periodo_id == periodo.id))}
    empleados = list(db.scalars(select(SpdEmpleado).where((SpdEmpleado.activo.is_(True)) | (SpdEmpleado.id.in_(list(novedades) or [0])))
                                .order_by(SpdEmpleado.nombre)))
    descuentos = descuentos_para(db, periodo)
    totales = {"personas": 0, "devengado": 0.0, "deducciones": 0.0, "neto": 0.0, "alertas": 0, "excluidos": 0}
    for e in empleados:
        if motivo_exclusion(e, novedades.get(e.id)):
            totales["excluidos"] += 1
            continue
        r = calculo.liquidar(_empleado_dict(e), _novedad_dict(novedades.get(e.id)), p, periodo.anio, periodo.mes, periodo.quincena,
                             descuentos.get(e.id, []))
        if r.dias["contrato"] == 0 and e.id not in novedades:
            continue  # ingresó después de la quincena
        db.add(SpdLiquidacion(periodo_id=periodo.id, empleado_id=e.id, devengado=r.devengado, deducciones=r.deducciones, neto=r.neto,
                              detalle={"dias": r.dias, "conceptos": r.conceptos, "descuentos": r.descuentos, "ibc": r.ibc,
                                       "alertas": r.alertas, "aplica_programacion": e.aplica_programacion,
                                       "salario_mensual": float(e.salario or 0)}))
        for descuento_id, valor in r.aplicados.items():
            db.add(SpdDescuentoAplicado(descuento_id=descuento_id, periodo_id=periodo.id, valor=valor))
        totales["personas"] += 1
        totales["devengado"] += r.devengado
        totales["deducciones"] += r.deducciones
        totales["neto"] += r.neto
        totales["alertas"] += len(r.alertas)
    periodo.parametros = p
    periodo.calculado_en = datetime.now(timezone.utc)
    db.flush()
    return totales


# --- Excel de la quincena ---------------------------------------------------------------------------------

COLUMNAS_EXCEL = [
    ("salario", "SALARIO"), ("vacaciones", "VACACIONES"), ("incapacidad", "INCAPACIDAD"), ("auxilio_transporte", "AUX. TRANSPORTE"),
    ("horas_extras", "HORAS EXTRAS"), ("comisiones", "COMISIONES"), ("ley_2466", "LEY 2466"), ("bonificaciones", "BONIFICACIONES"),
    ("rodamiento", "RODAMIENTO"), ("turnos_adicionales", "TURNOS ADICIONALES"), ("pago_adicional", "PAGO ADICIONAL"), ("_devengado", "TOTAL DEVENGADO"), ("salud", "SALUD"), ("pension", "PENSIÓN"),
    ("embargos", "EMBARGOS"), ("prestamos", "PRÉSTAMOS"), ("cuotas", "CUOTAS"), ("_deducciones", "TOTAL DEDUCCIONES"), ("_neto", "NETO A PAGAR"),
]


def excel(periodo: SpdPeriodo, liquidaciones: list[SpdLiquidacion]) -> bytes:
    buf = io.BytesIO()
    libro = xlsxwriter.Workbook(buf, {"in_memory": True})
    negrita = libro.add_format({"bold": True, "bg_color": "#e2e8f0", "border": 1, "text_wrap": True, "valign": "vcenter"})
    plata = libro.add_format({"num_format": "$#,##0"})
    plata_n = libro.add_format({"num_format": "$#,##0", "bold": True})
    hoja = libro.add_worksheet(f"Quincena {periodo.quincena}")
    dias_cols = [("contrato", "DÍAS CONTRATO"), ("trabajados", "DÍAS TRABAJADOS"), ("no_laborados", "NO LABORADOS"),
                 ("incapacidad", "INCAPACIDAD"), ("vacaciones", "DÍAS VACACIONES"), ("remunerados", "LICENCIAS REMUNERADAS"),
                 ("variables", "DÍAS VARIABLES"), ("turnos_tad", "TAD"), ("turnos_tan", "TAN")]
    fijos = ["CÉDULA", "NOMBRE", "CARGO", "PUESTO", "REGLA PROGRAMACIÓN"] + [t for _, t in dias_cols] + ["IBC"]
    col_ibc = len(fijos) - 1
    hoja.write_row(0, 0, fijos + [t for _, t in COLUMNAS_EXCEL] + ["ALERTAS"], negrita)
    hoja.set_row(0, 32)
    for i, l in enumerate(liquidaciones, start=1):
        d, e = l.detalle or {}, l.empleado
        dias = d.get("dias", {})
        hoja.write_string(i, 0, e.cedula)
        hoja.write_row(i, 1, [e.nombre, e.cargo, e.puesto, "SÍ" if d.get("aplica_programacion") else "NO"]
                       + [dias.get(c) or 0 for c, _ in dias_cols])
        hoja.write_number(i, col_ibc, d.get("ibc", 0), plata)
        conceptos = d.get("conceptos", {})
        for j, (clave, _) in enumerate(COLUMNAS_EXCEL, start=col_ibc + 1):
            valor = {"_devengado": l.devengado, "_deducciones": l.deducciones, "_neto": l.neto}.get(clave, conceptos.get(clave, 0))
            hoja.write_number(i, j, float(valor or 0), plata_n if clave.startswith("_") else plata)
        hoja.write_string(i, col_ibc + 1 + len(COLUMNAS_EXCEL), " · ".join(d.get("alertas", [])))
    fin = len(liquidaciones) + 1
    hoja.write_string(fin, 1, "TOTAL", negrita)
    for j in range(col_ibc, col_ibc + 1 + len(COLUMNAS_EXCEL)):
        col = xlsxwriter.utility.xl_col_to_name(j)
        hoja.write_formula(fin, j, f"=SUM({col}2:{col}{fin})", plata_n)
    hoja.set_column(0, 0, 13)
    hoja.set_column(1, 1, 34)
    hoja.set_column(2, 3, 20)
    hoja.set_column(4, col_ibc - 1, 10)
    hoja.set_column(col_ibc, col_ibc + len(COLUMNAS_EXCEL), 14)
    hoja.set_column(col_ibc + 1 + len(COLUMNAS_EXCEL), col_ibc + 1 + len(COLUMNAS_EXCEL), 60)
    hoja.freeze_panes(1, 2)
    libro.close()
    return buf.getvalue()


def periodo_abierto(p: SpdPeriodo) -> bool:
    return p.estado == ABIERTO


__all__ = ["ADICIONAL", "excel", "importar_listado", "liquidar_periodo", "parametros", "sembrar"]
