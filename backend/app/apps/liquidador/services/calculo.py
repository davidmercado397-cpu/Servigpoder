"""Conteo de horas de un periodo (quincena o mes completo).

Con las horas se liquida la nómina de cada empleado (services/nomina.py).

Por cada día cargado: se clasifica la fecha (ordinario, sábado, domingo, festivo, víspera…), se lee
esa columna de la matriz del turno y se acumulan las horas de los 12 conceptos. Es el mismo cálculo
de la app original; lo nuevo es el conteo de "días con novedad" (vacaciones, licencias, etc.).
"""

import calendar
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.apps.liquidador.dominio.clasificador import classify
from app.apps.liquidador.dominio.expansor import expand_workday_to_concepts
from app.apps.liquidador.dominio.tipos import HourConcept
from app.apps.liquidador.models import CALCULADA, LiqDia, LiqPeriodo, LiqResultado, LiqTurno
from app.apps.liquidador.services import festivos, nomina, umbral

# Clases de día (columnas de conteo del archivo de liquidación)
TRABAJADO = "trabajado"
DESCANSO_PAGO = "descanso_pago"
LIBRE = "libre"
AUSENCIA = "ausencia"
INCAPACIDAD = "incapacidad"
NOVEDAD = "novedad"
CLASES = (TRABAJADO, DESCANSO_PAGO, LIBRE, AUSENCIA, INCAPACIDAD, NOVEDAD)

# Horas efectivamente trabajadas: las ordinarias (diurnas + nocturnas) y todas las extras.
# Los recargos no suman: marcan horas que ya están contadas.
CONCEPTOS_TRABAJADOS = (
    HourConcept.ORDINARY_DAY, HourConcept.OVERTIME_DAY, HourConcept.OVERTIME_NIGHT, HourConcept.HOLIDAY_OVERTIME_DAY,
    HourConcept.HOLIDAY_OVERTIME_NIGHT, HourConcept.SUNDAY_OVERTIME_DAY, HourConcept.SUNDAY_OVERTIME_NIGHT,
)


def rango_quincena(anio: int, mes: int, quincena: int) -> tuple[date, date]:
    """1: días 1 al 15; 2: del 16 al fin de mes; 0 (mensual): el mes completo."""
    if quincena == 0:
        return date(anio, mes, 1), date(anio, mes, calendar.monthrange(anio, mes)[1])
    if quincena == 1:
        return date(anio, mes, 1), date(anio, mes, 15)
    if quincena == 2:
        return date(anio, mes, 16), date(anio, mes, calendar.monthrange(anio, mes)[1])
    raise ValueError("La quincena debe ser 1, 2 o 0 (mensual)")


def clase_de(turno: LiqTurno) -> str:
    """Z, L y AUS por código (como en la app original), incapacidad por su check; con horas es un día
    trabajado y cualquier otro código sin horas (V, LR, LNR, SUS, AI, LM…) es un día con novedad."""
    if turno.incapacidad:
        return INCAPACIDAD
    codigo = (turno.codigo or "").upper()
    if codigo == "Z":
        return DESCANSO_PAGO
    if codigo == "L":
        return LIBRE
    if codigo == "AUS":
        return AUSENCIA
    if (turno.horas_ordinarias or 0) + (turno.horas_extras or 0) > 0:
        return TRABAJADO
    return NOVEDAD


