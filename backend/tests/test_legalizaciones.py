"""Contabilidad → Legalizaciones: formato (Excel o PDF) + soportes → nota contable NC / LG de World Office."""

import json
from types import SimpleNamespace as N

import httpx
import pytest
import xlrd

from app.apps.contabilidad.services import legalizacion as lg
from app.core import ia
from app.core.config import get_settings
from tests.conftest import xlsx

API = "/api/contabilidad/legalizaciones"
TIPO = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

FORMATO = {
    "numero": "031", "colaborador": {"nombre": "COLABORADOR DE PRUEBA", "documento": "44.444.444"}, "sucursal": "BOGOTA D.C",
    "motivo": "LEGALIZACION CTAS POR CONCEPTO DE ALIMENTACION Y PASAJES", "reembolso_a": "FONDO FIJO", "fecha_legalizacion": "2026-11-19",
    "anticipo": {"fecha": None, "valor": 0, "descripcion": ""}, "total": 72200,
    "lineas": [
        {"fecha": "2026-11-09", "beneficiario": "PEDRO PRUEBA", "documento": "11111111", "columna": "alimentacion", "valor": 20000,
         "detalle": "Se entrega auxilio de comida"},
        {"fecha": "2026-11-16", "beneficiario": "ANA EJEMPLO", "documento": "22222222", "columna": "transporte", "valor": 10000,
         "detalle": "auxilio de transporte a otro puesto"},
        {"fecha": "2026-11-18", "beneficiario": "COLABORADOR DE PRUEBA", "documento": "44444444", "columna": "transporte", "valor": 16100,
         "detalle": "Valor del peaje pagado via a la sede del cliente"},
        {"fecha": "2026-11-18", "beneficiario": "COLABORADOR DE PRUEBA", "documento": "44444444", "columna": "otros", "valor": 26100,
         "detalle": "Parqueadero del edificio"},
    ],
}


@pytest.fixture
def speed(admin):
    assert admin.post("/api/plataforma/empresa", json={"codigo": "speed"}).status_code == 200
    return admin


@pytest.fixture
def proveedor(monkeypatch):
    monkeypatch.setattr(get_settings(), "ia_api_key", "sk-or-prueba")
    pedidos, respuestas = [], []

    def falso(request: httpx.Request) -> httpx.Response:
        pedidos.append(json.loads(request.content))
        contenido = respuestas.pop(0) if respuestas else "{}"
        return httpx.Response(200, json={"model": "m", "usage": {}, "choices": [{"message": {"content": contenido}, "finish_reason": "stop"}]})

    monkeypatch.setattr(ia, "cliente_http", lambda: httpx.Client(transport=httpx.MockTransport(falso)))
    return pedidos, respuestas


def test_legalizacion_de_reembolso_al_plano(speed, proveedor):
    pedidos, respuestas = proveedor
    respuestas += [json.dumps(FORMATO), json.dumps({"lineas": [{"n": 1, "soporte": True, "nota": "foto de entrega PEDRO PRUEBA"},
                                                               {"n": 2, "soporte": True}, {"n": 3, "soporte": True, "nota": "recibo de peaje"}]})]
    # Personas: quien elabora (columna F)
    elabora = xlsx([["Personas"], ["Nombre", "Cedula"], ["PERSONA QUE ELABORA", "55.555.555"]])
    assert speed.post(f"{API}/personas/importar?tipo=elabora", files={"archivo": ("p.xlsx", elabora, TIPO)}).json()["data"]["personas"] == 1
    r = speed.post(API, files={"formato": ("Formato_CM_2026 #031.pdf", b"%PDF-1.4 formato", "application/pdf"),
                              "soportes": ("Soportes.pdf", b"%PDF-1.4 fotos", "application/pdf")}, data={"elabora_documento": "55555555"})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert (d["numero_formato"], d["colaborador_documento"], d["elabora_documento"], d["elabora_nombre"]) == ("031", "44444444", "55555555", "PERSONA QUE ELABORA")
    # Cuenta por columna; en transporte/parqueo/peajes manda el detalle
    assert [(x["columna"], x["cuenta"]) for x in d["lineas"]] == [("alimentacion", "519560"), ("transporte", "513550"), ("peajes", "515595"), ("otros", "519595")]
    assert [x["soporte"] for x in d["lineas"]] == [True, True, True, False] and any("Sin soporte: línea(s) 4" in a for a in d["avisos"])
    assert pedidos[0]["messages"][1]["content"][1]["type"] == "file"  # el PDF del formato va a la IA (el archivo no se guarda)
    # La contrapartida de un reembolso: crédito 233595 por el total
    assert d["movimientos"][-1] == {"cuenta": "233595", "nota": "reintegro de dinero", "tercero": "44444444", "debito": 0.0, "credito": 72200.0}

    lineas = [{"id": x["id"], "cuenta": x["cuenta"], "documento": x["documento"], "columna": x["columna"], "excluida": False} for x in d["lineas"]]
    r = speed.put(f"{API}/{d['id']}", json={"colaborador_nombre": d["colaborador_nombre"], "colaborador_documento": d["colaborador_documento"],
                                           "elabora_documento": "55555555", "nota": "Legalizacion de gastos", "lista": True, "lineas": lineas})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["estado"] == "lista"
    speed.put(f"{API}/config/datos", json={"ultimo_numero": 30})
    r = speed.post(f"{API}/plano/descargar", json={"fecha": "2026-11-19"})
    assert r.status_code == 200, r.text
    hoja = xlrd.open_workbook(file_contents=r.content).sheet_by_index(0)
    enc = hoja.row_values(0)
    assert enc == lg.COLUMNAS_NC and len(enc) == 48 and hoja.nrows == 6  # 4 gastos + la contrapartida
    filas = [dict(zip(enc, hoja.row_values(i))) for i in range(1, hoja.nrows)]
    f0 = filas[0]
    assert (f0["Encab: Tipo Documento"], f0["Encab: Prefijo"], f0["Encab: Documento Número"]) == ("NC", "LG", 31)
    assert (f0["Encab: Tercero Interno"], f0["Encab: Tercero Externo"]) == (55555555, 44444444)
    assert (f0["Detalle Con: IdCuentaContable"], f0["Detalle Con: Tercero_Externo"], f0["Detalle Con: Débito"]) == (519560, 11111111, 20000)
    assert sum(f["Detalle Con: Débito"] for f in filas) == sum(f["Detalle Con: Crédito"] for f in filas) == 72200  # cuadra
    planos = speed.get(f"{API}/plano/planos").json()["data"]
    assert speed.post(f"{API}/plano/planos/{planos[0]['id']}/contabilizar", json={"ids": [d["id"]]}).json()["data"]["contabilizadas"] == 1
    assert speed.get(f"{API}/{d['id']}").json()["data"]["documento_numero"] == 31


