"""Nómina de cada empleado a partir de los días y las horas contadas del periodo.

- Salario básico: salario mensual ÷ 30 por cada día trabajado, de descanso (Z) o libre (L). Las ausencias
  y las novedades (vacaciones, licencias…, que se pagan en otro proceso) no se pagan aquí.
- Base de 30 días: el día 31 no suma salario; si se paga el último día de febrero, se completan los 30.
- Incapacidad: se paga al 100 %. Los 2 primeros días de cada incapacidad los paga la empresa y del 3.º en
  adelante la EPS (que reconoce el 66,67 %); la división es informativa.
- Recargos y extras: horas del concepto × valor de la hora (salario ÷ horas del mes) × su %. Los recargos
  llevan solo el adicional (la hora ya está en el salario); las extras, la hora completa.
- Auxilio de transporte: ÷ 30 por día trabajado o de descanso, si el salario no supera 2 mínimos.
- Salud y pensión: % del devengado sin auxilio de transporte. Después, embargos y préstamos.
Cada día se paga con la tarifa vigente ese día (salario mínimo, horas del mes y %).
"""

import calendar
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.apps.liquidador.dominio.tipos import HourConcept
from app.apps.liquidador.models import (
    EMBARGO, MENSUAL, LiqDescuento, LiqDia, LiqEmpleado, LiqPeriodo, LiqResultado, LiqTarifa,
)

# Clases de día (mismos valores que calculo.py)
PAGAN_SALARIO = ("trabajado", "descanso_pago", "libre")
PAGAN_AUXILIO = ("trabajado", "descanso_pago")
INCAPACIDAD = "incapacidad"
DIAS_EMPRESA_INCAPACIDAD = 2

# Conceptos que se pagan aparte del salario (las horas ordinarias diurnas ya están en el salario)
CONCEPTOS_PAGO: tuple[str, ...] = tuple(c.value for c in HourConcept if c != HourConcept.ORDINARY_DAY)
RECARGOS = ("ordinary_night", "holiday_day_surcharge", "holiday_night_surcharge", "sunday_surcharge", "sunday_night_surcharge")


def porcentajes_de_ley(dominical: int) -> dict[str, int]:
    """Código Sustantivo del Trabajo y Ley 2466 de 2025: nocturno 35 %, extra diurna 25 %, extra nocturna 75 %
    y el recargo dominical/festivo (80 % desde jul-2025, 90 % desde jul-2026, 100 % desde jul-2027)."""
    d = dominical
    return {
        "ordinary_night": 35,
        "holiday_day_surcharge": d, "sunday_surcharge": d,
        "holiday_night_surcharge": d + 35, "sunday_night_surcharge": d + 35,
        "overtime_day": 125, "overtime_night": 175,
        "holiday_overtime_day": 125 + d, "sunday_overtime_day": 125 + d,
        "holiday_overtime_night": 175 + d, "sunday_overtime_night": 175 + d,
    }


TARIFAS_INICIALES = (
    (date(2026, 1, 1), 80, "Valores 2026. Recargo dominical y festivo del 80 % (Ley 2466 de 2025)."),
    (date(2026, 7, 1), 90, "Desde el 1-jul-2026 el recargo dominical y festivo sube al 90 % (Ley 2466 de 2025)."),
)


def sembrar_tarifas(db: Session) -> None:
    if db.scalar(select(LiqTarifa.id).limit(1)) is not None:
        return
    for desde, dominical, nota in TARIFAS_INICIALES:
        db.add(LiqTarifa(vigente_desde=desde, smlmv=Decimal("1750905"), auxilio_transporte=Decimal("249095"), horas_mes=210,
                         salud_pct=Decimal("4"), pension_pct=Decimal("4"), porcentajes=porcentajes_de_ley(dominical), nota=nota))
    db.flush()


def _pesos(valor: Decimal) -> Decimal:
    return valor.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


class Tarifas:
    def __init__(self, db: Session):
        self.lista = list(db.scalars(select(LiqTarifa).order_by(LiqTarifa.vigente_desde)))

    def en(self, fecha: date) -> LiqTarifa:
        if not self.lista:
            raise ValueError("No hay tarifas de nómina configuradas")
        vigente = self.lista[0]
        for t in self.lista:
            if t.vigente_desde <= fecha:
                vigente = t
        return vigente


