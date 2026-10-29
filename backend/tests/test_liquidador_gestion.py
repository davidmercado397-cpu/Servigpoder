"""Gestión humana: incapacidades con CIE y prórrogas, restricciones médicas, tutelas y demandas, soportes adjuntos y
la importación del formato de ausentismo (archivo sintético con la misma estructura del FT-SST-023)."""

from datetime import date, datetime, timedelta

from tests.conftest import archivo
from tests.test_liquidador import API
from tests.test_liquidador_personal import _base, _libro

ENC_INC = ["ITEM", "IDENTIFICACION", "NOMBRE DEL TRABAJADOR", "PUESTO", "NOVEDAD", "ORIGEN INCAPACIDAD", "Inicial / Prorroga",
           "Fecha de inicio", "Fecha de fin", "Dias de Inc", "EPS / ARL / CENTRO MEDICO", "Codigo", "Diagnostico", "Observaciones"]
PDF = b"%PDF-1.4\n%prueba\n"


def _inc(i, doc, desde, hasta, cie, tipo="INICIAL", origen="E.G", novedad="INCAPACIDAD", obs="ESCANEADA", dias=None, puesto="#N/D"):
    d0, d1 = datetime.fromisoformat(desde), datetime.fromisoformat(hasta)
    return [i, doc, f"PERSONA {doc}", puesto, novedad, origen, tipo, d0, d1, dias if dias is not None else (d1 - d0).days + 1,
            "NUEVA EPS", cie, None, obs]


def _ausentismo() -> bytes:
    # 5001: incapacidad de 120 días + prórrogas de otra categoría CIE marcadas como prórroga → 190 días acumulados
    cadena = [_inc(1, 5001.0, "2026-01-01", "2026-04-30", "M545"),
              _inc(2, 5001.0, "2026-05-01", "2026-05-30", "M511", tipo="PRORROGA"),
              # misma categoría (M51) sin marcar como prórroga, después de 10 días: también continúa
              _inc(3, 5001.0, "2026-06-10", "2026-06-19", "M519", dias=9)]
    hoja_2025 = [ENC_INC, _inc(1, 5002.0, "2025-03-01", "2025-03-02", "J00X", obs="FISICA"), *cadena,
                 _inc(5, 5002.0, "2025-03-01", "2025-03-02", "J00X"),  # repetida en la misma hoja
                 _inc(6, 9999.0, "2025-07-01", "2025-07-03", "AB12", origen="A.T", obs="Falta historia clinica")]
    hoja_2026 = [ENC_INC, *cadena,  # el año también está en el histórico: se carga una vez
                 _inc(4, 5004.0, "2026-08-01", "2026-12-28", "O820", novedad="LICENCIA MATERNIDAD", origen=None)]
    restricciones = [["RECOMENDACIONES O RESTRICCIONES MEDICAS"],
                     ["CEDULA", "NOMBRE", "PUESTO", "NOVEDAD", "Fecha de inicio", "Fecha de fin", "Diagnostico", "NOVEDAD"],
                     [5002.0, "EVA ADMIN", "ALCALDIA", "RESTRICCIONES", datetime(2026, 7, 1), datetime(2099, 1, 1), None, "NO CARGAR PESO"],
                     [5001.0, "ANA", "HROB", "RESTRICCIONES", datetime(2025, 1, 1), datetime(2025, 6, 1)],
                     [], ["CASOS ONCOLOGICOS"], ["CEDULA", "NOMBRE", "PUESTO", "Diagnostico"],
                     [5004.0, "LUIS", "ALCALDIA", "TUMOR MALIGNO DE MAMA"]]
    casos = [["DERECHOS DE PETICIÓN"],
             ["CC", "NOMBRE", "ENTIDAD", "FECHA RECIBIDO", "FECHA DE CONTESTACION", "MEDIO DE CONTESTACION", "CORREO / CELULAR", "OBSERVACION"],
             [5002.0, "EVA ADMIN", "DERECHO DE PETICION TRABAJADOR", datetime(2026, 3, 24), "20/04/2026 - 06/05/2026", "CORREO", "eva@x.co"],
             [5002.0, "EVA ADMIN", "AUTO INCIDENTE DE DESACATO", datetime(2026, 5, 22), datetime(2026, 5, 26), "CORREO", "juzgado@x.co"],
             [7777.0, "EXTERNO", "JUZGADO DOCE CIVIL MUNICIPAL", datetime(2026, 4, 22), "ABIERTO", "CORREO", "j12@x.co",
              "LA PERSONA NO LABORA EN LA EMPRESA"],
             [5001.0, "ANA", "ACCION DE TUTELA", datetime(2026, 7, 3), "SE RETIRO EL 28/08", "WHATSAPP", 3001234567.0]]
    return _libro({"CIE": [["Código", "Descripción"]], "REGISTRO INCAPACIDADES 2025": hoja_2025, "REGISTRO INCAPACIDADES 2026": hoja_2026,
                   "RECOMENDACIONES O RESTRICCIONES": restricciones, "DERECHOS, TUTELAS, DEMANDAS": casos})


