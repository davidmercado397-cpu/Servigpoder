"""Costeo por puestos: los hombres salen del servicio y la dotación de las tablas de compras según lo que lleva cada puesto.

El comercial escoge en cada puesto la dotación (gala u overol) y el arma (sin arma, fuego, fogeo o traumática). Con eso,
cada elemento del catálogo de la dotación de la tarifa entra si aplica al puesto, con su cantidad por hombre o por
puesto. Lo que el comercial no cambia (tarifas, hombres, salario, auxilio de transporte, Ley 2101, ICA y precios de
la dotación) se toma del catálogo o de lo que ya dejó el área contable en el costeo.
"""

from collections import defaultdict

DOTACIONES = {"gala": "Gala", "overol": "Overol"}
ARMAS = {"sin": "Sin arma", "fuego": "Arma de fuego", "fogeo": "Arma de fogeo", "traumatica": "Arma traumática"}
# A qué puestos aplica cada elemento de la dotación de la tarifa ("" = no entra solo: se agrega a mano)
APLICA = {
    "": "Solo si se agrega a mano", "todos": "Todos los puestos", "gala": "Dotación de gala", "overol": "Dotación de overol",
    "arma": "Puestos con arma (cualquiera)", "fuego": "Arma de fuego", "fogeo": "Arma de fogeo", "traumatica": "Arma traumática",
}


class CosteoInvalido(ValueError):
    pass


def _n(v, defecto: float = 0.0) -> float:
    try:
        return float(v) if v not in (None, "") else defecto
    except (TypeError, ValueError):
        return defecto


def aplica_al_puesto(aplica: str, puesto: dict) -> bool:
    arma = puesto.get("arma") or "sin"
    if aplica == "todos":
        return True
    if aplica in DOTACIONES:
        return (puesto.get("dotacion") or "gala") == aplica
    if aplica == "arma":
        return arma != "sin"
    return aplica in ARMAS and arma == aplica


def dotacion_automatica(servicios: list[dict], catalogo: list[dict]) -> list[dict]:
    """Dotación de la tarifa de todos los puestos, sumada por elemento. `catalogo`: elementos activos de la dotación
    de la tarifa (nombre, valor_unitario, vida_util_meses, entregas_anio, por_hombre, aplica, cantidad)."""
    filas: dict[str, dict] = {}
    for s in servicios:
        puestos = _n(s.get("cantidad"), 1)
        hombres = _n(s.get("hombres")) * puestos
        for c in catalogo:
            if not aplica_al_puesto(c.get("aplica") or "", s):
                continue
            cantidad = _n(c.get("cantidad"), 1) * (hombres if c.get("por_hombre") else puestos)
            if not cantidad:
                continue
            f = filas.setdefault(c["nombre"], {
                "nombre": c["nombre"], "valor_unitario": _n(c.get("valor_unitario")), "cantidad": 0.0,
                "vida_util_meses": c.get("vida_util_meses"), "entregas_anio": c.get("entregas_anio"),
                "aplica": c.get("aplica") or "", "por_hombre": bool(c.get("por_hombre")), "automatica": True})
            f["cantidad"] = round(f["cantidad"] + cantidad, 4)
    return list(filas.values())


def personal_automatico(servicios: list[dict], personal: list[dict]) -> list[dict]:
    """Los hombres de cada tipo de personal son los de los puestos que lo usan; un puesto sin tipo va al primero."""
    if not personal:
        return []
    indice = {}
    for i, p in enumerate(personal):
        indice.setdefault(p.get("nombre") or "", i)
    hombres: dict[int, float] = defaultdict(float)
    for s in servicios:
        i = indice.get(s.get("personal") or "", 0)
        hombres[i] += _n(s.get("hombres")) * _n(s.get("cantidad"), 1)
    return [{**p, "hombres": round(hombres.get(i, 0.0), 4)} for i, p in enumerate(personal)]


