from tests.conftest import entrar
import json

import httpx
import pytest

from app.core import ia
from app.core.config import get_settings
from app.models import Usuario
from app.apps.capacidad.services import asistente
from tests.test_cubrimientos import _cargar


def _herramientas(db_session, username="admin", datos_personales=True):
    usuario = db_session.query(Usuario).filter_by(username=username).one()
    ctx = asistente.Contexto(db_session, usuario, datos_personales)
    return {t.nombre: t for t in asistente.crear_herramientas(ctx)}, ctx


def test_herramientas_con_datos_reales_del_escenario(admin, db):
    _cargar(admin)
    with db() as s:
        h, ctx = _herramientas(s)
        r = json.loads(h["resumen_cobertura"].call({}))
        assert r["cubrimientos"] == 3 and "cobertura_pct" in r and r["enlace_tablero"] == "/capacidad/cobertura"

        d = json.loads(h["detalle_puesto"].call({"codigo": "25"}))
        assert d["vendido"]["incluye_festivos"] is True and len(d["vendido"]["franjas"]) == 2
        assert any(p["nombre"] == "TITULAR A" and p["titular"] for p in d["personas"])

        c = json.loads(h["cubrimientos"].call({"codigo_puesto": "25", "estado": "pendiente"}))
        assert c["total"] == 1 and c["cubrimientos"][0]["nombre"] == "EXTRA Y"

        assert json.loads(h["buscar_puestos"].call({"texto": "47"}))[0]["codigo"] == "47A"
        assert "error" in json.loads(h["detalle_puesto"].call({"codigo": "no-existe"}))
        assert ctx.herramientas_usadas == ["resumen_cobertura", "detalle_puesto", "cubrimientos", "buscar_puestos", "detalle_puesto"]


def test_sin_datos_personales_seudonimiza(admin, db):
    _cargar(admin)
    with db() as s:
        h, _ = _herramientas(s, datos_personales=False)
        texto = h["cubrimientos"].call({})
    assert "EXTRA Y" not in texto and "Persona-" in texto
    assert '"cedula"' not in texto


def test_herramientas_respetan_permisos(admin, db):
    admin.post("/api/roles", json={"nombre": "Solo usuarios", "permisos": ["usuarios.ver"]})
    rid = next(r["id"] for r in admin.get("/api/roles").json()["data"] if r["nombre"] == "Solo usuarios")
    admin.post("/api/usuarios", json={"username": "limitado", "nombre": "Limitado", "password": "clave-segura-1", "roles": [rid]})
    _cargar(admin)
    with db() as s:
        h, _ = _herramientas(s, "limitado")
        r = json.loads(h["resumen_cobertura"].call({}))
    assert "permiso" in r["error"]


class _ProveedorFalso:
    """Simula un proveedor compatible con OpenAI (OpenRouter): pide una herramienta y luego responde."""

    def __init__(self, respuestas=None):
        self.cuerpos: list[dict] = []
        self.cabeceras: list = []
        self.respuestas = respuestas

    def __call__(self, request: httpx.Request) -> httpx.Response:
        cuerpo = json.loads(request.content)
        self.cuerpos.append(cuerpo)
        self.cabeceras.append(request.headers)
        if self.respuestas:
            return self.respuestas.pop(0)
        uso = {"prompt_tokens": 100, "completion_tokens": 20}
        if len(self.cuerpos) == 1:
            llamada = {"id": "c1", "type": "function", "function": {"name": "estado_datos", "arguments": "{}"}}
            return httpx.Response(200, json={"model": cuerpo["model"], "usage": uso, "choices": [
                {"finish_reason": "tool_calls", "message": {"role": "assistant", "content": None, "tool_calls": [llamada]}}]})
        return httpx.Response(200, json={"model": cuerpo["model"], "usage": uso, "choices": [
            {"finish_reason": "stop", "message": {"role": "assistant", "content": "La cobertura sale de 1 − descubiertas ÷ vendidas."}}]})


@pytest.fixture
def con_clave(monkeypatch):
    monkeypatch.setattr(get_settings(), "ia_api_key", "sk-or-prueba")
    falso = _ProveedorFalso()
    monkeypatch.setattr(ia, "cliente_http", lambda: httpx.Client(transport=httpx.MockTransport(falso)))
    return falso


def test_endpoint_responde_y_audita(admin, con_clave):
    r = admin.post("/api/capacidad/asistente", json={"mensajes": [{"rol": "usuario", "texto": "¿De dónde sale la cobertura?"}]})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert "descubiertas" in d["texto"] and d["usadas_hoy"] == 1
    assert d["herramientas"] == ["estado_datos"]
    # Lo enviado al proveedor: modelo, instrucciones, pregunta, herramientas y la política de datos de OpenRouter
    primero, segundo = con_clave.cuerpos
    assert primero["model"] == get_settings().ia_modelo
    assert primero["messages"][0]["role"] == "system" and primero["messages"][1:] == [{"role": "user", "content": "¿De dónde sale la cobertura?"}]
    assert {t["function"]["name"] for t in primero["tools"]} >= {"resumen_cobertura", "detalle_puesto"}
    assert primero["provider"] == {"data_collection": "deny", "zdr": True}
    assert con_clave.cabeceras[0]["authorization"] == "Bearer sk-or-prueba"
    # El resultado de la herramienta vuelve al modelo en la segunda llamada
    assert segundo["messages"][-1]["role"] == "tool" and "matrices" in segundo["messages"][-1]["content"]
    assert admin.get("/api/capacidad/asistente/estado").json()["data"]["usadas_hoy"] == 1