def contar(db: Session, periodo, dias: list) -> tuple[dict, dict, dict]:
    """Horas por concepto y clase de cada día (también para el costeo, con días que no se guardan).
    Devuelve horas y conteo de días por empleado, y el detalle del umbral semanal."""
    fest = festivos.conjunto(db, periodo.desde, periodo.hasta + timedelta(days=1))
    horas_por_empleado: dict[int, dict[HourConcept, Decimal]] = defaultdict(lambda: defaultdict(lambda: Decimal("0")))
    conteo_por_empleado: dict[int, dict[str, int]] = defaultdict(lambda: dict.fromkeys(CLASES, 0))
    # Nómina por horas: otros turnos del mismo día (varias líneas en el Excel); sus horas se suman al día
    ids_extra = {i for d in dias for i in (getattr(d, "turnos_extra", None) or [])}
    extra = {t.id: t for t in db.scalars(select(LiqTurno).where(LiqTurno.id.in_(ids_extra)))} if ids_extra else {}
    for d in dias:
        tipo = classify(d.fecha, holiday_today=d.fecha in fest, holiday_tomorrow=d.fecha + timedelta(days=1) in fest)
        conceptos = expand_workday_to_concepts(d.turno.matriz or {}, tipo)
        for tid in getattr(d, "turnos_extra", None) or []:
            if tid in extra:
                for c, h in expand_workday_to_concepts(extra[tid].matriz or {}, tipo).items():
                    conceptos[c] = conceptos.get(c, Decimal("0")) + h
        d.tipo_dia = tipo.value
        d.clase = clase_de(d.turno)
        d.horas = {c.value: float(h) for c, h in conceptos.items()}
    # Umbral semanal (si se marcó al liquidar): ajusta las extras de cada día antes de totalizar
    semanas = umbral.aplicar(periodo, dias) if periodo.umbral_activo else {}
    for d in dias:
        for c, h in (d.horas or {}).items():
            horas_por_empleado[d.empleado_id][HourConcept(c)] += Decimal(str(h))
        conteo_por_empleado[d.empleado_id][d.clase] += 1
    return horas_por_empleado, conteo_por_empleado, semanas


def calcular(db: Session, periodo: LiqPeriodo, con_hermanas: bool = True) -> int:
    """Recalcula cada día y los totales por empleado con los turnos y festivos vigentes. Después recalcula las
    otras nóminas abiertas de fechas que se cruzan, porque una persona en dos nóminas paga sus préstamos, embargos
    y auxilios en una sola."""
    dias = list(db.scalars(select(LiqDia).where(LiqDia.periodo_id == periodo.id).order_by(LiqDia.empleado_id, LiqDia.fecha)))
    horas_por_empleado, conteo_por_empleado, semanas = contar(db, periodo, dias)

    db.execute(delete(LiqResultado).where(LiqResultado.periodo_id == periodo.id))
    resultados: dict[int, LiqResultado] = {}
    for empleado_id, conteo in conteo_por_empleado.items():
        horas = horas_por_empleado[empleado_id]
        resultados[empleado_id] = LiqResultado(
            periodo_id=periodo.id, empleado_id=empleado_id, dias=conteo,
            horas={c.value: float(horas.get(c, Decimal("0"))) for c in HourConcept},
            total_horas=sum((horas.get(c, Decimal("0")) for c in CONCEPTOS_TRABAJADOS), Decimal("0")),
            umbral_semanas=semanas.get(empleado_id, []),
        )
    nomina.liquidar(db, periodo, dias, resultados)
    db.add_all(resultados.values())
    periodo.estado = CALCULADA
    periodo.calculado_en = datetime.now(timezone.utc)
    db.flush()
    if con_hermanas:
        recalcular_hermanas(db, periodo)
    return len(conteo_por_empleado)


def hermanas(db: Session, periodo: LiqPeriodo) -> list[LiqPeriodo]:
    """Otras nóminas con fechas que se cruzan (las del mismo periodo y la mensual o quincenas del mismo mes)."""
    return list(db.scalars(select(LiqPeriodo).where(LiqPeriodo.id != periodo.id, LiqPeriodo.desde <= periodo.hasta,
                                                    LiqPeriodo.hasta >= periodo.desde).order_by(LiqPeriodo.id)))


def recalcular_hermanas(db: Session, periodo: LiqPeriodo) -> None:
    for h in hermanas(db, periodo):
        if h.estado == CALCULADA and h.cargado_en is not None:
            calcular(db, h, con_hermanas=False)
