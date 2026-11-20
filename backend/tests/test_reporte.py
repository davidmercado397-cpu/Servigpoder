from datetime import date

import pytest

from app.apps.reporte.services import lector, pdf
from tests.conftest import ACCESOS, archivo, entrar, xlsx

API = "/api/reporte"


def _siesa(desde: date, hasta: date, filas: list[tuple[str, str, str, str, str, str, dict[int, str], str]]) -> bytes:
    """Excel con el formato del ReporteAsignacionResumido de SIESA (días 1 a 31 en columnas)."""
    datos: list[list[object]] = [
        ["Compañia", "EMPRESA DE PRUEBA"], ["Desde", desde.isoformat()], ["Hasta", hasta.isoformat()], [],
        ["C.C. Empleado", "NOMBRE EMPLEADO", "UBICACION", "DESCRIPCION UBICACION", "PUESTO", "DESCRIPCION PUESTO",
         *[str(d) for d in range(1, 32)], "CENTRO DE OPERACION", "DESCRIPCION CENTRO DE OPERACION"],
    ]
    for cedula, nombre, ubi, desc_ubi, puesto, desc_puesto, dias, ciudad in filas:
        datos.append([cedula, nombre, ubi, desc_ubi, puesto, desc_puesto, *[dias.get(d) for d in range(1, 32)], "001", ciudad])
    return xlsx(datos)


def _todos(valor: str, desde: int, hasta: int) -> dict[int, str]:
    return {d: valor for d in range(desde, hasta + 1)}


FILAS = [
    ("1", "ZULUAGA ANA", "122", "CONJUNTO FALCO", "1221-1", "RONDERO 4X2", _todos("18:00 - 06:00", 1, 31), "CALI"),
    ("2", "ALVAREZ LUIS", "12", "CAHUINARI", "12-10", "PUERTA", _todos("06:00 - 18:00*", 1, 31), "CALI"),
    ("3", "BENITEZ JUAN", "12", "CAHUINARI", "12-2", "RONDA", {1: "[VAC]", 2: "Z", 3: "L", 12: "IND CORP"}, "CALI"),
    ("4", "CARDONA EVA", "2", "EDIFICIO", "2", "RECEPCION", {5: "A", 6: "10D"}, "PALMIRA"),
    ("5", "ARANGO PEDRO", "12", "CAHUINARI", "12-2", "RONDA", {1: "12:00 - 20:00 ECO"}, "CALI"),
]


def test_orden_natural():
    codigos = ["122", "12", "2", "1221-1", "12-10", "12-2", "2843-7G", "05 DISPONIBLES", "00-1"]
    assert sorted(codigos, key=lector.clave_natural) == ["00-1", "2", "05 DISPONIBLES", "12", "12-2", "12-10", "122", "1221-1", "2843-7G"]


@pytest.mark.parametrize("desde,hasta,dias", [
    (date(2026, 10, 1), date(2026, 10, 15), 15),
    (date(2026, 10, 16), date(2026, 10, 31), 16),
    (date(2026, 10, 1), date(2026, 10, 31), 31),
    (date(2027, 2, 1), date(2027, 2, 28), 28),
])
def test_rangos_quincena_y_mes(desde, hasta, dias):
    prog = lector.leer(_siesa(desde, hasta, FILAS))
    assert len(prog.fechas) == dias and prog.filas == 5 and prog.puestos == 4
    ana = prog.ubicaciones["122"].puestos["1221-1"].empleados[0]
    assert sorted(ana.dias) == prog.fechas  # solo los días del rango
    contenido, paginas, total = pdf.construir(prog)
    assert contenido.startswith(b"%PDF") and total >= 2


def test_ubicaciones_y_puestos_en_orden():
    prog = lector.leer(_siesa(date(2026, 10, 1), date(2026, 10, 31), FILAS))
    orden = lector.ordenada(prog)
    assert [u.codigo for u in orden] == ["2", "12", "122"]
    assert list(orden[1].puestos) == ["12-2", "12-10"]
    # Empleados por nombre dentro del puesto
    assert [e.nombre for e in orden[1].puestos["12-2"].empleados] == ["ARANGO PEDRO", "BENITEZ JUAN"]
    _, paginas, _ = pdf.construir(prog)
    assert paginas["u-2"] <= paginas["u-12"] <= paginas["u-122"]


