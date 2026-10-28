"""Nómina del liquidador. Valores calculados a mano con el mínimo 2026 ($1.750.905), auxilio $249.095 y 210
horas al mes: valor día = 58.363,5 · valor hora = 8.337,642857…"""

from io import BytesIO

from openpyxl import load_workbook

from tests.conftest import ACCESOS, entrar, xlsx
from tests.test_liquidador import API, _cargar, _excel_sep_q2, _quincena, _resultados

HORA = 1750905 / 210


def _periodo_con(cliente, anio, mes, quincena, filas, encabezado_dias) -> int:
    pid = _quincena(cliente, anio, mes, quincena)
    r = _cargar(cliente, pid, xlsx([["documento", "MES", *encabezado_dias], *filas]))
    assert r.status_code == 200, r.text
    return pid


def _nomina(cliente, pid, doc) -> dict:
    res = _resultados(cliente, pid)[doc]
    return cliente.get(f"{API}/periodos/{pid}/empleados/{res['empleado_id']}").json()["data"]["empleado"]["nomina"]


def test_tarifas_de_ley_por_vigencia(admin):
    r = admin.get(f"{API}/tarifas").json()
    t = {x["vigente_desde"]: x for x in r["data"]}
    assert set(t) == {"2026-01-01", "2026-07-01"}
    julio = t["2026-07-01"]
    assert (julio["smlmv"], julio["auxilio_transporte"], julio["horas_mes"], julio["salud_pct"], julio["pension_pct"]) == (1750905, 249095, 210, 4, 4)
    assert julio["porcentajes"] == {
        "ordinary_night": 35, "holiday_day_surcharge": 90, "sunday_surcharge": 90, "holiday_night_surcharge": 125,
        "sunday_night_surcharge": 125, "overtime_day": 125, "overtime_night": 175, "holiday_overtime_day": 215,
        "sunday_overtime_day": 215, "holiday_overtime_night": 265, "sunday_overtime_night": 265}
    assert t["2026-01-01"]["porcentajes"]["sunday_surcharge"] == 80 and t["2026-01-01"]["porcentajes"]["sunday_overtime_night"] == 255


def test_nomina_de_una_quincena(admin):
    pid = _quincena(admin)
    _cargar(admin, pid, _excel_sep_q2())
    # 1001: 13 turnos A (7 ordinarias + 1 extra diurna) y 2 descansos Z
    n = _nomina(admin, pid, "1001")
    assert n["dias_salario"] == 15 and n["dias_auxilio"] == 15 and n["salario_minimo"]
    assert n["basico"] == 875453  # 15 × 58.363,5
    assert n["valores"] == {"overtime_day": round(13 * HORA * 1.25)} == {"overtime_day": 135487}
    assert n["auxilio"] == 124548  # 15 × 249.095 / 30
    assert n["devengado"] == 875453 + 135487 + 124548 == 1135488
    assert n["ibc"] == 1010940 and n["salud"] == 40438 and n["pension"] == 40438
    assert n["neto"] == 1135488 - 80876 == 1054612

    # 3003: V×5 y LR (otro proceso) y AUS no se pagan; L sí; INC al 100 %; el auxilio solo por los 4 días A
    n = _nomina(admin, pid, "3003")
    assert n["dias_salario"] == 5 and n["dias_incapacidad"] == 2 and n["dias_sin_pago"] == 7 and n["dias_auxilio"] == 4
    assert n["basico"] == 291818 and n["incapacidad"] == 116727 and n["auxilio"] == 33213
    assert (n["incapacidad_empresa"], n["incapacidad_eps"]) == (2, 0)

    lista = admin.get(f"{API}/periodos/{pid}/resultados?orden=neto").json()
    netos = [x["neto"] for x in lista["data"]]
    assert netos == sorted(netos, reverse=True) and 1054612 in netos
    assert lista["meta"]["extra"]["totales"]["nomina"]["neto"] == sum(x["neto"] for x in lista["data"])


