from tests.conftest import entrar
import json
from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.models import Usuario
from app.apps.capacidad.services import asistente
from tests.test_cubrimientos import _cargar


def _herramientas(db_session, username="admin", datos_personales=True):
    usuario = db_session.query(Usuario).filter_by(username=username).one()
    ctx = asistente.Contexto(db_session, usuario, datos_personales)
    return {t.name: t for t in asistente.crear_herramientas(ctx)}, ctx


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


class _ClienteFalso:
    """Simula el SDK: el Tool Runner devuelve un mensaje final con texto."""

    def __init__(self):
        self.kwargs = None
        self.beta = SimpleNamespace(messages=SimpleNamespace(tool_runner=self._runner))

    def _runner(self, **kwargs):
        self.kwargs = kwargs
        uso = SimpleNamespace(input_tokens=100, output_tokens=20)
        return [SimpleNamespace(stop_reason="end_turn", model=kwargs["model"], usage=uso,
                                content=[SimpleNamespace(type="text", text="La cobertura sale de 1 − descubiertas ÷ vendidas.")])]


@pytest.fixture
def con_clave(monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "sk-prueba")
    falso = _ClienteFalso()
    monkeypatch.setattr(asistente, "cliente", lambda: falso)
    return falso


def test_endpoint_responde_y_audita(admin, con_clave):
    r = admin.post("/api/capacidad/asistente", json={"mensajes": [{"rol": "usuario", "texto": "¿De dónde sale la cobertura?"}]})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert "descubiertas" in d["texto"] and d["usadas_hoy"] == 1
    # Parámetros enviados al SDK
    k = con_clave.kwargs
    assert k["model"] == "claude-opus-5" and k["max_iterations"] == asistente.MAX_ITERACIONES
    assert k["messages"] == [{"role": "user", "content": "¿De dónde sale la cobertura?"}]
    assert {t.name for t in k["tools"]} >= {"resumen_cobertura", "detalle_puesto"}
    assert admin.get("/api/capacidad/asistente/estado").json()["data"]["usadas_hoy"] == 1


def test_sin_clave_responde_503(admin, monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "")
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
    contenido = con_clave.kwargs["messages"][-1]["content"]
    assert "puesto 25" in contenido and contenido.endswith("¿Por qué hay hueco?")
    assert admin.post("/api/capacidad/asistente", json={"mensajes": [{"rol": "usuario", "texto": "x"}], "pantalla": "javascript:alert(1)"}).status_code == 422
