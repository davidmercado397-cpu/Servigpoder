"""Novedades manuales de nómina, Excel de todo el periodo y comparación con el reporte de netos de Siigo."""

from io import BytesIO

from openpyxl import Workbook, load_workbook

from tests.conftest import archivo, xlsx
from tests.test_liquidador import API, _cargar
from tests.test_liquidador_nomina import HORA, _nomina, _periodo_con

DIAS = list(range(1, 16))


def _nov(cliente, pid, **datos):
    return cliente.post(f"{API}/periodos/{pid}/novedades", json={"documento": "1001", "descripcion": "Ajuste", **datos})


def test_novedades_manuales(admin):
    pid = _periodo_con(admin, 2026, 11, 1, [[1001, "1001", *(["A"] * 15)], [2002, "2002", *(["A"] * 15)]], DIAS)
    n0 = _nomina(admin, pid, "1001")

    r = _nov(admin, pid, tipo="mayor_valor", valor=50000, nomina_origen="Octubre Q2")
    assert r.status_code == 201, r.text
    n = _nomina(admin, pid, "1001")
    assert n["novedades_deduccion"] == 50000 and n["salud"] == n0["salud"] and n["neto"] == n0["neto"] - 50000

    assert _nov(admin, pid, tipo="menor_valor", valor=100000).status_code == 201
    n = _nomina(admin, pid, "1001")
    assert n["ibc"] == n0["ibc"] + 100000 and n["salud"] == n0["salud"] + 4000 and n["devengado"] == n0["devengado"] + 100000

    # Horas causadas en junio (dominical al 80 %) y agosto (al 90 %): cada una con la tarifa de su fecha
    assert _nov(admin, pid, tipo="recargos", horas={"sunday_surcharge": 8}, fecha_causacion="2026-06-14").status_code == 201
    assert _nov(admin, pid, tipo="horas_extras", horas={"overtime_day": 2, "sunday_surcharge": 0}, fecha_causacion="2026-08-10").status_code == 201
    n = _nomina(admin, pid, "1001")
    por_tipo = {x["tipo"]: x for x in n["novedades"]}
    assert por_tipo["recargos"]["valor"] == round(8 * HORA * 0.80) and "80 %" in por_tipo["recargos"]["calculo"]
    assert por_tipo["horas_extras"]["valor"] == round(2 * HORA * 1.25) and "tarifa del 01/07/2026" in por_tipo["horas_extras"]["calculo"]
    devengo = 100000 + round(8 * HORA * 0.80) + round(2 * HORA * 1.25)
    assert n["novedades_devengo"] == devengo and n["ibc"] == n0["ibc"] + devengo

    # Otro devengo no salarial: suma al pago, no a la base
    assert _nov(admin, pid, tipo="otro_devengo", valor=60000, salarial=False).status_code == 201
    n2 = _nomina(admin, pid, "1001")
    assert n2["ibc"] == n["ibc"] and n2["devengado"] == n["devengado"] + 60000

    # Validaciones
    assert _nov(admin, pid, tipo="menor_valor").status_code == 422
    assert _nov(admin, pid, tipo="recargos", horas={"inventado": 3}).status_code == 422
    assert _nov(admin, pid, tipo="mayor_valor", valor=1, documento="9999").status_code == 409
    assert _nov(admin, pid, tipo="recargos", horas={"ordinary_night": 2}, fecha_causacion="2026-12-01").status_code == 422

    # Lo pagado de más que no alcanza: se descuenta hasta el neto y avisa
    _nov(admin, pid, documento="2002", tipo="mayor_valor", valor=5_000_000)
    n3 = _nomina(admin, pid, "2002")
    assert n3["neto"] == 0 and any("quedan" in a for a in n3["alertas"])

    lista = admin.get(f"{API}/periodos/{pid}/novedades").json()["data"]
    assert len(lista) == 6 and all(x["valor"] is not None for x in lista)
    mayor = next(x for x in lista if x["documento"] == "1001" and x["tipo"] == "mayor_valor")
    assert admin.put(f"{API}/novedades/{mayor['id']}", json={"documento": "1001", "tipo": "mayor_valor", "descripcion": "Ajuste",
                                                             "valor": 20000}).status_code == 200
    assert _nomina(admin, pid, "1001")["novedades_deduccion"] == 20000
    assert admin.delete(f"{API}/novedades/{mayor['id']}").status_code == 200

    libro = load_workbook(BytesIO(admin.get(f"{API}/periodos/{pid}/nomina").content))
    filas = list(libro.worksheets[0].iter_rows(values_only=True))
    fila = dict(zip(filas[0], next(f for f in filas if f[0] == "1001")))
    assert fila["NOVEDADES DEVENGO"] == devengo + 60000 and fila["NOVEDADES DEDUCCION"] == 0
    assert "Novedades" in libro.sheetnames

    admin.post(f"{API}/periodos/{pid}/cerrar")
    assert _nov(admin, pid, tipo="menor_valor", valor=1000).status_code == 409


