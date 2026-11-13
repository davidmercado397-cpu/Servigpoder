"""Agente de IA: configuración desde el panel de administración (clave cifrada y modelos) y costeo llenado desde archivos."""

import json

import httpx
import pytest

from app.core import ia
from app.core.config import get_settings
from app.models import Auditoria, IAConfig
from tests.conftest import ACCESOS, entrar, xlsx

API = "/api/costeo"
CLAVE = "sk-or-v1-clave-de-prueba-9876"


class Proveedor:
    """OpenRouter falso: guarda lo que se le pide y responde con el JSON que se le indique."""

    def __init__(self, contenido: str = "Conexión correcta."):
        self.contenido = contenido
        self.pedidos: list[dict] = []
        self.cabeceras: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [
                {"id": "anthropic/claude-opus-5", "name": "Claude Opus 5", "context_length": 200000,
                 "pricing": {"prompt": "0.000005", "completion": "0.000025"},
                 "architecture": {"input_modalities": ["text", "image", "file"]}},
                {"id": "openai/gpt-5-mini", "name": "GPT-5 mini", "pricing": {"prompt": "0.00000025", "completion": "0.000002"},
                 "architecture": {"input_modalities": ["text"]}}]})
        self.pedidos.append(json.loads(request.content))
        self.cabeceras.append(dict(request.headers))
        return httpx.Response(200, json={"model": self.pedidos[-1]["model"], "usage": {"prompt_tokens": 900, "completion_tokens": 300},
                                         "choices": [{"message": {"content": self.contenido}, "finish_reason": "stop"}]})


@pytest.fixture
def proveedor(monkeypatch):
    monkeypatch.setattr(get_settings(), "ia_api_key", "")
    p = Proveedor()
    monkeypatch.setattr(ia, "cliente_http", lambda: httpx.Client(transport=httpx.MockTransport(p)))
    ia._panel.clear()
    yield p
    ia._panel.clear()


def test_clave_y_modelo_desde_el_panel(admin, db, proveedor):
    c = admin.get("/api/ia/config").json()["data"]
    assert not c["configurada"] and c["modelo_vigente"] == get_settings().ia_modelo
    assert admin.post("/api/ia/probar", json={}).status_code == 422  # sin clave

    r = admin.put("/api/ia/config", json={"api_key": CLAVE, "modelo": "openai/gpt-5-mini", "modelo_costeo": "anthropic/claude-opus-5"})
    assert r.status_code == 200, r.text
    c = r.json()["data"]
    assert c["configurada"] and c["origen_clave"] == "panel" and c["clave_final"] == "9876"
    assert c["modelo_vigente"] == "openai/gpt-5-mini" and c["modelo_costeo_vigente"] == "anthropic/claude-opus-5"
    assert CLAVE not in r.text
    with db() as s:
        fila = s.get(IAConfig, 1)
        assert fila.api_key_cifrada and CLAVE not in fila.api_key_cifrada  # cifrada en la base
        assert all(CLAVE not in json.dumps(a.detalle, ensure_ascii=False) for a in s.query(Auditoria).all())

    # La prueba usa la clave del panel y el modelo general
    p = admin.post("/api/ia/probar", json={})
    assert p.status_code == 200, p.text
    assert p.json()["data"]["respuesta"] == "Conexión correcta."
    assert proveedor.cabeceras[-1]["authorization"] == f"Bearer {CLAVE}" and proveedor.pedidos[-1]["model"] == "openai/gpt-5-mini"
    assert proveedor.pedidos[-1]["provider"]["data_collection"] == "deny"

    # Guardar sin clave la conserva; los modelos inválidos se rechazan
    assert admin.put("/api/ia/config", json={"modelo": "openai/gpt-5-mini"}).json()["data"]["clave_final"] == "9876"
    assert admin.put("/api/ia/config", json={"modelo": "no es un modelo"}).status_code == 422

    modelos = admin.get("/api/ia/modelos").json()["data"]
    assert modelos[0]["id"] == "anthropic/claude-opus-5" and modelos[0]["imagenes"] and modelos[0]["precio_entrada"] == 5

    c = admin.put("/api/ia/config", json={"borrar_clave": True}).json()["data"]
    assert not c["configurada"] and c["origen_clave"] == ""


