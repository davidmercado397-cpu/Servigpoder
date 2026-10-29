"""Ficha del personal: importación de la base de personal y del libro de vacaciones (archivos sintéticos con la misma
estructura que los de gestión humana)."""

from datetime import datetime
from io import BytesIO

from openpyxl import Workbook

from tests.conftest import archivo, xlsx
from tests.test_liquidador import API, _cargar, _quincena, _resultados

ACTIVOS = ["ITEM", "CEDULA", "NOMBRE Y APELLIDO", "CARGO", "PUESTO", "CIUDAD", "SEXO", "FECHA DE NACIMIENTO", "MES", "EDAD", "RH",
           "CELULAR", "ID PAIS NACIMIENTO (Obligatorio) CODIGOS SEGÚN DANE", "ID DEPTO NACIMIENTO (Obligatorio) CODIGOS SEGÚN DANE",
           "ID CIUDAD NACIMIENTO (Obligatorio) CODIGOS SEGÚN DANE", "FECHA EXPEDICION IDENTIFICACION (YYYYMMDD, Obligatorio)",
           "ID PAIS EXPEDICION IDENTIFICACION (Obligatorio) CODIGOS SEGÚN DANE", "ID DEPTO EXPEDICION IDENTIFICACION (Obligatorio) CODIGOS SEGÚN DANE",
           "ID CIUDAD EXPEDICION IDENTIFICACION (Obligatorio) CODIGOS SEGÚN DANE", "INDICADOR ESTADO CIVIL (Obligatorio, (0=Ninguno, 1=Soltero…))",
           "INDICADOR EXTRANJERO (Obligatorio, (0=No, 1=Si))", "CORREO", "DIRECCION", "BARRIO", "CAJA DE COMPENSACION", "FONDO DE PENSIONES",
           "FONDO DE CESANTIAS", "EPS", "PLAN EXEQUIAL", "NUMERO DE CUENTA", "FECHA DE INICIO DEL CONTRATO", "ANTIGÜEDAD", "CONTRATO 3 MESES",
           "NIVEL EDUCATIVO", "CURSOS ADICIONALES / CUALES", datetime(2026, 10, 28)]
RETIROS = ["ITEM", "CEDULA", "NOMBRE Y APELLIDO", "CARGO", "PUESTO", "CIUDAD", "CELULAR", "CORREO", "DIRECCION", "BARRIO",
           "NUMERO DE CUENTA", "FECHA DE INICIO DEL CONTRATO", "ANTIGÜEDAD", "FECHA DE RETIRO", "OBSERVACION", datetime(2026, 8, 11)]


def _activo(i, cedula, nombre, cargo="OPERARIO DE ASEO", expedicion=datetime(2000, 1, 10), barrio="CENTRO", pension="PORVENIR",
            inicio=datetime(2024, 3, 1)):
    return [i, cedula, nombre, cargo, "002 - 6 CONJUNTO", "CALI", "F", datetime(1990, 3, 15), "marzo", 36, "O+", 3001234567.0,
            "COLOMBIA", "VALLE DEL CAUCA", "CALI", expedicion, "COLOMBIA", "VALLE DEL CAUCA", "CALI", 1.0, 0.0, "Ana@Correo.com",
            "CALLE 1 # 2-3", barrio, "COMFENALCO", pension, "PORVENIR", "SURA", None, 123456789.0, inicio, 2.6, "OBRA A LABOR",
            "BACHILLER 11°", None, None]


def _libro(hojas: dict[str, list[list]]) -> bytes:
    libro = Workbook()
    libro.remove(libro.active)
    for nombre, filas in hojas.items():
        hoja = libro.create_sheet(nombre)
        for f in filas:
            hoja.append(f)
    buf = BytesIO()
    libro.save(buf)
    return buf.getvalue()


