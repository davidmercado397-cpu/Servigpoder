"""Motor de validación de la nómina (modalidades FIJAS).

Para cada persona de cada nómina cargada (quincenal: días 16 al 30; mensual: días 1 al 30; el día 31 no
suma) se calcula, con la programación del mes:

- días pagables: días con turno, Z, L, IND… (todo código sin el check "Descuenta"); también son los días
  que llevan auxilio de transporte;
- la modalidad de cada día según el puesto donde trabajó (prioridad: modalidad del puesto > de la ubicación);
- el valor esperado de cada concepto de la modalidad (días × valor por día) y de cada cuota;

y se compara con lo pagado. Las diferencias se vuelven alertas. Funciones puras: no tocan la base.
"""

import calendar
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.apps.nomina.models import ADMINISTRATIVO, CONTRATOS, CUOTAS, EXCLUIDO, MENSUAL, MODALIDADES, PROGRAMACION, QUINCENAL, UBICACIONES
from app.apps.nomina.services.lectores import codigo_programacion

_HORARIO = re.compile(r"^\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}")

# Tipos de alerta: (título, severidad, grupo)
TIPOS: dict[str, tuple[str, str, str]] = {
    "SIN_CONTRATO_ACTIVO": ("Con nómina sin contrato activo", "alta", "Personas"),
    "TIPO_NOMINA_DIFERENTE": ("Tipo de nómina distinto al del contrato", "media", "Personas"),
    "NOMINA_SIN_PROGRAMACION": ("Con nómina y sin programación", "alta", "Personas"),
    "PROGRAMADO_SIN_NOMINA": ("Programado y sin nómina", "alta", "Personas"),
    "PROGRAMADO_SIN_CONTRATO": ("Programado sin contrato activo", "media", "Personas"),
    "PAGO_SIN_DIAS": ("Pago sin días trabajados", "alta", "Salario"),
    "SALARIO_MAYOR_DIAS": ("Salario por más días de los trabajados", "alta", "Salario"),
    "VACACIONES_CON_PAGO": ("Vacaciones con salario o modalidad completa", "alta", "Salario"),
    "DIAS_SIN_PAGAR": ("Días trabajados sin pagar", "media", "Salario"),
    "AUX_CERO": ("Auxilio de transporte en 0 días", "alta", "Auxilio de transporte"),
    "AUX_DIFERENTE": ("Auxilio de transporte no consecuente con los días", "media", "Auxilio de transporte"),
    "EXTRAS_SIN_DIAS": ("Extras o modalidad sin días trabajados", "alta", "Modalidad"),
    "MODALIDAD_MAYOR": ("Modalidad pagada por encima de lo esperado", "alta", "Modalidad"),
    "MODALIDAD_MENOR": ("Modalidad pagada por debajo de lo esperado", "media", "Modalidad"),
    "CUOTA_DE_MAS": ("Cuota: se descontó de más", "alta", "Cuotas"),
    "CUOTA_DE_MENOS": ("Cuota: se descontó de menos", "media", "Cuotas"),
    "CUOTA_NO_DESCONTADA": ("Cuota activa no descontada", "alta", "Cuotas"),
    "CUOTA_DEVENGO_DIFERENTE": ("Devengo de cuota distinto a lo pactado", "media", "Cuotas"),
    "CUOTA_MAESTRO": ("Cuota mal configurada (valor mayor al tope)", "media", "Cuotas"),
    "DESCUENTO_SIN_SUELDO": ("Descuentos sin sueldo", "alta", "Cuotas"),
    "NETO_NEGATIVO": ("Neto negativo: se descuenta más de lo devengado", "alta", "Cuotas"),
}

CUOTA_ACTIVA = {"EN PROCESO", "PENDIENTE"}
CONCEPTO_SALARIO = "100"
CONCEPTO_AUXILIO = "103"
# Devengos que son horas extras o recargos por hora (además de los de la modalidad)
CONCEPTOS_EXTRAS = {"104", "105", "106", "107", "108", "109", "111", "115", "116", "142", "143"}


