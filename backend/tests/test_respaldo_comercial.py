"""Respaldo de la base comercial: se descarga en una instalación y se restaura idéntico en otra."""

import json

from tests.conftest import archivo, xlsx
from tests.test_f1 import HORARIOS, importar_matriz

API = "/api/capacidad/matriz/respaldo"


def _sin_fecha(datos: dict) -> dict:
    return {k: v for k, v in datos.items() if k != "generado"}


def _restaurar(cliente, contenido: bytes, nombre: str = "base_comercial.json"):
    return cliente.post(API, files={"archivo": (nombre, contenido, "application/json")})


def test_respaldo_y_restauracion_en_otra_empresa(admin):
    # Base comercial con ajustes hechos en la aplicación: horarios, una excepción, una nota y un mes aprobado
    admin.post("/api/capacidad/catalogos/turnos/importar", files=archivo(xlsx(HORARIOS)))
    sep = importar_matriz(admin).json()["data"]["periodo_id"]
    mp = admin.get(f"/api/capacidad/matriz/periodos/{sep}/puestos").json()["data"][0]
    admin.patch(f"/api/capacidad/matriz/puestos/{mp['id']}", json={"hombres": "2", "nota": "Ajustado con el cliente"})
    admin.post(f"/api/capacidad/matriz/puestos/{mp['id']}/excepciones", json={"fecha": "2026-09-16", "sin_servicio": True, "observacion": "Cierre"})
    admin.put(f"/api/capacidad/matriz/periodos/{sep}/estado", json={"estado": "aprobado"})
    importar_matriz(admin, mes=10)

    r = admin.get(API)
    assert r.status_code == 200 and r.headers["content-disposition"].startswith('attachment; filename="base_comercial_')
    original = r.json()
    assert [(p["anio"], p["mes"], p["estado"]) for p in original["periodos"]] == [(2026, 9, "aprobado"), (2026, 10, "borrador")]

    # Otra instalación vacía (otra empresa con su propio esquema)
    admin.post("/api/empresas", json={"codigo": "destino", "nombre": "Destino", "apps": ["capacidad"]})
    admin.post("/api/plataforma/empresa", json={"codigo": "destino"})
    assert admin.get("/api/capacidad/matriz/periodos").json()["data"] == []
    r = _restaurar(admin, r.content)
    assert r.status_code == 200, r.text
    res = r.json()["data"]
    assert res["creados"]["puestos"] == len(original["puestos"]) and len(res["meses_restaurados"]) == 2
    assert _sin_fecha(admin.get(API).json()) == _sin_fecha(original)  # idéntica

    # Restaurar de nuevo: actualiza maestros y no toca el mes aprobado
    res = _restaurar(admin, json.dumps(original).encode()).json()["data"]
    assert res["creados"] == {} and res["meses_omitidos"][0].startswith("09/2026")
    assert res["meses_restaurados"] == ["10/2026 (7 puestos, borrador)"]
    assert _sin_fecha(admin.get(API).json()) == _sin_fecha(original)


def test_respaldo_invalido(admin):
    assert _restaurar(admin, b"no es json").status_code == 422
    assert _restaurar(admin, json.dumps({"tipo": "otra cosa"}).encode()).status_code == 422
    assert _restaurar(admin, b"{}", "base.xlsx").status_code == 415
