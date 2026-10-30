"""Motor del costeo: tarifa, MFP, costo laboral, dotación, otros costos, gastos, impuestos y margen.

Reproduce la hoja de costeo de Servigpoder (COSTEO_PALMASECA) con las correcciones acordadas:
- la dotación adicional del puesto sí entra al costo (en el Excel la celda de prorrateo estaba vacía);
- cada elemento de dotación es mensual por vida útil o anual por entregas, sin dividir dos veces;
- los auxilios no salariales (productividad, rodamiento, auxilio del motorizado) son costo y afectan el margen;
- el gasto administrativo es una provisión mensual: el % sobre la tarifa mensual;
- la reserva de representación es el % mensual sobre la tarifa (no un solo mes repartido en el contrato);
- la renta nunca es negativa.
Todo valor sale de los parámetros (editables) o de las entradas del costeo: nada queda fijo en el código.
Función pura: recibe datos y parámetros y devuelve el resultado.
"""

from dataclasses import dataclass

# clave: (valor por defecto, nombre, grupo, ayuda)
PARAMETROS: dict[str, tuple[float, str, str, str]] = {
    "salario_minimo": (1750905, "Salario mínimo mensual", "Laborales", "Salario por defecto de cada tipo de personal"),
    "auxilio_transporte": (249095, "Auxilio de transporte mensual", "Laborales", ""),
    "ley_2101": (60000, "Aplicación aporte Ley 2101 (por hombre)", "Laborales", ""),
    "pct_salud_empleador": (0, "Salud a cargo del empleador (%)", "Laborales", "0 si aplica la exoneración"),
    "pct_pension": (12, "Pensión a cargo del empleador (%)", "Laborales", "Sobre salario + horas extras"),
    "pct_caja": (4, "Caja de compensación (%)", "Laborales", "Sobre salario + horas extras"),
    "pct_arl": (4.35, "ARL (%)", "Laborales", "Según la clase de riesgo"),
    "pct_primas": (8.33, "Primas (%)", "Laborales", "Sobre salario + horas extras + auxilio de transporte"),
    "pct_cesantias": (8.33, "Cesantías (%)", "Laborales", "Sobre salario + horas extras + auxilio de transporte"),
    "pct_intereses_cesantias": (12, "Intereses de cesantías (% de las cesantías)", "Laborales", ""),
    "pct_vacaciones": (4.33, "Vacaciones (%)", "Laborales", "Sobre salario + horas extras"),
    "pct_salud_trabajador": (4, "Salud del trabajador (%)", "Laborales", "Solo para el salario neto informativo"),
    "pct_pension_trabajador": (4, "Pensión del trabajador (%)", "Laborales", "Solo para el salario neto informativo"),
    "horas_turno_bolsa": (12, "Horas del turno para costear la hora adicional", "Laborales",
                          "Valor hora = costo mensual por hombre ÷ 30 ÷ este valor"),
    "tasa_cupo_inversion": (1, "Tasa mensual del cupo de inversión (%)", "MFP",
                            "El cupo se lleva a valor presente con esta tasa y se reparte en los meses del contrato"),
    "pct_admin": (10, "Gasto administrativo (%)", "Gastos", "Provisión mensual sobre la tarifa mensual (tarifa decreto)"),
    "publicidad_gasto": (120373349, "Gasto en publicidad", "Gastos", "Junto con la facturación contratada da el % de publicidad"),
    "publicidad_facturacion": (50567261418, "Facturación total contratada", "Gastos", "Base del % de publicidad"),
    "publicidad_sobre_contrato": (0, "Bolsa de publicidad sobre el contrato completo (1 = sí, 0 = sobre la facturación mensual)",
                                  "Gastos", "La bolsa se amortiza en los meses del contrato"),
    "pct_representacion": (1, "Reserva de gastos de representación (%)", "Gastos",
                           "Mensual sobre la tarifa mensual; la bolsa del contrato es ese valor por los meses"),
    "pct_renta": (35, "Impuesto de renta (%)", "Impuestos", "Sobre el margen antes de impuestos (nunca negativo)"),
    "ica_por_mil": (6.6, "ICA (por mil)", "Impuestos", "Sobre el AIU"),
    "pct_aiu": (10, "AIU (%)", "Impuestos", "Base del IVA y del ICA"),
    "pct_iva": (19, "IVA (%)", "Impuestos", "Sobre el AIU"),
    "comision_factor_base": (0.9, "Comisión: factor sobre la tarifa", "Comisiones", "Constante de la fórmula de comisión"),
    "comision_part_vendedor": (0.62, "Comisión: participación del vendedor", "Comisiones", ""),
    "comision_part_director": (0.4, "Comisión: participación del director", "Comisiones", ""),
}

