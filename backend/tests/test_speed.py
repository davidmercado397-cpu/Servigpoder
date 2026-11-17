"""Nómina Speed: cálculo de la quincena (contra la Hoja1 del Excel de salarios), Listado, novedades, descuentos y cierre."""

import io
from datetime import date

import pytest
import xlsxwriter
from openpyxl import load_workbook

from app.apps.speed.services.calculo import Descuento, dias_contrato, liquidar, parametros_por_defecto

API = "/api/speed"
P = parametros_por_defecto()
GUARDA = {"salario": 1750905, "horas_extras": 485370, "ley_2466": 60000, "bonificaciones": 0, "rodamiento": 0, "comisiones": 0,
          "aplica_programacion": True, "fecha_ingreso": date(2025, 1, 10), "auxilio_listado": 249095}


def test_quincena_igual_a_la_hoja_del_excel():
    """Turno 2x2x2 de la Hoja1: neto mensual 2.366.468 → 1.183.234 por quincena."""
    r = liquidar(GUARDA, None, P, 2026, 11, 1, [])
    c = r.conceptos
    assert (c["salario"], c["auxilio_transporte"], c["horas_extras"], c["ley_2466"]) == (875453, 124548, 242685, 30000)
    assert r.ibc == 875453 + 242685 and c["salud"] == c["pension"] == 44726
    assert r.devengado == 1272686 and r.neto == 1183234 and r.alertas == []
    # Directora comercial: gana más de 2 SMLMV, sin auxilio de transporte; salud sobre el salario
    directora = {**GUARDA, "salario": 3502000, "horas_extras": 0, "ley_2466": 0, "aplica_programacion": False, "auxilio_listado": 0}
    r = liquidar(directora, None, P, 2026, 11, 2, [])
    assert r.conceptos["auxilio_transporte"] == 0 and r.conceptos["salud"] == 70040


def test_dias_programados_no_laborados_e_incapacidad():
    # Aplica a la regla: 10 días programados y 2 ausencias → variables por 8 días; salario y auxilio por 13
    r = liquidar(GUARDA, {"dias_programados": 10, "ausencias": 2}, P, 2026, 11, 1, [])
    assert r.dias["trabajados"] == 13 and r.dias["variables"] == 8
    assert r.conceptos["salario"] == round(1750905 / 30 * 13) and r.conceptos["horas_extras"] == round(485370 / 30 * 8)
    assert r.conceptos["auxilio_transporte"] == round(249095 / 30 * 13)
    # Quien no aplica: los días programados no cuentan, los variables van por días trabajados
    admin = {**GUARDA, "aplica_programacion": False, "bonificaciones": 300000}
    r = liquidar(admin, {"dias_programados": 3, "ausencias": 1}, P, 2026, 11, 1, [])
    assert r.dias["variables"] == 14 and r.conceptos["bonificaciones"] == 140000
    # Incapacidad de 4 días (la primera de la racha): 2 al 100 % y 2 al 66,67 % con piso del mínimo diario
    r = liquidar(GUARDA, {"incapacidad": 4}, P, 2026, 11, 1, [])
    diario = 1750905 / 30
    assert r.conceptos["incapacidad"] == round(2 * diario + 2 * diario)  # el 66,67 % del mínimo sube al mínimo
    alto = {**GUARDA, "salario": 3000000}
    r = liquidar(alto, {"incapacidad": 4, "incapacidad_previos": 1}, P, 2026, 11, 1, [])
    assert r.dias["incapacidad_100"] == 1 and r.conceptos["incapacidad"] == round(100000 + 3 * 100000 * 0.6667)
    assert r.conceptos["salario"] == round(100000 * 11) and r.ibc == r.conceptos["salario"] + r.conceptos["incapacidad"] + r.conceptos["horas_extras"]


def test_fecha_de_ingreso_comercial():
    assert dias_contrato(date(2026, 11, 22), 2026, 11, 2) == 9
    assert dias_contrato(date(2026, 11, 22), 2026, 11, 1) == 0
    assert dias_contrato(date(2026, 10, 31), 2026, 10, 2) == 1
    assert dias_contrato(date(2026, 2, 16), 2026, 2, 2) == 15  # febrero completa los 30 días comerciales


