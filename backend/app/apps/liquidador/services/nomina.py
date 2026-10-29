"""Nómina de cada empleado a partir de los días y las horas contadas del periodo.

- Salario básico: salario mensual ÷ 30 por cada día trabajado, de descanso (Z) o libre (L). Las ausencias
  y las demás novedades (licencias…, que se pagan en otro proceso) no se pagan aquí.
- Base de 30 días: el día 31 no suma salario; si se paga el último día de febrero, se completan los 30.
- Incapacidad: se paga al 100 %. Los 2 primeros días de cada incapacidad los paga la empresa y del 3.º en
  adelante la EPS (que reconoce el 66,67 %); la división es informativa.
- Recargos y extras: horas del concepto × valor de la hora (salario ÷ horas del mes) × su %. Los recargos
  llevan solo el adicional (la hora ya está en el salario); las extras, la hora completa.
- Vacaciones (códigos marcados "Es vacaciones"): (salario + promedio variable) ÷ 30 por cada día, separando
  hábiles y no hábiles; ver services/vacaciones.py.
- Auxilio de transporte: ÷ 30 por día trabajado o de descanso, si el salario no supera 2 mínimos.
- Auxilios no prestacionales: valor mensual menos 1/30 por cada día de tiempo no laborado (ausencias, incapacidades,
  vacaciones y demás novedades).
- Novedades manuales: lo que se pagó de menos en nóminas anteriores (y las horas extras o recargos pendientes, valorados
  con la tarifa de la fecha en que se causaron) se paga; lo que se pagó de más se descuenta. Las de horas y el menor
  valor pagado hacen base de salud y pensión; el mayor valor pagado es solo una deducción.
- Salud y pensión: % del devengado sin auxilio de transporte. Después, embargos, novedades que descuentan, préstamos
  y cuotas.
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
    CUOTA, EMBARGO, MENSUAL, NOVEDADES_DEDUCCION, NOVEDADES_HORAS, PRESTAMO, LiqAuxilio, LiqDescuento, LiqDia, LiqEmpleado,
    LiqNovedad, LiqPeriodo, LiqResultado, LiqTarifa,
)
from app.apps.liquidador.services import festivos, vacaciones as vac

# Clases de día (mismos valores que calculo.py)
PAGAN_SALARIO = ("trabajado", "descanso_pago", "libre")
PAGAN_AUXILIO = ("trabajado", "descanso_pago")
INCAPACIDAD = "incapacidad"
AUSENCIA = "ausencia"
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


AMBAS, PRIMERA, SEGUNDA = "ambas", "primera", "segunda"
TOPE_NO_SALARIAL = Decimal("0.40")  # Ley 1393 de 2010, art. 30: lo que pase del 40 % entra en la base de aportes
_NOMBRE_QUINCENA = {PRIMERA: "solo 1.ª quincena", SEGUNDA: "solo 2.ª quincena"}


def _aplica_quincena(quincena: str, periodo: LiqPeriodo) -> bool:
    """El periodo mensual liquida todo; en quincenas, "primera"/"segunda" solo aplican en la suya."""
    if periodo.quincena == MENSUAL or quincena == AMBAS:
        return True
    return (quincena == PRIMERA and periodo.quincena == 1) or (quincena == SEGUNDA and periodo.quincena == 2)


def _fraccion_mensual(periodo: LiqPeriodo, quincena: str = AMBAS) -> Decimal:
    """Parte del valor mensual que va en el periodo: la mitad por quincena si aplica en ambas; completo si es mensual
    o si solo aplica en una quincena."""
    return Decimal("1") if periodo.quincena == MENSUAL or quincena != AMBAS else Decimal("0.5")


def _txt_fraccion(periodo: LiqPeriodo, quincena: str) -> str:
    if periodo.quincena == MENSUAL:
        return ""
    return " ÷ 2 (quincena)" if quincena == AMBAS else f" ({_NOMBRE_QUINCENA[quincena]})"


def _vigente(d, periodo: LiqPeriodo) -> bool:
    return (d.activo and d.desde <= periodo.hasta and (d.hasta is None or d.hasta >= periodo.desde)
            and _aplica_quincena(getattr(d, "quincena", AMBAS) or AMBAS, periodo))


def descontado(db: Session, ids: set[int], excepto_periodo: int | None = None) -> dict[int, Decimal]:
    """Lo que ya se descontó de cada préstamo, embargo o cuota (en todos los periodos o en los demás)."""
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
    vac_habiles: int = 0  # días en base 30 (los que se pagan)
    vac_no_habiles: int = 0
    vac_habiles_reales: int = 0  # días calendario hábiles (los que descuentan del saldo)
    vac_dias: int = 0  # días calendario de vacaciones
    vac_valor_habiles: Decimal = Decimal("0")
    vac_valor_no_habiles: Decimal = Decimal("0")
    horas: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    valores: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    tarifas: set[date] = field(default_factory=set)


NOMBRES_HORAS = {
    "ordinary_night": "recargo nocturno", "holiday_day_surcharge": "recargo festivo diurno",
    "holiday_night_surcharge": "recargo festivo nocturno", "sunday_surcharge": "recargo dominical diurno",
    "sunday_night_surcharge": "recargo dominical nocturno", "overtime_day": "extra diurna", "overtime_night": "extra nocturna",
    "holiday_overtime_day": "extra festiva diurna", "holiday_overtime_night": "extra festiva nocturna",
    "sunday_overtime_day": "extra dominical diurna", "sunday_overtime_night": "extra dominical nocturna",
}


def valor_novedad(x: LiqNovedad, empleado: LiqEmpleado, tarifas: Tarifas, periodo: LiqPeriodo) -> tuple[Decimal, str]:
    """Valor y cálculo de una novedad. Las de horas: horas × valor de la hora × % con la tarifa vigente en la fecha
    en que se causaron (con el salario actual del empleado); un valor escrito reemplaza el calculado."""
    if x.tipo not in NOVEDADES_HORAS:
        return _pesos(x.valor or Decimal("0")), "valor registrado"
    fecha = x.fecha_causacion or periodo.desde
    t = tarifas.en(fecha)
    salario = empleado.salario or t.smlmv
    valor_hora = salario / t.horas_mes
    total, partes = Decimal("0"), []
    for concepto, h in (x.horas or {}).items():
        horas = Decimal(str(h or 0))
        if not horas:
            continue
        pct = Decimal(str(t.porcentajes.get(concepto, 0)))
        total += horas * valor_hora * pct / 100
        partes.append(f"{horas:g} h {NOMBRES_HORAS.get(concepto, concepto)} × {pct:g} %")
    calculo = f"{', '.join(partes) or 'sin horas'} × hora {valor_hora:,.0f} (tarifa del {t.vigente_desde:%d/%m/%Y}, causadas el {fecha:%d/%m/%Y})"
    if x.valor is not None:
        return _pesos(x.valor), f"valor escrito (calculado: {_pesos(total):,.0f} = {calculo})"
    return _pesos(total), calculo


def liquidar_empleado(empleado: LiqEmpleado, dias: list[LiqDia], periodo: LiqPeriodo, tarifas: Tarifas,
                      descuentos: list[LiqDescuento], ya_descontado: dict[int, Decimal], auxilios: list | None = None,
                      vacaciones: dict | None = None, novedades: list[LiqNovedad] | None = None) -> dict:
    """`vacaciones` (solo si tiene días de vacaciones): festivos, promedio sugerido y meses, promedio manual y
    días hábiles ya disfrutados antes del periodo."""
    a = Acumulado()
    ctx = vacaciones or {}
    fest = ctx.get("festivos", set())
    promedio = ctx.get("manual") if ctx.get("manual") is not None else ctx.get("sugerido", Decimal("0"))
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
        elif vac.es_vacaciones(d):
            valor_vac = (salario + promedio) / 30 * base
            a.vac_dias += 1
            if vac.es_habil(d.fecha, empleado.dias_habiles, fest):
                a.vac_habiles += base
                a.vac_habiles_reales += 1
                a.vac_valor_habiles += valor_vac
            else:
                a.vac_no_habiles += base
                a.vac_valor_no_habiles += valor_vac
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

    vac_habiles, vac_no_habiles = _pesos(a.vac_valor_habiles), _pesos(a.vac_valor_no_habiles)
    vacaciones_valor = vac_habiles + vac_no_habiles
    alertas = []
    detalle_vac = None
    if a.vac_dias:
        t_vac = tarifas.en(periodo.hasta)
        salario_vac = empleado.salario or t_vac.smlmv
        saldo = vac.saldo(empleado, ctx.get("antes", 0) + a.vac_habiles_reales, periodo.hasta)
        detalle_vac = {
            "dias_habiles": a.vac_habiles, "dias_no_habiles": a.vac_no_habiles, "habiles_calendario": a.vac_habiles_reales,
            "valor_habiles": float(vac_habiles), "valor_no_habiles": float(vac_no_habiles), "valor": float(vacaciones_valor),
            "salario": float(salario_vac), "promedio": float(promedio), "promedio_sugerido": float(ctx.get("sugerido", 0)),
            "meses_promedio": float(ctx.get("meses", 0)), "promedio_manual": ctx.get("manual") is not None,
            "base": float(salario_vac + promedio), "valor_dia": float(round((salario_vac + promedio) / 30, 2)),
            "dias_habiles_empleado": vac.texto_habiles(empleado.dias_habiles), "saldo": saldo,
        }
        if saldo is not None and saldo["pendientes"] < 0:  # se dan más días hábiles de los pendientes
            pendientes_antes = saldo["pendientes"] + a.vac_habiles_reales
            alertas.append(f"Se liquidan {a.vac_habiles_reales} día(s) hábiles de vacaciones pero solo tenía "
                           f"{max(pendientes_antes, 0):,.2f} pendientes (causados {saldo['causados']:,.2f} al {periodo.hasta:%d/%m/%Y})")

    # Auxilios no prestacionales: se descuentan en proporción al tiempo no laborado (TNL) del periodo: ausencias,
    # incapacidades, vacaciones y cualquier otra novedad; los descansos (Z) y libres (L) no descuentan
    dias_ausencia = sum(1 for d in dias if d.clase == AUSENCIA)
    dias_incapacidad_tnl = sum(1 for d in dias if d.clase == INCAPACIDAD)
    dias_otras_tnl = sum(1 for d in dias if d.clase not in PAGAN_SALARIO and d.clase not in (AUSENCIA, INCAPACIDAD)) - a.vac_dias
    dias_descuento = dias_ausencia + dias_incapacidad_tnl + a.vac_dias + dias_otras_tnl
    aux_aplicados = []
    for x in sorted((x for x in auxilios or [] if _vigente(x, periodo)), key=lambda x: (x.desde, x.id)):
        q = x.quincena or AMBAS
        base = x.valor_mensual * _fraccion_mensual(periodo, q)
        menos = x.valor_mensual / 30 * dias_descuento
        valor = _pesos(max(base - menos, Decimal("0")))
        calculo = f"valor mensual {x.valor_mensual:,.0f}{_txt_fraccion(periodo, q)}"
        if dias_descuento:
            motivo = ", ".join(t for t in (f"{dias_ausencia} de ausencia" if dias_ausencia else "",
                                           f"{dias_incapacidad_tnl} de incapacidad" if dias_incapacidad_tnl else "",
                                           f"{a.vac_dias} de vacaciones" if a.vac_dias else "",
                                           f"{dias_otras_tnl} de otras novedades" if dias_otras_tnl else "") if t)
            calculo += f" − {dias_descuento} día(s) ({motivo}) × {x.valor_mensual / 30:,.0f}"
        aux_aplicados.append({"id": x.id, "descripcion": x.descripcion, "valor": float(valor), "calculo": calculo})
    no_prestacional = sum((Decimal(str(x["valor"])) for x in aux_aplicados), Decimal("0"))

    # Novedades manuales de esta nómina
    nov_aplicadas, nov_salarial, nov_no_salarial, nov_deducciones = [], Decimal("0"), Decimal("0"), []
    for x in sorted(novedades or [], key=lambda x: x.id):
        valor, calculo = valor_novedad(x, empleado, tarifas, periodo)
        deduccion = x.tipo in NOVEDADES_DEDUCCION
        item = {"id": x.id, "tipo": x.tipo, "descripcion": x.descripcion, "valor": float(valor), "calculo": calculo,
                "salarial": not deduccion and x.salarial, "deduccion": deduccion, "nomina_origen": x.nomina_origen, "observacion": ""}
        nov_aplicadas.append(item)
        if deduccion:
            nov_deducciones.append(item)
        elif x.salarial:
            nov_salarial += valor
        else:
            nov_no_salarial += valor
    nov_devengo = nov_salarial + nov_no_salarial

    salarial = basico + incapacidad + recargos + extras + vacaciones_valor + nov_salarial
    devengado = salarial + no_prestacional + nov_no_salarial + auxilio
    # Lo no salarial que pase del 40 % de la remuneración total sí entra en la base de salud y pensión
    no_salarial = no_prestacional + nov_no_salarial
    exceso = _pesos(max(no_salarial - TOPE_NO_SALARIAL * (salarial + no_salarial), Decimal("0")))
    ibc = salarial + exceso
    if exceso:
        alertas.append(f"Los pagos no salariales superan el 40 % de la remuneración: {exceso:,.0f} entran en la base de salud y pensión")

    t_cierre = tarifas.en(periodo.hasta)
    salud = _pesos(ibc * t_cierre.salud_pct / 100)
    pension = _pesos(ibc * t_cierre.pension_pct / 100)
    disponible = devengado - salud - pension

    aplicados = []

    def aplicar(x: LiqDescuento) -> None:
        nonlocal disponible
        if x.valor_mensual:
            q = x.quincena or AMBAS
            valor = _pesos(x.valor_mensual * _fraccion_mensual(periodo, q))
            base_txt = f"cuota mensual {x.valor_mensual:,.0f}{_txt_fraccion(periodo, q)}"
        else:
            valor = _pesos(salarial * (x.porcentaje or 0) / 100)
            base_txt = f"{x.porcentaje} % de {salarial:,.0f} (devengado sin auxilios)"
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

    # Primero los embargos (orden judicial), luego las novedades que descuentan (lo pagado de más), los préstamos y al
    # final las cuotas (exequial, pólizas…)
    orden = {EMBARGO: 0, CUOTA: 2}
    vigentes = sorted((x for x in descuentos if _vigente(x, periodo)), key=lambda x: (orden.get(x.tipo, 1), x.desde, x.id))
    for x in vigentes:
        if x.tipo == EMBARGO:
            aplicar(x)
    nov_deduccion = Decimal("0")
    for item in nov_deducciones:
        valor = Decimal(str(item["valor"]))
        if valor > disponible:
            pendiente = valor - max(disponible, Decimal("0"))
            valor = max(_pesos(disponible), Decimal("0"))
            item["observacion"] = f"el neto no alcanza: quedan {pendiente:,.0f} por descontar en otra nómina"
            alertas.append(f"«{item['descripcion']}»: el neto no alcanza; quedan {pendiente:,.0f} por descontar en otra nómina")
            item["valor"] = float(valor)
        disponible -= valor
        nov_deduccion += valor
    for x in vigentes:
        if x.tipo != EMBARGO:
            aplicar(x)

    def total(tipo: str) -> Decimal:
        return sum((Decimal(str(x["valor"])) for x in aplicados if x["tipo"] == tipo), Decimal("0"))

    prestamos, embargos, cuotas = total(PRESTAMO), total(EMBARGO), total(CUOTA)
    deducciones = salud + pension + prestamos + embargos + cuotas + nov_deduccion
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
        "auxilios": aux_aplicados, "auxilios_no_prestacionales": float(no_prestacional), "dias_ausencia": dias_ausencia, "dias_tnl": dias_descuento,
        "exceso_no_salarial": float(exceso), "alertas": alertas,
        "vacaciones": detalle_vac, "vacaciones_valor": float(vacaciones_valor),
        "horas": {c: float(h) for c, h in a.horas.items() if h},
        "valores": {c: float(v) for c, v in valores.items()},
        "recargos": float(recargos), "extras": float(extras),
        "devengado": float(devengado), "ibc": float(ibc),
        "salud": float(salud), "salud_pct": float(t_cierre.salud_pct),
        "pension": float(pension), "pension_pct": float(t_cierre.pension_pct),
        "descuentos": aplicados, "prestamos": float(prestamos), "embargos": float(embargos), "cuotas": float(cuotas),
        "novedades": nov_aplicadas, "novedades_devengo": float(nov_devengo), "novedades_deduccion": float(nov_deduccion),
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
    auxilios: dict[int, list[LiqAuxilio]] = defaultdict(list)
    if resultados:
        for x in db.scalars(select(LiqAuxilio).where(LiqAuxilio.empleado_id.in_(list(resultados)))):
            auxilios[x.empleado_id].append(x)
    novedades: dict[int, list[LiqNovedad]] = defaultdict(list)
    for x in db.scalars(select(LiqNovedad).where(LiqNovedad.periodo_id == periodo.id)):
        novedades[x.empleado_id].append(x)
    ya = descontado(db, {x.id for lista in descuentos.values() for x in lista if x.monto_total is not None}, periodo.id)
    contexto_vac = _contexto_vacaciones(db, periodo, por_empleado, empleados)
    otras = _otras_nominas(db, periodo, por_empleado)
    for empleado_id, r in resultados.items():
        avisos, aplica = [], True
        if empleado_id in otras:
            avisos, duenia = otras[empleado_id]
            aplica = duenia is None
        n = liquidar_empleado(empleados[empleado_id], por_empleado[empleado_id], periodo, tarifas,
                              descuentos[empleado_id] if aplica else [], ya, auxilios[empleado_id] if aplica else [],
                              contexto_vac.get(empleado_id), novedades[empleado_id])
        e = empleados[empleado_id]
        if e.estado == "retirado" and e.fecha_retiro and any(d.fecha > e.fecha_retiro for d in por_empleado[empleado_id]):
            avisos = [f"Está retirado desde el {e.fecha_retiro:%d/%m/%Y} y tiene turnos después de esa fecha", *avisos]
        n["alertas"] = avisos + n["alertas"]
        n["otras_nominas"] = any("nómina «" in a for a in avisos)
        r.nomina, r.devengado, r.neto = n, Decimal(str(n["devengado"])), Decimal(str(n["neto"]))


def _contexto_vacaciones(db: Session, periodo: LiqPeriodo, por_empleado: dict[int, list[LiqDia]],
                         empleados: dict[int, LiqEmpleado]) -> dict[int, dict]:
    """Datos para liquidar las vacaciones de quienes tienen días de vacaciones en el periodo."""
    con_vac = {eid: empleados[eid] for eid, dias in por_empleado.items() if eid in empleados and any(vac.es_vacaciones(d) for d in dias)}
    if not con_vac:
        return {}
    fest = festivos.conjunto(db, periodo.desde, periodo.hasta)
    sugeridos = vac.promedios_sugeridos(db, list(con_vac), periodo)
    manuales = vac.promedios_manuales(db, periodo.id)
    antes = vac.habiles_disfrutados(db, con_vac, antes_de=periodo.desde)
    return {eid: {"festivos": fest, "sugerido": sugeridos.get(eid, (Decimal("0"), Decimal("0")))[0],
                  "meses": sugeridos.get(eid, (Decimal("0"), Decimal("0")))[1], "manual": manuales.get(eid),
                  "antes": antes.get(eid, 0)} for eid in con_vac}


def _otras_nominas(db: Session, periodo: LiqPeriodo, por_empleado: dict[int, list[LiqDia]]) -> dict[int, tuple[list[str], str | None]]:
    """Quienes también están en otra nómina de fechas que se cruzan: {empleado: (alertas, nómina que aplica sus
    préstamos, embargos, cuotas y auxilios o None si es esta)}. Los aplica la nómina creada primero."""
    from app.apps.liquidador.services.calculo import hermanas

    otras = hermanas(db, periodo)
    if not otras or not por_empleado:
        return {}
    por_id = {h.id: h for h in otras}
    fechas_otras: dict[tuple[int, int], set[date]] = defaultdict(set)
    for pid, eid, fecha in db.execute(select(LiqDia.periodo_id, LiqDia.empleado_id, LiqDia.fecha)
                                      .where(LiqDia.periodo_id.in_(list(por_id)), LiqDia.empleado_id.in_(list(por_empleado)))):
        fechas_otras[(eid, pid)].add(fecha)
    salida: dict[int, tuple[list[str], str | None]] = {}
    for eid, dias in por_empleado.items():
        ids = sorted(pid for (e, pid) in fechas_otras if e == eid)
        if not ids:
            continue
        propias = {d.fecha for d in dias}
        alertas = []
        for pid in ids:
            h = por_id[pid]
            repetidas = sorted(propias & fechas_otras[(eid, pid)])
            texto = f"También está en la nómina «{h.nombre}» ({h.etiqueta})"
            if repetidas:
                texto += (f": {len(repetidas)} día(s) están en las dos ({', '.join(f.strftime('%d/%m') for f in repetidas[:6])}"
                          f"{'…' if len(repetidas) > 6 else ''}) y se pagarían dos veces")
            alertas.append(texto)
        primera = min([*ids, periodo.id])
        duenia = None if primera == periodo.id else por_id[primera]
        if duenia is not None:
            alertas.append(f"Sus préstamos, embargos, cuotas y auxilios no prestacionales se aplican en la nómina «{duenia.nombre}» ({duenia.etiqueta})")
        salida[eid] = (alertas, duenia.nombre if duenia else None)
    return salida
