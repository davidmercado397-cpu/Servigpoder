"""Vacaciones: días hábiles y no hábiles, base de pago y saldo por empleado.

- Los días con un código marcado "Es vacaciones" (V) se pagan: los hábiles (según los días hábiles del empleado,
  lunes a sábado por defecto, sin festivos) descuentan del saldo; los no hábiles (domingos, festivos y los días
  que no son hábiles para la persona) también se pagan, porque el salario mensual cubre los 30 días.
- Base mensual = salario + promedio variable. El promedio sugerido es el recargo nocturno ordinario (lo variable
  que es salario ordinario, art. 192 CST: no cuentan extras ni el trabajo en dominicales o festivos) de los
  periodos cargados en los 12 meses anteriores; nómina puede reemplazarlo por periodo.
- Saldo: 15 días hábiles por año (360 días) desde la fecha de ingreso, menos los disfrutados antes del liquidador
  (o hasta el corte del libro de vacaciones) y los liquidados en él después del corte. Sin fecha de ingreso no hay
  saldo ni alerta.
"""

from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.apps.liquidador.models import MENSUAL, LiqDia, LiqEmpleado, LiqPeriodo, LiqResultado, LiqTurno, LiqVacacionBase
from app.apps.liquidador.services import festivos

DIAS_POR_ANIO = Decimal("15")
HABILES_DEFECTO = "012345"  # lunes (0) a sábado (5)
NOMBRES_DIA = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
CONCEPTOS_PROMEDIO = ("ordinary_night",)


def es_vacaciones(d: LiqDia) -> bool:
    return d.turno is not None and bool(d.turno.vacaciones)


def es_habil(fecha: date, habiles: str | None, fest: set[date]) -> bool:
    return str(fecha.weekday()) in (habiles or HABILES_DEFECTO) and fecha not in fest


def texto_habiles(habiles: str | None) -> str:
    dias = sorted(int(c) for c in (habiles or HABILES_DEFECTO))
    if dias == list(range(dias[0], dias[-1] + 1)) and len(dias) > 2:
        return f"{NOMBRES_DIA[dias[0]]} a {NOMBRES_DIA[dias[-1]]}"
    return ", ".join(NOMBRES_DIA[i] for i in dias)


def dias360(desde: date, hasta: date) -> int:
    """Días entre dos fechas (incluidas) en año de 360 días, como se causan las prestaciones."""
    if hasta < desde:
        return 0
    d1, d2 = min(desde.day, 30), min(hasta.day, 30)
    return (hasta.year - desde.year) * 360 + (hasta.month - desde.month) * 30 + (d2 - d1) + 1


def causados(fecha_ingreso: date, hasta: date) -> Decimal:
    return (DIAS_POR_ANIO * dias360(fecha_ingreso, hasta) / 360).quantize(Decimal("0.01"), ROUND_HALF_UP)


def promedios_sugeridos(db: Session, empleado_ids: list[int], periodo: LiqPeriodo) -> dict[int, tuple[Decimal, Decimal]]:
    """Promedio mensual del recargo nocturno en los 12 meses antes del periodo: {empleado: (promedio, meses)}.
    Si un mes tiene periodo mensual se usa ese; si no, sus quincenas (cada una cuenta medio mes)."""
    if not empleado_ids:
        return {}
    inicio = date(periodo.desde.year - 1, periodo.desde.month, 1)
    filas = db.execute(select(LiqResultado.empleado_id, LiqResultado.nomina, LiqPeriodo.anio, LiqPeriodo.mes, LiqPeriodo.quincena)
                       .join(LiqPeriodo, LiqPeriodo.id == LiqResultado.periodo_id)
                       .where(LiqResultado.empleado_id.in_(empleado_ids), LiqPeriodo.hasta < periodo.desde,
                              LiqPeriodo.desde >= inicio))
    por_mes: dict[tuple[int, int, int], dict[int, Decimal]] = defaultdict(dict)
    for eid, nomina, anio, mes, quincena in filas:
        valor = sum((Decimal(str((nomina or {}).get("valores", {}).get(c, 0))) for c in CONCEPTOS_PROMEDIO), Decimal("0"))
        q = por_mes[(eid, anio, mes)]
        q[quincena] = q.get(quincena, Decimal("0")) + valor  # varias nóminas del mismo periodo se suman
    total: dict[int, Decimal] = defaultdict(Decimal)
    meses: dict[int, Decimal] = defaultdict(Decimal)
    for (eid, _, _), q in por_mes.items():
        if MENSUAL in q:
            total[eid] += q[MENSUAL]
            meses[eid] += 1
        else:
            total[eid] += sum(q.values(), Decimal("0"))
            meses[eid] += Decimal("0.5") * len(q)
    return {eid: ((total[eid] / meses[eid]).quantize(Decimal("1"), ROUND_HALF_UP), meses[eid]) for eid in meses}


def promedios_manuales(db: Session, periodo_id: int) -> dict[int, Decimal]:
    return {x.empleado_id: x.promedio for x in db.scalars(select(LiqVacacionBase).where(LiqVacacionBase.periodo_id == periodo_id))}


def habiles_disfrutados(db: Session, empleados: dict[int, LiqEmpleado], antes_de: date | None = None) -> dict[int, int]:
    """Días hábiles de vacaciones ya liquidados en el liquidador (cada fecha una vez, aunque esté en dos periodos). Con
    corte del libro de vacaciones solo cuentan los posteriores: los anteriores ya están en los días previos."""
    if not empleados:
        return {}
    consulta = (select(LiqDia.empleado_id, LiqDia.fecha).join(LiqTurno, LiqTurno.id == LiqDia.turno_id)
                .where(LiqTurno.vacaciones.is_(True), LiqDia.empleado_id.in_(list(empleados))).distinct())
    if antes_de is not None:
        consulta = consulta.where(LiqDia.fecha < antes_de)
    filas = list(db.execute(consulta))
    if not filas:
        return {}
    fest = festivos.conjunto(db, min(f for _, f in filas), max(f for _, f in filas))
    cuenta: dict[int, int] = defaultdict(int)
    for eid, fecha in filas:
        corte = getattr(empleados[eid], "vacaciones_corte", None)
        if corte is not None and fecha <= corte:
            continue
        if es_habil(fecha, empleados[eid].dias_habiles, fest):
            cuenta[eid] += 1
    return dict(cuenta)


def saldo(empleado: LiqEmpleado, disfrutados_liquidador: int, hasta: date) -> dict | None:
    """Causados, disfrutados y pendientes a una fecha; None si el empleado no tiene fecha de ingreso."""
    if empleado.fecha_ingreso is None:
        return None
    c = causados(empleado.fecha_ingreso, hasta)
    previas = empleado.vacaciones_previas or Decimal("0")
    return {"fecha_ingreso": empleado.fecha_ingreso.isoformat(), "corte": hasta.isoformat(), "causados": float(c),
            "previos": float(previas), "liquidador": disfrutados_liquidador,
            "corte_libro": empleado.vacaciones_corte.isoformat() if getattr(empleado, "vacaciones_corte", None) else None,
            "pendientes": float(c - previas - disfrutados_liquidador)}
