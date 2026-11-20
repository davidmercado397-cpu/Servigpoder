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
    col_inc = next(c for c in range(1, h.max_column + 1) if h.cell(1, c).value == "Días de incapacidad")
    h.cell(fila_uno, col_inc).value = 3  # 3 días de incapacidad
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


# --- Archivo de programación (2026-11-18) ------------------------------------------------------------------------

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_vacaciones_licencias_remuneradas_y_turnos_adicionales():
    p = {**P, "valor_tad": 70000, "valor_tan": 90000}
    # 3 días de vacaciones y 1 de luto: pagan salario, pero no auxilio ni variables; 1 renuncia descuenta todo
    r = liquidar(GUARDA, {"vacaciones": 3, "permisos_remunerados": 1, "desprogramados": 1, "turnos_tad": 2, "turnos_tan": 1}, p, 2026, 11, 1, [])
    d, c = r.dias, r.conceptos
    assert (d["trabajados"], d["vacaciones"], d["remunerados"], d["laborados"], d["variables"]) == (14, 3, 1, 10, 10)
    diario = 1750905 / 30
    assert c["salario"] == 641999 and c["vacaciones"] == 175091  # ÷ 30 × días, redondeo hacia arriba en ,5
    assert c["auxilio_transporte"] == round(249095 / 30 * 10) and c["horas_extras"] == round(485370 / 30 * 10)
    # Turnos adicionales: no son salariales
    assert c["turnos_adicionales"] == 2 * 70000 + 90000
    assert r.ibc == c["salario"] + c["vacaciones"] + c["horas_extras"]
    # Sin valor del turno adicional: alerta
    r = liquidar(GUARDA, {"turnos_tad": 1}, P, 2026, 11, 1, [])
    assert r.conceptos["turnos_adicionales"] == 0 and any("TAD" in a for a in r.alertas)
    # Dos incapacidades distintas en la quincena: cada una con sus 2 primeros días al 100 %
    alto = {**GUARDA, "salario": 3000000}
    r = liquidar(alto, {"incapacidad": 6, "incapacidad_tramos": [3, 3]}, P, 2026, 11, 1, [])
    assert r.dias["incapacidad_100"] == 4
    r = liquidar(alto, {"incapacidad": 6, "incapacidad_tramos": [3, 3], "incapacidad_previos": 5}, P, 2026, 11, 1, [])
    assert r.dias["incapacidad_100"] == 2  # la primera viene de antes


def programacion_xlsx(general: list[list], sandra: list[list] | None = None, primer_dia_letra: str = "D") -> bytes:
    """Imita el archivo: título, encabezado PUESTO/APELLIDOS/DOCUMENTO…, y por bloque las filas de semana y número de día.
    Una celda («TRASLADO…», n.º de días) se escribe combinada."""
    letras = ["D", "L", "M", "MM", "J", "V", "S"]
    inicio = letras.index(primer_dia_letra)
    buf = io.BytesIO()
    libro = xlsxwriter.Workbook(buf, {"in_memory": True})

    def hoja(nombre: str, filas: list[list]):
        h = libro.add_worksheet(nombre)
        h.write(0, 0, "PROGRAMACION GENERAL MES DE OCTUBRE")  # el título del archivo real a veces trae otro mes
        h.write_row(3, 0, ["PUESTO", "APELLIDOS Y NOMBRES", "DOCUMENTO", "MODALIDAD", "TELEFONO", "PUESTOS"])
        h.write(4, 0, "PROGRAMACIÓN Y DESCANSOS PARA PERSONAL DE PRUEBA")
        h.write_row(4, 6, [letras[(inicio + i) % 7] for i in range(31)])
        h.write_row(5, 6, list(range(1, 32)))
        for i, f in enumerate(filas, start=6):
            puesto, nombre, doc, dias = f
            h.write_row(i, 0, [puesto, nombre, doc, "24 HORAS", "300", "CONTROL DE ACCESO"])
            for j, v in enumerate(dias):
                if isinstance(v, tuple):
                    h.merge_range(i, 6 + j, i, 6 + j + v[1] - 1, v[0])
                elif v:
                    h.write(i, 6 + j, v)

    hoja("PROGRAMACION GENERAL", general)
    if sandra:
        hoja("SEÑORA SANDRA", sandra)
    libro.add_worksheet("CAJA MENOR").write_row(0, 0, ["FECHA", "CONCEPTO", "DOCUMENTO", "VALOR"])
    libro.close()
    return buf.getvalue()