def test_solo_quien_tiene_el_permiso_configura_la_ia(admin, proveedor):
    roles = {r["nombre"]: r["id"] for r in admin.get("/api/roles").json()["data"]}
    admin.post("/api/usuarios", json={"accesos": ACCESOS, "username": "comercial", "nombre": "comercial", "password": "clave-segura-1",
                                      "roles": [roles["Comercial costeo"]]})
    admin.post("/api/auth/logout")
    entrar(admin, "comercial", "clave-segura-1")
    assert admin.get("/api/ia/config").status_code == 403
    assert admin.put("/api/ia/config", json={"api_key": CLAVE}).status_code == 403


PROPUESTA = {
    "nombre_sugerido": "Conjunto Las Palmas 2027", "cliente": {"nombre": "Conjunto Las Palmas", "nit": "900111222"},
    "municipio": "Cali", "fecha_inicio": "2026-12-01", "duracion_meses": 24, "pct_comision_vendedor": 0.5, "pct_nota_credito": 3, "pct_cupo_inversion": None, "horas_bolsa_total": 96,
    "donaciones": None, "ica_por_mil": 10,
    "servicios": [{"servicio_id": "SERV24", "cantidad": 2, "puesto": "Portería", "dotacion": "gala", "arma": "noletal", "personal": "Guarda"},
                  {"servicio_id": 99999, "cantidad": 1, "puesto": "Escolta VIP", "dotacion": "gala", "arma": "sin", "personal": "Escolta"}],
    "personal": [{"nombre": "Guarda", "horas_extras": 450000, "auxilios_no_salariales": 80000, "rodamiento": None}],
    "otros": [{"nombre": "Cámaras IP", "tipo_item": "EQUIPOS", "valor_unitario": "1.200.000", "cantidad": 4, "vida_util_meses": 24},
              {"nombre": "Capacitación brigada", "tipo_item": "NO_EXISTE", "valor_unitario": 500000, "cantidad": 1, "entregas_anio": 1}],
    "dotacion_puesto": [{"nombre": "linternas", "cantidad": 2}, {"nombre": "Dron", "cantidad": 1}],
    "resumen": "El conjunto pide 2 porterías 24 horas con arma.", "supuestos": ["Dotación de gala"], "faltantes": ["Valor de las donaciones"],
    "conflictos": ["Nota crédito: costeo 3 %, apoyo comercial 3,5 % (se tomó 3 %)"], "beneficios_sin_costo": ["Estudio de seguridad"],
}