def dias_base_30(fecha: date) -> int:
    """Días que suma una fecha pagada en base 30: el 31 no suma; el último de febrero completa el mes."""
    if fecha.day == 31:
        return 0
    ultimo = calendar.monthrange(fecha.year, fecha.month)[1]
    if fecha.month == 2 and fecha.day == ultimo:
        return 1 + 30 - ultimo
    return 1


def _fraccion_mensual(periodo: LiqPeriodo) -> Decimal:
    return Decimal("1") if periodo.quincena == MENSUAL else Decimal("0.5")


def _vigente(d: LiqDescuento, periodo: LiqPeriodo) -> bool:
    return d.activo and d.desde <= periodo.hasta and (d.hasta is None or d.hasta >= periodo.desde)


def descontado(db: Session, ids: set[int], excepto_periodo: int | None = None) -> dict[int, Decimal]:
    """Lo que ya se descontó de cada préstamo o embargo (en todos los periodos o en los demás)."""
    total: dict[int, Decimal] = defaultdict(Decimal)
    if not ids:
        return total
    consulta = select(LiqResultado.nomina)
    if excepto_periodo is not None:
        consulta = consulta.where(LiqResultado.periodo_id != excepto_periodo)
    for nomina in db.scalars(consulta):
        for x in (nomina or {}).get("descuentos", []):
            if x.get("id") in ids:
                total[x["id"]] += Decimal(str(x.get("valor", 0)))
    return total


@dataclass
class Acumulado:
    dias_salario: int = 0
    basico: Decimal = Decimal("0")
    dias_incapacidad: int = 0
    incapacidad_empresa: int = 0
    incapacidad_eps: int = 0
    incapacidad: Decimal = Decimal("0")
    dias_auxilio: int = 0
    auxilio: Decimal = Decimal("0")
    dias_sin_pago: int = 0
    horas: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    valores: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    tarifas: set[date] = field(default_factory=set)


