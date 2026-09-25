from app.models import Auditoria


def test_login_invalido_formato_estandar(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "mala"})
    assert r.status_code == 401
    body = r.json()
    assert body["success"] is False and body["data"] is None
    assert body["error"]["code"] == "NO_AUTENTICADO"
    assert body["meta"]["api_version"] == "v1"
    assert body["meta"]["request_id"] == r.headers["x-request-id"]


def test_respuesta_exitosa_formato_estandar(admin):
    body = admin.get("/api/auth/me").json()
    assert body["success"] is True and body["error"] is None
    assert body["data"]["username"] == "admin"
    assert set(body["meta"]) >= {"api_version", "request_id", "timestamp"}


def test_sin_sesion(client):
    assert client.get("/api/auth/me").status_code == 401


def test_admin_tiene_todos_los_permisos(admin):
    me = admin.get("/api/auth/me").json()["data"]
    assert "usuarios.gestionar" in me["permisos"]
    assert [r["nombre"] for r in me["roles"]] == ["Administrador"]


def test_roles_base(admin):
    nombres = {r["nombre"] for r in admin.get("/api/roles").json()["data"]}
    assert nombres == {"Administrador", "Programador", "Nómina"}


def test_crear_usuario_y_permisos_por_rol(admin):
    roles = {r["nombre"]: r["id"] for r in admin.get("/api/roles").json()["data"]}
    r = admin.post("/api/usuarios", json={"username": "Nomina1", "nombre": "Especialista Nómina",
                                          "password": "clave-segura-1", "roles": [roles["Nómina"]]})
    assert r.status_code == 201
    assert r.json()["data"]["username"] == "nomina1"

    admin.post("/api/auth/logout")
    assert admin.post("/api/auth/login", json={"username": "nomina1", "password": "clave-segura-1"}).status_code == 200
    me = admin.get("/api/auth/me").json()["data"]
    assert "cubrimientos.aprobar" in me["permisos"]
    r = admin.get("/api/usuarios")
    assert r.status_code == 403 and r.json()["error"]["code"] == "SIN_PERMISO"


def test_politica_de_contrasena(admin):
    r = admin.post("/api/usuarios", json={"username": "debil", "nombre": "Débil", "password": "solo-letras"})
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "DATOS_INVALIDOS"
    # Nunca se devuelve el valor enviado
    assert "solo-letras" not in r.text


def test_rol_dinamico(admin):
    r = admin.post("/api/roles", json={"nombre": "Consulta", "descripcion": "Solo lectura", "permisos": ["analisis.ver"]})
    assert r.status_code == 201
    rid = r.json()["data"]["id"]
    r = admin.put(f"/api/roles/{rid}", json={"nombre": "Consulta", "permisos": ["analisis.ver", "matriz.ver"]})
    assert r.json()["data"]["permisos"] == ["analisis.ver", "matriz.ver"]
    assert admin.post("/api/roles", json={"nombre": "XY", "permisos": ["no.existe"]}).status_code == 400


def test_usuario_desactivado_pierde_sesion(admin, client):
    admin.post("/api/usuarios", json={"username": "temp", "nombre": "Temporal", "password": "clave-segura-1"})
    uid = next(u["id"] for u in admin.get("/api/usuarios").json()["data"] if u["username"] == "temp")
    admin.patch(f"/api/usuarios/{uid}", json={"activo": False})
    admin.post("/api/auth/logout")
    assert admin.post("/api/auth/login", json={"username": "temp", "password": "clave-segura-1"}).status_code == 401


def test_cambio_de_contrasena_invalida_sesiones(admin, db):
    from fastapi.testclient import TestClient

    from app.main import app
    from tests.conftest import CSRF

    admin.post("/api/usuarios", json={"username": "prog", "nombre": "Programador", "password": "clave-segura-1"})
    uid = next(u["id"] for u in admin.get("/api/usuarios").json()["data"] if u["username"] == "prog")
    with TestClient(app, headers=CSRF) as otro:
        assert otro.post("/api/auth/login", json={"username": "prog", "password": "clave-segura-1"}).status_code == 200
        assert otro.get("/api/auth/me").status_code == 200
        admin.patch(f"/api/usuarios/{uid}", json={"password": "otra-clave-2"})
        assert otro.get("/api/auth/me").status_code == 401


def test_no_puede_desactivarse_a_si_mismo(admin):
    me = admin.get("/api/auth/me").json()["data"]
    assert admin.patch(f"/api/usuarios/{me['id']}", json={"activo": False}).status_code == 400


def test_bloqueo_por_intentos_fallidos(client):
    for _ in range(5):
        assert client.post("/api/auth/login", json={"username": "admin", "password": "mala"}).status_code == 401
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin-clave-123"})
    assert r.status_code == 423 and r.json()["error"]["code"] == "BLOQUEADO"


def test_rate_limit_login_por_ip(client):
    codigos = [client.post("/api/auth/login", json={"username": f"u{i}", "password": "x"}).status_code for i in range(11)]
    assert codigos[-1] == 429
    r = client.post("/api/auth/login", json={"username": "otro", "password": "x"})
    assert r.json()["error"]["code"] == "DEMASIADAS_SOLICITUDES"
    assert "retry-after" in r.headers


def test_csrf_requiere_cabecera(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin-clave-123"},
                    headers={"X-Requested-With": ""})
    assert r.status_code == 403 and r.json()["error"]["code"] == "CSRF"


def test_cabeceras_de_seguridad(client):
    h = client.get("/api/health").headers
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-frame-options"] == "DENY"
    assert "default-src 'none'" in h["content-security-policy"]
    assert h["cache-control"] == "no-store"
    assert "server" not in h


def test_cookie_segura(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin-clave-123"})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


def test_limite_de_tamano(admin):
    grande = b"PK\x03\x04" + b"0" * (16 * 1024 * 1024)
    r = admin.post("/api/programacion/cargas", files={"archivo": ("x.xlsx", grande, "application/octet-stream")})
    assert r.status_code == 413


def test_auditoria_registra_login(admin, db):
    with db() as s:
        acciones = [a.accion for a in s.query(Auditoria).all()]
    assert "login_exitoso" in acciones