def test_costeo_llenado_con_ia_desde_archivos(admin, db, proveedor):
    admin.put("/api/ia/config", json={"api_key": CLAVE, "modelo": "openai/gpt-5-mini", "modelo_costeo": "anthropic/claude-opus-5"})
    servicio = next(s for s in admin.get(f"{API}/servicios").json()["data"] if "24 horas" in s["descripcion"])
    proveedor.contenido = "Aquí está el costeo:\n```json\n" + json.dumps({**PROPUESTA, "servicios": [
        {**PROPUESTA["servicios"][0], "servicio_id": servicio["id"]}, PROPUESTA["servicios"][1]]}, ensure_ascii=False) + "\n```"
    cid = admin.post(f"{API}/clientes", json={"nit": "900111222", "nombre": "Las Palmas"}).json()["data"]["id"]
    c = admin.post(f"{API}/costeos", json={"cliente_id": cid, "nombre": "Las Palmas"}).json()["data"]
    excel = xlsx([["Puesto", "Horario", "Cantidad"], ["Portería", "24 horas", 2], ["Valor cámaras", 1200000.5, None]])
    archivos = [("archivos", ("solicitud.xlsx", excel, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
                ("archivos", ("correo.txt", "El cliente pide armas de fuego en portería".encode(), "text/plain"))]
    r = admin.post(f"{API}/costeos/{c['id']}/ia", files=archivos, data={"indicaciones": "Contrato a dos años"})
    assert r.status_code == 200, r.text
    d, inf = r.json()["data"]["datos"], r.json()["data"]["informe"]

    # Lo que se le mandó al modelo: los archivos leídos, los catálogos y el modelo de costeos
    pedido = proveedor.pedidos[-1]
    assert pedido["model"] == "anthropic/claude-opus-5"
    texto = json.dumps(pedido["messages"], ensure_ascii=False)
    assert "Portería | 24 horas | 2" in texto and "armas de fuego" in texto and "Contrato a dos años" in texto
    assert servicio["descripcion"] in pedido["messages"][0]["content"]  # el catálogo de servicios va en las instrucciones

    # Normalizado contra los catálogos: tarifa y hombres del catálogo; lo desconocido queda en faltantes
    assert d["pct_comision_vendedor"] == 0.005 and inf["fecha_inicio"] == "2026-12-01"
    assert inf["conflictos"] and inf["beneficios_sin_costo"] == ["Estudio de seguridad"]
    assert d["duracion_meses"] == 24 and d["pct_nota_credito"] == 0.03 and d["horas_bolsa_total"] == 96 and d["automatico"]
    assert len(d["servicios"]) == 1
    s = d["servicios"][0]
    assert (s["servicio_id"], s["tarifa"], s["hombres"], s["cantidad"], s["arma"]) == (servicio["id"], servicio["tarifa"], servicio["hombres"], 2, "noletal")
    guarda = next(p for p in d["personal"] if p["nombre"] == "Guarda")
    assert (guarda["horas_extras"], guarda["auxilios_no_salariales"]) == (450000, 80000)
    camaras, capacitacion = d["otros"]
    assert (camaras["valor_unitario"], camaras["tipo_item"], camaras["vida_util_meses"]) == (1200000, "EQUIPOS", 24)
    assert capacitacion["tipo_item"] == "OTROS" and capacitacion["entregas_anio"] == 1
    assert [x["nombre"] for x in d["dotacion_puesto"]] == ["LINTERNAS"] and d["dotacion_puesto"][0]["valor_unitario"] == 57120
    assert any("Escolta VIP" in f for f in inf["faltantes"]) and any("Dron" in f for f in inf["faltantes"])
    assert "Valor de las donaciones" in inf["faltantes"] and inf["cliente"]["nit"] == "900111222" and inf["ica_por_mil"] == 10

    # Nada se guardó: el costeo sigue igual hasta que el usuario revise y guarde
    assert admin.get(f"{API}/costeos/{c['id']}").json()["data"]["datos"]["servicios"] == []
    # Al guardar la propuesta pasa por las reglas de siempre
    g = admin.put(f"{API}/costeos/{c['id']}", json={"cliente_id": cid, "nombre": "Las Palmas", "datos": d})
    assert g.status_code == 200, g.text
    assert g.json()["data"]["resultado"]["tarifa_decreto"] == servicio["tarifa"] * 2
    assert "ARMA NO LETAL" in {x["nombre"] for x in g.json()["data"]["datos"]["dotacion_tarifa"]}  # el arma no letal entra sola
    with db() as ses:
        a = ses.query(Auditoria).filter(Auditoria.accion == "cst_costeo_ia").one()
        assert a.detalle["archivos"] == ["solicitud.xlsx", "correo.txt"] and "Portería" not in json.dumps(a.detalle)


def test_costeo_ia_valida_los_archivos(admin, proveedor):
    cid = admin.post(f"{API}/clientes", json={"nit": "5", "nombre": "Cliente X"}).json()["data"]["id"]
    c = admin.post(f"{API}/costeos", json={"cliente_id": cid, "nombre": "Costeo X"}).json()["data"]
    url = f"{API}/costeos/{c['id']}/ia"
    txt = ("archivos", ("a.txt", b"hola", "text/plain"))
    # Sin clave configurada
    r = admin.post(url, files=[txt])
    assert r.status_code == 503 and "Administración" in r.json()["error"]["message"]
    admin.put("/api/ia/config", json={"api_key": CLAVE})
    assert admin.post(url, files=[txt] * 7).status_code == 422
    r = admin.post(url, files=[("archivos", ("viejo.xls", b"xx", "application/vnd.ms-excel"))])
    assert r.status_code == 422 and ".xlsx" in r.json()["error"]["message"]
    assert admin.post(url, files=[("archivos", ("roto.xlsx", b"no es excel", "application/octet-stream"))]).status_code == 422
    # El modelo responde algo que no es JSON
    proveedor.contenido = "No pude leer el documento"
    r = admin.post(url, files=[txt])
    assert r.status_code == 502 and "legible" in r.json()["error"]["message"]
