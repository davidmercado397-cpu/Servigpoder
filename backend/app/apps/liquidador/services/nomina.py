"""Nómina de cada empleado a partir de los días y las horas contadas del periodo.

- Salario básico: salario mensual ÷ 30 por cada día trabajado, de descanso (Z) o libre (L). Las ausencias
  y las demás novedades no remuneradas no se pagan aquí; las licencias remuneradas sí (ver abajo).
- Base de 30 días: el día 31 no suma salario; si se paga el último día de febrero, se completan los 30.
- Incapacidad: se paga al 100 %. Los 2 primeros días de cada incapacidad los paga la empresa y del 3.º en
  adelante la EPS (que reconoce el 66,67 %); la división es informativa.
- Recargos y extras: horas del concepto × valor de la hora (salario ÷ horas del mes) × su %. Los recargos
  llevan solo el adicional (la hora ya está en el salario); las extras, la hora completa.
- Vacaciones (códigos marcados "Es vacaciones"): (salario + promedio variable) ÷ 30 por cada día, separando
  hábiles y no hábiles; ver services/vacaciones.py.
- Licencias remuneradas (códigos marcados «Remunerado» en Turnos: maternidad, paternidad, luto, licencia remunerada…):
  salario ÷ 30 por cada día (base 30). Hacen base de salud y pensión; no pagan auxilio de transporte y, como tiempo no
  laborado, descuentan los auxilios no prestacionales.
- Auxilio de transporte: ÷ 30 por día trabajado o de descanso, si el salario no supera 2 mínimos.
- Auxilios no prestacionales: valor mensual menos 1/30 por cada día de tiempo no laborado (ausencias, incapacidades,
  vacaciones y demás novedades).
- Novedades manuales: lo que se pagó de menos en nóminas anteriores (y las horas extras o recargos pendientes, valorados
  con la tarifa de la fecha en que se causaron) se paga; lo que se pagó de más se descuenta. Las de horas y el menor
  valor pagado hacen base de salud y pensión; el mayor valor pagado es solo una deducción.
- Auxilio no prestacional variable (novedad de una sola nómina, p. ej. rodamiento intermunicipal): suma a los
  auxilios no prestacionales por su valor, sin descuento por tiempo no laborado.
- Nómina por horas: el salario son las horas ordinarias trabajadas × (salario ÷ horas del mes); recargos y extras como
  siempre. Descansos (Z), libres (L) y festivos no trabajados no pagan salario ni auxilio de transporte. El auxilio va
  por día con horas trabajadas, una sola vez por día: si ese día también trabajó en otra nómina que lo paga (una normal o
  una por horas creada antes), aquí no. Descuenta salud y/o pensión según se marque en la nómina.
- Código 180 (incapacidad de más de 180 días): no se paga (lo paga el fondo de pensiones o nadie) y cuenta como tiempo no
  laborado; SERA provisiona la seguridad social de esos días (salud y pensión del empleado y del empleador sobre el
  salario de esos días; la salud del empleador no va si está exonerado, art. 114-1 E.T.). No se descuenta del neto.
- Salud y pensión: % del devengado sin auxilio de transporte. Quien está marcado como pensionado en la ficha no descuenta
  pensión (ni en la nómina normal ni en la por horas, aunque esta descuente pensión). Después, embargos, novedades que descuentan, préstamos
  y cuotas.
Cada día se paga con la tarifa vigente ese día (salario mínimo, horas del mes y %).
"""

