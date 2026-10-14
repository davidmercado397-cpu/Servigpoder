"""Marca de la plataforma: lectura pública, edición con permiso e imágenes validadas y normalizadas."""

from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from tests.conftest import ACCESOS, CSRF, entrar

API = "/api/marca"


def _imagen(formato: str = "PNG", tamano=(1200, 900), color=(29, 95, 191, 255)) -> bytes:
    buf = BytesIO()
    modo = "RGBA" if formato == "PNG" else "RGB"
    Image.new(modo, tamano, color if modo == "RGBA" else color[:3]).save(buf, formato)
    return buf.getvalue()


def _subir(cliente, tipo: str, contenido: bytes, nombre: str = "img.png"):
    return cliente.post(f"{API}/imagen/{tipo}", files={"archivo": (nombre, contenido, "application/octet-stream")})


VALORES = {"nombre": "Grupo SERA", "subtitulo": "Plataforma de gestión", "color_primario": "#0F766E", "color_acento": "#facc15",
           "color_barra": "#134e4a", "color_barra_fin": "#042f2e", "login_fondo": "color", "login_color": "#134e4a", "login_oscurecer": 30}


def test_lectura_publica_con_valores_de_fabrica(client):
    with TestClient(app, headers=CSRF) as anonimo:
        r = anonimo.get(API)
    assert r.status_code == 200
    m = r.json()["data"]
    assert m["nombre"] == "Plataforma Servigpoder" and m["color_primario"] == "#1d5fbf" and m["logo"] is None
    assert anonimo is not None


def test_editar_colores_y_nombre(admin):
    r = admin.put(API, json=VALORES)
    assert r.status_code == 200, r.text
    m = r.json()["data"]
    assert m["nombre"] == "Grupo SERA" and m["color_primario"] == "#0f766e" and m["login_fondo"] == "color" and m["version"] == 2
    assert admin.put(API, json={**VALORES, "color_primario": "azul"}).status_code == 422
    assert admin.put(API, json={**VALORES, "login_fondo": "video"}).status_code == 422
    eventos = admin.get("/api/plataforma/auditoria?accion=marca_editada").json()["data"]
    assert eventos[0]["detalle"]["cambios"]["nombre"] == ["Plataforma Servigpoder", "Grupo SERA"]


def test_imagenes_se_validan_y_normalizan(admin):
    r = _subir(admin, "logo", _imagen(tamano=(2000, 600)))
    assert r.status_code == 200, r.text
    logo = r.json()["data"]["logo"]
    assert (logo["ancho"], logo["alto"]) == (800, 240) and logo["url"].startswith("/api/marca/imagen/logo?v=")

    r = _subir(admin, "favicon", _imagen("JPEG", (300, 200)), "icono.jpg")
    assert r.json()["data"]["favicon"]["ancho"] == 64 and r.json()["data"]["favicon"]["alto"] == 64

    r = _subir(admin, "fondo", _imagen("PNG", (4000, 3000)), "fondo.png")
    datos = r.json()["data"]
    assert datos["fondo"]["ancho"] == 2133 and datos["login_fondo"] == "imagen"  # al subir un fondo se usa

    # Se sirven ya convertidos, con caché y ETag
    r = admin.get("/api/marca/imagen/fondo")
    assert r.headers["content-type"] == "image/jpeg" and Image.open(BytesIO(r.content)).size == (2133, 1600)
    assert admin.get("/api/marca/imagen/fondo", headers={"If-None-Match": r.headers["etag"]}).status_code == 304
    assert admin.get("/api/marca/imagen/logo").headers["content-type"] == "image/png"

    # Archivos que no son imágenes o formatos no admitidos
    assert _subir(admin, "logo", b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>", "x.svg").status_code == 415
    assert _subir(admin, "logo", b"no es una imagen", "x.png").status_code == 415
    assert _subir(admin, "banner", _imagen()).status_code == 404

    # Quitar el fondo vuelve al degradado; restablecer quita todo
    assert admin.delete(f"{API}/imagen/fondo").json()["data"]["login_fondo"] == "degradado"
    assert admin.get("/api/marca/imagen/fondo").status_code == 404
    r = admin.post(f"{API}/restablecer").json()["data"]
    assert r["nombre"] == "Plataforma Servigpoder" and r["logo"] is None and r["favicon"] is None


def test_solo_con_permiso(admin):
    rid = next(r["id"] for r in admin.get("/api/roles").json()["data"] if r["nombre"] == "Programador")
    admin.post("/api/usuarios", json={"accesos": ACCESOS, "username": "prog", "nombre": "Prog", "password": "clave-segura-1", "roles": [rid]})
    admin.post("/api/auth/logout")
    entrar(admin, "prog", "clave-segura-1")
    assert admin.get(API).status_code == 200
    assert admin.put(API, json=VALORES).status_code == 403
    assert _subir(admin, "logo", _imagen()).status_code == 403
    assert admin.post(f"{API}/restablecer").status_code == 403
    with TestClient(app, headers=CSRF) as anonimo:
        assert anonimo.put(API, json=VALORES).status_code == 401