def test_lector_de_programacion_traslados_y_codigos():
    from app.apps.speed.services import programacion as pg

    turnos = ["X", "D", "D", "N", "N"] * 3
    archivo = programacion_xlsx(
        [["TORRE 98", "UNO GUARDA", 1006306373, turnos],
         # Traslado: los días 1 a 4 están en otra fila (combinada con el texto), del 5 en adelante aquí
         ["HEROES 80", "DOS TRASLADO", 52112768, [("TRASLADO DE DISPONIBLE", 4), None, None, None,
                                                  "D", "TAD", "N", "N", "X", "VAC", "VAC", "INC", "INC", "INC", "X"]],
         ["DISPONIBLE", "DOS TRASLADO", 52112768, ["X", "AUS", "X", "PR", ("TRASLADO A HEROES 80", 11)]],
         ["SIN DOC", "TRES SIN DOCUMENTO", None, ["D", "D", "TAN"]]],
        sandra=[["IRAKA", "UNO GUARDA", 1006306373, ["X", "D", "RUN"]]])
    personas, _, info = pg.leer(archivo)
    assert info["hojas"] == ["PROGRAMACION GENERAL", "SEÑORA SANDRA"] and "nombre:tres sin documento" in personas
    dos = personas["52112768"]
    assert [dos.dias.get(d) for d in range(1, 16)] == ["X", "AUS", "X", "PR", "D", "TAD", "N", "N", "X", "VAC", "VAC", "INC", "INC", "INC", "X"]
    n = pg.novedad(dos, 2026, 11, 1, None)
    assert (n["ausencias"], n["permisos_remunerados"], n["vacaciones"], n["incapacidad"], n["turnos_tad"]) == (1, 1, 2, 3, 1)
    assert n["dias_programados"] == 15 and n["programacion"]["tramos_incapacidad"] == [3]
    # Dos filas con códigos distintos el mismo día: gana el que afecta el pago (RUN) y queda el aviso
    uno = pg.novedad(personas["1006306373"], 2026, 11, 1, None)
    assert uno["desprogramados"] == 1 and uno["programacion"]["conflictos"] == ["día 3: D y RUN (se tomó RUN)"]
    # Días vacíos: sin programación (no pagan variables); los días antes del ingreso no cuentan
    tres = pg.novedad(personas["nombre:tres sin documento"], 2026, 11, 1, date(2026, 11, 2))
    assert tres["turnos_tan"] == 1 and tres["sin_programacion"] == 12 and tres["dias_programados"] == 2
    # Noviembre de 2026 empieza en domingo: el archivo corresponde; con octubre avisa
    assert pg.revisar_mes(info["semana"], 2026, 11) is None and pg.revisar_mes(info["semana"], 2026, 10)


def test_importar_programacion_en_la_quincena(speed):
    archivo = listado_xlsx([fila(1, 1006306373, "UNO GUARDA"), fila(2, 52112768, "DOS ADMIN", regla="NO APLICA"),
                            fila(3, 80128728, "TRES SIN DOCUMENTO"), fila(4, 79000001, "CUATRO FALTA")])
    assert speed.post(f"{API}/empleados/importar", files={"archivo": ("l.xlsx", archivo, XLSX)}).status_code == 200
    assert speed.put(f"{API}/parametros", json={"valor_tan": 90000}).status_code == 200
    p1 = speed.post(f"{API}/periodos", json={"anio": 2026, "mes": 11, "quincena": 1}).json()["data"]
    p2 = speed.post(f"{API}/periodos", json={"anio": 2026, "mes": 11, "quincena": 2}).json()["data"]
    emp = {e["cedula"]: e["id"] for e in speed.get(f"{API}/empleados").json()["data"]}
    # A mano antes de la programación: se reemplaza al importar (la observación se conserva)
    speed.put(f"{API}/periodos/{p1['id']}/novedades/{emp['1006306373']}", json={"ausencias": 5, "observacion": "a mano"})

    q1 = ["X", "D", "D", "N", "N", "X", "X", "D", "D", "N", "N", "X", "INC", "INC", "INC"]
    archivo = programacion_xlsx([["TORRE 98", "UNO GUARDA", 1006306373, q1],
                                 ["TORRE 98", "DOCUMENTO SIN TRES", None, ["D", "TAN"] + ["X"] * 13],
                                 ["OTRO", "NO ESTA EN EL LISTADO", 123456, ["D"] * 15]])
    r = speed.post(f"{API}/periodos/{p1['id']}/programacion/importar", files={"archivo": ("programacion.xlsx", archivo, XLSX)})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["cargadas"] == 2 and d["no_encontrados"][0]["cedula"] == "123456"
    assert d["por_nombre"][0]["cedula"] == "80128728"  # cruzada por el nombre (sin documento en la programación)
    assert [x["cedula"] for x in d["sin_programacion"]] == ["79000001"]  # aplica a la regla y no viene
    nov = {n["cedula"]: n for n in speed.get(f"{API}/periodos/{p1['id']}/novedades").json()["data"]}
    assert nov["1006306373"]["ausencias"] == 0 and nov["1006306373"]["incapacidad"] == 3 and nov["1006306373"]["origen"] == "programacion"
    assert nov["1006306373"]["observacion"] == "a mano" and nov["1006306373"]["programacion"]["dias"]["13"] == "INC"
    liq = {x["cedula"]: x for x in speed.post(f"{API}/periodos/{p1['id']}/liquidar").json()["data"]["liquidaciones"]}
    assert liq["1006306373"]["dias"]["incapacidad_100"] == 2 and liq["80128728"]["conceptos"]["turnos_adicionales"] == 90000

    # La incapacidad sigue en la 2.ª quincena: ya no paga otra vez 2 días al 100 %
    q2 = ["INC", "INC", "X"] + ["D"] * 12
    archivo = programacion_xlsx([["TORRE 98", "UNO GUARDA", 1006306373, [None] * 15 + q2]])
    r = speed.post(f"{API}/periodos/{p2['id']}/programacion/importar", files={"archivo": ("p2.xlsx", archivo, XLSX)})
    assert r.status_code == 200, r.text
    nov2 = {n["cedula"]: n for n in speed.get(f"{API}/periodos/{p2['id']}/novedades").json()["data"]}
    assert nov2["1006306373"]["incapacidad"] == 2 and nov2["1006306373"]["incapacidad_previos"] == 3
    liq2 = {x["cedula"]: x for x in speed.post(f"{API}/periodos/{p2['id']}/liquidar").json()["data"]["liquidaciones"]}
    assert liq2["1006306373"]["dias"]["incapacidad_100"] == 0

    # Volver a subir la programación de la 1.ª sin una persona le quita la novedad que venía de la programación
    archivo = programacion_xlsx([["TORRE 98", "UNO GUARDA", 1006306373, q1]])
    d = speed.post(f"{API}/periodos/{p1['id']}/programacion/importar", files={"archivo": ("p.xlsx", archivo, XLSX)}).json()["data"]
    assert d["quitadas"] == 1
    # Un Excel sin programación
    malo = listado_xlsx([fila(1, 1, "X")])
    r = speed.post(f"{API}/periodos/{p1['id']}/programacion/importar", files={"archivo": ("x.xlsx", malo, XLSX)})
    assert r.status_code == 422 and "DOCUMENTO" in r.json()["error"]["message"]