import calendar
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.apps.liquidador.dominio.tipos import HourConcept
from app.apps.liquidador.models import (
    AUXILIOS_VARIABLES, CUOTA, EMBARGO, MENSUAL, NOVEDADES_DEDUCCION, NOVEDADES_HORAS, PRESTAMO, LiqAuxilio, LiqDescuento, LiqDia, LiqEmpleado,
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
    """Días que suma una fecha pagada en base 30: el 31 no suma (salvo en vacaciones); el último de febrero completa el mes."""
    if fecha.day == 31:
        return 0
    ultimo = calendar.monthrange(fecha.year, fecha.month)[1]
    if fecha.month == 2 and fecha.day == ultimo:
        return 1 + 30 - ultimo
    return 1


CODIGO_180 = "180"  # incapacidad de más de 180 días: no se paga; se provisiona la seguridad social

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
    licencias: dict = field(default_factory=dict)  # código → [días base 30, valor, nombre]
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


def provision_codigo_180(empleado: LiqEmpleado, dias: list[LiqDia], tarifas: Tarifas) -> dict | None:
    """Seguridad social que SERA provisiona por los días con código 180: base = salario ÷ 30 por día (base 30) con la
    tarifa de cada día; salud y pensión del empleado (% de la tarifa) y del empleador (pensión 12 %, salud 8,5 % salvo
    exoneración por ganar menos de 10 salarios mínimos). El trabajador recibe 0; nada se descuenta de su neto."""
    from app.apps.liquidador.services.costeo_nomina import PARAMETROS, TOPE_EXONERACION

    del_180 = [d for d in dias if (getattr(d, "codigo", "") or "").strip().upper() == CODIGO_180]
    if not del_180:
        return None
    base = Decimal("0")
    dias_base, pct_salud, pct_pension, exonerado = 0, Decimal("0"), Decimal("0"), True
    for d in del_180:
        t = tarifas.en(d.fecha)
        salario = empleado.salario or t.smlmv
        b = dias_base_30(d.fecha)
        dias_base += b
        base += salario / 30 * b
        pct_salud, pct_pension = t.salud_pct, t.pension_pct
        exonerado = salario < TOPE_EXONERACION * t.smlmv
    base = _pesos(base)
    salud_empleador_pct = Decimal("0") if exonerado else Decimal(str(PARAMETROS["salud"][0]))
    pension_empleador_pct = Decimal(str(PARAMETROS["pension"][0]))
    if empleado.pensionado:  # el pensionado no cotiza pensión
        pct_pension = pension_empleador_pct = Decimal("0")
    partes = {
        "salud_empleado": _pesos(base * pct_salud / 100), "pension_empleado": _pesos(base * pct_pension / 100),
        "salud_empleador": _pesos(base * salud_empleador_pct / 100), "pension_empleador": _pesos(base * pension_empleador_pct / 100),
    }
    return {"dias": len(del_180), "dias_base": dias_base, "base": float(base), "exonerado": exonerado,
            **{k: float(v) for k, v in partes.items()}, "total": float(sum(partes.values(), Decimal("0"))),
            "porcentajes": {"salud_empleado": float(pct_salud), "pension_empleado": float(pct_pension),
                            "salud_empleador": float(salud_empleador_pct), "pension_empleador": float(pension_empleador_pct)}}


def liquidar_empleado(empleado: LiqEmpleado, dias: list[LiqDia], periodo: LiqPeriodo, tarifas: Tarifas,
                      descuentos: list[LiqDescuento], ya_descontado: dict[int, Decimal], auxilios: list | None = None,
                      vacaciones: dict | None = None, novedades: list[LiqNovedad] | None = None,
                      aux_en_otra: dict[date, str] | None = None, mes_previo: dict | None = None) -> dict:
    """`vacaciones` (solo si tiene días de vacaciones): festivos, promedio sugerido y meses, promedio manual y
    días hábiles ya disfrutados antes del periodo. `mes_previo`: lo salarial, lo no salarial y el exceso de las nóminas
    del mismo mes liquidadas antes (el tope del 40 % es sobre el mes)."""
    a = Acumulado()
    por_horas = getattr(periodo, "tipo_nomina", "normal") == "horas"
    aux_en_otra = aux_en_otra or {}
    horas_pagadas, dias_trabajados, aux_otra = Decimal("0"), 0, []
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
        if por_horas and d.clase in PAGAN_SALARIO:
            # Solo las horas trabajadas (las ordinarias; recargos y extras se suman abajo). Z y L no pagan
            h_ord = Decimal(str((d.horas or {}).get(HourConcept.ORDINARY_DAY.value, 0) or 0))
            trabajo = h_ord > 0 or any(v for c, v in (d.horas or {}).items() if c != HourConcept.ORDINARY_DAY.value)
            horas_pagadas += h_ord
            a.basico += h_ord * valor_hora
            if trabajo:
                dias_trabajados += 1
                if d.fecha in aux_en_otra:
                    aux_otra.append(d.fecha)
                elif salario <= 2 * t.smlmv:
                    a.dias_auxilio += 1
                    a.auxilio += t.auxilio_transporte / 30
        elif d.clase in PAGAN_SALARIO:
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
            base = base or 1  # el 31 sí se paga en vacaciones
            valor_vac = (salario + promedio) / 30 * base
            a.vac_dias += 1
            if vac.es_habil(d.fecha, empleado.dias_habiles, fest):
                a.vac_habiles += base
                a.vac_habiles_reales += 1
                a.vac_valor_habiles += valor_vac
            else:
                a.vac_no_habiles += base
                a.vac_valor_no_habiles += valor_vac
        elif getattr(getattr(d, "turno", None), "remunerado", False):
            # Licencia remunerada (maternidad, paternidad, luto…): se paga el día con el salario
            t_lic = a.licencias.setdefault(d.turno.codigo, [0, Decimal("0"), d.turno.nombre])
            t_lic[0] += base
            t_lic[1] += valor_dia * base
        else:
            a.dias_sin_pago += 1
        if not por_horas and d.clase in PAGAN_AUXILIO and salario <= 2 * t.smlmv:
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
    # Auxilios variables de esta nómina (novedades): por su valor, sin descuento por tiempo no laborado
    for x in sorted((x for x in novedades or [] if x.tipo in AUXILIOS_VARIABLES), key=lambda x: x.id):
        aux_aplicados.append({"id": f"nov-{x.id}", "descripcion": x.descripcion, "valor": float(_pesos(x.valor or Decimal("0"))),
                              "calculo": ("auxilio intermunicipal" if x.tipo == "auxilio_intermunicipal" else "auxilio variable") + " de esta nómina" + (f" · origen: {x.nomina_origen}" if x.nomina_origen else "")})
    no_prestacional = sum((Decimal(str(x["valor"])) for x in aux_aplicados), Decimal("0"))

    # Novedades manuales de esta nómina
    nov_aplicadas, nov_salarial, nov_no_salarial, nov_deducciones = [], Decimal("0"), Decimal("0"), []
    for x in sorted((x for x in novedades or [] if x.tipo not in AUXILIOS_VARIABLES), key=lambda x: x.id):
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

    licencias = [{"codigo": c, "nombre": n, "dias": dd, "valor": float(_pesos(v))} for c, (dd, v, n) in sorted(a.licencias.items())]
    licencias_valor = sum((Decimal(str(x["valor"])) for x in licencias), Decimal("0"))
    salarial = basico + incapacidad + recargos + extras + vacaciones_valor + licencias_valor + nov_salarial
    devengado = salarial + no_prestacional + nov_no_salarial + auxilio
    # Lo no salarial que pase del 40 % de la remuneración total del mes sí entra en la base de salud y pensión. Con
    # nóminas anteriores en el mes (la 1.ª quincena) se suman a esta y aquí entra lo que falte del exceso del mes.
    no_salarial = no_prestacional + nov_no_salarial
    previo = mes_previo or {}
    sal_mes = salarial + previo.get("salarial", Decimal("0"))
    no_sal_mes = no_salarial + previo.get("no_salarial", Decimal("0"))
    exceso_mes = _pesos(max(no_sal_mes - TOPE_NO_SALARIAL * (sal_mes + no_sal_mes), Decimal("0")))
    exceso = max(exceso_mes - previo.get("exceso", Decimal("0")), Decimal("0"))
    ibc = salarial + exceso
    if previo and (no_sal_mes or exceso_mes):
        con = ", ".join(f"«{x}»" for x in previo["nominas"])
        if previo.get("supuesta"):
            sup = previo["supuesta"]
            texto = (f"la 1.ª quincena no está en el sistema: se supone con el salario de la ficha, {sup['dias']} día(s) = "
                     f"{sup['salarial']:,.0f}" + (f" y {sup['no_salarial']:,.0f} de auxilios" if sup["no_salarial"] else ""))
            con = f"{con}; {texto}" if con else texto
        alertas.append(f"Tope del 40 % sobre el mes ({con}): no salariales "
                       f"{no_sal_mes:,.0f} de una remuneración de {sal_mes + no_sal_mes:,.0f} (tope "
                       f"{_pesos(TOPE_NO_SALARIAL * (sal_mes + no_sal_mes)):,.0f}); exceso del mes {exceso_mes:,.0f}"
                       + (f", {previo['exceso']:,.0f} ya en la base de esas nóminas" if previo["exceso"] else "")
                       + f": {exceso:,.0f} entran en la base de salud y pensión de esta")
    elif exceso:
        alertas.append(f"Los pagos no salariales superan el 40 % de la remuneración: {exceso:,.0f} entran en la base de salud y pensión")

    t_cierre = tarifas.en(periodo.hasta)
    if aux_otra:
        nominas_otra = sorted({aux_en_otra[f] for f in aux_otra})
        alertas.append(f"{len(aux_otra)} día(s) también los trabajó en {', '.join(f'«{n}»' for n in nominas_otra)}: "
                       f"el auxilio de transporte de esos días se paga allá")
    provision_180 = provision_codigo_180(empleado, dias, tarifas)
    if provision_180:
        alertas.append(f"{provision_180['dias']} día(s) con código 180 (incapacidad de más de 180 días): no se pagan en nómina; "
                       f"SERA provisiona {provision_180['total']:,.0f} de seguridad social")
    salud_pct = t_cierre.salud_pct if not por_horas or getattr(periodo, "descuenta_salud", True) else Decimal("0")
    pension_pct = t_cierre.pension_pct if not por_horas or getattr(periodo, "descuenta_pension", True) else Decimal("0")
    pensionado = bool(getattr(empleado, "pensionado", False))
    if pensionado:  # marcado como pensionado en la ficha: nunca descuenta pensión (en ninguna nómina)
        pension_pct = Decimal("0")
    salud = _pesos(ibc * salud_pct / 100)
    pension = _pesos(ibc * pension_pct / 100)
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
        "exceso_no_salarial": float(exceso), "salarial": float(salarial), "no_salarial": float(no_salarial), "alertas": alertas,
        "primera_supuesta": {k: float(v) if isinstance(v, Decimal) else v for k, v in previo["supuesta"].items()} if previo.get("supuesta") else None,
        "vacaciones": detalle_vac, "vacaciones_valor": float(vacaciones_valor),
        "licencias": licencias, "licencias_valor": float(licencias_valor), "dias_licencia": sum(x["dias"] for x in licencias),
        "horas": {c: float(h) for c, h in a.horas.items() if h},
        "valores": {c: float(v) for c, v in valores.items()},
        "recargos": float(recargos), "extras": float(extras),
        "devengado": float(devengado), "ibc": float(ibc),
        "salud": float(salud), "salud_pct": float(salud_pct),
        "pension": float(pension), "pension_pct": float(pension_pct), "pensionado": pensionado,
        "por_horas": por_horas, "horas_pagadas": float(horas_pagadas), "dias_trabajados": dias_trabajados,
        "dias_auxilio_otra_nomina": len(aux_otra),
        "descuentos": aplicados, "prestamos": float(prestamos), "embargos": float(embargos), "cuotas": float(cuotas),
        "novedades": nov_aplicadas, "novedades_devengo": float(nov_devengo), "novedades_deduccion": float(nov_deduccion),
        "seguridad_social_180": provision_180, "provision_ss_180": provision_180["total"] if provision_180 else 0.0,
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
    aux_otra = _auxilio_en_otras(db, periodo, por_empleado) if getattr(periodo, "tipo_nomina", "normal") == "horas" else {}
    mes_previo = _mes_previo(db, periodo, list(resultados))
    if periodo.quincena == 2:  # sin la 1.ª quincena en el sistema, se supone con el salario de la ficha
        for empleado_id in resultados:
            previo = mes_previo.get(empleado_id)
            if previo and previo["con_primera"]:
                continue
            sup = _primera_supuesta(empleados[empleado_id], periodo, tarifas, auxilios[empleado_id])
            if sup:
                x = mes_previo.setdefault(empleado_id, {"salarial": Decimal("0"), "no_salarial": Decimal("0"), "exceso": Decimal("0"),
                                                        "nominas": [], "con_primera": True})
                x["supuesta"] = sup
                for c in ("salarial", "no_salarial", "exceso"):
                    x[c] += sup[c]
    for empleado_id, r in resultados.items():
        avisos, aplica = [], True
        if empleado_id in otras:
            avisos, duenia = otras[empleado_id]
            aplica = duenia is None
        n = liquidar_empleado(empleados[empleado_id], por_empleado[empleado_id], periodo, tarifas,
                              descuentos[empleado_id] if aplica else [], ya, auxilios[empleado_id] if aplica else [],
                              contexto_vac.get(empleado_id), novedades[empleado_id], aux_otra.get(empleado_id),
                              mes_previo.get(empleado_id))
        e = empleados[empleado_id]
        if e.estado == "retirado" and e.fecha_retiro and any(d.fecha > e.fecha_retiro for d in por_empleado[empleado_id]):
            avisos = [f"Está retirado desde el {e.fecha_retiro:%d/%m/%Y} y tiene turnos después de esa fecha", *avisos]
        n["alertas"] = avisos + n["alertas"]
        n["otras_nominas"] = any("nómina «" in a for a in avisos)
        r.nomina, r.devengado, r.neto = n, Decimal(str(n["devengado"])), Decimal(str(n["neto"]))


def _orden_en_mes(p: LiqPeriodo) -> tuple[int, int]:
    """Orden de las nóminas de un mes: la 1.ª quincena antes que la 2.ª y la mensual; entre iguales, la creada primero."""
    return (1 if p.quincena == 1 else 2, p.id)


def _mes_previo(db: Session, periodo: LiqPeriodo, ids: list[int]) -> dict[int, dict]:
    """{empleado: salarial, no salarial y exceso del 40 % de las nóminas del mismo mes anteriores a esta}."""
    previas = {p.id: p for p in db.scalars(select(LiqPeriodo).where(LiqPeriodo.anio == periodo.anio, LiqPeriodo.mes == periodo.mes,
                                                                    LiqPeriodo.id != periodo.id))
               if _orden_en_mes(p) < _orden_en_mes(periodo)}
    if not previas or not ids:
        return {}
    salida: dict[int, dict] = {}
    for r in db.scalars(select(LiqResultado).where(LiqResultado.periodo_id.in_(list(previas)), LiqResultado.empleado_id.in_(ids))):
        n = r.nomina or {}
        if "devengado" not in n:
            continue
        d = lambda c: Decimal(str(n.get(c) or 0))  # noqa: E731
        exceso = d("exceso_no_salarial")
        # Las nóminas calculadas antes de guardar lo salarial y lo no salarial: se deducen del IBC y del devengado
        salarial = d("salarial") if "salarial" in n else d("ibc") - exceso
        no_salarial = d("no_salarial") if "no_salarial" in n else d("devengado") - d("auxilio") - salarial
        x = salida.setdefault(r.empleado_id, {"salarial": Decimal("0"), "no_salarial": Decimal("0"), "exceso": Decimal("0"), "nominas": [],
                                              "con_primera": False})
        x["salarial"] += salarial
        x["no_salarial"] += no_salarial
        x["exceso"] += exceso
        p = previas[r.periodo_id]
        sup = n.get("primera_supuesta")
        if sup:  # otra nómina de la 2.ª quincena ya supuso la 1.ª: se suma igual, una sola vez
            for c in ("salarial", "no_salarial", "exceso"):
                x[c] += Decimal(str(sup[c]))
        x["con_primera"] = x["con_primera"] or p.quincena == 1 or bool(sup)
        x["nominas"].append(f"{'1.ª quincena' if p.quincena == 1 else '2.ª quincena' if p.quincena == 2 else 'mes'} {p.nombre}")
    return salida


def _primera_supuesta(empleado: LiqEmpleado, periodo: LiqPeriodo, tarifas: Tarifas, auxilios: list) -> dict | None:
    """1.ª quincena que no está en el sistema, para el tope del 40 % del mes: el salario de la ficha por los días desde
    el 1 (o desde la fecha de ingreso) al 15 y los auxilios no prestacionales de esa quincena; el exceso, el de ella sola."""
    inicio, fin = date(periodo.anio, periodo.mes, 1), date(periodo.anio, periodo.mes, 15)
    desde = max(inicio, empleado.fecha_ingreso or inicio)
    if desde > fin:
        return None
    dias = (fin - desde).days + 1
    salario = empleado.salario or tarifas.en(fin).smlmv
    salarial = _pesos(salario / 30 * dias)
    q1 = SimpleNamespace(desde=inicio, hasta=fin, quincena=1)
    no_salarial = sum((max(x.valor_mensual * _fraccion_mensual(q1, x.quincena or AMBAS) - x.valor_mensual / 30 * (15 - dias), Decimal("0"))
                       for x in auxilios or [] if _vigente(x, q1)), Decimal("0"))
    no_salarial = _pesos(no_salarial)
    exceso = _pesos(max(no_salarial - TOPE_NO_SALARIAL * (salarial + no_salarial), Decimal("0")))
    return {"dias": dias, "salarial": salarial, "no_salarial": no_salarial, "exceso": exceso}


def _auxilio_en_otras(db: Session, periodo: LiqPeriodo, por_empleado: dict[int, list[LiqDia]]) -> dict[int, dict[date, str]]:
    """En una nómina por horas: {empleado: {fecha: nómina}} de los días que esa persona también trabajó en otra nómina que
    paga ese auxilio de transporte: una normal (siempre lo paga) o una por horas creada antes que esta."""
    from app.apps.liquidador.services.calculo import hermanas

    otras = [h for h in hermanas(db, periodo) if h.tipo_nomina != "horas" or h.id < periodo.id]
    if not otras or not por_empleado:
        return {}
    por_id = {h.id: h for h in otras}
    salida: dict[int, dict[date, str]] = defaultdict(dict)
    for pid, eid, fecha, clase, horas in db.execute(
            select(LiqDia.periodo_id, LiqDia.empleado_id, LiqDia.fecha, LiqDia.clase, LiqDia.horas)
            .where(LiqDia.periodo_id.in_(list(por_id)), LiqDia.empleado_id.in_(list(por_empleado)))):
        h = por_id[pid]
        paga = (clase in PAGAN_AUXILIO) if h.tipo_nomina != "horas" else any(v for v in (horas or {}).values())
        if paga:
            salida[eid].setdefault(fecha, h.nombre)
    return salida


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
                          f"{'…' if len(repetidas) > 6 else ''})")
                texto += (" (por horas: cada nómina paga sus horas y el auxilio de transporte va una sola vez)"
                          if "horas" in (periodo.tipo_nomina, h.tipo_nomina) else " y se pagarían dos veces")
            alertas.append(texto)
        primera = min([*ids, periodo.id])
        duenia = None if primera == periodo.id else por_id[primera]
        if duenia is not None:
            alertas.append(f"Sus préstamos, embargos, cuotas y auxilios no prestacionales se aplican en la nómina «{duenia.nombre}» ({duenia.etiqueta})")
        salida[eid] = (alertas, duenia.nombre if duenia else None)
    return salida
