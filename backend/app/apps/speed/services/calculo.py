"""Liquidación de la quincena de una persona (Speed). Función pura: recibe empleado, novedad, parámetros y descuentos.

Reglas acordadas con el usuario (2026-11-17):
- Nómina quincenal y comercial: cada quincena tiene 15 días (1–15 y 16–30; el 31 no cuenta, febrero completa 30).
- Salario: la mitad por quincena = salario ÷ 30 × días trabajados. Los tiempos no laborados (ausencias, licencias no
  remuneradas, suspensiones) descuentan salario y auxilio de transporte.
- Incapacidad: los 2 primeros días al 100 % y desde el 3.º al 66,67 %, sin bajar del salario mínimo diario.
- Variables (horas extras, comisiones, Ley 2466, bonificaciones, rodamiento) = valor mensual ÷ 30 × días:
  · quien aplica a la regla de programación: días con programación de la quincena menos los no laborados;
  · quien no aplica: días trabajados.
- Auxilio de transporte ÷ 30 × días trabajados, para quien gana hasta 2 SMLMV en lo salarial (salario + horas extras).
- Salud 4 % y pensión 4 % sobre salario, incapacidad, horas extras y pagos adicionales salariales.
- Deducciones en orden: embargos → préstamos → cuotas por mayores valores pagados; nunca dejan el neto en negativo.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

DIAS_QUINCENA = 15

PARAMETROS: dict[str, tuple[float, str, str]] = {
    "salario_minimo": (1750905, "Salario mínimo mensual", "Para el piso de la incapacidad y el tope del auxilio de transporte"),
    "auxilio_transporte": (249095, "Auxilio de transporte mensual", ""),
    "smlmv_auxilio": (2, "Auxilio de transporte hasta (SMLMV)", "Lo reciben quienes ganan en lo salarial hasta este número de salarios mínimos"),
    "pct_salud": (4, "Salud del empleado (%)", "Sobre salario, incapacidad, horas extras y pagos adicionales salariales"),
    "pct_pension": (4, "Pensión del empleado (%)", "Sobre la misma base de salud"),
    "dias_incapacidad_100": (2, "Días de incapacidad al 100 %", "Los primeros días de cada incapacidad"),
    "pct_incapacidad": (66.67, "Incapacidad desde el día siguiente (%)", "Sin bajar del salario mínimo diario"),
}


def parametros_por_defecto() -> dict[str, float]:
    return {k: v[0] for k, v in PARAMETROS.items()}


def redondear(v: float) -> float:
    return float(Decimal(str(v)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def prorrata(mensual: float, dias: float) -> float:
    """Valor mensual ÷ 30 × días, en decimal exacto (para que 249.095 ÷ 2 redondee a 124.548 como en el Excel)."""
    return float(Decimal(str(mensual)) * Decimal(str(dias)) / Decimal(30))


def _n(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def dias_del_periodo(anio: int, mes: int, quincena: int) -> tuple[int, int]:
    """Días comerciales de la quincena: (primero, último) en un mes de 30."""
    return (1, 15) if quincena == 1 else (16, 30)


def dias_contrato(ingreso: date | None, anio: int, mes: int, quincena: int) -> int:
    """Días de la quincena desde la fecha de ingreso (comercial: el 31 cuenta como 30)."""
    desde, hasta = dias_del_periodo(anio, mes, quincena)
    if ingreso is None or (ingreso.year, ingreso.month) < (anio, mes):
        return DIAS_QUINCENA
    if (ingreso.year, ingreso.month) > (anio, mes):
        return 0
    dia = min(ingreso.day, 30)
    if dia > hasta:
        return 0
    return hasta - max(desde, dia) + 1


@dataclass
class Descuento:
    id: int
    tipo: str  # embargo | prestamo | cuota | adicional
    descripcion: str
    cuota: float
    saldo: float | None  # None = sin tope
    salarial: bool = True


@dataclass
class Resultado:
    dias: dict
    conceptos: dict
    descuentos: list[dict]
    ibc: float
    devengado: float
    deducciones: float
    neto: float
    alertas: list[str] = field(default_factory=list)
    aplicados: dict[int, float] = field(default_factory=dict)  # id del descuento → valor aplicado


ORDEN_DEDUCCIONES = ("embargo", "prestamo", "cuota")


def liquidar(emp: dict, nov: dict | None, p: dict, anio: int, mes: int, quincena: int, descuentos: list[Descuento]) -> Resultado:
    """emp: salario, horas_extras, comisiones, ley_2466, bonificaciones, rodamiento, aplica_programacion, fecha_ingreso, auxilio_listado.
    nov: dias_programados (None = toda la quincena), ausencias, licencias, suspensiones, incapacidad, incapacidad_previos."""
    nov = nov or {}
    alertas: list[str] = []
    salario = _n(emp.get("salario"))
    diario = salario / 30
    contrato = dias_contrato(emp.get("fecha_ingreso"), anio, mes, quincena)

    tnl = _n(nov.get("ausencias")) + _n(nov.get("licencias")) + _n(nov.get("suspensiones"))
    inc = _n(nov.get("incapacidad"))
    if tnl + inc > contrato:
        alertas.append(f"Los días no laborados e incapacidad ({tnl + inc:g}) superan los días de la quincena ({contrato}): se toman {contrato}")
        inc = min(inc, contrato)
        tnl = contrato - inc
    trabajados = max(0.0, contrato - tnl - inc)

    if emp.get("aplica_programacion"):
        prog = nov.get("dias_programados")
        programados = contrato if prog in (None, "") else min(_n(prog), contrato)
        dias_variables = max(0.0, programados - tnl - inc)
    else:
        programados = None
        dias_variables = trabajados

    # Incapacidad: los primeros días al 100 %; los siguientes al %, sin bajar del mínimo diario
    previos = _n(nov.get("incapacidad_previos"))
    al_100 = max(0.0, min(inc, _n(p["dias_incapacidad_100"]) - previos))
    al_pct = inc - al_100
    minimo_diario = _n(p["salario_minimo"]) / 30
    diario_pct = max(diario * _n(p["pct_incapacidad"]) / 100, minimo_diario) if al_pct else 0.0
    incapacidad = prorrata(salario, al_100) + al_pct * diario_pct

    # Auxilio de transporte: hasta N SMLMV en lo salarial (salario + horas extras del mes)
    salarial_mes = salario + _n(emp.get("horas_extras"))
    aplica_auxilio = salarial_mes <= _n(p["smlmv_auxilio"]) * _n(p["salario_minimo"]) + 0.5
    auxilio = prorrata(_n(p["auxilio_transporte"]), trabajados) if aplica_auxilio else 0.0
    listado = emp.get("auxilio_listado")
    if listado is not None and (_n(listado) > 0) != aplica_auxilio:
        alertas.append("El auxilio de transporte del Listado no coincide con la regla de 2 SMLMV "
                       f"({'sí aplica' if aplica_auxilio else 'no aplica'} por ganar {redondear(salarial_mes):,.0f} en lo salarial)".replace(",", "."))

    var = lambda clave: prorrata(_n(emp.get(clave)), dias_variables)  # noqa: E731
    conceptos = {
        "salario": redondear(prorrata(salario, trabajados)),
        "incapacidad": redondear(incapacidad),
        "auxilio_transporte": redondear(auxilio),
        "horas_extras": redondear(var("horas_extras")),
        "comisiones": redondear(var("comisiones")),
        "ley_2466": redondear(var("ley_2466")),
        "bonificaciones": redondear(var("bonificaciones")),
        "rodamiento": redondear(var("rodamiento")),
    }

    # Pagos adicionales (menores valores pagados) suman; los salariales entran a salud y pensión
    detalle_desc: list[dict] = []
    aplicados: dict[int, float] = {}
    adicional = adicional_salarial = 0.0
    for d in descuentos:
        if d.tipo != "adicional":
            continue
        valor = redondear(d.cuota if d.saldo is None else min(d.cuota, d.saldo))
        if valor <= 0:
            continue
        adicional += valor
        adicional_salarial += valor if d.salarial else 0
        aplicados[d.id] = valor
        detalle_desc.append({"id": d.id, "tipo": d.tipo, "descripcion": d.descripcion, "valor": valor})
    conceptos["pago_adicional"] = redondear(adicional)

    ibc = conceptos["salario"] + conceptos["incapacidad"] + conceptos["horas_extras"] + adicional_salarial
    conceptos["salud"] = redondear(ibc * _n(p["pct_salud"]) / 100)
    conceptos["pension"] = redondear(ibc * _n(p["pct_pension"]) / 100)
    devengado = sum(conceptos[k] for k in ("salario", "incapacidad", "auxilio_transporte", "horas_extras", "comisiones", "ley_2466",
                                         "bonificaciones", "rodamiento", "pago_adicional"))
    deducciones = conceptos["salud"] + conceptos["pension"]

    # Embargos → préstamos → cuotas: sin dejar el neto en negativo
    totales = {t: 0.0 for t in ORDEN_DEDUCCIONES}
    for tipo in ORDEN_DEDUCCIONES:
        for d in [x for x in descuentos if x.tipo == tipo]:
            pedido = d.cuota if d.saldo is None else min(d.cuota, d.saldo)
            disponible = max(0.0, devengado - deducciones)
            valor = redondear(min(pedido, disponible))
            if valor < redondear(pedido):
                alertas.append(f"{d.descripcion or tipo}: no alcanzó el neto (se descontaron {valor:,.0f} de {redondear(pedido):,.0f})".replace(",", "."))
            if valor <= 0:
                continue
            deducciones += valor
            totales[tipo] += valor
            aplicados[d.id] = valor
            detalle_desc.append({"id": d.id, "tipo": d.tipo, "descripcion": d.descripcion, "valor": valor})
    conceptos["embargos"] = redondear(totales["embargo"])
    conceptos["prestamos"] = redondear(totales["prestamo"])
    conceptos["cuotas"] = redondear(totales["cuota"])

    if contrato == 0:
        alertas.append("Ingresó después de esta quincena: no tiene días")
    dias = {"contrato": contrato, "trabajados": trabajados, "no_laborados": tnl, "incapacidad": inc, "incapacidad_100": al_100,
            "incapacidad_pct": al_pct, "programados": programados, "variables": dias_variables}
    return Resultado(dias=dias, conceptos=conceptos, descuentos=detalle_desc, ibc=redondear(ibc), devengado=redondear(devengado),
                     deducciones=redondear(deducciones), neto=redondear(devengado - deducciones), alertas=alertas, aplicados=aplicados)
