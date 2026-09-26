import time

import pyotp
from fastapi.testclient import TestClient

from app.core.security import crear_token_sesion
from app.main import app
from app.models import Usuario
from tests.conftest import CSRF, RECUPERACION, SECRETOS, entrar


def _login(client, user="admin", pwd="admin-clave-123"):
    return client.post("/api/auth/login", json={"username": user, "password": pwd})


def test_contrasena_sola_no_da_sesion(client):
    r = _login(client)
    assert r.json()["data"]["paso"] == "enrolar_mfa" and r.json()["data"]["sesion"] is None
    assert "sesion=" not in r.headers.get("set-cookie", "")
    # La cookie de pre-autenticación no sirve para usar la API
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/usuarios").status_code == 401


def test_configurar_mfa(client, db):
    _login(client)
    conf = client.post("/api/auth/mfa/configurar").json()["data"]
    assert conf["qr"].startswith("data:image/svg+xml;base64,") and conf["uri"].startswith("otpauth://totp/")
    assert client.post("/api/auth/mfa/activar", json={"codigo": "000000"}).status_code == 401

    r = client.post("/api/auth/mfa/activar", json={"codigo": pyotp.TOTP(conf["secreto"]).now()})
    d = r.json()["data"]
    assert d["paso"] == "listo" and d["sesion"]["mfa_activo"] and len(d["codigos_recuperacion"]) == 10
    assert client.get("/api/auth/me").status_code == 200
    # El secreto se guarda cifrado
    with db() as s:
        u = s.query(Usuario).filter_by(username="admin").one()
        assert u.mfa_secreto and conf["secreto"] not in u.mfa_secreto
        assert all(c not in u.mfa_recuperacion for c in d["codigos_recuperacion"])


def test_segundo_ingreso_pide_codigo_y_evita_repeticion(client):
    entrar(client, "admin", "admin-clave-123")
    secreto = SECRETOS["admin"]
    client.post("/api/auth/logout")

    assert _login(client).json()["data"]["paso"] == "mfa"
    assert client.post("/api/auth/mfa/verificar", json={"codigo": "123456"}).status_code == 401
    # El código usado al activar no se acepta de nuevo (protección contra repetición)
    paso_usado = int(time.time()) // 30
    repetido = pyotp.TOTP(secreto).generate_otp(paso_usado)
    assert client.post("/api/auth/mfa/verificar", json={"codigo": repetido}).status_code == 401
    siguiente = pyotp.TOTP(secreto).generate_otp(paso_usado + 1)
    assert client.post("/api/auth/mfa/verificar", json={"codigo": siguiente}).status_code == 200


def test_codigo_de_recuperacion_es_de_un_solo_uso(client):
    entrar(client, "admin", "admin-clave-123")
    codigo = RECUPERACION["admin"][0]
    for esperado in (200, 401):
        client.post("/api/auth/logout")
        _login(client)
        assert client.post("/api/auth/mfa/verificar", json={"codigo": codigo}).status_code == esperado


def test_bloqueo_por_codigos_incorrectos(client):
    entrar(client, "admin", "admin-clave-123")
    client.post("/api/auth/logout")
    _login(client)
    for _ in range(5):
        client.post("/api/auth/mfa/verificar", json={"codigo": "000000"})
    r = client.post("/api/auth/mfa/verificar", json={"codigo": "111111"})
    assert r.status_code == 423


def test_contrasena_temporal_obliga_a_cambiarla(admin):
    admin.post("/api/usuarios", json={"username": "nuevo", "nombre": "Nuevo", "password": "temporal-123"})
    with TestClient(app, headers=CSRF) as c:
        _login(c, "nuevo", "temporal-123")
        conf = c.post("/api/auth/mfa/configurar").json()["data"]
        r = c.post("/api/auth/mfa/activar", json={"codigo": pyotp.TOTP(conf["secreto"]).now()})
        assert r.json()["data"]["sesion"]["debe_cambiar_password"] is True
        # Solo puede cambiar la contraseña
        r = c.get("/api/plataforma/apps")
        assert r.status_code == 403 and r.json()["error"]["code"] == "CAMBIO_PASSWORD_REQUERIDO"
        assert c.post("/api/auth/cambiar-password", json={"actual": "mala-123456", "nueva": "definitiva-456"}).status_code == 400
        assert c.post("/api/auth/cambiar-password", json={"actual": "temporal-123", "nueva": "temporal-123"}).status_code == 400
        r = c.post("/api/auth/cambiar-password", json={"actual": "temporal-123", "nueva": "definitiva-456"})
        assert r.status_code == 200 and r.json()["data"]["debe_cambiar_password"] is False
        assert c.get("/api/plataforma/apps").status_code == 200


def test_restablecer_mfa(admin):
    admin.post("/api/usuarios", json={"username": "perdio", "nombre": "Perdió el teléfono", "password": "clave-segura-1"})
    uid = next(u["id"] for u in admin.get("/api/usuarios").json()["data"] if u["username"] == "perdio")
    with TestClient(app, headers=CSRF) as c:
        entrar(c, "perdio", "clave-segura-1")
        assert c.get("/api/auth/me").status_code == 200
        r = admin.post(f"/api/usuarios/{uid}/restablecer-mfa")
        assert r.status_code == 200 and r.json()["data"]["mfa_activo"] is False
        assert c.get("/api/auth/me").status_code == 401  # su sesión se cerró
        c.post("/api/auth/logout")
        assert _login(c, "perdio", "clave-segura-1-n1").json()["data"]["paso"] == "enrolar_mfa"


def test_sesion_vence_por_duracion_maxima(admin, db):
    with db() as s:
        u = s.query(Usuario).filter_by(username="admin").one()
        vieja = crear_token_sesion(u.id, u.sesion_version, auth_time=int(time.time()) - 13 * 3600)
    admin.cookies.set("sesion", vieja)
    assert admin.get("/api/auth/me").status_code == 401


def test_auditoria(admin):
    r = admin.get("/api/plataforma/auditoria?accion=login").json()
    assert r["success"] and any(a["accion"] == "login_exitoso" and a["usuario"] == "admin" for a in r["data"])
    assert any(a["detalle"].get("mfa") == "totp" for a in r["data"] if a["accion"] == "login_exitoso")
