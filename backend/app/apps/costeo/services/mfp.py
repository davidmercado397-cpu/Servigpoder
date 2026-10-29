"""Cálculos de la MFP: estado de cada ítem (pactado, ejecutado, pendiente, causado), bolsa de horas por año de
contrato, reembolso por terminación anticipada y alertas. Funciones puras sobre los modelos ya cargados.

Reembolso (buena práctica aprobada): lo entregado por adelantado se amortiza en línea recta durante el contrato.
Si el cliente termina antes, devuelve lo ejecutado × meses que faltaban ÷ duración, solo en los ítems
reembolsables (reinversión, equipos, capacitación, nota crédito de una vez). Los mensuales y la bolsa de horas no
se reembolsan, y lo pactado que no se ejecutó se cancela. Los meses que faltan nunca son negativos.
"""

import calendar
import math
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.apps.costeo.models import HORAS, PESOS_MES, CstMfp, CstMfpItem

DIAS_POR_VENCER = 60
TOLERANCIA = 1.0  # pesos u horas


def sumar_meses(d: date, meses: int) -> date:
    """Como FECHA.MES de Excel: el mismo día, n meses después (o el último día de ese mes)."""
    m = d.month - 1 + meses
    anio, mes = d.year + m // 12, m % 12 + 1
    return date(anio, mes, min(d.day, calendar.monthrange(anio, mes)[1]))


def meses_entre(desde: date, hasta: date) -> float:
    """Meses (con fracción) de desde a hasta; negativo si hasta es anterior."""
    if hasta < desde:
        return -meses_entre(hasta, desde)
    completos = (hasta.year - desde.year) * 12 + hasta.month - desde.month
    if hasta.day < desde.day:
        completos -= 1
    base = sumar_meses(desde, completos)
    siguiente = sumar_meses(desde, completos + 1)
    return completos + (hasta - base).days / max(1, (siguiente - base).days)


def fin_contrato(m: CstMfp) -> date | None:
    if not m.fecha_inicio or not m.duracion_meses:
        return None
    return sumar_meses(m.fecha_inicio, m.duracion_meses)


def meses_faltantes(m: CstMfp, d: date) -> float:
    """Meses del contrato que faltan a la fecha, entre 0 y la duración. Se cuentan desde el inicio (duración −
    transcurridos) y no desde d hasta el fin: si d cae en un día recortado (29-31 → fin de mes), contar hacia
    adelante desde d da una fracción de más y transcurridos + faltantes no sumaría la duración."""
    duracion = float(m.duracion_meses or 0)
    return max(0.0, min(duracion, duracion - meses_entre(m.fecha_inicio, d)))