def _lista(cliente, ruta):
    return cliente.get(f"{API}/{ruta}").json()


def test_importar_formato_de_ausentismo(admin):
    admin.post(f"{API}/personal/importar-base", files=archivo(_base(), "base.xlsx"))
    r = admin.post(f"{API}/gestion/importar-ausentismo", files=archivo(_ausentismo(), "ausentismo.xlsx"))
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["incapacidades"] == {"leidas": 10, "creadas": 6, "actualizadas": 0, "repetidas": 1, "en_varias_hojas": 3}
    assert d["restricciones"]["creadas"] == 3 and d["casos"]["creadas"] == 4 and d["casos"]["abiertos"] == 2
    detalles = [h["detalle"] for h in d["hallazgos"]]
    assert any("Repetida" in x for x in detalles)
    assert any("El Excel dice 9 días y por las fechas son 10" in x for x in detalles)
    assert any("AB12 no está en el catálogo" in x for x in detalles)

    incs = {(x["documento"], x["desde"]): x for x in _lista(admin, "incapacidades?tamano=100")["data"]}
    j00 = incs[("5002", "2025-03-01")]
    assert j00["cie"] == "J00" and j00["diagnostico"] == "RINOFARINGITIS AGUDA (RESFRIADO COMUN)" and j00["soporte"] == "fisico"
    assert j00["puesto"] == "002 - 6 CONJUNTO"  # «#N/D»: se toma de la ficha
    externo = incs[("9999", "2025-07-01")]
    assert externo["empleado_id"] is None and externo["origen"] == "accidente_trabajo" and externo["cie_desconocidos"] == ["AB12"]
    assert externo["observacion"] == "Falta historia clinica"
    # Cadena: 120 + 30 + 10 = 160; la última suma también los días previos
    ultima = incs[("5001", "2026-06-10")]
    assert ultima["acumulado"] == 160 and ultima["inicio_caso"] == "2026-01-01" and ultima["alerta"] is None
    assert incs[("5004", "2026-08-01")]["novedad"] == "licencia_maternidad" and incs[("5004", "2026-08-01")]["acumulado"] is None

    # Volver a importar no duplica
    r = admin.post(f"{API}/gestion/importar-ausentismo", files=archivo(_ausentismo(), "ausentismo.xlsx"))
    assert r.json()["data"]["incapacidades"]["creadas"] == 0 and len(_lista(admin, "incapacidades?tamano=100")["data"]) == 6

    rest = {(x["documento"], x["tipo"]): x for x in _lista(admin, "restricciones")["data"]}
    assert rest[("5002", "restriccion")]["estado"] == "vigente" and rest[("5002", "restriccion")]["observacion"] == "NO CARGAR PESO"
    assert rest[("5001", "restriccion")]["estado"] == "vencida"
    assert rest[("5004", "oncologico")]["estado"] == "seguimiento" and rest[("5004", "oncologico")]["diagnostico"] == "TUMOR MALIGNO DE MAMA"

    casos = {x["asunto"]: x for x in _lista(admin, "casos")["data"]}
    peticion = casos["DERECHO DE PETICION TRABAJADOR"]
    assert peticion["tipo"] == "derecho_peticion" and peticion["estado"] == "contestado"
    assert [a["fecha"] for a in peticion["actuaciones"]] == ["2026-04-20", "2026-05-06"]
    assert casos["AUTO INCIDENTE DE DESACATO"]["tipo"] == "desacato"
    juzgado = casos["JUZGADO DOCE CIVIL MUNICIPAL"]
    assert juzgado["tipo"] == "orden_judicial" and juzgado["estado"] == "abierto" and juzgado["empleado_id"] is None
    tutela = casos["ACCION DE TUTELA"]
    assert tutela["tipo"] == "tutela" and tutela["contacto"] == "3001234567" and tutela["observacion"] == "SE RETIRO EL 28/08"