def test_anticipo_y_diferencia():
    c = N(cuenta_anticipo="13301501", cuenta_reintegro="233595", cuenta_por_cobrar="136595")
    lineas = [N(cuenta="519560", detalle="comida", documento="1", valor=60000, excluida=False)]
    leg = N(lineas=lineas, colaborador_documento="99", anticipo_valor=50000, anticipo_descripcion="del 1 de nov")
    movs = lg.movimientos(leg, c)  # gastó más: anticipo + diferencia a reintegro
    assert [(m.cuenta, m.debito, m.credito) for m in movs] == [("519560", 60000, 0), ("13301501", 0, 50000), ("233595", 0, 10000)]
    leg.anticipo_valor = 80000  # gastó menos: lo que debe devolver queda por cobrar
    assert [(m.cuenta, m.debito, m.credito) for m in lg.movimientos(leg, c)][1:] == [("13301501", 0, 80000), ("136595", 20000, 0)]


def test_formato_en_excel_va_como_texto(speed, proveedor):
    pedidos, respuestas = proveedor
    respuestas.append(json.dumps(FORMATO))
    formato = xlsx([["FORMATO REEMBOLSO", None, "NO. 031"], ["FECHA", "PROVEEDOR", "ALIMENTACION", "NIT", "DETALLE"],
                    ["9/11/2026", "PEDRO PRUEBA", 20000, 11111111, "auxilio de comida"]])
    speed.put(f"{API}/personas/lista", json={"tipo": "elabora", "documento": "55555555", "nombre": "PERSONA QUE ELABORA"})
    r = speed.post(API, files={"formato": ("formato.xlsx", formato, TIPO)})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["elabora_documento"] == "55555555"  # una sola persona elabora: queda puesta sola
    assert r.json()["data"]["leida_con"] == "excel" and not r.json()["data"]["soportes_revisados"]
    texto = pedidos[0]["messages"][1]["content"][0]["text"]
    assert "PEDRO PRUEBA" in texto and "ALIMENTACION" in texto  # el Excel va como texto (sin archivo)
    assert speed.get(f"{API}?estado=pendiente").json()["meta"]["extra"]["conteos"]["pendiente"] == 1


def test_listado_de_empleados_con_retirados(speed):
    from datetime import datetime as dt

    listado = xlsx([["SPEED SECURITY LTDA"], ["Informe de Personal "], ["Entre el 01/01/2025 y el 31/12/2026"],
                    ["CentroTrabajo", "Apellidos y Nombres_", "Identificacion__", "Codigo Empleado", "Fecha de Ingreso", "Fecha de Retiro_"],
                    ["1", "PRUEBA UNO", "10000001", "1", dt(2025, 1, 1), None],
                    ["1", "PRUEBA DOS", "10000002", "2", dt(2025, 1, 1), dt(2025, 6, 30)],  # ya se retiró
                    ["1", "PRUEBA TRES", "10000003", "3", dt(2025, 1, 1), dt(2099, 1, 1)]])
    r = speed.post(f"{API}/personas/importar?tipo=empleado", files={"archivo": ("empleados.xlsx", listado, TIPO)})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["personas"] == 3
    activos = {p["documento"]: p["activo"] for p in speed.get(f"{API}/personas/lista?tipo=empleado").json()["data"]}
    assert activos == {"10000001": True, "10000002": False, "10000003": True}