def test_sin_clave_responde_503(admin, monkeypatch):
    monkeypatch.setattr(get_settings(), "ia_api_key", "")
    r = admin.post("/api/capacidad/asistente", json={"mensajes": [{"rol": "usuario", "texto": "hola"}]})
    assert r.status_code == 503 and r.json()["error"]["code"] == "ASISTENTE_NO_CONFIGURADO"
    assert admin.get("/api/capacidad/asistente/estado").json()["data"]["configurado"] is False


def test_validaciones_y_limite_diario(admin, con_clave, monkeypatch):
    assert admin.post("/api/capacidad/asistente", json={"mensajes": [{"rol": "asistente", "texto": "x"}]}).status_code == 422
    assert admin.post("/api/capacidad/asistente", json={"mensajes": [{"rol": "usuario", "texto": "x" * 5000}]}).status_code == 422
    monkeypatch.setattr(get_settings(), "asistente_max_diario", 1)
    assert admin.post("/api/capacidad/asistente", json={"mensajes": [{"rol": "usuario", "texto": "uno"}]}).status_code == 200
    r = admin.post("/api/capacidad/asistente", json={"mensajes": [{"rol": "usuario", "texto": "dos"}]})
    assert r.status_code == 429 and "límite" in r.json()["error"]["message"]


def test_sin_permiso_de_asistente(admin, con_clave):
    admin.post("/api/roles", json={"nombre": "Sin IA", "permisos": ["capacidad.analisis.ver"]})
    rid = next(r["id"] for r in admin.get("/api/roles").json()["data"] if r["nombre"] == "Sin IA")
    admin.post("/api/usuarios", json={"username": "sinia", "nombre": "Sin IA", "password": "clave-segura-1", "roles": [rid]})
    admin.post("/api/auth/logout")
    entrar(admin, "sinia", "clave-segura-1")
    assert admin.post("/api/capacidad/asistente", json={"mensajes": [{"rol": "usuario", "texto": "hola"}]}).status_code == 403


def test_contexto_de_pantalla(admin, con_clave):
    _cargar(admin)
    puesto_id = next(p["id"] for p in admin.get("/api/capacidad/maestros/puestos?q=25").json()["data"] if p["codigo"] == "25")
    r = admin.post("/api/capacidad/asistente", json={"mensajes": [{"rol": "usuario", "texto": "¿Por qué hay hueco?"}],
                                          "pantalla": f"/capacidad/cobertura/{puesto_id}?analisis=1"})
    assert r.status_code == 200
    contenido = con_clave.cuerpos[0]["messages"][-1]["content"]
    assert "puesto 25" in contenido and contenido.endswith("¿Por qué hay hueco?")
    assert admin.post("/api/capacidad/asistente", json={"mensajes": [{"rol": "usuario", "texto": "x"}], "pantalla": "javascript:alert(1)"}).status_code == 422


def test_errores_del_proveedor(admin, monkeypatch):
    monkeypatch.setattr(get_settings(), "ia_api_key", "sk-or-prueba")
    casos = [(401, 503, "ASISTENTE_NO_CONFIGURADO"), (402, 503, "ASISTENTE_NO_CONFIGURADO"), (429, 429, None), (500, 502, "ERROR_IA")]
    for estado, esperado, codigo in casos:
        falso = _ProveedorFalso([httpx.Response(estado, json={"error": {"code": estado, "message": "x"}})])
        monkeypatch.setattr(ia, "cliente_http", lambda f=falso: httpx.Client(transport=httpx.MockTransport(f)))
        r = admin.post("/api/capacidad/asistente", json={"mensajes": [{"rol": "usuario", "texto": "hola"}]})
        assert r.status_code == esperado, (estado, r.text)
        if codigo:
            assert r.json()["error"]["code"] == codigo


def test_esquema_de_herramienta_desde_la_firma():
    @ia.herramienta
    def ejemplo(codigo: str, anio: int | None = None) -> str:
        """Hace algo.

        Args:
            codigo: Código del puesto,
                en varias líneas.
            anio: Año.
        """
        return codigo

    assert ejemplo.nombre == "ejemplo" and ejemplo.descripcion == "Hace algo."
    assert ejemplo.parametros["required"] == ["codigo"]
    assert ejemplo.parametros["properties"]["anio"] == {"type": "integer", "description": "Año."}
    assert ejemplo.parametros["properties"]["codigo"]["description"] == "Código del puesto, en varias líneas."
    assert ia._ejecutar(ejemplo, '{"codigo": "25", "otro": 1}') == "25"
    assert "error" in ia._ejecutar(ejemplo, "no-json")