def _base() -> bytes:
    return _libro({
        "OPERATIVOS": [ACTIVOS,
                       _activo(1, 5001.0, "ANA OPERATIVA", inicio=datetime(2025, 1, 15)),
                       _activo(2, "PPT 1234567", "JOSE EXTRANJERO", expedicion="#VALUE!", barrio=datetime(2026, 8, 7), pension="COLPENSIONES"),
                       _activo(3, 5004.0, "LUIS PENSIONADO", pension="PENSIONADO VEJEZ - COLPENSIONES")],
        "RETIROS OP": [RETIROS,
                       [1, 5003.0, "PEDRO RETIRADO", "OPERARIO DE ASEO", None, "PALMIRA", None, None, None, None, None,
                        datetime(2024, 5, 1), 1.4, datetime(2026, 9, 30), "RENUNCIA VOLUNTARIA", "ABANDONO DEL PUESTO"],
                       [2, 5003.0, "PEDRO RETIRADO", "OPERARIO DE ASEO", None, "PALMIRA", None, None, None, None, None,
                        datetime(2024, 5, 1), 1.4, datetime(2026, 9, 30), "RENUNCIA VOLUNTARIA", None],
                       [3, 5001.0, "ANA OPERATIVA", "OPERARIO DE ASEO", None, "CALI", None, None, None, None, None,
                        datetime(2023, 2, 1), 1.0, datetime(2024, 1, 31), "TERMINACION DE CONTRATO POR OBRA A LABOR", "REINTEGRO 2"]],
        "ADMINISTRATIVOS": [ACTIVOS, _activo(1, 5001.0, "ANA ADMINISTRATIVA", cargo="COORDINADOR DE PUESTO", inicio=datetime(2025, 1, 15)),
                            _activo(2, 5002.0, "EVA ADMIN", cargo="ANALISTA")],
        "RETIROS ADMIN": [["ITEM", "CEDULA", "NOMBRE Y APELLIDO", "CARGO", "CIUDAD", "CELULAR", "CORREO", "DIRECCION", "NUMERO DE CUENTA",
                           "FECHA DE INICIO DEL CONTRATO", "ANTIGÜEDAD", "CONTRATO 3 MESES", "FECHA DE RETIRO", "OBSERVACION", datetime(2026, 8, 11)],
                          [1, 5005.0, "MARIA COORDINADORA", "COORDINADOR OPERATIVA", "002 - 77 ALCALDIA", 3001.0, "m@x.co", "CRA 1",
                           1.0, datetime(2024, 11, 5), 1.8, "OBRA A LABOR", datetime(2026, 3, 18), "RENUNCIA VOLUNTARIA", None]],
    })


def _ficha(cliente, doc):
    e = cliente.get(f"{API}/empleados?q={doc}").json()["data"][0]
    return cliente.get(f"{API}/empleados/{e['id']}").json()["data"]


