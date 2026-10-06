"""Empresas: cada una con sus datos en su esquema, desarrollos habilitados y acceso por usuario."""

from tests.conftest import ACCESOS, entrar
from tests.test_liquidador import API, _cargar, _quincena


def _elegir(cliente, codigo: str):
    return cliente.post("/api/plataforma/empresa", json={"codigo": codigo})


def test_empresas_iniciales(admin):
    r = admin.get("/api/empresas").json()
    empresas = {e["codigo"]: e for e in r["data"]}
    assert empresas["servigpoder"]["apps"] == ["capacidad", "nomina", "reporte"] and empresas["servigpoder"]["esquema"] == "emp_servigpoder"
    assert empresas["sera"]["apps"] == ["liquidador"] and empresas["sera"]["usuarios"] == 1
    assert [a["codigo"] for a in r["meta"]["extra"]["apps"]] == ["capacidad", "liquidador", "reporte", "nomina"]


def test_los_datos_de_una_empresa_no_se_ven_en_otra(admin):
    pid = _quincena(admin)  # en SERA (única empresa con el liquidador)
    _cargar(admin, pid)
    r = admin.post("/api/empresas", json={"codigo": "nueva", "nombre": "Nueva SAS", "apps": ["liquidador"]})
    assert r.status_code == 201, r.text
    # Con dos empresas con el liquidador hay que elegir
    admin.cookies.delete("empresa")
    r = admin.get(f"{API}/periodos")
    assert r.status_code == 409 and r.json()["error"]["code"] == "EMPRESA_REQUERIDA"

    assert _elegir(admin, "nueva").status_code == 200
    assert admin.get(f"{API}/periodos").json()["data"] == []  # esquema propio, vacío
    assert admin.get(f"{API}/empleados").json()["data"] == []
    assert admin.get(f"{API}/turnos").json()["meta"]["extra"]["total"] == 131  # con su configuración inicial
    assert admin.get(f"{API}/periodos/{pid}").status_code == 404  # el periodo de SERA no existe aquí

    _elegir(admin, "sera")
    assert [p["id"] for p in admin.get(f"{API}/periodos").json()["data"]] == [pid]
    assert admin.get(f"{API}/periodos/{pid}").json()["data"]["empleados"] == 3
    # La auditoría registra en qué empresa se trabajó
    eventos = admin.get("/api/plataforma/auditoria?accion=liq_excel_cargado").json()["data"]
    assert eventos[0]["empresa"] == "sera"


def test_desarrollo_no_habilitado_en_la_empresa(admin):
    _elegir(admin, "sera")
    r = admin.get("/api/capacidad/analisis/meses")
    assert r.status_code == 403 and r.json()["error"]["code"] == "SIN_ACCESO_EMPRESA"
    _elegir(admin, "servigpoder")
    assert admin.get("/api/capacidad/analisis/meses").status_code == 200
    # Deshabilitar el desarrollo en la empresa corta el acceso
    eid = next(e["id"] for e in admin.get("/api/empresas").json()["data"] if e["codigo"] == "servigpoder")
    assert admin.patch(f"/api/empresas/{eid}", json={"apps": ["nomina", "reporte"]}).json()["data"]["apps"] == ["nomina", "reporte"]
    assert admin.get("/api/capacidad/analisis/meses").status_code == 403


def test_accesos_del_usuario_por_empresa(admin):
    rid = next(r["id"] for r in admin.get("/api/roles").json()["data"] if r["nombre"] == "Liquidador")
    datos = {"username": "ana", "nombre": "Ana", "password": "clave-segura-1", "roles": [rid]}
    assert admin.post("/api/usuarios", json={**datos, "accesos": {"servigpoder": ["liquidador"]}}).status_code == 400  # no habilitado
    assert admin.post("/api/usuarios", json={**datos, "accesos": {"otra": ["liquidador"]}}).status_code == 400
    r = admin.post("/api/usuarios", json={**datos, "accesos": {"sera": ["liquidador"]}})
    assert r.status_code == 201 and r.json()["data"]["accesos"] == {"sera": ["liquidador"]}
    uid = r.json()["data"]["id"]

    admin.post("/api/auth/logout")
    entrar(admin, "ana", "clave-segura-1")
    me = admin.get("/api/auth/me").json()["data"]
    assert me["empresas"] == [{"codigo": "sera", "nombre": "SERA", "apps": ["liquidador"]}]
    assert admin.get(f"{API}/periodos").status_code == 200
    assert _elegir(admin, "servigpoder").status_code == 403
    assert admin.get("/api/nomina/periodos").status_code == 403  # ni su rol ni sus accesos lo permiten
    assert admin.get("/api/empresas").status_code == 403

    # Quitarle el acceso corta la entrada aunque conserve el rol
    admin.post("/api/auth/logout")
    entrar(admin, "admin", "admin-clave-123")
    r = admin.patch(f"/api/usuarios/{uid}", json={"accesos": {}})
    assert r.json()["data"]["accesos"] == {}
    admin.post("/api/auth/logout")
    entrar(admin, "ana", "clave-segura-1")
    assert admin.get(f"{API}/periodos").status_code == 403
    assert admin.get("/api/plataforma/apps").json()["data"] == []


def test_solo_quien_gestiona_empresas_las_crea(admin):
    admin.post("/api/roles", json={"nombre": "Admin usuarios", "permisos": ["usuarios.ver", "usuarios.gestionar"]})
    rid = next(r["id"] for r in admin.get("/api/roles").json()["data"] if r["nombre"] == "Admin usuarios")
    admin.post("/api/usuarios", json={"accesos": ACCESOS, "username": "rrhh", "nombre": "RRHH", "password": "clave-segura-1", "roles": [rid]})
    admin.post("/api/auth/logout")
    entrar(admin, "rrhh", "clave-segura-1")
    assert admin.get("/api/empresas").status_code == 200  # para asignar accesos
    assert admin.post("/api/empresas", json={"codigo": "otra", "nombre": "Otra", "apps": []}).status_code == 403
    assert admin.post("/api/empresas", json={"codigo": "Mal Código", "nombre": "x"}).status_code in (403, 422)
