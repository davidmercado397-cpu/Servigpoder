"""Puestos nuevos creados desde la aplicación: maestro, matriz comercial y equivalencia de SIESA."""

from tests.conftest import archivo, xlsx
from tests.test_f1 import HORARIOS, importar_matriz, programacion

API = "/api/capacidad"


def _cargar_programacion(admin) -> int:
    sep = importar_matriz(admin).json()["data"]["periodo_id"]
    admin.post(f"{API}/catalogos/turnos/importar", files=archivo(xlsx(HORARIOS)))
    filas = programacion({"25": ["06:00 - 18:00"], "2843-7G": ["06:00 - 18:00", "18:00 - 06:00"]})
    assert admin.post(f"{API}/programacion/cargas", files=archivo(xlsx(filas))).status_code == 201
    return sep


def test_crear_puesto_desde_por_aclarar(admin):
    sep = _cargar_programacion(admin)
    r = admin.get(f"{API}/maestros/por-aclarar").json()
    fila = r["data"][0]
    assert fila["codigo_siesa"] == "2843-7G" and fila["ubicacion_siesa"] == "2843" and fila["ubicacion"] is None
    assert r["meta"]["extra"]["matriz"] == {"id": sep, "estado": "borrador"} and r["meta"]["extra"]["mes"] == 9

    datos = {"codigo": "2843-7G", "descripcion": "PORTERIA SENA", "ubicacion_codigo": "2843", "codigo_siesa": "2843-7G",
             "periodo_id": sep, "hombres": "2", "secuencia": "4x2"}
    r = admin.post(f"{API}/maestros/puestos", json=datos)
    assert r.status_code == 422 and r.json()["error"]["code"] == "UBICACION_NUEVA"  # la ubicación no existe: pide su nombre

    r = admin.post(f"{API}/maestros/puestos", json={**datos, "ubicacion_nombre": "SENA", "ubicacion_ciudad": "CALI"})
    assert r.status_code == 201, r.text
    creado = r.json()["data"]
    assert creado["ubicacion_creada"] and creado["equivalencia"] == "2843-7G" and creado["matriz_puesto_id"]
    assert creado["puesto"]["ubicacion"]["nombre"] == "SENA"

    # Quedó aclarado, en la matriz del mes (para configurar su cobertura) y con la programación ya cruzada
    assert admin.get(f"{API}/maestros/por-aclarar").json()["data"] == []
    mp = next(m for m in admin.get(f"{API}/matriz/periodos/{sep}/puestos?q=2843").json()["data"] if m["puesto"]["codigo"] == "2843-7G")
    assert mp["hombres"] == "2.00" and mp["secuencia"] == "4x2" and mp["requiere_revision"] and mp["franjas"] == []
    r = admin.patch(f"{API}/matriz/puestos/{mp['id']}", json={"franjas": [{"dias": 127, "inicio": "06:00", "fin": "18:00", "cantidad": 1}],
                                                             "requiere_revision": False})
    assert r.status_code == 200 and len(r.json()["data"]["franjas"]) == 1

    assert admin.post(f"{API}/maestros/puestos", json={**datos, "ubicacion_nombre": "SENA"}).status_code == 409  # ya existe
    # Un segundo puesto en la misma ubicación ya no pide su nombre
    r = admin.post(f"{API}/maestros/puestos", json={"codigo": "2843-8", "ubicacion_codigo": "2843"})
    assert r.status_code == 201 and not r.json()["data"]["ubicacion_creada"] and r.json()["data"]["matriz_puesto_id"] is None


def test_agregar_puesto_existente_a_la_matriz(admin):
    importar_matriz(admin)
    oct_ = importar_matriz(admin, mes=10).json()["data"]["periodo_id"]
    nuevo = admin.post(f"{API}/maestros/puestos", json={"codigo": "999", "ubicacion_codigo": "999", "ubicacion_nombre": "CLIENTE NUEVO"})
    pid = nuevo.json()["data"]["puesto"]["id"]
    r = admin.post(f"{API}/matriz/periodos/{oct_}/puestos", json={"puesto_id": pid, "hombres": "1"})
    assert r.status_code == 201 and r.json()["data"]["puesto"]["codigo"] == "999"
    assert admin.post(f"{API}/matriz/periodos/{oct_}/puestos", json={"puesto_id": pid}).status_code == 409
    # Un mes cerrado no admite puestos nuevos
    admin.put(f"{API}/matriz/periodos/{oct_}/estado", json={"estado": "cerrado"})
    otro = admin.post(f"{API}/maestros/puestos", json={"codigo": "999-1", "ubicacion_codigo": "999"}).json()["data"]["puesto"]["id"]
    assert admin.post(f"{API}/matriz/periodos/{oct_}/puestos", json={"puesto_id": otro}).status_code == 409
    assert [u["codigo"] for u in admin.get(f"{API}/maestros/ubicaciones/opciones?q=nuevo").json()["data"]] == ["999"]