def test_importar_base_de_personal(admin):
    r = admin.post(f"{API}/personal/importar-base", files=archivo(_base(), "base.xlsx"))
    assert r.status_code == 200, r.text
    res = r.json()["data"]
    assert (res["empleados"], res["creados"], res["activos"], res["retirados"]) == (6, 6, 4, 2)
    hallazgos: dict[tuple, str] = {}
    for h in res["hallazgos"]:
        hallazgos[(h["hoja"], h["fila"])] = hallazgos.get((h["hoja"], h["fila"]), "") + " | " + h["detalle"]
    assert "letras" in hallazgos[("OPERATIVOS", 3)] and "PPT 1234567" in {h["documento"] for h in res["hallazgos"]}
    assert any("expedición no válida" in h["detalle"] for h in res["hallazgos"] if h["fila"] == 3)
    assert any("barrio quedó convertido en fecha" in h["detalle"] for h in res["hallazgos"])
    assert "se toma la información de ADMINISTRATIVOS" in hallazgos[("ADMINISTRATIVOS", 2)]
    assert "Retiro repetido" in hallazgos[("RETIROS OP", 3)]
    assert "trae un puesto" in hallazgos[("RETIROS ADMIN", 2)]

    ana = _ficha(admin, "5001")
    assert (ana["nombre"], ana["cargo"], ana["estado"], ana["tipo_personal"]) == ("ANA ADMINISTRATIVA", "COORDINADOR DE PUESTO", "activo", "administrativo")
    assert ana["fecha_ingreso"] == "2025-01-15" and [c["fecha_retiro"] for c in ana["contratos"]] == [None, "2024-01-31"]
    p = ana["personal"]
    assert (p["correo"], p["celular"], p["numero_cuenta"], p["estado_civil"], p["sexo"]) == ("ana@correo.com", "3001234567", "123456789", 1, "F")
    assert p["edad"] >= 36
    pedro = _ficha(admin, "5003")
    assert pedro["estado"] == "retirado" and pedro["fecha_retiro"] == "2026-09-30" and pedro["contratos"][0]["observacion"] == "ABANDONO DEL PUESTO"
    luis = _ficha(admin, "5004")["personal"]
    assert luis["pensionado"] and luis["fondo_pensiones"] == "COLPENSIONES"
    jose = _ficha(admin, "PPT 1234567")["personal"]  # afiliado a Colpensiones: no es pensionado
    assert not jose["pensionado"] and jose["fondo_pensiones"] == "COLPENSIONES"
    assert _ficha(admin, "5005")["puesto"] == "002 - 77 ALCALDIA"
    assert [e["documento"] for e in admin.get(f"{API}/empleados?estado=retirado").json()["data"]] == ["5005", "5003"]
    # Volver a importar no duplica contratos
    res2 = admin.post(f"{API}/personal/importar-base", files=archivo(_base(), "base.xlsx")).json()["data"]
    assert res2["creados"] == 0 and len(_ficha(admin, "5001")["contratos"]) == 2

    # Edición de datos personales y retiro manual desde la ficha
    ana_id = ana["id"]
    datos = {**{k: v for k, v in p.items() if k not in ("edad", "antiguedad_anios")}, "nombre": "ANA ADMINISTRATIVA",
             "cargo": "COORDINADOR DE PUESTO", "celular": "3110000000", "barrio": "SAN FERNANDO"}
    r = admin.put(f"{API}/empleados/{ana_id}/datos", json=datos)
    assert r.status_code == 200, r.text
    assert set(r.json()["data"]["cambios"]) == {"celular", "barrio"}
    abierto = _ficha(admin, "5001")["contratos"][0]
    assert admin.put(f"{API}/contratos/{abierto['id']}", json={**abierto, "fecha_retiro": "2026-10-31", "motivo_retiro": "RENUNCIA"}).status_code == 200
    assert _ficha(admin, "5001")["estado"] == "retirado"