def test_importar_novedades(admin):
    pid = _periodo_con(admin, 2026, 11, 1, [[1001, "1001", *(["A"] * 15)]], DIAS)
    _nov(admin, pid, tipo="menor_valor", valor=1000)  # manual: se conserva al importar
    libro = load_workbook(BytesIO(admin.get(f"{API}/periodos/{pid}/novedades/plantilla").content))
    hoja = libro["Novedades"]
    enc = [c.value for c in hoja[1]]
    hoja.delete_rows(2)

    def fila(**v):
        hoja.append([v.get(c) for c in enc])

    fila(CEDULA=1001, TIPO="MAYOR VALOR PAGADO", DESCRIPCION="Pago doble", VALOR=30000, **{"NOMINA ORIGEN": "Oct Q2"})
    fila(CEDULA=1001, TIPO="RECARGOS PENDIENTES", **{"FECHA CAUSACION": "15/10/2026", "RECARGO NOCTURNO": 10})
    fila(CEDULA=1001, TIPO="OTRO DEVENGO", VALOR=5000, SALARIAL="NO")
    fila(CEDULA=7777, TIPO="MENOR VALOR PAGADO", VALOR=1)
    fila(CEDULA=1001, TIPO="BONO", VALOR=1)
    fila(CEDULA=1001, TIPO="HORAS EXTRAS")
    buf = BytesIO()
    libro.save(buf)
    r = admin.post(f"{API}/periodos/{pid}/novedades/importar", files=archivo(buf.getvalue(), "novedades.xlsx"))
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["cargadas"] == 3 and len(d["hallazgos"]) == 3
    n = _nomina(admin, pid, "1001")
    assert n["novedades_deduccion"] == 30000 and n["novedades_devengo"] == 1000 + round(10 * HORA * 0.35) + 5000
    # Importar de nuevo reemplaza las de Excel y conserva la manual
    r = admin.post(f"{API}/periodos/{pid}/novedades/importar", files=archivo(buf.getvalue(), "novedades.xlsx"))
    assert r.json()["data"]["reemplazadas"] == 3 and len(admin.get(f"{API}/periodos/{pid}/novedades").json()["data"]) == 4


def _siigo(hojas: dict[str, list[list]]) -> bytes:
    libro = Workbook()
    libro.remove(libro.active)
    for nombre, filas in hojas.items():
        h = libro.create_sheet(nombre)
        h.append(["NOMBRE", None, "CEDULA", "CONTRATO", "DETALLE", "INGRESOS", "DEDUCCIONES", "NETO A PAGAR"])
        for f in filas:
            h.append(f)
        h.append([None] * 7 + [sum(f[7] for f in filas)])
    buf = BytesIO()
    libro.save(buf)
    return buf.getvalue()


