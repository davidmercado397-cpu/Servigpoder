"""Instructivos SIESA: carga de PDF (solo el texto), búsqueda y respuestas limitadas a la base."""

from io import BytesIO

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from app.apps.siesa import services
from app.core import ia
from tests.conftest import ACCESOS, entrar

API = "/api/siesa"


def _pdf(paginas: list[list[str]], titulo: str = "") -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    if titulo:
        c.setTitle(titulo)
    for lineas in paginas:
        y = 720
        for linea in lineas:
            c.drawString(60, y, linea)
            y -= 18
        c.showPage()
    c.save()
    return buf.getvalue()


INSTRUCTIVO = _pdf([
    ["Instructivo de creacion de terceros en SIESA Enterprise.",
     "Paso 1. Ingrese al menu Generales, opcion Terceros.",
     "Paso 2. Haga clic en el boton Nuevo y digite el NIT del tercero.",
     "Paso 3. Seleccione el tipo de identificacion y guarde con F10."],
    ["Anulacion de documentos contables.",
     "Para anular un documento contable ingrese a Contabilidad, Movimiento, Documentos.",
     "Busque el documento y use la opcion Anular. El documento queda en estado anulado."],
], titulo="Manual de terceros y documentos")


def _subir(cliente, *archivos: tuple[str, bytes]):
    return cliente.post(f"{API}/documentos", files=[("archivos", (n, c, "application/pdf")) for n, c in archivos])


def test_carga_solo_texto_y_valida_archivos(admin):
    r = _subir(admin, ("terceros.pdf", INSTRUCTIVO), ("notas.txt", b"hola"), ("escaneado.pdf", _pdf([[]])))
    assert r.status_code == 200, r.text
    ok_, txt, escaneado = r.json()["data"]
    assert ok_["ok"] and ok_["documento"]["titulo"] == "Manual de terceros y documentos" and ok_["documento"]["paginas"] == 2
    assert ok_["documento"]["fragmentos"] >= 2
    assert not txt["ok"] and "PDF" in txt["error"]
    assert not escaneado["ok"] and "escaneado" in escaneado["error"]
    # El mismo PDF otra vez no se duplica
    otra = _subir(admin, ("copia.pdf", INSTRUCTIVO)).json()["data"][0]
    assert otra["duplicado"] and "terceros.pdf" in otra["advertencias"][0]
    docs = admin.get(f"{API}/documentos").json()["data"]
    assert [d["nombre"] for d in docs] == ["terceros.pdf"]
    assert admin.get(f"{API}/estado").json()["data"]["paginas"] == 2


def test_responde_solo_con_la_base_y_cita_las_fuentes(admin, monkeypatch):
    _subir(admin, ("terceros.pdf", INSTRUCTIVO))
    llamadas = []

    def falso(instrucciones, mensajes, **kw):
        llamadas.append(instrucciones)
        return ia.Respuesta(texto="1. Ingrese a Generales > Terceros [1].\n2. Clic en Nuevo y digite el NIT [1].", modelo="prueba")

    monkeypatch.setattr(ia, "completar", falso)
    monkeypatch.setattr(ia, "configurada", lambda: True)
    r = admin.post(f"{API}/chat", json={"mensajes": [{"rol": "usuario", "texto": "¿Cómo creo un tercero nuevo?"}]}).json()["data"]
    assert r["encontrado"] and r["fuentes"][0]["documento"] == "Manual de terceros y documentos" and r["fuentes"][0]["pagina"] == 1
    assert "Paso 2. Haga clic en el boton Nuevo" in llamadas[0]  # el modelo recibe el texto del instructivo
    assert "EXCLUSIVAMENTE" in llamadas[0]

    # Pregunta sin relación con los instructivos: ni siquiera se consulta al modelo
    r = admin.post(f"{API}/chat", json={"mensajes": [{"rol": "usuario", "texto": "¿Quién ganó el mundial de fútbol?"}]}).json()["data"]
    assert not r["encontrado"] and r["texto"] == services.NO_ENCONTRADO and len(llamadas) == 1

    # Una respuesta sin citar los instructivos se descarta
    monkeypatch.setattr(ia, "completar", lambda *a, **k: ia.Respuesta(texto="Los terceros se crean en el módulo de ventas."))
    r = admin.post(f"{API}/chat", json={"mensajes": [{"rol": "usuario", "texto": "¿Cómo creo un tercero?"}]}).json()["data"]
    assert not r["encontrado"] and r["fuentes"] == []

    # Pregunta corta de seguimiento: se busca junto con la anterior
    assert "anulo" in services._consulta([{"role": "user", "content": "¿Cómo anulo un documento contable?"},
                                            {"role": "assistant", "content": "…"},
                                            {"role": "user", "content": "¿y luego?"}]).lower()
    eventos = admin.get("/api/plataforma/auditoria?accion=asistente_pregunta").json()["data"]
    assert eventos[0]["detalle"]["app"] == "siesa" and eventos[0]["empresa"] == "servigpoder"


def test_busqueda_encuentra_la_pagina_correcta(admin, en_empresa):
    _subir(admin, ("terceros.pdf", INSTRUCTIVO))
    with en_empresa("servigpoder") as s:
        primero = services.buscar(s, "anular documento contable")[0]
        assert primero.pagina == 2 and "Anular" in primero.texto
        assert services.buscar(s, "receta de arepas") == []


def test_trocear_respeta_el_tamano_y_la_pagina():
    texto = " ".join(f"Oracion numero {i} del instructivo." for i in range(200))
    partes = services.trocear([texto, "", "Pagina tres corta."])
    assert all(len(t) <= services.TAMANO_FRAGMENTO + services.SOLAPE + 50 for _, t in partes)
    assert partes[-1] == (3, "Pagina tres corta.") and {p for p, _ in partes} == {1, 3}


def test_permisos(admin):
    _subir(admin, ("terceros.pdf", INSTRUCTIVO))
    rid = next(r["id"] for r in admin.get("/api/roles").json()["data"] if r["nombre"] == "Consulta instructivos SIESA")
    admin.post("/api/usuarios", json={"accesos": ACCESOS, "username": "consulta", "nombre": "Consulta", "password": "clave-segura-1", "roles": [rid]})
    doc = admin.get(f"{API}/documentos").json()["data"][0]["id"]
    admin.post("/api/auth/logout")
    entrar(admin, "consulta", "clave-segura-1")
    admin.post("/api/plataforma/empresa", json={"codigo": "servigpoder"})
    assert admin.get(f"{API}/documentos").status_code == 200
    assert _subir(admin, ("otro.pdf", INSTRUCTIVO)).status_code == 403
    assert admin.delete(f"{API}/documentos/{doc}").status_code == 403
    admin.post("/api/auth/logout")
    entrar(admin, "admin", "admin-clave-123")
    assert admin.delete(f"{API}/documentos/{doc}").status_code == 200
    assert admin.get(f"{API}/documentos").json()["data"] == []
