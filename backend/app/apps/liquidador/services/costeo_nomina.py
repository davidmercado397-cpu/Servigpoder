"""Costeo de nómina: cuánto costaría a la empresa un Excel de turnos, con la misma lógica de la nómina pero sin
dejar rastro de pago (no descuenta préstamos ni embargos, no cuenta auxilios pagados, no gasta vacaciones y no
crea empleados). Las cédulas que no existen se costean con el salario mínimo.

Costo empresa = devengado + aportes del empleador + provisión de prestaciones, con % editables por costeo:
- Aportes (base: IBC de la nómina): salud 8,5 %, pensión 12 %, caja 4 %, ICBF 3 % y SENA 2 %; ARL según la clase de
  riesgo de la columna "arl" del Excel (si no viene, la configurada en Empleados; si tampoco, la clase por defecto del
  costeo) sobre el IBC sin vacaciones ni incapacidad. Exoneración (art. 114-1 E.T.): sin salud, ICBF ni SENA bajo 10 mínimos.
- Auxilio no prestacional: el valor mensual que se indica en el costeo (no los registrados en el módulo de auxilios);
  se descuenta por tiempo no laborado como en la nómina.
- Prestaciones: prima, cesantías e intereses sobre lo salarial más el auxilio de transporte (sin auxilios no
  prestacionales); vacaciones sobre el sueldo básico más el recargo nocturno.
"""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.apps.liquidador.models import LiqCosteo, LiqEmpleado
from app.apps.liquidador.services import calculo, festivos, importador, nomina, vacaciones as vac

# clave: (valor por defecto, nombre)
PARAMETROS: dict[str, tuple[float, str]] = {
    "salud": (8.5, "Salud empleador"),
    "pension": (12.0, "Pensión empleador"),
    "caja": (4.0, "Caja de compensación"),
    "icbf": (3.0, "ICBF"),
    "sena": (2.0, "SENA"),
    "prima": (8.33, "Prima de servicios"),
    "cesantias": (8.33, "Cesantías"),
    "intereses_cesantias": (1.0, "Intereses sobre cesantías"),
    "vacaciones": (4.17, "Vacaciones"),
}
APORTES = ("salud", "pension", "arl", "caja", "icbf", "sena")
NOMBRES_EXTRA = {"arl": "ARL (según la clase de riesgo)"}
ARL_DEFECTO = {"arl_tarifas": {str(c): t for c, t in importador.TARIFAS_ARL.items()}, "arl_clase": 4}
PRESTACIONES = ("prima", "cesantias", "intereses_cesantias", "vacaciones")
EXONERADOS = ("salud", "icbf", "sena")
TOPE_EXONERACION = 10  # salarios mínimos


def parametros_defecto() -> dict:
    return {**{k: v for k, (v, _) in PARAMETROS.items()}, "exonerado": True, **ARL_DEFECTO,
            "arl_tarifas": dict(ARL_DEFECTO["arl_tarifas"])}


def _completos(par: dict) -> dict:
    """Parámetros guardados con los valores por defecto que falten."""
    return {**parametros_defecto(), **{k: v for k, v in (par or {}).items() if k != "arl"}}


def clase_aplicada(r: dict, par: dict) -> int:
    return r.get("arl_clase") or int(par.get("arl_clase", 4))


def _p(valor: float) -> int:
    return int(nomina._pesos(Decimal(str(valor))))


def costo_empresa(n: dict, par: dict, smlmv: float, clase: int = 4) -> dict:
    """Aportes del empleador y provisión de prestaciones sobre la nómina calculada de una persona."""
    par = _completos(par)
    tarifa_arl = float(par["arl_tarifas"].get(str(clase), 0))
    exonerado = bool(par.get("exonerado")) and n.get("salario", 0) < TOPE_EXONERACION * smlmv
    ibc = n.get("ibc", 0)
    base_arl = max(ibc - n.get("vacaciones_valor", 0) - n.get("incapacidad", 0) - n.get("licencias_valor", 0), 0)  # sin riesgo: no laboró
    base_prest = n.get("devengado", 0) - n.get("auxilios_no_prestacionales", 0)
    base_vac = n.get("basico", 0) + n.get("valores", {}).get("ordinary_night", 0)
    aportes = {}
    for k in APORTES:
        if k == "arl":
            aportes[k] = _p(base_arl * tarifa_arl / 100)
        else:
            aportes[k] = 0 if (exonerado and k in EXONERADOS) else _p(ibc * par.get(k, 0) / 100)
    prestaciones = {k: _p((base_vac if k == "vacaciones" else base_prest) * par.get(k, 0) / 100) for k in PRESTACIONES}
    total_aportes, total_prest = sum(aportes.values()), sum(prestaciones.values())
    return {"exonerado": exonerado, "arl_clase": clase, "arl_tarifa": tarifa_arl, "base_aportes": ibc, "base_arl": base_arl, "base_prestaciones": base_prest,
            "base_vacaciones": base_vac, "aportes": aportes, "prestaciones": prestaciones, "total_aportes": total_aportes,
            "total_prestaciones": total_prest, "devengado": n.get("devengado", 0),
            "costo_total": _p(n.get("devengado", 0) + total_aportes + total_prest)}