@dataclass
class Parametros:
    tolerancia: float = 1000
    smlmv: float = 1750905
    auxilio_transporte: float = 249095
    horas_dia: float = 7
    solo_primera_quincena: set[str] = field(default_factory=lambda: {"600", "630", "631", "632"})
    excluidos_base_embargo: set[str] = field(default_factory=lambda: {"103", "132", "142", "143"})
    embargos_sin_minimo: set[str] = field(default_factory=lambda: {"606"})
    # Concepto de cuota → conceptos de la nómina con que se paga (además del mismo código)
    equivalencias_cuotas: dict[str, list[str]] = field(default_factory=lambda: {"152": ["129"]})


@dataclass
class Codigo:
    descuenta: bool
    vacaciones: bool = False


@dataclass
class Alerta:
    nomina: str
    cedula: str
    nombre: str
    tipo: str
    mensaje: str
    referencia: str = ""
    esperado: float | None = None
    pagado: float | None = None
    datos: dict = field(default_factory=dict)

    @property
    def severidad(self) -> str:
        return TIPOS[self.tipo][1]


@dataclass
class Resultado:
    personas: list[dict]
    alertas: list[Alerta]
    puestos_sin_modalidad: list[dict]
    resumen: dict


def pesos(v: float) -> str:
    return "$" + f"{v:,.0f}".replace(",", ".")


def rango(nomina: str, anio: int, mes: int) -> tuple[date, date]:
    """Quincenal: 16 al 30 (2.ª quincena); mensual: 1 al 30. El día 31 nunca suma."""
    ultimo = min(30, calendar.monthrange(anio, mes)[1])
    return (date(anio, mes, 16) if nomina == QUINCENAL else date(anio, mes, 1)), date(anio, mes, ultimo)


def codigo_por_defecto(crudo: str) -> Codigo:
    """Para códigos nuevos: los que vienen entre corchetes son novedades (descuentan); horarios, turnos,
    descansos (Z, L) e inducción no descuentan."""
    base = codigo_programacion(crudo).upper()
    return Codigo(descuenta=crudo.strip().startswith("["), vacaciones=base in {"VAC", "PRV"})


def mapa_modalidades(datos: dict) -> tuple[dict[str, dict], dict[tuple[str, str], dict]]:
    """Modalidades y, por (ubicación, puesto), la modalidad que aplica con su origen."""
    mods = datos[MODALIDADES]
    desc_a_cod = {m["descripcion"]: cod for cod, m in mods.items() if m["descripcion"]}
    puestos: dict[tuple[str, str], dict] = {}
    for f in datos[UBICACIONES]:
        m_puesto = f["modalidad_puesto"]
        m_puesto = desc_a_cod.get(m_puesto) or (m_puesto if m_puesto in mods else None) if m_puesto else None
        m_ubi = f["modalidad_ubicacion"] if f["modalidad_ubicacion"] in mods else None
        puestos[(f["ubicacion"], f["puesto"])] = {
            "modalidad": m_puesto or m_ubi, "origen": "puesto" if m_puesto else "ubicacion" if m_ubi else None,
            "ubicacion_nombre": f["ubicacion_nombre"], "puesto_nombre": f["puesto_nombre"],
            "modalidad_texto": f["modalidad_puesto"] or f["modalidad_ubicacion"],
        }
    return mods, puestos