def test_incapacidad_larga_y_base_30(admin):
    # Octubre 2026 mensual (31 días): 31 turnos A suman 30 días de salario; INC del 1 al 5 → 2 empresa + 3 EPS
    dias = list(range(1, 32))
    pid = _periodo_con(admin, 2026, 10, 0, [[1, "1", *(["A"] * 31)], [2, "2", *(["INC"] * 5 + ["A"] * 26)]], dias)
    a, b = _nomina(admin, pid, "1"), _nomina(admin, pid, "2")
    assert a["dias_salario"] == 30 and a["basico"] == 1750905 and a["auxilio"] == 249095
    assert b["dias_incapacidad"] == 5 and (b["incapacidad_empresa"], b["incapacidad_eps"]) == (2, 3)
    assert b["incapacidad"] == round(5 * 1750905 / 30) and b["dias_salario"] == 25  # el 31 no suma
    # Febrero 2027 mensual: trabajar hasta el 28 completa los 30 días
    pid = _periodo_con(admin, 2027, 2, 0, [[1, "1", *(["A"] * 28)]], list(range(1, 29)))
    assert _nomina(admin, pid, "1")["dias_salario"] == 30 and _nomina(admin, pid, "1")["basico"] == 1750905


def test_cada_dia_usa_la_tarifa_vigente(admin):
    # Domingo 21-jun-2026 (dominical 80 %) y domingo 5-jul-2026 (90 %), turno D: 8,4 ordinarias + 2,8 extras
    jun = _periodo_con(admin, 2026, 6, 2, [[1, "1", "D"]], [21])
    jul = _periodo_con(admin, 2026, 7, 1, [[1, "1", "D"]], [5])
    assert _nomina(admin, jun, "1")["valores"] == {"sunday_surcharge": round(8.4 * HORA * 0.80), "sunday_overtime_day": round(2.8 * HORA * 2.05)}
    assert _nomina(admin, jul, "1")["valores"] == {"sunday_surcharge": round(8.4 * HORA * 0.90), "sunday_overtime_day": round(2.8 * HORA * 2.15)}

    # Cambiar un % aplica al recalcular
    t = next(x for x in admin.get(f"{API}/tarifas").json()["data"] if x["vigente_desde"] == "2026-07-01")
    datos = {k: t[k] for k in ("vigente_desde", "smlmv", "auxilio_transporte", "horas_mes", "salud_pct", "pension_pct", "porcentajes", "nota")}
    datos["porcentajes"] = {**t["porcentajes"], "sunday_surcharge": 100}
    assert admin.put(f"{API}/tarifas/{t['id']}", json=datos).status_code == 200
    admin.post(f"{API}/periodos/{jul}/recalcular")
    assert _nomina(admin, jul, "1")["valores"]["sunday_surcharge"] == round(8.4 * HORA)
    # Validaciones
    assert admin.put(f"{API}/tarifas/{t['id']}", json={**datos, "porcentajes": {"overtime_day": 125}}).status_code == 422
    assert admin.post(f"{API}/tarifas", json=datos).status_code == 409  # misma fecha


def test_salario_propio_y_auxilio(admin):
    pid = _quincena(admin)
    _cargar(admin, pid, _excel_sep_q2())
    eid = _resultados(admin, pid)["1001"]["empleado_id"]
    assert admin.put(f"{API}/empleados/{eid}/salario", json={"salario": 3000000}).status_code == 200
    admin.post(f"{API}/periodos/{pid}/recalcular")
    n = _nomina(admin, pid, "1001")
    assert n["basico"] == 1500000 and n["auxilio"] == 124548 and not n["salario_minimo"]  # 3 M ≤ 2 mínimos
    admin.put(f"{API}/empleados/{eid}/salario", json={"salario": 4000000})
    admin.post(f"{API}/periodos/{pid}/recalcular")
    assert _nomina(admin, pid, "1001")["auxilio"] == 0  # más de 2 mínimos
    admin.put(f"{API}/empleados/{eid}/salario", json={"salario": None})
    e = admin.get(f"{API}/empleados?q=1001").json()["data"][0]
    assert e["salario"] is None