def test_celdas_y_festivos():
    assert pdf.celda("06:00 - 18:00") == "06:00\n18:00"
    assert pdf.celda("08:00 - 22:00*") == "08:00\n22:00*"
    assert pdf.celda("12:00 - 20:00 ECO") == "12:00\n20:00\nECO"
    assert pdf.celda("IND CORP") == "IND\nCORP"
    assert pdf.celda("[VAC]") == "[VAC]" and pdf.celda("10D") == "10D"


def test_validaciones_del_archivo():
    with pytest.raises(lector.ErrorReporte, match="dos veces el día 15"):
        lector.leer(_siesa(date(2026, 10, 15), date(2026, 11, 15), FILAS))
    with pytest.raises(lector.ErrorReporte, match="Desde"):
        lector.leer(xlsx([["Compañia", "X"], ["Hasta", "2026-10-31"], [], [], ["C.C. Empleado"]]))
    with pytest.raises(lector.ErrorReporte, match="filas de empleados"):
        lector.leer(_siesa(date(2026, 10, 1), date(2026, 10, 15), []))


def test_api_analizar_y_pdf_con_filtros(admin):
    contenido = _siesa(date(2026, 10, 1), date(2026, 10, 15), FILAS)
    r = admin.post(f"{API}/analizar", files=archivo(contenido, "ReporteAsignacionResumido.xlsx"))
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["dias"] == 15 and d["ciudades"] == ["CALI", "PALMIRA"] and d["filas"] == 5
    assert [u["codigo"] for u in d["ubicaciones"]] == ["2", "12", "122"]

    r = admin.post(f"{API}/pdf", files=archivo(contenido, "ReporteAsignacionResumido.xlsx"), data={"ciudades": "CALI"})
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    assert r.headers["content-disposition"] == 'attachment; filename="programacion_2026-10-01_a_2026-10-15.pdf"'

    r = admin.post(f"{API}/pdf", files=archivo(contenido), data={"ubicaciones": "999"})
    assert r.status_code == 422 and "Ninguna ubicación" in r.json()["error"]["message"]
    auditoria = admin.get("/api/plataforma/auditoria?accion=reporte_pdf_generado").json()["data"]
    assert auditoria[0]["detalle"]["filtros"] == ["ciudad CALI"]


def test_api_rechaza_archivo_que_no_es_de_siesa(admin):
    r = admin.post(f"{API}/analizar", files=archivo(xlsx([["hola"], ["mundo"]])))
    assert r.status_code == 422 and r.json()["error"]["code"] == "EXCEL_INVALIDO"


def test_permiso_del_reporte(admin):
    admin.post("/api/roles", json={"nombre": "Sin reporte", "permisos": ["capacidad.analisis.ver"]})
    rid = next(r["id"] for r in admin.get("/api/roles").json()["data"] if r["nombre"] == "Sin reporte")
    admin.post("/api/usuarios", json={"accesos": ACCESOS, "username": "sinrep", "nombre": "Sin reporte", "password": "clave-segura-1", "roles": [rid]})
    admin.post("/api/auth/logout")
    entrar(admin, "sinrep", "clave-segura-1")
    contenido = _siesa(date(2026, 10, 1), date(2026, 10, 15), FILAS)
    assert admin.post(f"{API}/analizar", files=archivo(contenido)).status_code == 403
    assert admin.post(f"{API}/pdf", files=archivo(contenido)).status_code == 403