def calcular(anio: int, mes: int, datos: dict, codigos: dict[str, Codigo], grupos: dict[str, str],
             puestos_aprobados: set[tuple[str, str]], p: Parametros) -> Resultado:
    mods, puestos = mapa_modalidades(datos)
    conceptos_modalidad = sorted({c for m in mods.values() for c in m["conceptos"]})
    desc_concepto = {c: d["descripcion"] for m in mods.values() for c, d in m["conceptos"].items()}
    contratos: dict[str, dict] = datos[CONTRATOS]
    cuotas_por_persona: dict[str, list[dict]] = defaultdict(list)
    for c in datos.get(CUOTAS) or []:
        cuotas_por_persona[c["cedula"]].append(c)
    conceptos_cuota = {c["concepto"] for c in datos.get(CUOTAS) or []}

    prog = datos[PROGRAMACION]
    p_desde, p_hasta = date.fromisoformat(prog["desde"]), date.fromisoformat(prog["hasta"])
    filas_por_persona: dict[str, list[dict]] = defaultdict(list)
    for f in prog["filas"]:
        filas_por_persona[f["cedula"]].append(f)

    def tratamiento(ced: str) -> str:
        c = contratos.get(ced)
        return grupos.get(c["grupo"], "validar") if c else "validar"

    personas: list[dict] = []
    alertas: list[Alerta] = []
    sin_modalidad: dict[tuple[str, str], dict] = {}

    for nomina in (QUINCENAL, MENSUAL):
        archivo = datos.get(nomina)
        if not archivo:
            continue
        desde, hasta = rango(nomina, anio, mes)
        if p_desde > desde or p_hasta < hasta:
            raise ValueError(f"La programación cargada ({p_desde:%d/%m} al {p_hasta:%d/%m}) no cubre el periodo de la nómina "
                             f"{nomina} ({desde:%d/%m} al {hasta:%d/%m})")
        base_dias = 15 if nomina == QUINCENAL else 30
        fechas = [desde + timedelta(days=i) for i in range((hasta - desde).days + 1)]
        faltan_mes_corto = base_dias - len(fechas) if hasta.day == calendar.monthrange(anio, mes)[1] else 0
        en_nomina: set[str] = set(archivo["personas"])

        for ced, pago in archivo["personas"].items():
            trat = tratamiento(ced)
            if trat == EXCLUIDO:
                continue
            contrato = contratos.get(ced)
            persona = _persona(ced, pago, nomina, contrato, trat, fechas, faltan_mes_corto, filas_por_persona.get(ced, []),
                               codigos, puestos, puestos_aprobados, mods, conceptos_modalidad, desc_concepto, p, sin_modalidad)
            a = _alertas_persona(persona, pago, contrato, trat, nomina, base_dias, p)
            a += _alertas_cuotas(persona, pago, cuotas_por_persona.get(ced, []), conceptos_cuota, archivo["conceptos"], nomina, p)
            persona["alertas"] = len(a)
            personas.append(persona)
            alertas += a

        # Programados (con algún código en el periodo) que no están en esta nómina
        for ced, filas in filas_por_persona.items():
            if ced in en_nomina or tratamiento(ced) in (EXCLUIDO, ADMINISTRATIVO):
                continue
            codigos_periodo = {d for f in filas for d in fechas if f["dias"].get(d.isoformat())}  # días distintos
            if not codigos_periodo:
                continue
            contrato = contratos.get(ced)
            nombre = filas[0]["nombre"]
            if contrato is None or not contrato["activo"]:
                if nomina == QUINCENAL or not datos.get(QUINCENAL):  # una sola vez por persona
                    alertas.append(Alerta(nomina, ced, nombre, "PROGRAMADO_SIN_CONTRATO",
                                          f"Tiene {len(codigos_periodo)} días programados y no tiene contrato activo.",
                                          datos={"puestos": sorted({f['puesto'] for f in filas})}))
            elif contrato["tipo_nomina"] == nomina.upper():
                alertas.append(Alerta(nomina, ced, nombre, "PROGRAMADO_SIN_NOMINA",
                                      f"Tiene {len(codigos_periodo)} días con programación del {desde:%d} al {hasta:%d} y no aparece en la nómina {nomina}.",
                                      datos={"puestos": sorted({f['puesto'] for f in filas})}))

    lista_sin_mod = _puestos_sin_modalidad(puestos, prog["filas"], puestos_aprobados, sin_modalidad, mods)
    resumen = _resumen(personas, alertas, lista_sin_mod, datos)
    return Resultado(personas, alertas, lista_sin_mod, resumen)