def _totales(resultados: list[dict]) -> dict:
    t = {"personas": len(resultados), "no_registradas": sum(1 for r in resultados if not r["existe"]),
         "sin_arl": sum(1 for r in resultados if not r.get("arl_clase")),
         "devengado": 0, "neto": 0, "total_aportes": 0, "total_prestaciones": 0, "costo_total": 0,
         "aportes": {k: 0 for k in APORTES}, "prestaciones": {k: 0 for k in PRESTACIONES}}
    for r in resultados:
        c = r["costo"]
        t["devengado"] += r["nomina"].get("devengado", 0)
        t["neto"] += r["nomina"].get("neto", 0)
        for k in ("total_aportes", "total_prestaciones", "costo_total"):
            t[k] += c[k]
        for k in APORTES:
            t["aportes"][k] += c["aportes"][k]
        for k in PRESTACIONES:
            t["prestaciones"][k] += c["prestaciones"][k]
    return t


def recostear(db: Session, costeo: LiqCosteo) -> None:
    """Vuelve a calcular solo el costo empresa (los % cambiaron); la nómina de cada persona no cambia."""
    smlmv = float(nomina.Tarifas(db).en(costeo.hasta).smlmv)
    resultados = [{**r, "costo": costo_empresa(r["nomina"], costeo.parametros, smlmv, clase_aplicada(r, costeo.parametros))}
                  for r in costeo.resultados or []]
    costeo.resultados, costeo.totales = resultados, _totales(resultados)
    costeo.actualizado_en = datetime.now(timezone.utc)


def costear(db: Session, costeo: LiqCosteo, contenido: bytes) -> importador.Resumen:
    """Lee el Excel, cuenta las horas y liquida a cada persona en memoria; guarda solo el resultado."""
    leidas, res = importador.leer(db, costeo, contenido, con_arl=True)
    documentos = list({f.documento for f in leidas})
    existentes = {e.documento: e for e in db.scalars(select(LiqEmpleado).where(LiqEmpleado.documento.in_(documentos)))}
    personas: dict[int, tuple[object, bool, str]] = {}
    arl_excel: dict[int, int | None] = {}
    ids: dict[str, int] = {}
    dias = []
    for f in leidas:
        if f.documento not in ids:
            emp = existentes.get(f.documento)
            if emp is None:  # no se crea: se costea con el salario mínimo y los días hábiles por defecto
                emp = SimpleNamespace(id=-(len(ids) + 1), documento=f.documento, nombre=f.nombre, cargo=f.cargo, salario=None,
                                      dias_habiles=vac.HABILES_DEFECTO, fecha_ingreso=None, vacaciones_previas=Decimal("0"))
            ids[f.documento] = emp.id
            personas[emp.id] = (emp, f.documento in existentes, f.cargo)
        if f.arl is not None:
            arl_excel[ids[f.documento]] = f.arl
        for fecha, turno in f.dias:
            dias.append(SimpleNamespace(empleado_id=ids[f.documento], fecha=fecha, turno=turno, clase="", horas={}, tipo_dia=""))

    horas, conteo, semanas = calculo.contar(db, costeo, dias)
    tarifas = nomina.Tarifas(db)
    if not tarifas.lista:
        nomina.sembrar_tarifas(db)
        tarifas = nomina.Tarifas(db)
    reales = [eid for eid, (_, existe, _) in personas.items() if existe]
    fest = festivos.conjunto(db, costeo.desde, costeo.hasta)
    sugeridos = vac.promedios_sugeridos(db, reales, costeo)
    por_empleado: dict[int, list] = {}
    for d in dias:
        por_empleado.setdefault(d.empleado_id, []).append(d)

    smlmv = float(tarifas.en(costeo.hasta).smlmv)
    resultados = []
    for eid, (emp, existe, cargo) in sorted(personas.items(), key=lambda x: x[1][0].nombre):
        ctx = {"festivos": fest, "sugerido": sugeridos.get(eid, (Decimal("0"), Decimal("0")))[0],
               "meses": sugeridos.get(eid, (Decimal("0"), Decimal("0")))[1], "manual": None, "antes": 0}
        valor_aux = Decimal(str(costeo.auxilio_mensual or 0))
        auxilios = [SimpleNamespace(id=0, descripcion="Auxilio no prestacional (costeo)", valor_mensual=valor_aux, desde=costeo.desde,
                                    hasta=None, quincena="ambas", activo=True)] if valor_aux > 0 else []
        n = nomina.liquidar_empleado(emp, por_empleado.get(eid, []), costeo, tarifas, [], {}, auxilios, ctx)
        clase = arl_excel.get(eid) or getattr(emp, "arl_clase", None)
        origen = "excel" if arl_excel.get(eid) else ("empleado" if clase else None)
        n["alertas"] = [a for a in n["alertas"] if "vacaciones" not in a]  # el saldo no aplica a un costeo
        h = horas.get(eid, {})
        resultados.append({
            "documento": emp.documento, "nombre": emp.nombre, "cargo": cargo, "existe": existe,
            "arl_clase": clase, "arl_origen": origen, "auxilio_mensual": float(valor_aux),
            "dias": dict(conteo.get(eid, {})), "horas": {c.value: float(v) for c, v in h.items()},
            "total_horas": float(sum((h.get(c, Decimal("0")) for c in calculo.CONCEPTOS_TRABAJADOS), Decimal("0"))),
            "umbral_semanas": semanas.get(eid, []), "nomina": n,
            "costo": costo_empresa(n, costeo.parametros, smlmv, clase or int(costeo.parametros.get("arl_clase", 4))),
        })
    costeo.resultados, costeo.totales = resultados, _totales(resultados)
    costeo.advertencias = res.advertencias[:500]
    costeo.actualizado_en = datetime.now(timezone.utc)
    return res
