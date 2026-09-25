def test_login_invalido(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "mala"})
    assert r.status_code == 401


def test_sin_sesion(client):
    assert client.get("/api/auth/me").status_code == 401


def test_admin_tiene_todos_los_permisos(admin):
    me = admin.get("/api/auth/me").json()
    assert "usuarios.gestionar" in me["permisos"]
    assert [r["nombre"] for r in me["roles"]] == ["Administrador"]


def test_roles_base(admin):
    nombres = {r["nombre"] for r in admin.get("/api/roles").json()}
    assert nombres == {"Administrador", "Programador", "Nómina"}


def test_crear_usuario_y_permisos_por_rol(admin):
    roles = {r["nombre"]: r["id"] for r in admin.get("/api/roles").json()}
    r = admin.post(
        "/api/usuarios",
        json={"username": "Nomina1", "nombre": "Especialista Nómina", "password": "clave-segura-1", "roles": [roles["Nómina"]]},
    )
    assert r.status_code == 201
    assert r.json()["username"] == "nomina1"

    admin.post("/api/auth/logout")
    assert admin.post("/api/auth/login", json={"username": "nomina1", "password": "clave-segura-1"}).status_code == 200
    me = admin.get("/api/auth/me").json()
    assert "cubrimientos.aprobar" in me["permisos"]
    assert "usuarios.gestionar" not in me["permisos"]
    # Nómina no puede administrar usuarios
    assert admin.get("/api/usuarios").status_code == 403


def test_rol_dinamico(admin):
    r = admin.post("/api/roles", json={"nombre": "Consulta", "descripcion": "Solo lectura", "permisos": ["analisis.ver"]})
    assert r.status_code == 201
    rid = r.json()["id"]
    r = admin.put(f"/api/roles/{rid}", json={"nombre": "Consulta", "permisos": ["analisis.ver", "matriz.ver"]})
    assert r.json()["permisos"] == ["analisis.ver", "matriz.ver"]
    assert admin.post("/api/roles", json={"nombre": "X", "permisos": ["no.existe"]}).status_code in (400, 422)


def test_usuario_desactivado_no_entra(admin):
    r = admin.post("/api/usuarios", json={"username": "temp", "nombre": "Temporal", "password": "clave-segura-1"})
    uid = r.json()["id"]
    admin.patch(f"/api/usuarios/{uid}", json={"activo": False})
    admin.post("/api/auth/logout")
    assert admin.post("/api/auth/login", json={"username": "temp", "password": "clave-segura-1"}).status_code == 401


def test_no_puede_desactivarse_a_si_mismo(admin):
    me = admin.get("/api/auth/me").json()
    assert admin.patch(f"/api/usuarios/{me['id']}", json={"activo": False}).status_code == 400