def anio_contrato(m: CstMfp, d: date) -> int:
    """Año del contrato (1, 2, 3…) en que cae la fecha."""
    if not m.fecha_inicio or d < m.fecha_inicio:
        return 1
    return int(meses_entre(m.fecha_inicio, d) // 12) + 1


def anios_contrato(m: CstMfp) -> int:
    return max(1, math.ceil((m.duracion_meses or 12) / 12))


def rango_anio(m: CstMfp, n: int) -> tuple[date | None, date | None]:
    if not m.fecha_inicio:
        return None, None
    desde = sumar_meses(m.fecha_inicio, 12 * (n - 1))
    hasta = sumar_meses(m.fecha_inicio, 12 * n) - timedelta(days=1)
    fin = fin_contrato(m)
    return desde, (min(hasta, fin - timedelta(days=1)) if fin else hasta)


@dataclass
class EstadoItem:
    id: int
    tipo: str
    tipo_codigo: str
    unidad: str
    descripcion: str
    reembolsable: bool
    cuenta_en_mfp: bool
    pactado: float  # como se pactó: total, valor mensual u horas por año
    pactado_total: float  # en todo el contrato
    ejecutado: float
    pendiente: float  # pesos: pactado − ejecutado; horas: saldo del año en curso
    causado: float | None = None  # pesos_mes: lo que corresponde hasta la fecha
    reembolso: float = 0.0
    excede: bool = False
    anios: list[dict] = field(default_factory=list)  # horas: [{anio, desde, hasta, pactado, usado, saldo, vencido}]

    def a_dict(self) -> dict:
        return self.__dict__.copy()


def estado_item(m: CstMfp, it: CstMfpItem, hoy: date, fecha_reembolso: date | None = None) -> EstadoItem:
    tipo = it.tipo
    pactado = float(it.pactado or 0)
    ejecutado = sum(float(x.valor) for x in it.movimientos)
    duracion = m.duracion_meses or 0
    e = EstadoItem(it.id, tipo.nombre, tipo.codigo, tipo.unidad, it.descripcion, tipo.reembolsable, tipo.cuenta_en_mfp,
                   pactado, pactado, ejecutado, pactado - ejecutado)
    if tipo.unidad == PESOS_MES:
        e.pactado_total = pactado * duracion
        e.pendiente = e.pactado_total - ejecutado
        if m.fecha_inicio and duracion:
            transcurridos = 0 if hoy < m.fecha_inicio else min(duracion, int(meses_entre(m.fecha_inicio, hoy)) + 1)
            e.causado = pactado * transcurridos
        e.excede = ejecutado > e.pactado_total + TOLERANCIA
    elif tipo.unidad == HORAS:
        n = anios_contrato(m)
        e.pactado_total = pactado * n
        actual = anio_contrato(m, hoy)
        for i in range(1, n + 1):
            desde, hasta = rango_anio(m, i)
            usado = sum(float(x.valor) for x in it.movimientos if anio_contrato(m, x.fecha) == i)
            e.anios.append({"anio": i, "desde": desde.isoformat() if desde else None, "hasta": hasta.isoformat() if hasta else None,
                            "pactado": pactado, "usado": usado, "saldo": pactado - usado, "vencido": i < actual,
                            "actual": i == actual})
        e.pendiente = next((a["saldo"] for a in e.anios if a["actual"]), 0.0)
        e.excede = any(a["usado"] > a["pactado"] + TOLERANCIA for a in e.anios)
    else:
        e.excede = ejecutado > pactado + TOLERANCIA

    fin = fin_contrato(m)
    if tipo.reembolsable and tipo.unidad != HORAS and fin and duracion:
        ref = fecha_reembolso or (m.fecha_terminacion if m.terminada and m.fecha_terminacion else hoy)
        e.reembolso = round(ejecutado * meses_faltantes(m, ref) / duracion, 2)
    return e


def tope_movimiento(m: CstMfp, it: CstMfpItem, valor: float, fecha: date, excluir_id: int | None = None) -> str | None:
    """Mensaje si el movimiento supera lo pactado (o la bolsa del año, en horas); None si cabe."""
    tipo = it.tipo
    otros = [x for x in it.movimientos if x.id != excluir_id]
    pactado = float(it.pactado or 0)
    if tipo.unidad == HORAS:
        n = anio_contrato(m, fecha)
        usado = sum(float(x.valor) for x in otros if anio_contrato(m, x.fecha) == n)
        if usado + valor > pactado + 1e-6:
            return (f"La bolsa del año {n} del contrato tiene {pactado - usado:g} h disponibles de {pactado:g} h; "
                    f"la solicitud es de {valor:g} h")
        return None
    total = pactado * (m.duracion_meses or 0) if tipo.unidad == PESOS_MES else pactado
    usado = sum(float(x.valor) for x in otros)
    if usado + valor > total + TOLERANCIA:
        return f"Lo pactado es {pesos(total)}, ya se ejecutó {pesos(usado)} y este movimiento es de {pesos(valor)}: supera el tope en {pesos(usado + valor - total)}"
    return None


def pesos(v: float) -> str:
    return ("-" if v < 0 else "") + "$" + f"{abs(v):,.0f}".replace(",", ".")


def resumen(m: CstMfp, hoy: date, fecha_reembolso: date | None = None) -> dict:
    items = [estado_item(m, it, hoy, fecha_reembolso) for it in m.items]
    fin = fin_contrato(m)
    facturacion = float(m.valor_mensual or 0) * (m.duracion_meses or 0)
    en_pesos = [i for i in items if i.unidad != HORAS and i.cuenta_en_mfp]
    pactado = sum(i.pactado_total for i in en_pesos)
    ejecutado = sum(i.ejecutado for i in en_pesos)
    pct_mfp = pactado / facturacion if facturacion else None
    pct_comercial = float(m.pct_comercial) if m.pct_comercial is not None else None
    if m.terminada:
        estado = "terminada"
    elif fin and fin <= hoy:
        estado = "vencida"
    else:
        estado = "vigente"
    meses_pendientes = meses_faltantes(m, m.fecha_terminacion if m.terminada and m.fecha_terminacion else hoy) if fin else None
    pendiente = sum(max(0.0, i.pendiente) for i in en_pesos)

    alertas: list[dict] = []
    for i in items:
        if i.excede:
            alertas.append({"tipo": "excede", "severidad": "alta", "mensaje": f"{i.tipo}: se ejecutó más de lo pactado"})
    if pct_mfp is not None and pct_comercial is not None and pct_mfp > pct_comercial + 0.0005:
        alertas.append({"tipo": "supera_comercial", "severidad": "media",
                        "mensaje": f"La MFP pactada ({pct_mfp:.2%}) supera el % de la MFP física ({pct_comercial:.2%})"})
    if estado == "vigente" and fin and (fin - hoy).days <= DIAS_POR_VENCER and pendiente > TOLERANCIA:
        alertas.append({"tipo": "por_vencer", "severidad": "media",
                        "mensaje": f"El contrato vence el {fin:%d/%m/%Y} y quedan {pesos(pendiente)} por ejecutar"})
    for i in items:
        if i.unidad == HORAS and estado == "vigente" and i.pactado and i.pendiente <= 0:
            alertas.append({"tipo": "bolsa_agotada", "severidad": "baja", "mensaje": f"{i.tipo}: la bolsa del año en curso está agotada"})
    if not m.fecha_inicio or not m.duracion_meses or not m.valor_mensual:
        alertas.append({"tipo": "datos_incompletos", "severidad": "baja",
                        "mensaje": "Faltan datos del contrato (fecha de inicio, duración o valor mensual)"})

    return {
        "id": m.id, "numero": m.numero, "contrato": m.contrato,
        "cliente": {"id": m.cliente.id, "nit": m.cliente.nit, "nombre": m.cliente.nombre} if m.cliente else None,
        "fecha_inicio": m.fecha_inicio.isoformat() if m.fecha_inicio else None, "fecha_fin": fin.isoformat() if fin else None,
        "duracion_meses": m.duracion_meses, "valor_mensual": float(m.valor_mensual or 0), "facturacion_total": facturacion,
        "pct_comercial": pct_comercial, "pct_mfp": pct_mfp,
        "diferencia_pct": (pct_mfp - pct_comercial) if pct_mfp is not None and pct_comercial is not None else None,
        "pactado": pactado, "ejecutado": ejecutado, "pendiente": pendiente,
        "pct_ejecucion": ejecutado / pactado if pactado else None,
        "reembolso": round(sum(i.reembolso for i in items), 2), "meses_pendientes": meses_pendientes,
        "estado": estado, "terminada": m.terminada,
        "fecha_terminacion": m.fecha_terminacion.isoformat() if m.fecha_terminacion else None,
        "notas": m.notas, "costeo_id": m.costeo_id, "alertas": alertas, "items": [i.a_dict() for i in items],
    }