def _persona(ced, pago, nomina, contrato, trat, fechas, faltan_mes_corto, filas, codigos, puestos, puestos_aprobados,
             mods, conceptos_modalidad, desc_concepto, p, sin_modalidad) -> dict:
    dias: dict[str, dict] = {}
    pagables = novedad = vacaciones = vacios = dias_sin_modalidad = 0
    por_modalidad: dict[str, int] = defaultdict(int)
    esperado: dict[str, float] = defaultdict(float)
    ultimo_dia_modalidad: str | None = None
    for d in fechas:
        iso = d.isoformat()
        candidatos = []
        for f in filas:
            crudo = f["dias"].get(iso)
            if crudo:
                cod = codigo_programacion(crudo).upper()
                info = codigos.get(cod) or codigo_por_defecto(crudo)
                candidatos.append((f, crudo, cod, info))
        if not candidatos:
            vacios += 1
            dias[iso] = {"codigo": "", "clase": "vacio"}
            continue
        pagan = [c for c in candidatos if not c[3].descuenta]
        if not pagan:
            novedad += 1
            es_vac = any(c[3].vacaciones for c in candidatos)
            vacaciones += es_vac
            dias[iso] = {"codigo": candidatos[0][1], "clase": "vacaciones" if es_vac else "novedad", "puesto": candidatos[0][0]["puesto"]}
            ultimo_dia_modalidad = None
            continue
        # El día se paga una vez, con la modalidad del puesto donde trabajó (si tiene turno, ese manda)
        f, crudo, cod, _ = next((c for c in pagan if _HORARIO.match(c[1]) or c[2] not in {"Z", "L"}), pagan[0])
        pagables += 1
        clave = (f["ubicacion"], f["puesto"])
        info_puesto = puestos.get(clave)
        modalidad = info_puesto["modalidad"] if info_puesto else None
        dia = {"codigo": crudo, "clase": "pagable", "puesto": f["puesto"], "ubicacion": f["ubicacion"], "modalidad": modalidad}
        if modalidad:
            por_modalidad[modalidad] += 1
            for c, v in mods[modalidad]["conceptos"].items():
                esperado[c] += v["valor"]
        elif clave not in puestos_aprobados:
            dias_sin_modalidad += 1
            s = sin_modalidad.setdefault(clave, {"personas": set(), "dias": 0, "ubicacion_nombre": f["ubicacion_nombre"],
                                                 "puesto_nombre": f["puesto_nombre"], "en_maestro": info_puesto is not None})
            s["personas"].add(ced)
            s["dias"] += 1
        ultimo_dia_modalidad = modalidad
        dias[iso] = dia
    # Meses de menos de 30 días (febrero): si trabaja hasta el último día, se completa la base de 30
    if faltan_mes_corto > 0 and fechas and dias[fechas[-1].isoformat()]["clase"] == "pagable":
        pagables += faltan_mes_corto
        if ultimo_dia_modalidad:
            por_modalidad[ultimo_dia_modalidad] += faltan_mes_corto
            for c, v in mods[ultimo_dia_modalidad]["conceptos"].items():
                esperado[c] += v["valor"] * faltan_mes_corto

    devengos, deducciones, horas = pago["devengos"], pago["deducciones"], pago["horas"]
    usados = sorted(set(esperado) | {c for c in conceptos_modalidad if devengos.get(c)})
    return {
        "cedula": ced, "nombre": pago["nombre"] or (filas[0]["nombre"] if filas else ""), "nomina": nomina,
        "grupo": contrato["grupo"] if contrato else "", "tratamiento": trat, "cargo": pago["cargo"],
        "contrato": contrato, "salario": pago["salario"], "centros_costos": pago["centros_costos"],
        "desde": fechas[0].isoformat(), "hasta": fechas[-1].isoformat(),
        "tiene_programacion": any(d["clase"] != "vacio" for d in dias.values()),
        "dias": dias,
        "conteo": {"pagables": pagables, "novedad": novedad, "vacaciones": vacaciones, "vacios": vacios,
                   "sin_modalidad": dias_sin_modalidad},
        "modalidades": dict(por_modalidad),
        "dias_salario": round(horas.get(CONCEPTO_SALARIO, 0) / p.horas_dia, 2) if p.horas_dia else 0,
        "auxilio": {"pagado": devengos.get(CONCEPTO_AUXILIO, 0), "dias_pagados": round(devengos.get(CONCEPTO_AUXILIO, 0) / (p.auxilio_transporte / 30), 2),
                    "dias_esperados": pagables, "esperado": round(pagables * p.auxilio_transporte / 30)},
        "conceptos": [{"concepto": c, "descripcion": desc_concepto.get(c, ""), "esperado": round(esperado.get(c, 0)),
                       "pagado": round(devengos.get(c, 0))} for c in usados],
        "extras": {c: devengos[c] for c in CONCEPTOS_EXTRAS if devengos.get(c)},
        "devengado": round(sum(devengos.values())), "deducido": round(sum(deducciones.values())), "neto": round(pago["neto"]),
        "devengos": devengos, "deducciones": deducciones, "horas": horas,
    }