# Rangos de comisión por defecto: hasta % de MFP → % de comisión (carga prestacional del vendedor 1,37872)
COMISIONES = [(0.05, 0.015), (0.10, 0.01), (0.12, 0.005), (0.14, 0.003), (None, 0.002)]
CARGA_PRESTACIONAL = 1.37872


def _n(v, defecto: float = 0.0) -> float:
    try:
        return float(v) if v not in (None, "") else defecto
    except (TypeError, ValueError):
        return defecto


@dataclass
class Rango:
    hasta: float | None
    pct: float
    carga: float


def rango_comision(pct_mfp: float, rangos: list[Rango]) -> Rango:
    for r in sorted(rangos, key=lambda x: (x.hasta is None, x.hasta or 0)):
        if r.hasta is None or pct_mfp <= r.hasta + 1e-12:
            return r
    return rangos[-1] if rangos else Rango(None, 0, 1)


def valor_presente(tasa: float, periodos: int, pago: float) -> float:
    if periodos <= 0:
        return 0.0
    if not tasa:
        return pago * periodos
    return pago * (1 - (1 + tasa) ** -periodos) / tasa


def costo_hombre(p: dict, linea: dict) -> dict:
    """Costo mensual de un hombre de un tipo de personal (guarda, motorizado…)."""
    salario = _n(linea.get("salario"), p["salario_minimo"])
    extras = _n(linea.get("horas_extras"))
    aux_t = p["auxilio_transporte"] if linea.get("auxilio_transporte", True) else 0.0
    aux_ns = _n(linea.get("auxilios_no_salariales"))
    rodamiento = _n(linea.get("rodamiento"))
    ley = _n(linea.get("ley_2101"), p["ley_2101"])
    base = salario + extras
    pct = lambda k: p[k] / 100  # noqa: E731
    cesantias = (base + aux_t) * pct("pct_cesantias")
    partes = {
        "salario": salario, "horas_extras": extras, "auxilio_transporte": aux_t, "auxilios_no_salariales": aux_ns,
        "rodamiento": rodamiento, "ley_2101": ley,
        "salud": base * pct("pct_salud_empleador"), "pension": base * pct("pct_pension"), "caja": base * pct("pct_caja"),
        "arl": base * pct("pct_arl"), "primas": (base + aux_t) * pct("pct_primas"), "cesantias": cesantias,
        "intereses_cesantias": cesantias * pct("pct_intereses_cesantias"), "vacaciones": base * pct("pct_vacaciones"),
    }
    total = sum(partes.values())
    devengado = salario + extras + aux_t + aux_ns + rodamiento + ley
    neto = devengado - base * (pct("pct_salud_trabajador") + pct("pct_pension_trabajador"))
    return {"partes": partes, "total": total, "devengado": devengado, "neto": neto}


def costo_mensual_elemento(linea: dict, meses: int) -> float:
    """Dotación u otro costo: mensual por vida útil (o los meses del contrato si no tiene), o anual por entregas."""
    valor, cantidad = _n(linea.get("valor_unitario")), _n(linea.get("cantidad"))
    entregas = linea.get("entregas_anio")
    if entregas not in (None, ""):
        return valor * cantidad * _n(entregas) / 12
    vida = _n(linea.get("vida_util_meses")) or meses
    return valor * cantidad / vida if vida else 0.0