def test_prestamo_con_saldo_y_embargo(admin):
    dias = list(range(1, 16))
    filas = [[1001, "1001", *(["A"] * 15)]]
    p1 = _periodo_con(admin, 2026, 11, 1, filas, dias)
    r = admin.post(f"{API}/descuentos", json={"documento": "1001", "tipo": "prestamo", "descripcion": "Préstamo celular",
                                              "valor_mensual": 100000, "monto_total": 120000, "desde": "2026-11-01"})
    assert r.status_code == 201, r.text
    prestamo = r.json()["data"]["id"]
    assert admin.post(f"{API}/descuentos", json={"documento": "1001", "tipo": "embargo", "descripcion": "Juzgado 3",
                                                 "porcentaje": 10, "desde": "2026-11-01"}).status_code == 201
    assert admin.post(f"{API}/descuentos", json={"documento": "1001", "tipo": "embargo", "descripcion": "x",
                                                 "porcentaje": 10, "valor_mensual": 5, "desde": "2026-11-01"}).status_code == 422
    assert admin.post(f"{API}/descuentos", json={"documento": "999", "tipo": "embargo", "descripcion": "x",
                                                 "porcentaje": 10, "desde": "2026-11-01"}).status_code == 404

    admin.post(f"{API}/periodos/{p1}/recalcular")
    n = _nomina(admin, p1, "1001")
    embargo, cuota = n["descuentos"]
    assert embargo["tipo"] == "embargo" and embargo["valor"] == round(n["ibc"] * 0.10)
    assert cuota["valor"] == 50000  # la mitad de la cuota mensual en la quincena
    assert n["neto"] == n["devengado"] - n["salud"] - n["pension"] - embargo["valor"] - 50000

    p2 = _periodo_con(admin, 2026, 11, 2, filas, list(range(16, 31)))
    assert next(x for x in _nomina(admin, p2, "1001")["descuentos"] if x["id"] == prestamo)["valor"] == 50000
    p3 = _periodo_con(admin, 2026, 12, 1, filas, dias)
    x = next(x for x in _nomina(admin, p3, "1001")["descuentos"] if x["id"] == prestamo)
    assert x["valor"] == 20000 and "saldo" in x["observacion"]  # solo el saldo pendiente
    d = next(x for x in admin.get(f"{API}/descuentos?q=celular").json()["data"])
    assert d["descontado"] == 120000 and d["saldo"] == 0
    assert admin.delete(f"{API}/descuentos/{prestamo}").status_code == 409  # ya aplicado: se desactiva

    r = admin.get(f"{API}/periodos/{p1}/nomina")
    assert r.headers["content-disposition"] == 'attachment; filename="nomina_2026_11_Q1.xlsx"'
    libro = load_workbook(BytesIO(r.content))
    assert libro.sheetnames == ["Nomina 2026-11-Q1", "Prestamos y embargos", "Auxilios no prestacionales", "Tarifas usadas"]
    filas_x = list(libro.worksheets[0].iter_rows(values_only=True))
    enc = filas_x[0]
    fila = dict(zip(enc, filas_x[1]))
    assert fila["DOCUMENTO"] == "1001" and fila["NETO A PAGAR"] == n["neto"] and fila["TOTAL DEVENGADO"] == n["devengado"]
    assert "VR EXTRAS ORDINARIA DIURNAS" in enc and "VR DIURNAS ORDINARIA" not in enc
    assert filas_x[-1][0] == "TOTAL"


def test_permisos_de_nomina(admin):
    pid = _quincena(admin)
    _cargar(admin, pid, _excel_sep_q2())
    admin.post("/api/roles", json={"nombre": "Solo horas", "permisos": ["liquidador.periodos.ver"]})
    rid = next(r["id"] for r in admin.get("/api/roles").json()["data"] if r["nombre"] == "Solo horas")
    admin.post("/api/usuarios", json={"accesos": ACCESOS, "username": "horas", "nombre": "Horas", "password": "clave-segura-1", "roles": [rid]})
    admin.post("/api/auth/logout")
    entrar(admin, "horas", "clave-segura-1")
    fila = admin.get(f"{API}/periodos/{pid}/resultados").json()
    assert fila["data"][0]["neto"] is None and "nomina" not in fila["meta"]["extra"]["totales"]
    assert _nomina(admin, pid, "1001") is None
    assert admin.get(f"{API}/tarifas").status_code == 403
    assert admin.get(f"{API}/descuentos").status_code == 403
    assert admin.get(f"{API}/periodos/{pid}/nomina").status_code == 403


