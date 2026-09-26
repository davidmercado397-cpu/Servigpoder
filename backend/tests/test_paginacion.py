from tests.conftest import archivo, xlsx
from tests.test_f1 import MATRIZ


def _matriz_grande(admin, n=120):
    filas = MATRIZ[:2] + [[str(900 + i), str(900 + i), "800", f"CLIENTE {i:03d}", "3", "4x2", "PUERTA", "CALI", "TERNA NORMAL"]
                          for i in range(n)]
    r = admin.post("/api/capacidad/matriz/importar", data={"anio": 2026, "mes": 9}, files=archivo(xlsx(filas)))
    assert r.status_code == 201, r.text
    return r.json()["data"]["periodo_id"]


def test_paginas_de_50_100_y_150(admin):
    pid = _matriz_grande(admin)
    url = f"/api/capacidad/matriz/periodos/{pid}/puestos"

    r = admin.get(url).json()  # por defecto 50
    assert len(r["data"]) == 50
    assert {k: r["meta"]["extra"][k] for k in ("total", "pagina", "tamano", "paginas")} == {"total": 120, "pagina": 1, "tamano": 50, "paginas": 3}

    ultima = admin.get(f"{url}?pagina=3&tamano=50").json()
    assert len(ultima["data"]) == 20
    primeras = {p["puesto"]["codigo"] for p in r["data"]}
    assert primeras.isdisjoint({p["puesto"]["codigo"] for p in ultima["data"]})

    assert admin.get(f"{url}?tamano=100").json()["meta"]["extra"]["paginas"] == 2
    assert len(admin.get(f"{url}?tamano=150").json()["data"]) == 120


def test_tamano_no_permitido(admin):
    pid = _matriz_grande(admin, 5)
    for tamano in (10, 200, 1000):
        r = admin.get(f"/api/capacidad/matriz/periodos/{pid}/puestos?tamano={tamano}")
        assert r.status_code == 422 and "50, 100 o 150" in r.json()["error"]["message"]
    assert admin.get(f"/api/capacidad/matriz/periodos/{pid}/puestos?pagina=0").status_code == 422


def test_pagina_fuera_de_rango_devuelve_vacio(admin):
    pid = _matriz_grande(admin, 5)
    r = admin.get(f"/api/capacidad/matriz/periodos/{pid}/puestos?pagina=9").json()
    assert r["data"] == [] and r["meta"]["extra"]["total"] == 5


def test_filtros_y_paginacion_combinados(admin):
    _matriz_grande(admin)
    r = admin.get("/api/capacidad/maestros/puestos?q=CLIENTE 01&tamano=50").json()
    assert r["meta"]["extra"]["total"] == 10  # CLIENTE 010 … 019
    opciones = admin.get("/api/capacidad/maestros/puestos/opciones?q=CLIENTE").json()["data"]
    assert len(opciones) == 20  # el selector recibe máximo 20


def test_auditoria_y_usuarios_paginados(admin):
    r = admin.get("/api/plataforma/auditoria?tamano=50").json()
    assert r["meta"]["extra"]["tamano"] == 50 and r["meta"]["extra"]["total"] >= 1
    u = admin.get("/api/usuarios?tamano=100").json()
    assert u["meta"]["extra"]["total"] == 1 and u["data"][0]["username"] == "admin"