def test_quien_no_esta_en_el_listado_se_crea_asigna_o_descarta(speed):
    archivo = listado_xlsx([fila(1, 1006306373, "UNO GUARDA"), fila(2, 52112768, "DOS GUARDA")])
    assert speed.post(f"{API}/empleados/importar", files={"archivo": ("l.xlsx", archivo, XLSX)}).status_code == 200
    p = speed.post(f"{API}/periodos", json={"anio": 2026, "mes": 11, "quincena": 1}).json()["data"]
    assert speed.get(f"{API}/periodos/{p['id']}/programacion").json()["data"] is None
    # Un ingreso nuevo desde el día 13, una cédula mal escrita y un error
    archivo = programacion_xlsx([["OIKOS", "NUEVO INGRESO", 79557182, [None] * 12 + ["IND", "D", "N"]],
                                 ["TORRE", "DOS GUARDA MAL", 5211276, ["D", "N", "X"] * 5],
                                 ["TORRE", "NADIE", 111, ["D"] * 15]])
    r = speed.post(f"{API}/periodos/{p['id']}/programacion/importar", files={"archivo": ("p.xlsx", archivo, XLSX)}).json()["data"]
    assert len(r["no_encontrados"]) == 3 and r["archivo"] == "p.xlsx"
    nuevo = next(x for x in r["no_encontrados"] if x["cedula"] == "79557182")
    assert nuevo["ingreso_sugerido"] == "2026-11-13" and nuevo["estado"] == "pendiente"
    # El resultado queda guardado en la quincena
    guardado = speed.get(f"{API}/periodos/{p['id']}/programacion").json()["data"]
    assert [x["clave"] for x in guardado["no_encontrados"]] == [x["clave"] for x in r["no_encontrados"]]

    url = f"{API}/periodos/{p['id']}/programacion/resolver"
    datos = {"cedula": "79557182", "nombre": "NUEVO INGRESO", "fecha_ingreso": "2026-11-13", "cargo": "Vigilante", "salario": 1750905,
             "horas_extras": 450000}
    r = speed.post(url, json={"clave": "79557182", "accion": "crear", "empleado": datos})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["estado"] == "creado"
    assert speed.post(url, json={"clave": "79557182", "accion": "descartar"}).status_code == 409  # ya resuelto
    # Crear con una cédula que ya existe: debe asignarse
    assert speed.post(url, json={"clave": "5211276", "accion": "crear", "empleado": {**datos, "cedula": "52112768"}}).status_code == 409
    assert speed.post(url, json={"clave": "5211276", "accion": "asignar", "cedula": "52112768"}).status_code == 200
    assert speed.post(url, json={"clave": "111", "accion": "descartar"}).status_code == 200

    nov = {n["cedula"]: n for n in speed.get(f"{API}/periodos/{p['id']}/novedades").json()["data"]}
    assert nov["79557182"]["origen"] == "programacion" and nov["79557182"]["programacion"]["dias"]["13"] == "IND"
    assert nov["52112768"]["dias_programados"] == 15
    estados = {x["clave"]: x["estado"] for x in speed.get(f"{API}/periodos/{p['id']}/programacion").json()["data"]["no_encontrados"]}
    assert estados == {"79557182": "creado", "5211276": "asignado", "111": "descartado"}
    liq = {x["cedula"]: x for x in speed.post(f"{API}/periodos/{p['id']}/liquidar").json()["data"]["liquidaciones"]}
    assert liq["79557182"]["dias"]["contrato"] == 3 and liq["79557182"]["dias"]["variables"] == 3
    assert "111" not in liq