def test_descuentos_y_pagos_adicionales():
    desc = [Descuento(1, "cuota", "Mayor valor pagado", 100000, 150000), Descuento(2, "embargo", "Embargo alimentos", 200000, None),
            Descuento(3, "prestamo", "Préstamo", 2_000_000, 50000), Descuento(4, "adicional", "Menor valor pagado", 80000, 80000, salarial=True)]
    r = liquidar(GUARDA, None, P, 2026, 11, 1, desc)
    c = r.conceptos
    assert c["pago_adicional"] == 80000 and r.ibc == 875453 + 242685 + 80000  # el adicional salarial entra a salud y pensión
    assert (c["embargos"], c["prestamos"], c["cuotas"]) == (200000, 50000, 100000)
    assert r.aplicados == {4: 80000, 2: 200000, 3: 50000, 1: 100000}
    # Sin neto suficiente: lo que no alcanza no se descuenta y queda la alerta
    r = liquidar(GUARDA, {"ausencias": 14}, P, 2026, 11, 1, [Descuento(5, "prestamo", "Préstamo grande", 1_000_000, None)])
    assert r.neto == 0 and any("no alcanzó" in a for a in r.alertas)


def listado_xlsx(filas: list[list]) -> bytes:
    buf = io.BytesIO()
    libro = xlsxwriter.Workbook(buf, {"in_memory": True})
    hoja = libro.add_worksheet("LISTADO")
    hoja.write(0, 1, "SPEED SECURITY LTDA")
    hoja.write(3, 13, "Salarial")
    encabezado = ["ITEMS", "Identificacion__", "Apellidos y Nombres_", "Direccion Empleado", "Numero Telefonico", "Fecha de Ingreso",
                  "Tipo de Contrato", "TIPO DE NOMINA", "Cargo", "Área", "Puesto", "Cliente", "Tipo de turno", "Salario",
                  "Auxilio de transporte", "Horas extras", "Comisiones", "Ley 2466", "Bonificaciones", "Rodamiento", "Rodamiento",
                  "regla de programacion?"]
    hoja.write_row(4, 0, encabezado)
    fecha = libro.add_format({"num_format": "dd/mm/yyyy"})
    for i, f in enumerate(filas, start=5):
        for j, v in enumerate(f):
            if isinstance(v, date):
                hoja.write_datetime(i, j, v, fecha)
            elif v is not None:
                hoja.write(i, j, v)
    hoja.write_row(5 + len(filas), 13, [999999, 1, 2])  # fila de totales sin cédula
    otra = libro.add_worksheet("Hoja1")
    otra.write(0, 0, "TURNO 2X2X2")
    libro.close()
    return buf.getvalue()


def fila(n, cedula, nombre, salario=1750905, he=575880, regla="SI APLICA", ingreso=date(2025, 3, 1), bonif=0, nota=0):
    return [n, cedula, nombre, "Calle 1", "300", ingreso, "Fijo", "GENERAL", "Vigilante", "Produccion", "PORTERIA", "Cliente X",
            "Turnos 2x2x2", salario, 249095 if salario <= 3_501_810 else 0, he, 0, 60000 if regla == "SI APLICA" else 0, bonif, 0, nota, regla]


@pytest.fixture
def speed(admin):
    assert admin.post("/api/plataforma/empresa", json={"codigo": "speed"}).status_code == 200
    return admin