def test_excel_del_periodo_y_comparacion_con_siigo(admin, en_empresa):
    general = _periodo_con(admin, 2026, 11, 1, [[1001, "1001", *(["A"] * 15)], [2002, "2002", *(["A"] * 15)]], DIAS)
    otra = admin.post(f"{API}/periodos", json={"anio": 2026, "mes": 11, "quincena": 1, "nombre": "Cliente 2"}).json()["data"]["id"]
    _cargar(admin, otra, xlsx([["documento", "NOVIEMBRE", 1, 2], [3003, "3003", "A", "A"]]))
    a, b, c = (_nomina(admin, pid, doc) for pid, doc in ((general, "1001"), (general, "2002"), (otra, "3003")))

    r = admin.get(f"{API}/nominas-del-periodo/excel?anio=2026&mes=11&quincena=1")
    assert r.status_code == 200 and "nomina_periodo_2026_11_Q1" in r.headers["content-disposition"]
    libro = load_workbook(BytesIO(r.content))
    assert libro.sheetnames == ["Nomina", "Por persona", "Descuentos", "Novedades"]
    filas = list(libro["Nomina"].iter_rows(values_only=True))
    assert filas[0][0] == "NOMINA" and {f[1] for f in filas[1:-1]} == {"1001", "2002", "3003"} and filas[-1][0] == "TOTAL"
    assert admin.get(f"{API}/nominas-del-periodo/excel?anio=2030&mes=1&quincena=1").status_code == 404

    # Siigo: 1001 igual (con centavos), 2002 sin el auxilio de transporte, 3003 no está y 4004 solo en Siigo
    siigo = _siigo({
        "UNIDADES": [["A", None, 1001, "1001", "(4)", a["devengado"] + 0.3, a["deducciones"], a["neto"] + 0.3],
                     ["B", None, 2002, "2002-1", "(4)", b["devengado"] - b["auxilio"], b["deducciones"], b["neto"] - b["auxilio"]]],
        "CVC": [["D", None, 4004, "4004", "(4)", 500000, 40000, 460000]],
        "ACUAVALLE": [],
    })
    datos = {"anio": "2026", "mes": "11", "quincena": "1", "tolerancia": "1"}
    r = admin.post(f"{API}/comparar-siigo", files=archivo(siigo, "netos.xlsx"), data=datos)
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["resumen"]["cuadran"] == 1 and d["resumen"]["con_diferencia"] == 1
    assert d["resumen"]["solo_siigo"] == 1 and d["resumen"]["solo_sistema"] == 1
    filas = {f["documento"]: f for f in d["filas"]}
    assert filas["2002"]["estado"] == "diferencia" and filas["2002"]["diferencia"]["neto"] == round(b["auxilio"], 2)
    assert any("auxilio de transporte" in p for p in filas["2002"]["pistas"])
    assert filas["2002"]["siigo"]["hojas"] == [{"hoja": "UNIDADES", "ingresos": b["devengado"] - b["auxilio"], "deducciones": b["deducciones"],
                                                "neto": b["neto"] - b["auxilio"]}]
    assert filas["4004"]["estado"] == "solo_siigo" and filas["3003"]["estado"] == "solo_sistema"
    assert d["hojas_siigo"]["CVC"] == 460000 and set(d["nominas_sistema"]) == {"General", "Cliente 2"}
    assert round(d["resumen"]["neto_sistema"], 2) == round(a["neto"] + b["neto"] + c["neto"], 2)

    assert d["carga"]["archivo"] == "netos.xlsx"

    # Los datos quedan 24 horas: se vuelve a comparar sin subir el archivo, contra la nómina actual
    consulta = "anio=2026&mes=11&quincena=1"
    r = admin.get(f"{API}/comparar-siigo/excel?{consulta}")
    assert r.status_code == 200 and load_workbook(BytesIO(r.content)).sheetnames == ["Comparacion", "Resumen"]
    admin.post(f"{API}/descuentos", json={"documento": "1001", "tipo": "cuota", "descripcion": "Exequial", "valor_mensual": 20000,
                                          "desde": "2026-11-01"})
    admin.post(f"{API}/periodos/{general}/recalcular")
    otra_vez = admin.get(f"{API}/comparar-siigo?{consulta}").json()["data"]
    assert {f["documento"]: f for f in otra_vez["filas"]}["1001"]["estado"] == "diferencia"
    assert admin.get(f"{API}/comparar-siigo?anio=2026&mes=11&quincena=2").status_code == 404

    # Vencidos (más de 24 horas) se borran solos
    from datetime import datetime, timedelta, timezone

    from app.apps.liquidador.models import LiqSiigoCarga

    s = en_empresa("sera")
    s.query(LiqSiigoCarga).update({"vence_en": datetime.now(timezone.utc) - timedelta(minutes=1)})
    s.commit()
    assert admin.get(f"{API}/comparar-siigo?{consulta}").status_code == 404
    assert s.query(LiqSiigoCarga).count() == 0

    vacio = admin.post(f"{API}/comparar-siigo", files=archivo(xlsx([["hola"]]), "x.xlsx"), data=datos)
    assert vacio.status_code == 422
