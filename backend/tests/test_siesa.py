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
    partes = services.trocear([texto, "", "Pagina tres corta del instructivo."])
    assert all(len(f.texto) <= services.TAMANO_FRAGMENTO + services.SOLAPE + 50 for f in partes)
    assert (partes[-1].pagina, partes[-1].texto) == (3, "Pagina tres corta del instructivo.") and {f.pagina for f in partes} == {1, 3}


def test_trocear_por_secciones_y_sin_pies_de_pagina():
    pie = "SERVIGPODER - Instructivo interno"
    paginas = [
        f"VACACIONES\n1.1 Solicitud\nEl empleado radica la solicitud en Nomina, Novedades.\n{pie}\n1",
        f"1.2 Plazos\nEl plazo para aprobar es de 30 dias.\n{pie}\n2",
        f"El jefe puede rechazar la solicitud con una observacion.\n{pie}\nPagina 3 de 3",
    ]
    partes = services.trocear(paginas)
    assert [(f.pagina, f.seccion) for f in partes] == [
        (1, "VACACIONES > 1.1 Solicitud"), (2, "VACACIONES > 1.2 Plazos"), (3, "VACACIONES > 1.2 Plazos")]
    assert all(pie not in f.texto and "Pagina 3" not in f.texto for f in partes)  # encabezados/pies repetidos fuera
    assert partes[1].texto == "El plazo para aprobar es de 30 dias."  # nunca mezcla dos secciones
    assert services.encabezado("Manual de vacaciones", partes[1].seccion, "Nómina") == "Nómina · Manual de vacaciones > VACACIONES > 1.2 Plazos"


def test_trocear_usa_el_indice_del_pdf():
    # Con marcadores (índice) del PDF, la sección sale de ellos y no de los títulos detectados en el texto
    paginas = ["Introduccion general del proceso de cierre.", "CIERRE MENSUAL\nPaso 1. Ejecute el cierre."]
    marcadores = {1: [(1, "Introduccion")], 2: [(1, "Cierre"), (2, "Cierre mensual")]}
    partes = services.trocear(paginas, marcadores)
    assert [(f.pagina, f.seccion) for f in partes] == [(1, "Introduccion"), (2, "Cierre > Cierre mensual")]


MANUAL_NOMINA = _pdf([
    ["VACACIONES", "1.1 Solicitud", "El empleado registra la solicitud de vacaciones en el menu Nomina, Novedades."],
    ["1.2 Plazos", "El jefe inmediato aprueba la solicitud de vacaciones en un plazo de 3 dias."],
], titulo="Manual de vacaciones")


def test_metadatos_y_filtro_por_modulo(admin, en_empresa, monkeypatch):
    r = admin.post(f"{API}/documentos", data={"modulo": "Nómina"},
                   files=[("archivos", ("vacaciones.pdf", MANUAL_NOMINA, "application/pdf"))]).json()["data"][0]
    assert r["ok"] and r["documento"]["modulo"] == "Nómina" and r["documento"]["secciones"] == 2
    _subir(admin, ("terceros.pdf", INSTRUCTIVO))  # sin módulo
    lista = admin.get(f"{API}/documentos").json()
    assert lista["meta"]["extra"]["modulos"] == ["Nómina"] and admin.get(f"{API}/modulos").json()["data"] == ["Nómina"]

    with en_empresa("servigpoder") as s:
        f = services.buscar(s, "plazo para aprobar vacaciones")[0]
        assert f.encabezado == "Nómina · Manual de vacaciones > VACACIONES > 1.2 Plazos" and f.pagina == 2
        assert services.buscar(s, "documento contable", modulo="Nómina") == []  # filtra antes de buscar
        assert services.buscar(s, "documento contable")[0].documento.titulo == "Manual de terceros y documentos"
        assert len(services.buscar(s, "solicitud vacaciones plazo empleado jefe menu")) <= services.FRAGMENTOS_POR_RESPUESTA

    # El modelo recibe el encabezado de contexto y la fuente trae sección y módulo
    recibido = []
    monkeypatch.setattr(ia, "completar", lambda instr, m, **k: recibido.append(instr) or ia.Respuesta(texto="Son 3 días [1]."))
    monkeypatch.setattr(ia, "configurada", lambda: True)
    r = admin.post(f"{API}/chat", json={"mensajes": [{"rol": "usuario", "texto": "¿En qué plazo se aprueban las vacaciones?"}],
                                       "modulo": "Nómina"}).json()["data"]
    assert "[1] Nómina · Manual de vacaciones > VACACIONES > 1.2 Plazos (página 2" in recibido[0]
    assert r["fuentes"][0]["seccion"] == "VACACIONES > 1.2 Plazos" and r["fuentes"][0]["modulo"] == "Nómina"

    # Editar el módulo actualiza el encabezado de sus fragmentos
    doc = next(d for d in admin.get(f"{API}/documentos").json()["data"] if d["nombre"] == "vacaciones.pdf")
    r = admin.patch(f"{API}/documentos/{doc['id']}", json={"modulo": "Gestión humana", "fecha": "2026-05-01"})
    assert r.status_code == 200 and r.json()["data"]["modulo"] == "Gestión humana" and r.json()["data"]["fecha"] == "2026-05-01"
    with en_empresa("servigpoder") as s:
        assert services.buscar(s, "plazo aprobar vacaciones")[0].encabezado.startswith("Gestión humana · Manual de vacaciones")


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