def _alertas_persona(per: dict, pago: dict, contrato: dict | None, trat: str, nomina: str, base_dias: int, p: Parametros) -> list[Alerta]:
    a: list[Alerta] = []
    ced, nombre = per["cedula"], per["nombre"]

    def alerta(tipo, mensaje, referencia="", esperado=None, pagado=None, **datos):
        a.append(Alerta(nomina, ced, nombre, tipo, mensaje, referencia, esperado, pagado, datos))

    if contrato is None or not contrato["activo"]:
        alerta("SIN_CONTRATO_ACTIVO", "Aparece en la nómina pero no tiene un contrato activo" + (" (está retirado)." if contrato else "."))
    elif contrato["tipo_nomina"] and contrato["tipo_nomina"] != nomina.upper():
        alerta("TIPO_NOMINA_DIFERENTE", f"Está en la nómina {nomina} pero su contrato es de nómina {contrato['tipo_nomina'].lower()}.")
    if trat == ADMINISTRATIVO:
        return a  # a los administrativos solo se les revisan contrato y cuotas

    c, sal = per["conteo"], per["dias_salario"]
    pagables = c["pagables"]
    if not per["tiene_programacion"]:
        alerta("NOMINA_SIN_PROGRAMACION", f"Recibe pago ({sal:g} días de salario) pero no tiene programación del {per['desde'][8:]} al {per['hasta'][8:]}.",
               pagado=pago["devengos"].get(CONCEPTO_SALARIO, 0))
        return a

    pago_modalidad = sum(x["pagado"] for x in per["conceptos"])
    extras = sum(per["extras"].values()) + pago_modalidad
    if pagables == 0:
        if sal > 0:
            alerta("PAGO_SIN_DIAS", f"Se le pagan {sal:g} días de salario y no tiene días trabajados en la programación "
                                    f"({c['novedad']} días de novedad).", esperado=0, pagado=pago["devengos"].get(CONCEPTO_SALARIO, 0))
        if extras > p.tolerancia:
            alerta("EXTRAS_SIN_DIAS", f"Recibe {pesos(extras)} en extras/modalidad sin días trabajados.", esperado=0, pagado=extras)
    else:
        if sal > pagables + 0.5:
            tipo = "VACACIONES_CON_PAGO" if c["vacaciones"] else "SALARIO_MAYOR_DIAS"
            detalle = f" y {c['vacaciones']} de vacaciones" if c["vacaciones"] else ""
            alerta(tipo, f"Se le pagan {sal:g} días de salario pero solo tiene {pagables} días trabajados{detalle}.",
                   referencia=CONCEPTO_SALARIO, esperado=pagables, pagado=sal)
        elif sal < pagables - 0.5:
            alerta("DIAS_SIN_PAGAR", f"Tiene {pagables} días trabajados y solo se le pagan {sal:g} días de salario "
                                     f"(revisar si van en la liquidación de vacaciones u otra).", referencia=CONCEPTO_SALARIO,
                   esperado=pagables, pagado=sal)

    # Auxilio de transporte: días laborados + descansos (sin novedades), si gana hasta 2 SMLMV
    aux = per["auxilio"]
    if pagables > 0 and (per["salario"] or 0) <= 2 * p.smlmv:
        if aux["pagado"] <= 0:
            alerta("AUX_CERO", f"Tiene {pagables} días con derecho a auxilio de transporte y se le pagan 0 días.",
                   referencia=CONCEPTO_AUXILIO, esperado=aux["esperado"], pagado=0)
        elif abs(aux["pagado"] - aux["esperado"]) > p.tolerancia:
            alerta("AUX_DIFERENTE", f"Auxilio de transporte por {aux['dias_pagados']:g} días ({pesos(aux['pagado'])}); "
                                    f"le corresponden {pagables} días ({pesos(aux['esperado'])}).",
                   referencia=CONCEPTO_AUXILIO, esperado=aux["esperado"], pagado=aux["pagado"])
    elif pagables == 0 and aux["pagado"] > p.tolerancia:
        alerta("AUX_DIFERENTE", f"Se le paga auxilio de transporte ({pesos(aux['pagado'])}) sin días trabajados.",
               referencia=CONCEPTO_AUXILIO, esperado=0, pagado=aux["pagado"])

    # Modalidad: concepto por concepto
    if pagables > 0:
        for x in per["conceptos"]:
            dif = x["pagado"] - x["esperado"]
            if dif > p.tolerancia:
                tipo = "VACACIONES_CON_PAGO" if c["vacaciones"] and x["esperado"] else "MODALIDAD_MAYOR"
                alerta(tipo, f"{x['concepto']} {x['descripcion']}: pagado {pesos(x['pagado'])}, esperado {pesos(x['esperado'])} "
                             f"({pagables} días{', ' + str(c['vacaciones']) + ' de vacaciones' if c['vacaciones'] else ''}).",
                       referencia=x["concepto"], esperado=x["esperado"], pagado=x["pagado"])
            elif dif < -p.tolerancia:
                alerta("MODALIDAD_MENOR", f"{x['concepto']} {x['descripcion']}: pagado {pesos(x['pagado'])}, esperado {pesos(x['esperado'])} "
                                          f"({pagables} días).", referencia=x["concepto"], esperado=x["esperado"], pagado=x["pagado"])
    return a