def test_plano_de_novedades_para_world_office(speed):
    from datetime import datetime

    archivo = listado_xlsx([fila(1, 1006306373, "UNO GUARDA"), fila(2, 52112768, "DOS ADMIN", salario=3000000, regla="NO APLICA")])
    assert speed.post(f"{API}/empleados/importar", files={"archivo": ("l.xlsx", archivo, XLSX)}).status_code == 200
    assert speed.put(f"{API}/parametros", json={"valor_tad": 75000, "valor_tan": 82000}).status_code == 200
    p = speed.post(f"{API}/periodos", json={"anio": 2026, "mes": 11, "quincena": 1}).json()["data"]
    uno = ["X", "TAD", "AUS", "N", "INC", "INC", "INC", "X", "LUT", "TAN", "D", "X", "PR", "D", "N"]
    dos = ["D", "D", "INC", "INC", "INC", "D", "D", "D", "D", "D", "D", "D", "D", "D", "D"]
    archivo = programacion_xlsx([["TORRE", "UNO GUARDA", 1006306373, uno], ["OFICINA", "DOS ADMIN", 52112768, dos]])
    assert speed.post(f"{API}/periodos/{p['id']}/programacion/importar", files={"archivo": ("p.xlsx", archivo, XLSX)}).status_code == 200

    assert speed.get(f"{API}/periodos/{p['id']}/world-office/avisos").json()["data"]["documento"] == 75
    r = speed.get(f"{API}/periodos/{p['id']}/world-office?documento=80")
    assert r.status_code == 200 and r.headers["x-filas"] == "9"
    libro = load_workbook(io.BytesIO(r.content))
    assert libro.sheetnames == ["GENERAL"]
    hoja = libro["GENERAL"]
    assert [c.value for c in hoja[1]] == [
        "Encab: Empresa", "Encab: Tipo Documento", "Encab: Prefijo", "Encab: Documento Número", "Detalle: Empleado", "Detalle: Concepto",
        "Detalle: Fecha", "Detalle: Cantidad", "Detalle: Valor", "Detalle: Unidad Medida", "Detalle: Centro Costos", "Detalle: Nota",
        "Detalle: Proceso ", "Detalle: Pasa a Nómina", "Detalle: Aprobado", "Detalle: Usuario Aprueba", "Detalle: Código Centro Costos"]
    # Se propone el siguiente número de documento
    assert speed.get(f"{API}/periodos/{p['id']}/world-office/avisos").json()["data"]["documento"] == 81
    filas = [[c.value for c in f][4:] for f in hoja.iter_rows(min_row=2)]
    assert {tuple(c.value for c in f[:4]) for f in hoja.iter_rows(min_row=2)} == {("SPEED SECURITY LTDA", "NNO", "NOVNO", 80)}
    uno_f = [f for f in filas if f[0] == 1006306373]
    tipos = {(f[2].day, f[1]): f[4] for f in uno_f}
    diario = 1750905 / 30
    assert tipos == {(2, "Auxilio de Compensacion por descanso Diurno"): 75000, (3, "Ausencias"): round(diario, 2),
                     (5, "incapacidades Empresa 100%"): round(diario, 2),  # 5 y 6 en una fila
                     (7, "Incapacidades EPS 100%"): round(diario, 2),  # el 66,67 % del mínimo sube al mínimo
                     (9, "LICENCIA POR LUTO"): round(diario, 2), (10, "Auxilio de compensacion por descanso Nocturno"): 82000,
                     (13, "Licencia Remunerada"): round(diario, 2)}
    inc = next(x for x in uno_f if x[2].day == 5)
    assert inc[3] == 2 and inc[7] == "NOVEDADES 1RA QUINCENA NOVIEMBRE2026-5 al 6 NOV: Incapacidad 2 días"
    f = next(x for x in uno_f if x[2].day == 3)
    assert f[2] == datetime(2026, 11, 3) and f[3] == 1 and f[5] == "D" and f[6] == "Produccion"
    assert f[7] == "NOVEDADES 1RA QUINCENA NOVIEMBRE2026-3 NOV: Ausencia" and f[8] is None and f[9:] == [-1, -1, None, None]
    # Administrativo, salario alto: desde el 3.er día de incapacidad, al 66,67 %
    dos_f = {x[2].day: x for x in filas if x[0] == 52112768}
    assert dos_f[3][6] == "Administrativo" and dos_f[3][3] == 2 and dos_f[5][1] == "Incapacidades EPS 66.67%"
    assert dos_f[5][4] == round(100000 * 0.6667, 2) and dos_f[5][3] == 1

    # El concepto se cambia en Parámetros
    conceptos = speed.get(f"{API}/conceptos-wo").json()["data"]
    cambio = [{**c, "concepto": "Ausencia injustificada"} if c["codigo"] == "AUS" else c for c in conceptos]
    assert speed.put(f"{API}/conceptos-wo", json=cambio).status_code == 200
    hoja = load_workbook(io.BytesIO(speed.get(f"{API}/periodos/{p['id']}/world-office").content))["GENERAL"]
    tipos = {(f[6].value.day, f[5].value) for f in hoja.iter_rows(min_row=2) if f[4].value == 1006306373}
    assert (3, "Ausencia injustificada") in tipos
    assert speed.get(f"{API}/periodos/{p['id']}/world-office/avisos").json()["data"]["filas"] == 9


