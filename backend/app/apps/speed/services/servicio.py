"""Servicios de la nómina de Speed: parámetros, importación del Listado, liquidación de la quincena y Excel."""

import io
from datetime import datetime, timezone

import xlsxwriter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.apps.speed.models import (
    ABIERTO, ADICIONAL, TIPOS_DESCUENTO, SpdDescuento, SpdDescuentoAplicado, SpdEmpleado, SpdLiquidacion, SpdNovedad, SpdParametro,
    SpdPeriodo,
)
from app.apps.speed.services import calculo

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


def _novedad_dict(n: SpdNovedad | None) -> dict | None:
    if n is None:
        return None
    return {"dias_programados": None if n.dias_programados is None else float(n.dias_programados), "ausencias": float(n.ausencias or 0),
            "licencias": float(n.licencias or 0), "suspensiones": float(n.suspensiones or 0), "incapacidad": float(n.incapacidad or 0),
            "incapacidad_previos": float(n.incapacidad_previos or 0)}


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
    ("salario", "SALARIO"), ("incapacidad", "INCAPACIDAD"), ("auxilio_transporte", "AUX. TRANSPORTE"), ("horas_extras", "HORAS EXTRAS"),
    ("comisiones", "COMISIONES"), ("ley_2466", "LEY 2466"), ("bonificaciones", "BONIFICACIONES"), ("rodamiento", "RODAMIENTO"),
    ("pago_adicional", "PAGO ADICIONAL"), ("_devengado", "TOTAL DEVENGADO"), ("salud", "SALUD"), ("pension", "PENSIÓN"),
    ("embargos", "EMBARGOS"), ("prestamos", "PRÉSTAMOS"), ("cuotas", "CUOTAS"), ("_deducciones", "TOTAL DEDUCCIONES"), ("_neto", "NETO A PAGAR"),
]


def excel(periodo: SpdPeriodo, liquidaciones: list[SpdLiquidacion]) -> bytes:
    buf = io.BytesIO()
    libro = xlsxwriter.Workbook(buf, {"in_memory": True})
    negrita = libro.add_format({"bold": True, "bg_color": "#e2e8f0", "border": 1, "text_wrap": True, "valign": "vcenter"})
    plata = libro.add_format({"num_format": "$#,##0"})
    plata_n = libro.add_format({"num_format": "$#,##0", "bold": True})
    hoja = libro.add_worksheet(f"Quincena {periodo.quincena}")
    fijos = ["CÉDULA", "NOMBRE", "CARGO", "PUESTO", "REGLA PROGRAMACIÓN", "DÍAS CONTRATO", "DÍAS TRABAJADOS", "NO LABORADOS",
             "INCAPACIDAD", "DÍAS VARIABLES", "IBC"]
    hoja.write_row(0, 0, fijos + [t for _, t in COLUMNAS_EXCEL] + ["ALERTAS"], negrita)
    hoja.set_row(0, 32)
    for i, l in enumerate(liquidaciones, start=1):
        d, e = l.detalle or {}, l.empleado
        dias = d.get("dias", {})
        hoja.write_string(i, 0, e.cedula)
        hoja.write_row(i, 1, [e.nombre, e.cargo, e.puesto, "SÍ" if d.get("aplica_programacion") else "NO", dias.get("contrato", 0),
                              dias.get("trabajados", 0), dias.get("no_laborados", 0), dias.get("incapacidad", 0), dias.get("variables", 0)])
        hoja.write_number(i, 10, d.get("ibc", 0), plata)
        conceptos = d.get("conceptos", {})
        for j, (clave, _) in enumerate(COLUMNAS_EXCEL, start=11):
            valor = {"_devengado": l.devengado, "_deducciones": l.deducciones, "_neto": l.neto}.get(clave, conceptos.get(clave, 0))
            hoja.write_number(i, j, float(valor or 0), plata_n if clave.startswith("_") else plata)
        hoja.write_string(i, 11 + len(COLUMNAS_EXCEL), " · ".join(d.get("alertas", [])))
    fin = len(liquidaciones) + 1
    hoja.write_string(fin, 1, "TOTAL", negrita)
    for j in range(10, 11 + len(COLUMNAS_EXCEL)):
        col = xlsxwriter.utility.xl_col_to_name(j)
        hoja.write_formula(fin, j, f"=SUM({col}2:{col}{fin})", plata_n)
    hoja.set_column(0, 0, 13)
    hoja.set_column(1, 1, 34)
    hoja.set_column(2, 3, 20)
    hoja.set_column(4, 9, 10)
    hoja.set_column(10, 10 + len(COLUMNAS_EXCEL), 14)
    hoja.set_column(11 + len(COLUMNAS_EXCEL), 11 + len(COLUMNAS_EXCEL), 60)
    hoja.freeze_panes(1, 2)
    libro.close()
    return buf.getvalue()


def periodo_abierto(p: SpdPeriodo) -> bool:
    return p.estado == ABIERTO


__all__ = ["ADICIONAL", "excel", "importar_listado", "liquidar_periodo", "parametros", "sembrar"]