def test_flujo_completo_de_la_quincena(speed):
    archivo = listado_xlsx([fila(1, 1006306373, "UNO GUARDA"), fila(2, 52112768, "DOS ADMIN", salario=3502000, he=0, regla="NO APLICA",
                                                                    bonif=999990, nota="Auxilio de productividad ventas"),
                            fila(3, 80128728.0, "TRES NUEVO", ingreso=date(2026, 11, 22))])
    r = speed.post(f"{API}/empleados/importar", files={"archivo": ("SALARIOS COLABORADORES 2026.xlsx", archivo,
                                                                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["nuevos"] == 3 and r.json()["data"]["filas"] == 3
    emp = {e["cedula"]: e for e in speed.get(f"{API}/empleados").json()["data"]}
    assert emp["52112768"]["aplica_programacion"] is False and emp["52112768"]["nota"] == "Auxilio de productividad ventas"
    assert emp["80128728"]["fecha_ingreso"] == "2026-11-22" and "direccion" not in emp["1006306373"]

    p = speed.post(f"{API}/periodos", json={"anio": 2026, "mes": 11, "quincena": 2}).json()["data"]
    assert speed.post(f"{API}/periodos", json={"anio": 2026, "mes": 11, "quincena": 2}).status_code == 409
    uno = emp["1006306373"]["id"]
    assert speed.put(f"{API}/periodos/{p['id']}/novedades/{uno}", json={"dias_programados": 12, "ausencias": 1}).status_code == 200

    # Descuento: préstamo de 300.000 en cuotas de 200.000
    d = speed.post(f"{API}/descuentos", json={"empleado_id": uno, "tipo": "prestamo", "descripcion": "Préstamo", "valor_total": 300000,
                                              "cuota": 200000}).json()["data"]
    assert speed.post(f"{API}/descuentos", json={"empleado_id": uno, "tipo": "prestamo", "cuota": 1}).status_code == 422  # sin total

    r = speed.post(f"{API}/periodos/{p['id']}/liquidar")
    assert r.status_code == 200, r.text
    q = r.json()["data"]
    liq = {x["cedula"]: x for x in q["liquidaciones"]}
    assert set(liq) == {"1006306373", "52112768", "80128728"}
    assert liq["1006306373"]["dias"] == {**liq["1006306373"]["dias"], "trabajados": 14, "variables": 11}
    assert liq["1006306373"]["conceptos"]["prestamos"] == 200000
    assert liq["80128728"]["dias"]["contrato"] == 9  # ingresó el 22
    assert liq["52112768"]["conceptos"]["bonificaciones"] == round(999990 / 2)
    assert q["neto"] == pytest.approx(sum(x["neto"] for x in liq.values()))

    # El Excel de la quincena
    x = speed.get(f"{API}/periodos/{p['id']}/excel")
    assert x.status_code == 200
    hoja = load_workbook(io.BytesIO(x.content)).active
    titulos = [c.value for c in hoja[1]]
    assert "NETO A PAGAR" in titulos and hoja.cell(2, 1).value in liq

    # Cerrar: ya no se cambia; la siguiente quincena descuenta el saldo del préstamo (100.000)
    assert speed.post(f"{API}/periodos/{p['id']}/estado", json={"estado": "cerrado"}).status_code == 200
    assert speed.post(f"{API}/periodos/{p['id']}/liquidar").status_code == 409
    assert speed.delete(f"{API}/descuentos/{d['id']}").status_code == 409
    p2 = speed.post(f"{API}/periodos", json={"anio": 2026, "mes": 12, "quincena": 1}).json()["data"]
    q2 = speed.post(f"{API}/periodos/{p2['id']}/liquidar").json()["data"]
    assert next(x for x in q2["liquidaciones"] if x["cedula"] == "1006306373")["conceptos"]["prestamos"] == 100000
    assert speed.get(f"{API}/descuentos").json()["data"][0]["saldo"] == 0

    # Plantilla de novedades: se descarga y se vuelve a subir
    pl = speed.get(f"{API}/periodos/{p2['id']}/novedades/plantilla")
    libro = load_workbook(io.BytesIO(pl.content))
    h = libro["Novedades"]
    fila_uno = next(r for r in range(2, h.max_row + 1) if h.cell(r, 1).value == "1006306373")
    h.cell(fila_uno, 7).value = 3  # 3 días de incapacidad
    buf = io.BytesIO()
    libro.save(buf)
    r = speed.post(f"{API}/periodos/{p2['id']}/novedades/importar",
                   files={"archivo": ("novedades.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 200 and r.json()["data"]["cargadas"] >= 1
    nov = {n["cedula"]: n for n in speed.get(f"{API}/periodos/{p2['id']}/novedades").json()["data"]}
    assert nov["1006306373"]["incapacidad"] == 3

    # Volver a importar sin una persona la deja inactiva
    r = speed.post(f"{API}/empleados/importar", files={"archivo": ("l.xlsx", listado_xlsx([fila(1, 1006306373, "UNO GUARDA", he=600000)]),
                                                                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    data = r.json()["data"]
    assert data["actualizados"] == 1 and len(data["inactivados"]) == 2 and data["cambios"][0]["campo"] == "horas_extras"


def test_listado_sin_hoja_y_permisos(speed):
    buf = io.BytesIO()
    libro = xlsxwriter.Workbook(buf, {"in_memory": True})
    libro.add_worksheet("Otra").write(0, 0, "x")
    libro.close()
    r = speed.post(f"{API}/empleados/importar", files={"archivo": ("x.xlsx", buf.getvalue(),
                                                                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 422 and "LISTADO" in r.json()["error"]["message"]
    # En Servigpoder el desarrollo no está habilitado
    speed.post("/api/plataforma/empresa", json={"codigo": "servigpoder"})
    assert speed.get(f"{API}/periodos").status_code == 403