def test_vacaciones_y_retiros_de_la_quincena(speed):
    archivo = listado_xlsx([fila(1, 1006306373, "UNO GUARDA"), fila(2, 52112768, "DOS RENUNCIA"), fila(3, 80128728, "TRES SALE")])
    assert speed.post(f"{API}/empleados/importar", files={"archivo": ("l.xlsx", archivo, XLSX)}).status_code == 200
    p = speed.post(f"{API}/periodos", json={"anio": 2026, "mes": 11, "quincena": 1}).json()["data"]
    uno = ["VAC"] * 4 + ["D", "N", "X"] + ["VAC"] * 8
    dos = ["D", "N", "X", "D", "N"] + ["RUN"] * 10
    tres = ["D"] * 15
    archivo = programacion_xlsx([["T", "UNO GUARDA", 1006306373, uno], ["T", "DOS RENUNCIA", 52112768, dos], ["T", "TRES SALE", 80128728, tres]])
    assert speed.post(f"{API}/periodos/{p['id']}/programacion/importar", files={"archivo": ("p.xlsx", archivo, XLSX)}).status_code == 200
    # El Listado nuevo ya no trae a TRES: queda inactivo y se muestra como posible retiro
    archivo = listado_xlsx([fila(1, 1006306373, "UNO GUARDA"), fila(2, 52112768, "DOS RENUNCIA")])
    assert speed.post(f"{API}/empleados/importar", files={"archivo": ("l.xlsx", archivo, XLSX)}).status_code == 200

    d = speed.get(f"{API}/periodos/{p['id']}/vacaciones-retiros").json()["data"]
    v = d["vacaciones"][0]
    assert v["cedula"] == "1006306373" and v["dias"] == 12 and v["tramos"] == [["2026-11-01", "2026-11-04"], ["2026-11-08", "2026-11-15"]]
    assert v["desde_antes"] and v["sigue"] and v["centro"] == "Produccion"
    retiros = {r["cedula"]: r for r in d["retiros"]}
    assert retiros["52112768"]["ultimo_dia"] == "2026-11-05" and retiros["52112768"]["primer_dia_retiro"] == "2026-11-06"
    assert "inactivo" in retiros["80128728"]["motivo"]
    x = speed.get(f"{API}/periodos/{p['id']}/vacaciones-retiros/excel")
    assert x.status_code == 200 and load_workbook(io.BytesIO(x.content)).sheetnames == ["Vacaciones", "Retiros", "Incapacidad +180", "Sin programación"]
    # Quien tiene vacaciones o retiro no se liquida en esta nómina (va en otra)
    q = speed.post(f"{API}/periodos/{p['id']}/liquidar").json()["data"]
    assert q["liquidaciones"] == [] and q["excluidos"] == 3

    # Retiro registrado en la plataforma: no se liquida y el Listado no lo reactiva
    archivo = listado_xlsx([fila(1, 1006306373, "UNO GUARDA"), fila(2, 52112768, "DOS RENUNCIA"), fila(4, 1003000004, "CUATRO RETIRADA")])
    assert speed.post(f"{API}/empleados/importar", files={"archivo": ("l.xlsx", archivo, XLSX)}).status_code == 200
    cuatro = next(e for e in speed.get(f"{API}/empleados").json()["data"] if e["cedula"] == "1003000004")
    r = speed.post(f"{API}/empleados/{cuatro['id']}/retirar", json={"fecha_retiro": "2026-11-10", "motivo": "Renuncia, ya liquidada"})
    assert r.status_code == 200 and r.json()["data"]["activo"] is False
    r = speed.post(f"{API}/empleados/importar", files={"archivo": ("l.xlsx", archivo, XLSX)}).json()["data"]
    assert r["retirados_en_archivo"][0]["cedula"] == "1003000004" and r["reactivados"] == 0
    d = speed.get(f"{API}/periodos/{p['id']}/vacaciones-retiros").json()["data"]
    assert any(x["cedula"] == "1003000004" and "Renuncia, ya liquidada" in x["motivo"] for x in d["retiros"])
    retirado = {x["cedula"]: x["retirado"] for x in d["retiros"]}
    assert retirado["1003000004"] == "2026-11-10" and retirado["52112768"] is None  # a DOS (RUN) se le puede dar «Retirar»
    liq = speed.post(f"{API}/periodos/{p['id']}/liquidar").json()["data"]["liquidaciones"]
    assert "1003000004" not in {x["cedula"] for x in liq}
    assert speed.post(f"{API}/empleados/{cuatro['id']}/reintegrar").json()["data"]["activo"] is True


def test_cruce_por_nombre_escrito_distinto(speed):
    archivo = listado_xlsx([fila(1, 1018000001, "UCHUBO GOMEZ JOHN FELIPE"), fila(2, 52112768, "PEREZ LOPEZ CARLOS ANDRES")])
    assert speed.post(f"{API}/empleados/importar", files={"archivo": ("l.xlsx", archivo, XLSX)}).status_code == 200
    p = speed.post(f"{API}/periodos", json={"anio": 2026, "mes": 11, "quincena": 1}).json()["data"]
    dias = ["D", "AUS", "N", "X", "X"] * 3
    archivo = programacion_xlsx([["METRO", "UCHUBO GOMEZ JHON FELIPE", None, dias],  # sin cédula y JHON en vez de JOHN
                                 ["TORRE", "PEREZ LOPEZ CARLOS ANDRE", 5211276, dias]])  # con otra cédula: solo se sugiere
    d = speed.post(f"{API}/periodos/{p['id']}/programacion/importar", files={"archivo": ("p.xlsx", archivo, XLSX)}).json()["data"]
    assert d["por_nombre"] == [{"nombre": "UCHUBO GOMEZ JHON FELIPE", "cedula": "1018000001", "en_archivo": "sin documento",
                                "nombre_listado": "UCHUBO GOMEZ JOHN FELIPE", "parecido": True}]
    assert d["no_encontrados"][0]["sugeridos"] == [{"cedula": "52112768", "nombre": "PEREZ LOPEZ CARLOS ANDRES"}]
    nov = {n["cedula"]: n for n in speed.get(f"{API}/periodos/{p['id']}/novedades").json()["data"]}
    assert nov["1018000001"]["ausencias"] == 3