def test_prorrogas_y_alerta_de_180_dias(admin):
    base = {"documento": "8001", "nombre": "PERSONA NUEVA", "origen": "enfermedad_general", "cie": "s832"}
    inicio = date(2026, 1, 1)
    for i in range(7):  # 7 tramos de 30 días seguidos, misma categoría: 210 días
        desde = inicio + timedelta(days=30 * i)
        r = admin.post(f"{API}/incapacidades", json={**base, "desde": desde.isoformat(), "hasta": (desde + timedelta(days=29)).isoformat()})
        assert r.status_code == 201, r.text
    assert admin.post(f"{API}/incapacidades", json={**base, "desde": "2026-01-01", "hasta": "2026-01-30"}).status_code == 409
    assert admin.post(f"{API}/incapacidades", json={**base, "desde": "2026-02-01", "hasta": "2026-01-30"}).status_code == 422
    sin_nombre = {**base, "documento": "8002", "nombre": "", "desde": "2026-01-01", "hasta": "2026-01-02"}
    assert admin.post(f"{API}/incapacidades", json=sin_nombre).status_code == 422
    # Otra enfermedad 5 días después, sin marcar como prórroga: empieza otra cuenta
    otra = admin.post(f"{API}/incapacidades", json={**base, "cie": "J00", "desde": "2026-08-05", "hasta": "2026-08-06"}).json()["data"]["id"]

    assert admin.get(f"{API}/incapacidades?anio=&origen=&vista=todas").status_code == 200  # «Todos los años» llega vacío
    assert len(_lista(admin, "incapacidades?anio=2026")["data"]) == 8 and _lista(admin, "incapacidades?anio=2020")["data"] == []
    assert admin.get(f"{API}/personal/salidas?anio=&estado=").status_code == 200
    r = _lista(admin, "incapacidades?q=8001")
    assert r["meta"]["extra"]["resumen"]["prolongadas"] == 1
    lista = {x["id"]: x for x in r["data"]}
    assert lista[otra]["acumulado"] == 2
    ultima = max((x for x in r["data"] if x["cie"] == "S832"), key=lambda x: x["desde"])
    assert ultima["acumulado"] == 210 and ultima["alerta"] == "Supera 180 días acumulados" and ultima["diagnostico"].startswith("DESGARRO DE MENISCOS")
    prolongadas = _lista(admin, "incapacidades?vista=prolongadas")["data"]
    assert [x["id"] for x in prolongadas] == [ultima["id"]]
    # Marcar la otra como prórroga la suma al caso
    datos = {**base, "cie": "J00", "desde": "2026-08-05", "hasta": "2026-08-06", "prorroga": True}
    assert admin.put(f"{API}/incapacidades/{otra}", json=datos).status_code == 200
    assert {x["id"]: x for x in _lista(admin, "incapacidades?q=8001")["data"]}[otra]["acumulado"] == 212

    assert [c["codigo"] for c in _lista(admin, "cie?q=S83")["data"]][:2] == ["S830", "S831"]
    assert any(c["codigo"] == "J00" for c in _lista(admin, "cie?q=resfriado")["data"])


def test_soportes_casos_y_permisos(admin):
    from fastapi.testclient import TestClient

    from app.main import app
    from tests.conftest import ACCESOS, CSRF, entrar

    inc = admin.post(f"{API}/incapacidades", json={"documento": "8001", "nombre": "PERSONA", "desde": "2026-10-01",
                                                   "hasta": "2026-10-03", "cie": "J00"}).json()["data"]["id"]
    r = admin.post(f"{API}/documentos/incapacidad/{inc}", files={"archivo": ("incapacidad.pdf", PDF, "application/pdf")})
    assert r.status_code == 201, r.text
    doc = r.json()["data"]["id"]
    falso = admin.post(f"{API}/documentos/incapacidad/{inc}", files={"archivo": ("x.pdf", b"MZ ejecutable", "application/pdf")})
    assert falso.status_code == 415
    assert admin.post(f"{API}/documentos/otro/{inc}", files={"archivo": ("x.pdf", PDF, "application/pdf")}).status_code == 404
    assert admin.get(f"{API}/documentos/{doc}").content == PDF
    assert _lista(admin, "incapacidades")["data"][0]["documentos"][0]["nombre"] == "incapacidad.pdf"

    caso = admin.post(f"{API}/casos", json={"documento": "8001", "nombre": "PERSONA", "tipo": "tutela", "asunto": "Tutela por salud",
                                            "recibido": "2026-10-01", "vence": "2026-10-05"}).json()["data"]["id"]
    c = _lista(admin, "casos")
    assert c["data"][0]["vencido"] and c["meta"]["extra"]["resumen"] == {"abiertos": 1, "vencidos": 1}
    r = admin.post(f"{API}/casos/{caso}/actuaciones", json={"fecha": "2026-10-04", "descripcion": "Contestación al juzgado",
                                                            "medio": "Correo", "estado": "contestado"})
    assert r.json()["data"]["estado"] == "contestado"
    assert admin.post(f"{API}/documentos/caso/{caso}", files={"archivo": ("respuesta.pdf", PDF, "application/pdf")}).status_code == 201

    # Al borrar el registro se borran sus soportes
    assert admin.delete(f"{API}/incapacidades/{inc}").status_code == 200
    assert admin.get(f"{API}/documentos/{doc}").status_code == 404

    roles = {r["nombre"]: r["id"] for r in admin.get("/api/roles").json()["data"]}
    for usuario, rol in (("nomina1", "Liquidador"), ("gh1", "Gestión humana")):
        r = admin.post("/api/usuarios", json={"accesos": ACCESOS, "username": usuario, "nombre": usuario, "password": "clave-segura-1",
                                              "roles": [roles[rol]]})
        assert r.status_code == 201, r.text
    with TestClient(app, headers=CSRF) as cliente:
        entrar(cliente, "nomina1", "clave-segura-1")  # nómina no ve diagnósticos ni casos
        assert cliente.get(f"{API}/incapacidades").status_code == 403
        assert cliente.get(f"{API}/casos").status_code == 403
        assert cliente.post(f"{API}/gestion/importar-ausentismo", files=archivo(_ausentismo())).status_code == 403
        # Consulta la ficha pero no la modifica: crear empleados e importar la base es de gestión humana
        assert cliente.get(f"{API}/personal/cuotas-pendientes").status_code == 200
        assert cliente.post(f"{API}/empleados", json={"documento": "5551", "nombre": "NUEVO"}).status_code == 403
        assert cliente.post(f"{API}/personal/importar-base", files=archivo(_base(), "base.xlsx")).status_code == 403
    with TestClient(app, headers=CSRF) as cliente:
        entrar(cliente, "gh1", "clave-segura-1")
        assert cliente.get(f"{API}/casos").status_code == 200 and cliente.get(f"{API}/restricciones").status_code == 200
        assert cliente.get(f"{API}/personal/cuotas-pendientes").status_code == 200
        assert cliente.get(f"{API}/descuentos").status_code == 403  # la gestión de descuentos es de nómina


