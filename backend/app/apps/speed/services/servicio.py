"""Servicios de la nómina de Speed: parámetros, importación del Listado y de la programación, liquidación y Excel."""

import io
import re
import unicodedata
from datetime import datetime, timezone

import xlsxwriter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.apps.speed.models import (
    ABIERTO, ADICIONAL, TIPOS_DESCUENTO, SpdDescuento, SpdDescuentoAplicado, SpdEmpleado, SpdLiquidacion, SpdNovedad, SpdParametro,
    SpdPeriodo,
)
from app.apps.speed.services import calculo, programacion

CAMPOS_EMPLEADO = ("nombre", "fecha_ingreso", "tipo_contrato", "grupo", "cargo", "area", "puesto", "cliente", "tipo_turno", "salario",
                   "auxilio_listado", "horas_extras", "comisiones", "ley_2466", "bonificaciones", "rodamiento", "nota", "aplica_programacion")


def sembrar(db: Session) -> None:
    existentes = {p.clave for p in db.scalars(select(SpdParametro))}
    for orden, (clave, (valor, nombre, ayuda)) in enumerate(calculo.PARAMETROS.items()):
        if clave not in existentes:
            db.add(SpdParametro(clave=clave, valor=valor, nombre=nombre, ayuda=ayuda, orden=orden))


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
    for d in empleados:
        e = actuales.get(d["cedula"])
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
            "inactivados": [{"cedula": e.cedula, "nombre": e.nombre} for e in inactivados], "cambios": cambios[:300]}


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
    return d


# --- Archivo de programación ----------------------------------------------------------------------------------

def _clave_nombre(t: str) -> str:
    t = "".join(c for c in unicodedata.normalize("NFD", (t or "").lower()) if unicodedata.category(c) != "Mn")
    return " ".join(sorted(re.findall(r"[a-z0-9]+", t)))


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
    por_nombre_cruzados: list[dict] = []
    conflictos: list[dict] = []
    resumen = {"vacaciones": 0, "incapacidad": 0, "no_laborados": 0, "remunerados": 0, "turnos_tad": 0, "turnos_tan": 0, "sin_programacion": 0}
    for clave, per in personas.items():
        e = por_cedula.get(clave)
        if e is None:
            candidatos = por_nombre.get(_clave_nombre(per.nombre), [])
            if len(candidatos) == 1:
                e = candidatos[0]
                por_nombre_cruzados.append({"nombre": per.nombre, "cedula": e.cedula, "en_archivo": per.cedula or "sin documento"})
        if e is None:
            no_encontrados.append({"cedula": per.cedula, "nombre": per.nombre, "puestos": per.puestos[:3]})
            continue
        if e.id in cargados:
            conflictos.append({"cedula": e.cedula, "nombre": e.nombre, "detalle": ["aparece con dos documentos o nombres distintos; se tomó el primero"]})
            continue
        d = programacion.novedad(per, periodo.anio, periodo.mes, periodo.quincena, e.fecha_ingreso)
        n = existentes.get(e.id)
        if n is None:
            n = SpdNovedad(periodo_id=periodo.id, empleado_id=e.id, observacion="")
            db.add(n)
        for c in ("ausencias", "licencias", "suspensiones", "desprogramados", "permisos_remunerados", "vacaciones", "incapacidad",
                  "turnos_tad", "turnos_tan", "sin_programacion", "dias_programados", "programacion"):
            setattr(n, c, d[c])
        n.incapacidad_previos = _previos(d, previas.get(e.id))
        n.origen = "programacion"
        cargados.add(e.id)
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
            "no_encontrados": no_encontrados, "por_nombre": por_nombre_cruzados, "sin_programacion": sin_programacion,
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


def liquidar_periodo(db: Session, periodo: SpdPeriodo) -> dict:
    """Liquida a todos los empleados activos (y a quienes tengan novedad en la quincena). Rehace lo de la quincena."""
    p = parametros(db)
    db.query(SpdLiquidacion).filter(SpdLiquidacion.periodo_id == periodo.id).delete()
    db.query(SpdDescuentoAplicado).filter(SpdDescuentoAplicado.periodo_id == periodo.id).delete()
    db.flush()
    novedades = {n.empleado_id: n for n in db.scalars(select(SpdNovedad).where(SpdNovedad.periodo_id == periodo.id))}
    empleados = list(db.scalars(select(SpdEmpleado).where((SpdEmpleado.activo.is_(True)) | (SpdEmpleado.id.in_(list(novedades) or [0])))
                                .order_by(SpdEmpleado.nombre)))
    descuentos = descuentos_para(db, periodo)
    totales = {"personas": 0, "devengado": 0.0, "deducciones": 0.0, "neto": 0.0, "alertas": 0}
    for e in empleados:
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