def test_en_la_programacion_sin_ningun_turno_no_se_paga(speed):
    archivo = listado_xlsx([fila(1, 79806791, "NAVARRO INCAPACITADO"), fila(2, 52112768, "DOS GUARDA")])
    assert speed.post(f"{API}/empleados/importar", files={"archivo": ("l.xlsx", archivo, XLSX)}).status_code == 200
    p = speed.post(f"{API}/periodos", json={"anio": 2026, "mes": 11, "quincena": 1}).json()["data"]
    archivo = programacion_xlsx([["INCAPACITADO AV15", "NAVARRO INCAPACITADO", 79806791, [None] * 15],
                                 ["TORRE", "DOS GUARDA", 52112768, [None] * 3 + ["D", "N", "X"] * 4]])
    d = speed.post(f"{API}/periodos/{p['id']}/programacion/importar", files={"archivo": ("p.xlsx", archivo, XLSX)}).json()["data"]
    assert [x["cedula"] for x in d["sin_turnos"]] == ["79806791"]
    liq = {x["cedula"]: x for x in speed.post(f"{API}/periodos/{p['id']}/liquidar").json()["data"]["liquidaciones"]}
    nav = liq["79806791"]
    assert nav["devengado"] == 0 and nav["dias"]["trabajados"] == 0 and any("sin ningún turno" in a for a in nav["alertas"])
    # Con algunos días vacíos sí se paga el salario (solo no paga variables esos días)
    assert liq["52112768"]["dias"]["trabajados"] == 15 and liq["52112768"]["dias"]["variables"] == 12
    # En el plano de World Office van sus 15 días como desprogramado
    hoja = load_workbook(io.BytesIO(speed.get(f"{API}/periodos/{p['id']}/world-office").content))["GENERAL"]
    filas = [[c.value for c in f] for f in hoja.iter_rows(min_row=2) if f[4].value == 79806791]
    assert len(filas) == 15 and {f[5] for f in filas} == {"Licencia No remunerada"}


def test_puestos_de_la_senora_sandra_van_aparte(speed):
    sandra = fila(2, 52112768, "DOS SANDRA")
    sandra[7] = "SANDRA"
    archivo = listado_xlsx([fila(1, 1006306373, "UNO GENERAL"), sandra])
    assert speed.post(f"{API}/empleados/importar", files={"archivo": ("l.xlsx", archivo, XLSX)}).status_code == 200
    p = speed.post(f"{API}/periodos", json={"anio": 2026, "mes": 11, "quincena": 1}).json()["data"]
    d = speed.post(f"{API}/periodos/{p['id']}/liquidar").json()["data"]
    assert {x["cedula"]: x["nomina"] for x in d["liquidaciones"]} == {"1006306373": "general", "52112768": "sandra"}
    assert d["personas"] == 1 and d["sandra"]["personas"] == 1  # los totales son de la nómina general
    cedulas = lambda g: {load_workbook(io.BytesIO(speed.get(f"{API}/periodos/{p['id']}/excel" + g).content)).active.cell(r, 1).value  # noqa: E731
                         for r in range(2, 4)} - {None}
    assert cedulas("") == {"1006306373"} and cedulas("?grupo=sandra") == {"52112768"} and len(cedulas("?grupo=todos")) == 2


def test_quien_depende_de_la_programacion_y_no_esta_programado(speed):
    archivo = listado_xlsx([fila(1, 1006306373, "UNO PROGRAMADO"), fila(2, 52112768, "DOS NO VIENE"), fila(3, 80128728, "TRES ADMIN", regla="NO APLICA"),
                            fila(4, 79806791, "CUATRO SIN TURNOS"), fila(5, 1003000005, "CINCO MEDIO")])
    assert speed.post(f"{API}/empleados/importar", files={"archivo": ("l.xlsx", archivo, XLSX)}).status_code == 200
    p = speed.post(f"{API}/periodos", json={"anio": 2026, "mes": 11, "quincena": 1}).json()["data"]
    assert speed.get(f"{API}/periodos/{p['id']}/vacaciones-retiros").json()["data"]["sin_programacion"] == []  # aún sin programación
    archivo = programacion_xlsx([["T", "UNO PROGRAMADO", 1006306373, ["D", "N", "X"] * 5], ["INCAPACITADO", "CUATRO SIN TURNOS", 79806791, [None] * 15],
                                 ["T", "CINCO MEDIO", 1003000005, [None] * 5 + ["D"] * 10]])
    assert speed.post(f"{API}/periodos/{p['id']}/programacion/importar", files={"archivo": ("p.xlsx", archivo, XLSX)}).status_code == 200
    d = speed.get(f"{API}/periodos/{p['id']}/vacaciones-retiros").json()["data"]
    motivos = {x["cedula"]: (x["motivo"].split(" (")[0], x["dias"]) for x in d["sin_programacion"]}
    assert motivos == {"52112768": ("No viene en la programación", None), "79806791": ("Sale en la programación sin ningún turno", 15),
                       "1003000005": ("Tiene días sin turno en la programación", 5)}
    x = speed.get(f"{API}/periodos/{p['id']}/vacaciones-retiros/excel")
    assert load_workbook(io.BytesIO(x.content)).sheetnames == ["Vacaciones", "Retiros", "Incapacidad +180", "Sin programación"]