def test_rango_que_cruza_de_mes_en_un_archivo():
    # SIESA con columnas 1 … 31: del 20 de septiembre al 5 de octubre cada día va en la columna de su número
    prog = lector.leer(_siesa(date(2026, 9, 20), date(2026, 10, 5), [("9", "PEREZ", "7", "UBI", "7-1", "P", {20: "A", 30: "B", 1: "C", 5: "D"}, "CALI")]))
    e = prog.ubicaciones["7"].puestos["7-1"].empleados[0]
    assert e.dias == {date(2026, 9, 20): "A", date(2026, 9, 30): "B", date(2026, 10, 1): "C", date(2026, 10, 5): "D"}
    assert len(prog.fechas) == 16
    assert pdf._rango_texto(prog.desde, prog.hasta) == "Del 20 de septiembre al 5 de octubre de 2026"
    assert pdf._rango_texto(date(2026, 12, 15), date(2027, 1, 14)) == "Del 15 de diciembre de 2026 al 14 de enero de 2027"


def test_dos_meses_del_15_al_15_y_semanas():
    octubre = lector.leer(_siesa(date(2026, 10, 1), date(2026, 10, 31), [("1", "ANA", "5", "U", "5-1", "P", _todos("A", 1, 31), "CALI")]))
    noviembre = lector.leer(_siesa(date(2026, 11, 1), date(2026, 11, 30), [
        ("1", "ANA", "5", "U", "5-1", "P", _todos("B", 1, 30), "CALI"), ("2", "LUIS", "5", "U", "5-1", "P", {20: "N"}, "CALI")]))
    junto = lector.unir([noviembre, octubre])
    assert (junto.desde, junto.hasta) == (date(2026, 10, 1), date(2026, 11, 30))
    ana = junto.ubicaciones["5"].puestos["5-1"].empleados[0]
    assert ana.dias[date(2026, 10, 31)] == "A" and ana.dias[date(2026, 11, 1)] == "B"  # una sola fila con los dos meses
    # Del 15 de octubre al 15 de noviembre (32 días): Luis solo trabaja el 20 de noviembre, no sale
    r = lector.recortar(junto, date(2026, 10, 15), date(2026, 11, 15))
    assert len(r.fechas) == 32 and [e.nombre for e in r.ubicaciones["5"].puestos["5-1"].empleados] == ["ANA"]
    assert min(r.ubicaciones["5"].puestos["5-1"].empleados[0].dias) == date(2026, 10, 15)
    contenido, _, _ = pdf.construir(r)
    assert contenido.startswith(b"%PDF")
    # Una semana y tres semanas
    assert len(lector.recortar(junto, date(2026, 11, 2), date(2026, 11, 8)).fechas) == 7
    assert len(lector.recortar(junto, date(2026, 11, 2), date(2026, 11, 22)).fechas) == 21
    with pytest.raises(lector.ErrorReporte, match="35 días"):
        lector.recortar(junto, date(2026, 10, 1), date(2026, 11, 30))
    with pytest.raises(lector.ErrorReporte, match="entre el"):
        lector.recortar(junto, date(2026, 9, 25), date(2026, 10, 10))
    with pytest.raises(lector.ErrorReporte, match="faltan días"):
        lector.unir([octubre, lector.leer(_siesa(date(2026, 11, 5), date(2026, 11, 30), FILAS))])


def test_api_varios_archivos_y_rango(admin):
    tipo = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    archivos = [("archivos", ("oct.xlsx", _siesa(date(2026, 10, 1), date(2026, 10, 31), FILAS), tipo)),
                ("archivos", ("nov.xlsx", _siesa(date(2026, 11, 1), date(2026, 11, 30), FILAS), tipo))]
    d = admin.post(f"{API}/analizar", files=archivos).json()["data"]
    assert (d["desde"], d["hasta"], d["dias"]) == ("2026-10-01", "2026-11-30", 61)
    r = admin.post(f"{API}/pdf", files=archivos, data={"desde": "2026-10-15", "hasta": "2026-11-14"})
    assert r.status_code == 200, r.text
    assert r.headers["content-disposition"] == 'attachment; filename="programacion_2026-10-15_a_2026-11-14.pdf"'
    r = admin.post(f"{API}/pdf", files=archivos)  # sin rango: los 61 días no caben en un PDF
    assert r.status_code == 422 and "35 días" in r.json()["error"]["message"]