def test_libro_de_vacaciones_y_nomina(admin):
    admin.post(f"{API}/personal/importar-base", files=archivo(_base(), "base.xlsx"))
    libro = _libro({
        "BD": [["CEDULA", "NOMBRE Y APELLIDO", "CARGO", "PUESTO"]],
        "PERSONAL": [["Cédula", "Nombre Completo", "Puesto", "Fecha Ingreso", "Fecha Corte", "Días Laborados", "Vacaciones Causadas",
                      "Días Disfrutados", "Periodo Disfrutado", "Saldo Pendiente", "Periodo Pendiente"],
                     [5001.0, "ANA", "002", datetime(2025, 1, 15), datetime(2026, 10, 28), 651, 27.1, 15.0, 1, 12.1, "x"],
                     [5002.0, "EVA", "001", datetime(2023, 1, 1), datetime(2026, 10, 28), 1396, 58.2, 30.0, 2, 28.2, "x"],
                     [7777.0, "NUEVA", "002 - 9", datetime(2026, 1, 1), datetime(2026, 10, 28), 300, 12.5, 0, 0, 12.5, "x"],
                     [1234567.0, "JOSE", "002", datetime(2024, 3, 1), datetime(2026, 10, 28), 900, 37.5, 15, 1, 22.5, "x"]],
        "FECHAS VACACIONES": [["JULIO", None], ["Cédula", "Empleado", "Puesto", "Fecha Ingreso", "Fecha vacaciones", "Retoma Labores"],
                              [5001.0, "ANA", "002", datetime(2025, 1, 15), "03 al 22 de julio del 20226", "23 de julio del 2026", "Tulua"],
                              [5002.0, "EVA", "001", datetime(2023, 1, 1), "compensadas", "compensadas"],
                              ["NOVIEMBRE", None],
                              [5002.0, "EVA", "001", datetime(2023, 1, 1), "28 de octubre al 14 de noviembre del 2026", "17 de noviembre del 2026"],
                              [5001.0, "ANA", "002", datetime(2025, 1, 15), "la otra semana", ""],
                              [5003.0, "PEDRO", "002", datetime(2024, 5, 1), "01 al 05 de diciembre del 2026", "", "SE CANCELAN"]],
    })
    r = admin.post(f"{API}/personal/importar-vacaciones", files=archivo(libro, "libro.xlsx"))
    assert r.status_code == 200, r.text
    res = r.json()["data"]
    assert (res["saldos"], res["creados"], res["salidas"], res["programadas"], res["compensadas"], res["corte"]) == (4, 1, 4, 0, 1, "2026-10-28")
    detalles = [h["detalle"] for h in res["hallazgos"]]
    assert any("error de digitación" in d for d in detalles) and any("No se entendió" in d for d in detalles)
    assert any("No está en la base de personal: se creó" in d for d in detalles)
    assert any("Se tomó como el documento PPT 1234567" in d for d in detalles)
    assert _ficha(admin, "PPT")["vacaciones_previas"] == 15
    ana = _ficha(admin, "5001")
    assert ana["vacaciones_previas"] == 15 and ana["saldo_vacaciones"]["corte_libro"] == "2026-10-28"
    julio = next(s for s in ana["salidas"] if s["desde"])
    assert (julio["desde"], julio["hasta"], julio["retorno"], julio["estado"], julio["observacion"]) == ("2026-07-03", "2026-07-22", "2026-07-23", "historico", "Tulua")
    assert julio["dias_habiles"] == 15  # 3 al 22 de julio de lunes a sábado: sin 3 domingos ni los festivos 13 y 20 de julio
    eva = _ficha(admin, "5002")["salidas"]
    assert {(s["tipo"], s["estado"]) for s in eva} == {("compensadas", "historico"), ("disfrutadas", "historico")}
    assert next(s for s in eva if s["desde"])["desde"] == "2026-10-28"
    assert _ficha(admin, "5003")["salidas"][0]["estado"] == "cancelada"

    # Nómina de octubre Q2: V antes del corte (ya en el libro) no cuentan; Pedro está retirado desde el 30/09
    pid = _quincena(admin, 2026, 10, 2)
    dias = list(range(16, 32))
    _cargar(admin, pid, xlsx([["documento", "OCTUBRE", *dias], [5001, "otro nombre", *(["V"] * 5 + ["A"] * 11)], [5003, "5003", *(["A"] * 16)]]))
    ana = _ficha(admin, "5001")
    assert ana["nombre"] == "ANA ADMINISTRATIVA" and ana["cargo"] == "COORDINADOR DE PUESTO"  # la nómina no los pisa
    assert ana["vacaciones_liquidador"] == 0 and ana["vacaciones_liquidadas"][0]["antes_del_corte"]
    res = _resultados(admin, pid)
    n = admin.get(f"{API}/periodos/{pid}/empleados/{res['5003']['empleado_id']}").json()["data"]["empleado"]["nomina"]
    assert any("retirado desde el 30/09/2026" in a for a in n["alertas"])


def test_datos_personales_solo_con_permiso(admin):
    from fastapi.testclient import TestClient

    from app.main import app
    from tests.conftest import ACCESOS, CSRF, entrar

    admin.post(f"{API}/personal/importar-base", files=archivo(_base(), "base.xlsx"))
    roles = {r["nombre"]: r["id"] for r in admin.get("/api/roles").json()["data"]}
    rol = admin.post("/api/roles", json={"nombre": "Solo periodos", "permisos": ["liquidador.periodos.ver"]}).json()["data"]["id"]
    for usuario, rid in (("consulta1", rol), ("gh1", roles["Gestión humana"])):
        r = admin.post("/api/usuarios", json={"accesos": ACCESOS, "username": usuario, "nombre": usuario, "password": "clave-segura-1",
                                              "roles": [rid]})
        assert r.status_code == 201, r.text
    with TestClient(app, headers=CSRF) as c:
        entrar(c, "consulta1", "clave-segura-1")
        f = _ficha(c, "5001")
        assert "personal" not in f and "contratos" not in f
        assert c.post(f"{API}/personal/importar-base", files=archivo(_base(), "base.xlsx")).status_code == 403
    with TestClient(app, headers=CSRF) as c:
        entrar(c, "gh1", "clave-segura-1")
        f = _ficha(c, "5001")
        assert f["personal"]["correo"] == "ana@correo.com" and f["salario"] is None