def _alertas_cuotas(per: dict, pago: dict, cuotas: list[dict], conceptos_cuota: set[str], conceptos_nomina: dict[str, str],
                    nomina: str, p: Parametros) -> list[Alerta]:
    a: list[Alerta] = []
    ced, nombre = per["cedula"], per["nombre"]
    devengos, deducciones = pago["devengos"], pago["deducciones"]
    activas: dict[str, list[dict]] = defaultdict(list)
    for c in cuotas:
        if c["estado"] in CUOTA_ACTIVA:
            activas[c["concepto"]].append(c)
    detalle = []

    base_embargo = sum(v for k, v in devengos.items() if k not in p.excluidos_base_embargo and k != CONCEPTO_AUXILIO)
    minimo = p.smlmv * (15 / 30 if nomina == QUINCENAL else 1)

    for concepto in sorted(set(activas) | {k for k in conceptos_cuota if deducciones.get(k) or devengos.get(k)}):
        lista = activas.get(concepto, [])
        if nomina == QUINCENAL and concepto in p.solo_primera_quincena:
            continue  # en la 2.ª quincena estas cuotas no se descuentan
        esperado = 0.0
        es_devengo = any(c["devengo"] for c in lista) or (not lista and devengos.get(concepto))
        for c in lista:
            valor = c["devengo"] or c["deduccion"]
            saldo = c["maximo"] - c["acumulado"] if c["maximo"] else None
            if c["tasa"] and not valor:
                sin_minimo = concepto in p.embargos_sin_minimo
                valor = max(0.0, base_embargo - (0 if sin_minimo else minimo)) * c["tasa"] / 100
            elif c["maximo"] and valor > c["maximo"]:
                a.append(Alerta(nomina, ced, nombre, "CUOTA_MAESTRO",
                                f"{concepto} {c['descripcion']}: la cuota por pago ({pesos(valor)}) es mayor que el valor máximo ({pesos(c['maximo'])}).",
                                referencia=concepto, esperado=c["maximo"], pagado=valor))
            if saldo is not None:
                valor = min(valor, max(0.0, saldo))
            esperado += valor
        # Si el concepto no está en la nómina, cuenta como no pagado (salvo que se pague con un concepto equivalente)
        fuente = devengos if es_devengo else deducciones
        pagado = sum(fuente.get(c, 0.0) for c in [concepto, *p.equivalencias_cuotas.get(concepto, [])])
        descripcion = lista[0]["descripcion"] if lista else conceptos_nomina.get(concepto, "")
        equivalente = p.equivalencias_cuotas.get(concepto)
        if equivalente:
            descripcion += f" (se paga como {', '.join(equivalente)})"
        detalle.append({"concepto": concepto, "descripcion": descripcion, "devengo": bool(es_devengo), "esperado": round(esperado),
                        "pagado": round(pagado), "cuotas": len(lista), "pendiente": any(c["estado"] == "PENDIENTE" for c in lista)})
        if abs(pagado - esperado) <= p.tolerancia:
            continue
        if es_devengo:
            a.append(Alerta(nomina, ced, nombre, "CUOTA_DEVENGO_DIFERENTE",
                            f"{concepto} {descripcion}: pagado {pesos(pagado)}, pactado {pesos(esperado)}.", concepto, round(esperado), pagado))
        elif pagado == 0:
            estado = " (cuota en estado Pendiente)" if any(c["estado"] == "PENDIENTE" for c in lista) else ""
            a.append(Alerta(nomina, ced, nombre, "CUOTA_NO_DESCONTADA",
                            f"{concepto} {descripcion}: debía descontar {pesos(esperado)} y no se descontó{estado}.", concepto, round(esperado), 0))
        elif pagado > esperado:
            motivo = "" if lista else " (no tiene cuota activa en el maestro)"
            a.append(Alerta(nomina, ced, nombre, "CUOTA_DE_MAS",
                            f"{concepto} {descripcion}: descontó {pesos(pagado)}, debía {pesos(esperado)}{motivo}.", concepto, round(esperado), pagado))
        else:
            a.append(Alerta(nomina, ced, nombre, "CUOTA_DE_MENOS",
                            f"{concepto} {descripcion}: descontó {pesos(pagado)}, debía {pesos(esperado)}.", concepto, round(esperado), pagado))
    per["cuotas"] = detalle

    descuentos_cuotas = sum(deducciones.get(k, 0) for k in conceptos_cuota if k not in devengos)
    if devengos.get(CONCEPTO_SALARIO, 0) <= 0 and descuentos_cuotas > p.tolerancia:
        a.append(Alerta(nomina, ced, nombre, "DESCUENTO_SIN_SUELDO", f"No devenga salario y se le descuentan {pesos(descuentos_cuotas)} en cuotas.",
                        esperado=0, pagado=descuentos_cuotas))
    if per["neto"] < 0 or per["deducido"] > per["devengado"] + p.tolerancia:
        a.append(Alerta(nomina, ced, nombre, "NETO_NEGATIVO",
                        f"Devengado {pesos(per['devengado'])}, deducido {pesos(per['deducido'])}: neto {pesos(per['devengado'] - per['deducido'])}.",
                        esperado=per["devengado"], pagado=per["deducido"]))
    return a


