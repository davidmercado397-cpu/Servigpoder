"""Umbral semanal de horas: condicional que se activa por periodo al liquidar.

Sin el umbral, las extras se pagan día a día según el turno. Con el umbral activo, por persona y por semana
calendario (lunes a domingo):

- umbral de la semana = umbral × días de esa semana dentro del periodo ÷ 7 (semanas partidas al inicio o al
  final de la quincena) − horas por día de novedad × días con novedad justificada (incapacidad, vacaciones,
  licencias…; los descansos Z y L no lo bajan). Nunca es negativo;
- horas trabajadas = ordinarias + extras de la semana;
- extras que se pagan = lo que pase del umbral, sin superar las extras que generó el cálculo diario;
- las extras que no se pagan se vuelven horas ordinarias: pierden el porcentaje de hora extra pero conservan el
  recargo que les corresponde (una extra nocturna pasa a recargo nocturno; una dominical, a recargo dominical…).

El descuento se reparte en proporción entre todas las extras de la semana. Modifica las horas de cada día (con
eso se liquida la nómina) y devuelve el detalle por semana para mostrarlo y exportarlo.
"""

from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.apps.liquidador.dominio.tipos import HourConcept
from app.apps.liquidador.models import LiqDia, LiqPeriodo

ORDINARIA = HourConcept.ORDINARY_DAY.value
# Extra → recargo que conserva al volverse ordinaria (la extra diurna no lleva recargo)
RECARGO_DE_EXTRA: dict[str, str | None] = {
    HourConcept.OVERTIME_DAY.value: None,
    HourConcept.OVERTIME_NIGHT.value: HourConcept.ORDINARY_NIGHT.value,
    HourConcept.SUNDAY_OVERTIME_DAY.value: HourConcept.SUNDAY_SURCHARGE.value,
    HourConcept.SUNDAY_OVERTIME_NIGHT.value: HourConcept.SUNDAY_NIGHT_SURCHARGE.value,
    HourConcept.HOLIDAY_OVERTIME_DAY.value: HourConcept.HOLIDAY_DAY_SURCHARGE.value,
    HourConcept.HOLIDAY_OVERTIME_NIGHT.value: HourConcept.HOLIDAY_NIGHT_SURCHARGE.value,
}
EXTRAS = tuple(RECARGO_DE_EXTRA)
Q = Decimal("0.0001")


def _d(v) -> Decimal:
    return Decimal(str(v or 0))


def lunes(fecha: date) -> date:
    return fecha - timedelta(days=fecha.weekday())


def dias_en_periodo(inicio_semana: date, periodo: LiqPeriodo) -> int:
    fin = inicio_semana + timedelta(days=6)
    return max(0, (min(fin, periodo.hasta) - max(inicio_semana, periodo.desde)).days + 1)


def aplicar(periodo: LiqPeriodo, dias: list[LiqDia]) -> dict[int, list[dict]]:
    """Ajusta las horas de los días (d.horas) según el umbral y devuelve {empleado_id: [semanas]}."""
    umbral = _d(periodo.umbral_horas)
    por_novedad = _d(periodo.umbral_horas_novedad)
    grupos: dict[tuple[int, date], list[LiqDia]] = defaultdict(list)
    for d in dias:
        grupos[(d.empleado_id, lunes(d.fecha))].append(d)

    detalle: dict[int, list[dict]] = defaultdict(list)
    for (empleado_id, inicio), dias_semana in sorted(grupos.items(), key=lambda x: (x[0][0], x[0][1])):
        n_dias = dias_en_periodo(inicio, periodo)
        justificados = sum(1 for d in dias_semana if d.turno is not None and d.turno.justifica_umbral)
        umbral_semana = max(Decimal("0"), umbral * n_dias / 7 - por_novedad * justificados).quantize(Q, ROUND_HALF_UP)
        horas = [{k: _d(v) for k, v in (d.horas or {}).items()} for d in dias_semana]
        extras = sum((h.get(c, Decimal("0")) for h in horas for c in EXTRAS), Decimal("0"))
        trabajadas = sum((h.get(ORDINARIA, Decimal("0")) for h in horas), Decimal("0")) + extras
        pagadas = min(extras, max(Decimal("0"), trabajadas - umbral_semana))
        descontadas = extras - pagadas
        if descontadas > 0:
            _descontar(dias_semana, horas, descontadas / extras, descontadas)
        detalle[empleado_id].append({
            "desde": inicio.isoformat(), "hasta": (inicio + timedelta(days=6)).isoformat(), "dias_periodo": n_dias,
            "justificados": justificados, "umbral": float(umbral_semana), "trabajadas": float(trabajadas),
            "extras": float(extras), "pagadas": float(pagadas), "descontadas": float(descontadas),
        })
    return dict(detalle)


def _descontar(dias_semana: list[LiqDia], horas: list[dict[str, Decimal]], fraccion: Decimal, total: Decimal) -> None:
    """Pasa la fracción de cada extra a hora ordinaria con su recargo; el redondeo se corrige en la última."""
    movimientos = [(i, c, (h[c] * fraccion).quantize(Q, ROUND_HALF_UP)) for i, h in enumerate(horas) for c in EXTRAS if h.get(c)]
    if movimientos:
        i, c, m = movimientos[-1]
        movimientos[-1] = (i, c, m + total - sum(x[2] for x in movimientos))
    for i, c, m in movimientos:
        h = horas[i]
        h[c] = h[c] - m
        h[ORDINARIA] = h.get(ORDINARIA, Decimal("0")) + m
        recargo = RECARGO_DE_EXTRA[c]
        if recargo:
            h[recargo] = h.get(recargo, Decimal("0")) + m
    for d, h in zip(dias_semana, horas):
        d.horas = {k: float(v.quantize(Q, ROUND_HALF_UP)) for k, v in h.items() if v}