def calcular(datos: dict, p: dict, rangos: list[Rango]) -> dict:
    meses = int(_n(datos.get("duracion_meses"), 12)) or 12
    servicios = datos.get("servicios") or []
    tarifa = sum(_n(s.get("tarifa")) * _n(s.get("cantidad"), 1) for s in servicios)
    hombres_servicios = sum(_n(s.get("hombres")) * _n(s.get("cantidad"), 1) for s in servicios)
    pct_nc = _n(datos.get("pct_nota_credito"))
    pct_cupo = _n(datos.get("pct_cupo_inversion"))
    descuento = tarifa * pct_nc
    neta = tarifa - descuento

    # Personal
    personal = []
    laboral = hombres_personal = 0.0
    for linea in datos.get("personal") or []:
        h = _n(linea.get("hombres"))
        c = costo_hombre(p, linea)
        personal.append({"nombre": linea.get("nombre", ""), "hombres": h, "costo_hombre": c["total"], "costo_total": c["total"] * h,
                         "devengado_hombre": c["devengado"], "neto_hombre": c["neto"], "partes": c["partes"]})
        laboral += c["total"] * h
        hombres_personal += h
    costo_por_hombre = laboral / hombres_personal if hombres_personal else 0.0

    # Dotación y otros costos directos
    def bloque(nombre: str) -> tuple[list[dict], float]:
        filas = [{**x, "mensual": costo_mensual_elemento(x, meses)} for x in datos.get(nombre) or []]
        return filas, sum(f["mensual"] for f in filas)

    dot_tarifa, dot_tarifa_m = bloque("dotacion_tarifa")
    dot_puesto, dot_puesto_m = bloque("dotacion_puesto")
    otros, otros_m = bloque("otros")
    horas_bolsa = _n(datos.get("horas_bolsa_anual"))
    valor_hora = costo_por_hombre / 30 / p["horas_turno_bolsa"] if p["horas_turno_bolsa"] else 0.0
    horas_m = valor_hora * horas_bolsa / 12

    # MFP y cupo de inversión
    pct_otros = otros_m / tarifa if tarifa else 0.0
    pct_mfp = pct_nc + pct_cupo + pct_otros
    cupo_vp = valor_presente(p["tasa_cupo_inversion"] / 100, meses, tarifa * pct_cupo)
    cupo_m = cupo_vp / meses

    # Bolsas que se amortizan en el contrato
    pct_publicidad = p["publicidad_gasto"] / p["publicidad_facturacion"] if p["publicidad_facturacion"] else 0.0
    publicidad_bolsa = pct_publicidad * tarifa * (meses if p["publicidad_sobre_contrato"] else 1)
    representacion_m = p["pct_representacion"] / 100 * tarifa
    representacion_bolsa = representacion_m * meses
    publicidad_m = publicidad_bolsa / meses
    donaciones = _n(datos.get("donaciones"))
    donaciones_m = donaciones / meses

    # Comisiones (la carga prestacional depende del rango en que se vende). La del vendedor y la del director se
    # pueden digitar en el costeo (con la carga del rango de ese %, o la del rango automático); vacías salen del
    # rango del % de MFP.
    r = rango_comision(pct_mfp, rangos)

    def comision(clave: str) -> Rango:
        digitada = datos.get(clave)
        if digitada in (None, ""):
            return r
        pct_c = max(0.0, _n(digitada))
        return next((x for x in rangos if abs(x.pct - pct_c) < 1e-9), Rango(None, pct_c, r.carga))

    rv, rd = comision("pct_comision_vendedor"), comision("pct_comision_director")
    base_comision = (tarifa * p["comision_factor_base"]) - (pct_mfp / (meses / 12)) * neta
    com_vendedor = max(0.0, base_comision * meses * p["comision_part_vendedor"] * rv.pct * rv.carga)
    com_director = max(0.0, base_comision * meses * p["comision_part_director"] * rd.pct * rd.carga)
    com_vendedor_m, com_director_m = com_vendedor / meses, com_director / meses

    admin_m = p["pct_admin"] / 100 * tarifa  # provisión para gasto administrativo

    # Facturación con impuestos (informativa) e ICA
    aiu = tarifa * p["pct_aiu"] / 100
    iva = aiu * p["pct_iva"] / 100
    reteica = aiu * p["ica_por_mil"] / 1000
    total_a_pagar = tarifa + iva - reteica - descuento
    ica_m = total_a_pagar * p["pct_aiu"] / 100 * p["ica_por_mil"] / 1000

    costos = {
        "laboral": laboral, "dotacion_tarifa": dot_tarifa_m, "dotacion_puesto": dot_puesto_m, "horas_adicionales": horas_m,
        "otros_directos": otros_m, "publicidad": publicidad_m, "cupo_inversion": cupo_m,
        "comisiones": com_vendedor_m + com_director_m, "donaciones": donaciones_m, "gasto_administrativo": admin_m,
        "representacion": representacion_m, "ica": ica_m,
    }
    antes_renta = neta - sum(costos.values())
    renta = max(0.0, antes_renta) * p["pct_renta"] / 100
    costos["renta"] = renta
    margen = antes_renta - renta
    margen_total, neta_total = margen * meses, neta * meses
    total_costos = sum(costos.values())

    alertas = []
    if abs(hombres_personal - hombres_servicios) > 0.01:
        alertas.append(f"Los hombres del personal ({hombres_personal:g}) no coinciden con los que piden los servicios ({hombres_servicios:g})")
    if margen < 0:
        alertas.append("El margen del negocio es negativo")
    if not tarifa:
        alertas.append("No hay servicios con tarifa")

    return {
        "meses": meses, "tarifa_decreto": tarifa, "descuento_nota_credito": descuento, "tarifa_neta": neta,
        "hombres_servicios": hombres_servicios, "hombres_personal": hombres_personal, "costo_por_hombre": costo_por_hombre,
        "mfp": {"pct_nota_credito": pct_nc, "pct_cupo_inversion": pct_cupo, "pct_otros": pct_otros, "pct_total": pct_mfp,
                "nota_credito_total": descuento * meses, "cupo_inversion_vp": cupo_vp, "otros_total": otros_m * meses},
        "bolsas": {"publicidad": publicidad_bolsa, "representacion": representacion_bolsa, "horas_anuales": horas_bolsa,
                   "valor_hora": valor_hora, "pct_publicidad": pct_publicidad},
        "comision": {"pct": r.pct, "carga_prestacional": r.carga, "vendedor_total": com_vendedor, "director_total": com_director,
                     "pct_vendedor": rv.pct, "carga_vendedor": rv.carga, "vendedor_elegida": rv is not r,
                     "pct_director": rd.pct, "carga_director": rd.carga, "director_elegida": rd is not r},
        "facturacion": {"aiu": aiu, "iva": iva, "reteica": reteica, "total_a_pagar": total_a_pagar},
        "personal": personal, "dotacion_tarifa": dot_tarifa, "dotacion_puesto": dot_puesto, "otros": otros,
        # La dotación (de la tarifa y del puesto) es gasto operativo: no suma en el % de MFP ni pasa a la MFP
        "costos": costos, "gasto_operativo": dot_tarifa_m + dot_puesto_m, "total_costos": total_costos, "antes_renta": antes_renta,
        "margen_mensual": margen, "margen_por_hombre": margen / hombres_personal if hombres_personal else 0.0,
        "margen_total": margen_total, "pct_margen": margen / neta if neta else 0.0,
        # Rentabilidad: margen después de renta sobre la facturación neta, del mes y de todo el contrato
        "facturacion_neta_total": neta_total, "pct_rentabilidad_mensual": margen / neta if neta else 0.0,
        "pct_rentabilidad_total": margen_total / neta_total if neta_total else 0.0, "alertas": alertas,
    }