def test_cuotas_pendientes_e_historico_de_vacaciones(admin):
    from tests.test_liquidador_nomina import _periodo_con

    _periodo_con(admin, 2026, 11, 1, [[1001, "1001", *(["A"] * 15)]], list(range(1, 16)))
    base = {"documento": "1001", "desde": "2026-11-01"}
    admin.post(f"{API}/descuentos", json={**base, "tipo": "cuota", "descripcion": "Plan exequial", "valor_mensual": 30000})
    admin.post(f"{API}/descuentos", json={**base, "tipo": "prestamo", "descripcion": "Celular", "valor_mensual": 100000, "monto_total": 300000})
    pid = admin.get(f"{API}/periodos").json()["data"][0]["id"]
    admin.post(f"{API}/periodos/{pid}/recalcular")
    lista = {x["descripcion"]: x for x in _lista(admin, "personal/cuotas-pendientes")["data"]}
    assert lista["Celular"]["descontado"] == 50000 and lista["Celular"]["saldo"] == 250000
    assert lista["Plan exequial"]["saldo"] is None and lista["Plan exequial"]["tipo"] == "cuota"
    assert [x["descripcion"] for x in _lista(admin, "personal/cuotas-pendientes?tipo=cuota")["data"]] == ["Plan exequial"]

    e = admin.get(f"{API}/empleados?q=1001").json()["data"][0]
    admin.post(f"{API}/empleados/{e['id']}/salidas", json={"tipo": "disfrutadas", "desde": "2026-12-01", "hasta": "2026-12-15",
                                                           "dias_habiles": 13, "estado": "programada"})
    s = _lista(admin, "personal/salidas?estado=programada")["data"]
    assert s[0]["documento"] == "1001" and s[0]["dias_habiles"] == 13


def test_crear_empleado_desde_la_plataforma(admin):
    datos = {"documento": " 1.144.000.111 ", "nombre": "laura nueva", "tipo_personal": "operativo", "puesto": "002 - 6 CONJUNTO",
             "fecha_ingreso": "2026-10-01", "tipo_contrato": "OBRA A LABOR"}
    r = admin.post(f"{API}/empleados", json=datos)
    assert r.status_code == 201, r.text
    e = admin.get(f"{API}/empleados/{r.json()['data']['id']}").json()["data"]
    assert e["documento"] == "1144000111"
    assert e["nombre"] == "LAURA NUEVA" and e["cargo"] == "Operario de aseo" and e["estado"] == "activo" and e["fecha_ingreso"] == "2026-10-01"
    assert [c["fecha_inicio"] for c in e["contratos"]] == ["2026-10-01"]
    assert admin.post(f"{API}/empleados", json=datos).status_code == 409
    assert admin.post(f"{API}/empleados", json={**datos, "documento": "999888", "fecha_ingreso": "1900-01-01"}).status_code == 422