def test_exportar_base_y_volver_a_importar(admin):
    from openpyxl import load_workbook

    primera = admin.post(f"{API}/personal/importar-base", files=archivo(_base(), "base.xlsx")).json()["data"]
    r = admin.get(f"{API}/personal/exportar-base")
    assert r.status_code == 200 and "base_de_personal_" in r.headers["content-disposition"]
    libro = load_workbook(BytesIO(r.content))
    assert libro.sheetnames == ["OPERATIVOS", "ADMINISTRATIVOS", "RETIROS OP", "RETIROS ADMIN"]
    op = list(libro["OPERATIVOS"].iter_rows(values_only=True))
    enc = op[0]
    filas = {str(f[0]): dict(zip(enc, f)) for f in op[1:]}
    assert set(filas) == {"PPT 1234567", "5004"} and "SALARIO MENSUAL" in enc
    assert filas["5004"]["FONDO DE PENSIONES"] == "PENSIONADO - COLPENSIONES" and filas["5004"]["PENSIONADO"] == "SI"
    adm = {str(f[0]) for f in list(libro["ADMINISTRATIVOS"].iter_rows(values_only=True))[1:]}
    assert adm == {"5001", "5002"}
    retiros_op = {str(f[0]) for f in list(libro["RETIROS OP"].iter_rows(values_only=True))[1:]}
    retiros_adm = {str(f[0]) for f in list(libro["RETIROS ADMIN"].iter_rows(values_only=True))[1:]}
    assert retiros_op == {"5003"} and retiros_adm == {"5001", "5005"}  # 5001 volvió a ingresar: su contrato anterior queda en retiros
    # Volver a importar lo exportado no cambia nada
    otra = admin.post(f"{API}/personal/importar-base", files=archivo(r.content, "exportada.xlsx")).json()["data"]
    assert (otra["creados"], otra["activos"], otra["retirados"]) == (0, primera["activos"], primera["retirados"])
    luis = _ficha(admin, "5004")["personal"]
    assert luis["pensionado"] and luis["fondo_pensiones"] == "COLPENSIONES"
    assert not _ficha(admin, "PPT 1234567")["personal"]["pensionado"]


def test_controles_de_nombres_en_la_base_y_en_la_nomina(admin):
    from tests.test_liquidador_nomina import _periodo_con

    admin.post(f"{API}/personal/importar-base", files=archivo(_base(), "base.xlsx"))
    # Base con el nombre de otra persona copiado en la cédula 5002 (como pasó con la fila 130)
    base = _libro({"ADMINISTRATIVOS": [ACTIVOS, _activo(1, 5001.0, "ANA ADMINISTRATIVA", cargo="COORDINADOR DE PUESTO"),
                                       _activo(2, 5002.0, "ANA ADMINISTRATIVA", cargo="ANALISTA")]})
    d = admin.post(f"{API}/personal/importar-base", files=archivo(base, "base.xlsx")).json()["data"]
    detalles = [h["detalle"] for h in d["hallazgos"] if h["documento"] == "5002"]
    assert any("El nombre cambió de «EVA ADMIN»" in x for x in detalles) and any("mismo nombre" in x for x in detalles)

    # El Excel de la nómina no cambia el nombre de quien ya existe; avisa si no coincide
    pid = _periodo_con(admin, 2026, 11, 1, [[5004, "PEDRO EQUIVOCADO", *(["A"] * 15)], [5004.0, "LUIS PENSIONADO", *([""] * 15)]], list(range(1, 16)))
    assert _ficha(admin, "5004")["nombre"] == "LUIS PENSIONADO"
    avisos = admin.get(f"{API}/periodos/{pid}").json()["data"]["advertencias"]
    assert any("es de LUIS PENSIONADO en la ficha" in a for a in avisos)