def test_auxilios_no_prestacionales_y_quincena(admin):
    dias = list(range(1, 16))
    # 1001: 15 días A (7 + 1 extra diurna); 2002: 13 días A y 2 ausencias
    filas = [[1001, "1001", *(["A"] * 15)], [2002, "2002", *(["A"] * 13), "AUS", "AUS"], [3003, "3003", *(["A"] * 15)]]
    p1 = _periodo_con(admin, 2026, 12, 1, filas, dias)
    base = {"valor_mensual": 300000, "desde": "2026-12-01"}
    for doc in ("1001", "2002"):
        r = admin.post(f"{API}/auxilios", json={**base, "documento": doc, "descripcion": "Auxilio de rodamiento"})
        assert r.status_code == 201, r.text
    assert admin.post(f"{API}/auxilios", json={**base, "documento": "3003", "descripcion": "Bonificación", "valor_mensual": 2000000}).status_code == 201
    # Préstamo solo en la 2.ª quincena (valor completo en esa) y auxilio solo en la 1.ª
    assert admin.post(f"{API}/descuentos", json={"documento": "1001", "tipo": "prestamo", "descripcion": "Celular",
                                                 "valor_mensual": 80000, "desde": "2026-12-01", "quincena": "segunda"}).status_code == 201
    assert admin.post(f"{API}/auxilios", json={**base, "documento": "1001", "descripcion": "Alimentación", "valor_mensual": 100000,
                                               "quincena": "primera"}).status_code == 201
    assert admin.post(f"{API}/auxilios", json={**base, "documento": "1001", "descripcion": "x", "quincena": "tercera"}).status_code == 422
    admin.post(f"{API}/periodos/{p1}/recalcular")

    n = _nomina(admin, p1, "1001")
    # Rodamiento: mitad del mes en cada quincena (150.000); alimentación: completa en la 1.ª (100.000)
    assert sorted(x["valor"] for x in n["auxilios"]) == [100000, 150000] and n["auxilios_no_prestacionales"] == 250000
    horas = sum(n["valores"].values())  # extras y recargos (hay domingos y el festivo del 8)
    assert n["devengado"] == n["basico"] + horas + 250000 + n["auxilio"]
    # 250.000 no pasa del 40 % de la remuneración: la base de salud y pensión es solo lo salarial
    salarial = n["basico"] + horas
    assert n["exceso_no_salarial"] == 0 and n["ibc"] == salarial and not n["alertas"]
    # 1.000.000 (la mitad de 2.000.000) sí pasa del 40 %: el exceso entra en la base
    n3 = _nomina(admin, p1, "3003")
    sal3 = n3["basico"] + sum(n3["valores"].values())
    exceso = round(1000000 - 0.4 * (sal3 + 1000000))
    assert exceso > 0 and n3["exceso_no_salarial"] == exceso and n3["ibc"] == sal3 + exceso and n3["alertas"]
    assert n["prestamos"] == 0  # el préstamo es solo de la 2.ª quincena

    # Ausencias: 2 días × 300.000 / 30 = 20.000 menos
    n2 = _nomina(admin, p1, "2002")
    assert n2["dias_ausencia"] == 2 and n2["auxilios"][0]["valor"] == 150000 - 20000 and "ausencia" in n2["auxilios"][0]["calculo"]

    p2 = _periodo_con(admin, 2026, 12, 2, [[1001, "1001", *(["A"] * 16)]], list(range(16, 32)))
    n = _nomina(admin, p2, "1001")
    assert n["prestamos"] == 80000 and "solo 2.ª quincena" in n["descuentos"][0]["calculo"]
    assert [x["valor"] for x in n["auxilios"]] == [150000]  # la alimentación es solo de la 1.ª

    lista = admin.get(f"{API}/auxilios?q=1001").json()["data"]
    rodamiento = next(x for x in lista if x["descripcion"] == "Auxilio de rodamiento")
    assert rodamiento["pagado"] == 300000 and rodamiento["quincena"] == "ambas"
    assert admin.delete(f"{API}/auxilios/{rodamiento['id']}").status_code == 409  # ya se pagó: se desactiva
    libro = load_workbook(BytesIO(admin.get(f"{API}/periodos/{p1}/nomina").content))
    assert "Auxilios no prestacionales" in libro.sheetnames
    enc = [c.value for c in libro.worksheets[0][1]]
    assert "AUXILIOS NO PRESTACIONALES" in enc