def preparar(datos: dict, catalogo: list[dict]) -> dict:
    """Costeo automático: hombres del personal y dotación de la tarifa calculados. Uno digitado a mano queda igual."""
    if not datos.get("automatico"):
        return datos
    servicios = datos.get("servicios") or []
    return {**datos, "personal": personal_automatico(servicios, datos.get("personal") or []),
            "dotacion_tarifa": dotacion_automatica(servicios, catalogo)}


def _anterior(lista: list[dict], i: int, clave: str, valor) -> dict | None:
    """La línea del costeo guardado que corresponde: la de la misma posición si coincide, si no la primera que coincida."""
    if i < len(lista) and lista[i].get(clave) == valor:
        return lista[i]
    return next((x for x in lista if x.get(clave) == valor), None)


def proteger(nuevo: dict, previo: dict | None, servicios_cat: list[dict], catalogo: list[dict], contable: bool, precios: bool) -> dict:
    """Deja los datos que el comercial no puede cambiar como estaban (o como vienen del catálogo).

    - contable (área contable): tarifas y hombres de los servicios, salario, auxilio de transporte, Ley 2101 e ICA;
    - precios (compras): valor, vida útil y entregas de la dotación.
    El comercial cambia el resto: puestos, cantidades, dotación y arma del puesto, horas extras y auxilios no prestacionales.
    """
    previo = previo or {}
    d = dict(nuevo)
    if not contable:
        if previo.get("automatico"):
            d["automatico"] = True
        d["ica_por_mil"] = previo.get("ica_por_mil")
        por_id = {s["id"]: s for s in servicios_cat}
        por_desc = {s["descripcion"]: s for s in servicios_cat}
        prev_srv = previo.get("servicios") or []
        servicios = []
        for i, s in enumerate(d.get("servicios") or []):
            ant = _anterior(prev_srv, i, "descripcion", s.get("descripcion"))
            cat = por_id.get(s.get("servicio_id")) or por_desc.get(s.get("descripcion"))
            base = ant or cat
            if base is None:
                raise CosteoInvalido(f"El servicio «{(s.get('descripcion') or '')[:60]}» no está en el catálogo de servicios")
            servicios.append({**s, "descripcion": base["descripcion"], "tarifa": _n(base.get("tarifa")), "hombres": _n(base.get("hombres")),
                              **({"servicio_id": cat["id"]} if cat else {})})
        d["servicios"] = servicios
        prev_per = previo.get("personal") or []
        personal = []
        for i, p in enumerate(d.get("personal") or []):
            ant = _anterior(prev_per, i, "nombre", p.get("nombre")) or {}
            x = {**p, "salario": ant.get("salario"), "auxilio_transporte": ant.get("auxilio_transporte", True)}
            x.pop("ley_2101", None)
            if ant.get("ley_2101") not in (None, ""):
                x["ley_2101"] = ant["ley_2101"]
            if not d.get("automatico"):
                x["hombres"] = _n(ant.get("hombres"))
            personal.append(x)
        d["personal"] = personal
    if not precios:
        grupos = ["dotacion_puesto"] + ([] if d.get("automatico") else ["dotacion_tarifa"])
        for grupo in grupos:
            cat = {c["nombre"]: c for c in catalogo if c["grupo"] == grupo}
            anteriores = previo.get(grupo) or []
            filas = []
            for x in d.get(grupo) or []:
                c = cat.get(x.get("nombre"))
                if c is not None:
                    filas.append({**x, "valor_unitario": _n(c.get("valor_unitario")), "vida_util_meses": c.get("vida_util_meses"),
                                  "entregas_anio": c.get("entregas_anio")})
                    continue
                igual = next((a for a in anteriores if all(a.get(k) == x.get(k) for k in
                                                          ("nombre", "valor_unitario", "vida_util_meses", "entregas_anio"))), None)
                if igual is None:
                    raise CosteoInvalido(f"«{x.get('nombre') or 'Sin nombre'}» no está en el catálogo de compras: pídale a compras que lo cree")
                filas.append(x)
            d[grupo] = filas
    return d