def test_incapacidad_de_mas_de_180_dias_no_se_paga(speed):
    archivo = listado_xlsx([fila(1, 1006306373, "UNO INC CIENTO OCHENTA"), fila(2, 52112768, "DOS LLEGA A CIENTO OCHENTA"), fila(3, 80128728, "TRES GUARDA")])
    assert speed.post(f"{API}/empleados/importar", files={"archivo": ("l.xlsx", archivo, XLSX)}).status_code == 200
    p = speed.post(f"{API}/periodos", json={"anio": 2026, "mes": 11, "quincena": 1}).json()["data"]
    archivo = programacion_xlsx([["INCAPACITADO", "UNO INC CIENTO OCHENTA", 1006306373, ["INC 180"] * 15],
                                 ["T", "DOS LLEGA A CIENTO OCHENTA", 52112768, ["D", "N", "X"] * 2 + ["INC-180"] * 9],
                                 ["T", "TRES GUARDA", 80128728, ["D", "N", "X"] * 5]])
    assert speed.post(f"{API}/periodos/{p['id']}/programacion/importar", files={"archivo": ("p.xlsx", archivo, XLSX)}).status_code == 200
    # Toda la quincena en INC 180: no se liquida ni sale en la nómina
    q = speed.post(f"{API}/periodos/{p['id']}/liquidar").json()["data"]
    liq = {x["cedula"]: x for x in q["liquidaciones"]}
    assert "1006306373" not in liq and q["excluidos"] == 1
    # Parte de la quincena: los días INC 180 no pagan salario, auxilio ni variables
    assert liq["52112768"]["dias"]["trabajados"] == 6 and liq["80128728"]["dias"]["trabajados"] == 15
    d = speed.get(f"{API}/periodos/{p['id']}/vacaciones-retiros").json()["data"]
    inc = {x["cedula"]: (x["dias"], x["toda"]) for x in d["incapacidad_180"]}
    assert inc == {"1006306373": (15, True), "52112768": (9, False)}
    assert d["sin_programacion"] == []
    hoja = load_workbook(io.BytesIO(speed.get(f"{API}/periodos/{p['id']}/world-office").content))["GENERAL"]
    assert not [f for f in hoja.iter_rows(min_row=2) if f[4].value in (1006306373, 52112768)]


def nomina_wo_xlsx(filas: list[list]) -> bytes:
    """Excel como el que exporta World Office (ExportarAExcel)."""
    buf = io.BytesIO()
    libro = xlsxwriter.Workbook(buf, {"in_memory": True})
    hoja = libro.add_worksheet("ExportarAExcel")
    hoja.write(0, 0, "SPEED SECURITY LTDA")
    hoja.write(1, 0, "900259118-")
    hoja.write(2, 0, "Nómina # NOVNO 139 correspondiente al periodo del  01/11/2026 al  15/11/2026")
    hoja.write_row(3, 0, ["Puesto Trabajo", "Cuenta No", "Nombre  del  Trabajador", "Sueldo Básico", "Dias Trab", "Sueldo Devengado",
                          "Valor Incapac", "Horas Extras", "Auxilio Transporte y Conectividad", "Recargo Nocturno", "Otros Devengados",
                          "Total Devengado", "Aporte Salud", "Aporte Pensión", "Retención en la Fuente", "Fondo Solidar", "Valor Prestamos",
                          "OtrosDeducidos", "Total Descuento", "Neto a Pagar"])
    for i, f in enumerate(filas, start=4):
        hoja.write_row(i, 0, f)
    hoja.write_row(4 + len(filas), 0, ["Total Produccion", None, None, 1])
    libro.close()
    return buf.getvalue()


def fila_wo(liq: dict, nombre: str, cedula: str, **cambios) -> list:
    c = liq["conceptos"]
    v = {"dias": liq["dias"]["trabajados"], "sueldo": c["salario"] - 1, "incap": c["incapacidad"], "he": c["horas_extras"],
         "aux": c["auxilio_transporte"], "otros": c["ley_2466"] + c["bonificaciones"] + c["turnos_adicionales"],
         "salud": c["salud"], "pension": c["pension"]}
    v.update(cambios)
    dev = v["sueldo"] + v["incap"] + v["he"] + v["aux"] + v["otros"]
    desc = v["salud"] + v["pension"]
    return ["Produccion", "0123", f"{nombre} CC {cedula}", 1750905, v["dias"], v["sueldo"], v["incap"], v["he"], v["aux"], 0, v["otros"],
            dev, v["salud"], v["pension"], 0, 0, 0, 0, desc, dev - desc]