def liquidar_empleado(empleado: LiqEmpleado, dias: list[LiqDia], periodo: LiqPeriodo, tarifas: Tarifas,
                      descuentos: list[LiqDescuento], ya_descontado: dict[int, Decimal]) -> dict:
    a = Acumulado()
    racha_inc, anterior_inc = 0, None
    for d in sorted(dias, key=lambda x: x.fecha):
        t = tarifas.en(d.fecha)
        a.tarifas.add(t.vigente_desde)
        salario = empleado.salario or t.smlmv
        valor_dia = salario / 30
        valor_hora = salario / t.horas_mes
        base = dias_base_30(d.fecha)
        if d.clase in PAGAN_SALARIO:
            a.dias_salario += base
            a.basico += valor_dia * base
        elif d.clase == INCAPACIDAD:
            racha_inc = racha_inc + 1 if anterior_inc == d.fecha - timedelta(days=1) else 1
            anterior_inc = d.fecha
            a.dias_incapacidad += base
            a.incapacidad += valor_dia * base
            if racha_inc <= DIAS_EMPRESA_INCAPACIDAD:
                a.incapacidad_empresa += base
            else:
                a.incapacidad_eps += base
        else:
            a.dias_sin_pago += 1
        if d.clase in PAGAN_AUXILIO and salario <= 2 * t.smlmv:
            a.dias_auxilio += base
            a.auxilio += t.auxilio_transporte / 30 * base
        for concepto, h in (d.horas or {}).items():
            if concepto == HourConcept.ORDINARY_DAY.value or not h:
                continue
            horas = Decimal(str(h))
            a.horas[concepto] += horas
            a.valores[concepto] += horas * valor_hora * Decimal(str(t.porcentajes.get(concepto, 0))) / 100

    valores = {c: _pesos(v) for c, v in a.valores.items() if _pesos(v)}
    basico, incapacidad, auxilio = _pesos(a.basico), _pesos(a.incapacidad), _pesos(a.auxilio)
    recargos = sum((v for c, v in valores.items() if c in RECARGOS), Decimal("0"))
    extras = sum((v for c, v in valores.items() if c not in RECARGOS), Decimal("0"))
    devengado = basico + incapacidad + recargos + extras + auxilio
    ibc = devengado - auxilio

    t_cierre = tarifas.en(periodo.hasta)
    salud = _pesos(ibc * t_cierre.salud_pct / 100)
    pension = _pesos(ibc * t_cierre.pension_pct / 100)
    disponible = devengado - salud - pension

    aplicados = []
    # Primero los embargos (orden judicial), luego los préstamos
    for x in sorted((x for x in descuentos if _vigente(x, periodo)), key=lambda x: (x.tipo != EMBARGO, x.desde, x.id)):
        if x.valor_mensual:
            valor = _pesos(x.valor_mensual * _fraccion_mensual(periodo))
            base_txt = f"cuota mensual {x.valor_mensual:,.0f}" + (" ÷ 2 (quincena)" if periodo.quincena != MENSUAL else "")
        else:
            valor = _pesos(ibc * (x.porcentaje or 0) / 100)
            base_txt = f"{x.porcentaje} % de {ibc:,.0f} (devengado sin auxilio)"
        observacion = ""
        if x.monto_total is not None:
            saldo = max(x.monto_total - ya_descontado.get(x.id, Decimal("0")), Decimal("0"))
            if valor > saldo:
                valor, observacion = _pesos(saldo), "se descuenta solo el saldo pendiente"
        if valor > disponible:
            valor, observacion = max(_pesos(disponible), Decimal("0")), "el neto no alcanza para la cuota completa"
        disponible -= valor
        aplicados.append({"id": x.id, "tipo": x.tipo, "descripcion": x.descripcion, "valor": float(valor),
                          "calculo": base_txt, "observacion": observacion})

    prestamos = sum((Decimal(str(x["valor"])) for x in aplicados if x["tipo"] != EMBARGO), Decimal("0"))
    embargos = sum((Decimal(str(x["valor"])) for x in aplicados if x["tipo"] == EMBARGO), Decimal("0"))
    deducciones = salud + pension + prestamos + embargos
    neto = devengado - deducciones
    salario_ref = empleado.salario or t_cierre.smlmv
    return {
        "salario": float(salario_ref), "salario_minimo": empleado.salario is None,
        "valor_dia": float(round(salario_ref / 30, 2)), "valor_hora": float(round(salario_ref / t_cierre.horas_mes, 2)),
        "horas_mes": t_cierre.horas_mes,
        "dias_salario": a.dias_salario, "dias_incapacidad": a.dias_incapacidad,
        "incapacidad_empresa": a.incapacidad_empresa, "incapacidad_eps": a.incapacidad_eps,
        "dias_auxilio": a.dias_auxilio, "dias_sin_pago": a.dias_sin_pago,
        "basico": float(basico), "incapacidad": float(incapacidad), "auxilio": float(auxilio),
        "horas": {c: float(h) for c, h in a.horas.items() if h},
        "valores": {c: float(v) for c, v in valores.items()},
        "recargos": float(recargos), "extras": float(extras),
        "devengado": float(devengado), "ibc": float(ibc),
        "salud": float(salud), "salud_pct": float(t_cierre.salud_pct),
        "pension": float(pension), "pension_pct": float(t_cierre.pension_pct),
        "descuentos": aplicados, "prestamos": float(prestamos), "embargos": float(embargos),
        "deducciones": float(deducciones), "neto": float(neto),
        "tarifas": sorted(x.isoformat() for x in a.tarifas),
    }


def liquidar(db: Session, periodo: LiqPeriodo, dias: list[LiqDia], resultados: dict[int, LiqResultado]) -> None:
    """Calcula la nómina de cada resultado del periodo (se llama al contar las horas)."""
    tarifas = Tarifas(db)
    if not tarifas.lista:
        sembrar_tarifas(db)
        tarifas = Tarifas(db)
    por_empleado: dict[int, list[LiqDia]] = defaultdict(list)
    for d in dias:
        por_empleado[d.empleado_id].append(d)
    empleados = {e.id: e for e in db.scalars(select(LiqEmpleado).where(LiqEmpleado.id.in_(list(resultados))))} if resultados else {}
    descuentos: dict[int, list[LiqDescuento]] = defaultdict(list)
    if resultados:
        for x in db.scalars(select(LiqDescuento).where(LiqDescuento.empleado_id.in_(list(resultados)))):
            descuentos[x.empleado_id].append(x)
    ya = descontado(db, {x.id for lista in descuentos.values() for x in lista if x.monto_total is not None}, periodo.id)
    for empleado_id, r in resultados.items():
        n = liquidar_empleado(empleados[empleado_id], por_empleado[empleado_id], periodo, tarifas, descuentos[empleado_id], ya)
        r.nomina, r.devengado, r.neto = n, Decimal(str(n["devengado"])), Decimal(str(n["neto"]))