def _puestos_sin_modalidad(puestos, filas_prog, aprobados, vistos, mods) -> list[dict]:
    """Puestos sin modalidad: del maestro (ni en puesto ni en ubicación) y los de la programación que no están en él."""
    res: dict[tuple[str, str], dict] = {}
    for clave, info in puestos.items():
        if not info["modalidad"]:
            res[clave] = {"ubicacion": clave[0], "puesto": clave[1], "ubicacion_nombre": info["ubicacion_nombre"],
                          "puesto_nombre": info["puesto_nombre"], "motivo": "sin_modalidad" if not info["modalidad_texto"] else "modalidad_desconocida",
                          "modalidad_texto": info["modalidad_texto"], "personas": 0, "dias": 0}
    for f in filas_prog:
        clave = (f["ubicacion"], f["puesto"])
        if clave not in puestos and clave not in res:
            res[clave] = {"ubicacion": clave[0], "puesto": clave[1], "ubicacion_nombre": f["ubicacion_nombre"],
                          "puesto_nombre": f["puesto_nombre"], "motivo": "no_esta_en_maestro", "modalidad_texto": "", "personas": 0, "dias": 0}
    for clave, s in vistos.items():
        if clave in res:
            res[clave]["personas"] = len(s["personas"])
            res[clave]["dias"] = s["dias"]
    for clave, r in res.items():
        r["aprobado"] = clave in aprobados
    return sorted(res.values(), key=lambda r: (-r["dias"], r["ubicacion"], r["puesto"]))


def _resumen(personas, alertas, sin_mod, datos) -> dict:
    por_tipo: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for a in alertas:
        por_tipo[a.tipo][a.nomina] += 1
    por_nomina: dict[str, int] = defaultdict(int)
    validadas: dict[str, set[str]] = defaultdict(set)
    for x in personas:
        por_nomina[x["nomina"]] += 1
        validadas[x["nomina"]].add(x["cedula"])
    return {
        "personas": dict(por_nomina),
        "personas_con_alertas": len({(a.nomina, a.cedula) for a in alertas}),
        "alertas": len(alertas),
        "por_tipo": {t: dict(v) for t, v in por_tipo.items()},
        "puestos_sin_modalidad": len(sin_mod),
        "puestos_sin_modalidad_pendientes": sum(1 for x in sin_mod if not x["aprobado"]),
        "excluidas": {n: sum(1 for c in datos[n]["personas"] if c not in validadas[n]) for n in (QUINCENAL, MENSUAL) if datos.get(n)},
    }