def test_cruce_con_la_nomina_de_world_office(speed):
    archivo = listado_xlsx([fila(1, 1006306373, "UNO CUADRA BIEN"), fila(2, 52112768, "DOS PAGA DE MAS"), fila(3, 80128728, "TRES SOLO NUESTRA"),
                            fila(4, 805547339, "CUATRO CEDULA MAL ESCRITA"), fila(5, 1003000005, "CINCO CENTAVOS")])
    assert speed.post(f"{API}/empleados/importar", files={"archivo": ("l.xlsx", archivo, XLSX)}).status_code == 200
    p = speed.post(f"{API}/periodos", json={"anio": 2026, "mes": 11, "quincena": 1}).json()["data"]
    assert speed.get(f"{API}/periodos/{p['id']}/cruce-wo").json()["data"] == {"cargado": False}
    liq = {x["cedula"]: x for x in speed.post(f"{API}/periodos/{p['id']}/liquidar").json()["data"]["liquidaciones"]}
    uno, dos, cuatro, cinco = liq["1006306373"], liq["52112768"], liq["805547339"], liq["1003000005"]
    archivo = nomina_wo_xlsx([
        fila_wo(uno, "UNO CUADRA BIEN", "1006306373"),
        fila_wo(dos, "DOS PAGA DE MAS", "52112768", otros=dos["conceptos"]["ley_2466"] + 80000),  # 80.000 más
        fila_wo(cuatro, "CUATRO CEDULA MAL ESCRITA", "80547339"),  # en el Listado quedó con un 5 de más
        fila_wo(cinco, "CINCO CENTAVOS", "1003000005", otros=cinco["conceptos"]["ley_2466"] - 998),  # −999 en el neto: dentro de la tolerancia
        ["Produccion", "0999", "SEIS NO ESTA EN EL LISTADO CC 1012345678", 1750905, 15, 875452, 0, 0, 124548, 0, 0, 1000000, 35018, 35018,
         0, 0, 0, 0, 70036, 929964],
    ])
    r = speed.post(f"{API}/periodos/{p['id']}/cruce-wo/importar", files={"archivo": ("borrador 1q nov.xlsx", archivo, XLSX)})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["cargado"] and d["info"]["archivo"] == "borrador 1q nov.xlsx" and d["info"]["desde"] == "2026-11-01" and d["tolerancia"] == 1000
    filas = {f["cedula"]: f for f in d["filas"]}
    assert filas["1006306373"]["estado"] == "cuadra"  # 1 peso de redondeo en el salario no es diferencia
    assert filas["1003000005"]["estado"] == "cuadra"  # −999 no es diferencia
    difs = {x["concepto"]: x["diferencia"] for x in filas["52112768"]["diferencias"]}
    assert difs == {"otros_devengados": 80000, "total_devengado": 79999, "neto": 79999}  # 1 peso del redondeo del salario
    assert filas["805547339"]["cruce"] == "ambos" and filas["805547339"]["diferencias"][0]["concepto"] == "cedula"
    assert filas["80128728"]["cruce"] == "solo_nuestra" and filas["1012345678"]["cruce"] == "solo_wo"
    assert "No está en el Listado" in filas["1012345678"]["diferencias"][0]["detalle"]
    assert d["resumen"] | {} == {**d["resumen"], "personas_wo": 5, "personas_nuestras": 5, "cuadran": 2, "pendientes": 4, "justificadas": 0,
                                 "solo_wo": 1, "solo_nuestra": 1}

    # −1.100 sí es diferencia
    archivo = nomina_wo_xlsx([fila_wo(cinco, "CINCO CENTAVOS", "1003000005", otros=cinco["conceptos"]["ley_2466"] - 1099),
                              fila_wo(dos, "DOS PAGA DE MAS", "52112768", otros=dos["conceptos"]["ley_2466"] + 80000)])
    d = speed.post(f"{API}/periodos/{p['id']}/cruce-wo/importar", files={"archivo": ("b.xlsx", archivo, XLSX)}).json()["data"]
    filas = {f["cedula"]: f for f in d["filas"]}
    assert filas["1003000005"]["estado"] == "pendiente" and filas["1003000005"]["diferencias"][-1] == {
        "concepto": "neto", "nombre": "Neto a pagar", "nuestro": cinco["neto"], "wo": cinco["neto"] - 1100, "diferencia": -1100}

    # Justificar: World Office está bien (menor valor pagado de otra quincena)
    for concepto in ("otros_devengados", "total_devengado", "neto"):
        r = speed.post(f"{API}/periodos/{p['id']}/cruce-wo/justificar",
                       json={"cedula": "52112768", "concepto": concepto, "correcto": "wo", "motivo": "Menor valor pagado en la 2da quincena de octubre"})
        assert r.status_code == 200, r.text
    f = next(x for x in r.json()["data"]["filas"] if x["cedula"] == "52112768")
    assert f["estado"] == "justificada" and f["diferencias"][0]["justificacion"]["correcto"] == "wo"
    assert speed.post(f"{API}/periodos/{p['id']}/cruce-wo/justificar",
                      json={"cedula": "52112768", "concepto": "salud", "correcto": "wo", "motivo": "No existe"}).status_code == 404
    # Si la diferencia cambia, la justificación deja de aplicar
    archivo = nomina_wo_xlsx([fila_wo(dos, "DOS PAGA DE MAS", "52112768", otros=dos["conceptos"]["ley_2466"] + 95000)])
    d = speed.post(f"{API}/periodos/{p['id']}/cruce-wo/importar", files={"archivo": ("b.xlsx", archivo, XLSX)}).json()["data"]
    f = next(x for x in d["filas"] if x["cedula"] == "52112768")
    assert f["estado"] == "pendiente" and f["diferencias"][0]["justificacion"]["vigente"] is False
    r = speed.delete(f"{API}/periodos/{p['id']}/cruce-wo/justificar", params={"cedula": "52112768", "concepto": "neto"})
    assert r.status_code == 200
    x = speed.get(f"{API}/periodos/{p['id']}/cruce-wo/excel")
    assert x.status_code == 200 and load_workbook(io.BytesIO(x.content)).sheetnames == ["Diferencias", "Resumen"]
    # Un archivo que no es la nómina de World Office
    malo = speed.post(f"{API}/periodos/{p['id']}/cruce-wo/importar", files={"archivo": ("l.xlsx", listado_xlsx([]), XLSX)})
    assert malo.status_code == 422
