from datetime import date

from app.apps.capacidad.services import alertas
from tests.conftest import archivo
from tests.test_cubrimientos import D, ESCENARIO, N, _cargar, reporte


def test_comparar_cargas(admin):
    _cargar(admin)
    # Nueva carga del mismo mes: el titular A cambia su noche del 17 por vacaciones y se agrega un turno
    nuevo = [list(p) for p in ESCENARIO]
    nuevo[0] = ("1", "TITULAR A", "25", {15: D, 16: D, 17: "[VAC]", 18: N, 19: "Z", 20: "L"})
    nuevo.append(("7", "NUEVO Q", "25", {17: N}))
    r = admin.post("/api/capacidad/programacion/cargas", files=archivo(reporte([tuple(p) for p in nuevo])))
    assert r.status_code == 201

    c = admin.get("/api/capacidad/programacion/comparar").json()["data"]
    assert c["por_tipo"] == {"cambiado": 1, "agregado": 1}
    cambio = next(x for x in c["cambios"] if x["tipo"] == "cambiado")
    assert (cambio["nombre"], cambio["fecha"], cambio["antes"], cambio["despues"]) == ("TITULAR A", "2026-09-17", N, "VAC")
    # Los análisis de ambas cargas existen: el cambio no altera la cobertura del 25 (Q cubre la noche)
    assert isinstance(c["impacto"], list)


def test_comparar_sin_carga_anterior(admin):
    _cargar(admin)
    r = admin.get("/api/capacidad/programacion/comparar")
    assert r.status_code == 404


def test_historico(admin):
    _cargar(admin)
    h = admin.get("/api/capacidad/historico").json()["data"]
    assert len(h) == 1 and h[0]["analisis_id"] and h[0]["cubrimientos"] == 3


def test_alertas(admin, db):
    _cargar(admin)
    with db() as s:
        lista = alertas.evaluar(s, date(2026, 9, 18))
    titulos = [a["titulo"] for a in lista]
    assert any("cubrimientos pendientes" in t for t in titulos)
    assert any("puestos con hueco" in t for t in titulos)
    assert any("borrador" in t for t in titulos)
    assert lista[0]["nivel"] == "critica"  # ordenadas por gravedad
    # Endpoint (con la fecha real) responde en formato estándar
    assert admin.get("/api/capacidad/alertas").json()["success"] is True


def test_alerta_falta_proyectar(admin, db):
    _cargar(admin)
    with db() as s:
        titulos = [a["titulo"] for a in alertas.evaluar(s, date(2026, 9, 28))]
    assert "Falta proyectar la matriz del mes siguiente" in titulos


def test_parametros(admin):
    ps = {p["clave"]: p for p in admin.get("/api/capacidad/parametros").json()["data"]}
    assert ps["umbral_cobertura"]["valor"] == "95"
    assert admin.put("/api/capacidad/parametros/umbral_cobertura", json={"valor": "90"}).json()["data"]["valor"] == "90"
    assert admin.put("/api/capacidad/parametros/umbral_cobertura", json={"valor": "abc"}).status_code == 422
    assert admin.put("/api/capacidad/parametros/no_existe", json={"valor": "1"}).status_code == 404


def test_contadores_menu(admin):
    _cargar(admin)
    c = admin.get("/api/capacidad/menu/contadores").json()["data"]
    assert c["alertas"] >= 1 and c["cubrimientos_pendientes"] == 1
