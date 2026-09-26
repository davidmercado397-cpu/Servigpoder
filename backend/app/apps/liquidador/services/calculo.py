"""Conteo de horas de una quincena.

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
from app.apps.liquidador.services import festivos

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
    if quincena == 1:
        return date(anio, mes, 1), date(anio, mes, 15)
    if quincena == 2:
        return date(anio, mes, 16), date(anio, mes, calendar.monthrange(anio, mes)[1])
    raise ValueError("La quincena debe ser 1 o 2")


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


def calcular(db: Session, periodo: LiqPeriodo) -> int:
    """Recalcula cada día y los totales por empleado con los turnos y festivos vigentes."""
    dias = list(db.scalars(select(LiqDia).where(LiqDia.periodo_id == periodo.id).order_by(LiqDia.empleado_id, LiqDia.fecha)))
    fest = festivos.conjunto(db, periodo.desde, periodo.hasta + timedelta(days=1))

    horas_por_empleado: dict[int, dict[HourConcept, Decimal]] = defaultdict(lambda: defaultdict(lambda: Decimal("0")))
    conteo_por_empleado: dict[int, dict[str, int]] = defaultdict(lambda: dict.fromkeys(CLASES, 0))
    for d in dias:
        tipo = classify(d.fecha, holiday_today=d.fecha in fest, holiday_tomorrow=d.fecha + timedelta(days=1) in fest)
        conceptos = expand_workday_to_concepts(d.turno.matriz or {}, tipo)
        d.tipo_dia = tipo.value
        d.clase = clase_de(d.turno)
        d.horas = {c.value: float(h) for c, h in conceptos.items()}
        for c, h in conceptos.items():
            horas_por_empleado[d.empleado_id][c] += h
        conteo_por_empleado[d.empleado_id][d.clase] += 1

    db.execute(delete(LiqResultado).where(LiqResultado.periodo_id == periodo.id))
    for empleado_id, conteo in conteo_por_empleado.items():
        horas = horas_por_empleado[empleado_id]
        db.add(LiqResultado(
            periodo_id=periodo.id, empleado_id=empleado_id, dias=conteo,
            horas={c.value: float(horas.get(c, Decimal("0"))) for c in HourConcept},
            total_horas=sum((horas.get(c, Decimal("0")) for c in CONCEPTOS_TRABAJADOS), Decimal("0")),
        ))
    periodo.estado = CALCULADA
    periodo.calculado_en = datetime.now(timezone.utc)
    db.flush()
    return len(conteo_por_empleado)
