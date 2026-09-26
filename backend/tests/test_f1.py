from datetime import date

from tests.conftest import entrar, archivo, xlsx

MATRIZ = [
    [None, "BASE DE DATOS DE PUESTOS ACTIVOS SERVIGPODER"],
    [None, "PODER", "NIT", "NOMBRE", "HOMBRES", "SECUENCIA", "DESCRIPCION", "CIUDAD", "JORNADAS", "MODALIDAD", "VALOR X 15NA"],
    ["05", "05", None, "DISPONBLES", None, None, None, "CALI"],
    ["25", "25", "800", "EDIFICIO SEMINARIO", "3", "4x2 (2dia 2 noche 2 descanso)", "PUERTA", "CALI", "TERNA NORMAL"],
    ["47", "47A", "890", "CVC", "3", "4x2", "PORTERIA", "CALI", "TERNA NORMAL"],
    ["86", "86", "900", "C.R. X", "3", "4x2", "PUERTA", "CALI", "TERNA NORMAL"],
    ["86", "86", "900", "C.R. X", "1,5", "4x2", "RONDA", "CALI", "solo noche de lunesa domingo"],
    ["198", "198-3", "901", "Y", "15,", "4x2", "RONDA", "CALI", "SOLO NOCHE"],
    ["3", "3", "902", "NUBIA", "1", "6 x1", "RECEPCION", "CALI", "lunes a viernes 6:00 18:00 sabados 6:00 a 14: 00"],
    ["14", "14-J", "903", "CASINO", "1", "N/A", "ESCOLTA", "CALI", "SE PAGA CON MODALIDA FIJA"],
]

HORARIOS = [
    ["Código", "Descripción", "Activo", "Tipo jornada", "Entrada", "Salida"],
    ["06:00 - 18:00", "06:00 A 18:00", "Si", "Normal", "06:00", "18:00"],
    ["18:00 - 06:00", "18:00 A 06:00", "Si", "Normal", "18:00", "06:00"],
    ["T.P.", "partido", "Si", "Normal", "05:30", "12:00"],
    ["T.P.", "partido", "Si", "Normal", "14:30", "20:30"],
    ["IND", "INDUCCION", "Si", "Normal", "06:00", "18:00"],
    ["Z", "DESCANSO", "Si", "Descanso", "00:00", "00:00"],
    ["L", "LIBRE", "Si", "Descanso", "00:00", "00:00"],
]


def programacion(dias: dict[str, list[str]]) -> list[list[object]]:
    enc = ["C.C. Empleado", "NOMBRE EMPLEADO", "UBICACION", "DESCRIPCION UBICACION", "PUESTO", "DESCRIPCION PUESTO"]
    enc += [str(d) for d in range(1, 32)] + ["CENTRO DE OPERACION", "DESCRIPCION CENTRO DE OPERACION"]
    filas = [["Compañia", "SERVIGPODER"], ["Desde", "2026-09-15"], ["Hasta", "2026-09-30"], enc]
    for i, (puesto, celdas) in enumerate(dias.items()):
        fila = [f"100{i}", f"EMPLEADO {i}", puesto.split("-")[0], "UBIC", puesto, "DESC"] + [None] * 14
        fila += celdas + [None] * (17 - len(celdas)) + ["001", "CALI"]
        filas.append(fila)
    return filas


def importar_matriz(admin, anio=2026, mes=9):
    return admin.post("/api/capacidad/matriz/importar", data={"anio": anio, "mes": mes}, files=archivo(xlsx(MATRIZ)))


def test_importar_matriz(admin):
    r = importar_matriz(admin)
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["puestos"] == 7  # la bolsa 05 no entra a la matriz
    assert any("198-3" in a and "1,5" in a for a in data["avisos"])

    pid = data["periodo_id"]
    puestos = {p["puesto"]["codigo"]: p for p in admin.get(f"/api/capacidad/matriz/periodos/{pid}/puestos").json()["data"]}
    assert set(puestos) >= {"86", "86-1", "47A", "198-3"}  # el repetido 86 pasa a 86-1
    assert puestos["198-3"]["hombres"] == "1.50"
    assert puestos["14-J"]["puesto"]["excluido"] is True
    assert len(puestos["25"]["franjas"]) == 2

    bolsas = [p for p in admin.get("/api/capacidad/maestros/puestos").json()["data"] if p["tipo"] == "bolsa"]
    assert {b["codigo"] for b in bolsas} == {"05", "06", "07", "08"}


def test_importar_mes_repetido(admin):
    importar_matriz(admin)
    assert importar_matriz(admin).status_code == 409


def test_requerimiento_respeta_festivos(admin):
    pid = importar_matriz(admin, 2026, 12).json()["data"]["periodo_id"]
    puestos = {p["puesto"]["codigo"]: p for p in admin.get(f"/api/capacidad/matriz/periodos/{pid}/puestos").json()["data"]}
    dias = {d["fecha"]: d for d in admin.get(f"/api/capacidad/matriz/puestos/{puestos['3']['id']}/requerimiento").json()["data"]}
    # 8 de diciembre de 2026 (martes) es festivo: la recepción L-V no se cubre
    assert dias["2026-12-08"]["festivo"] and dias["2026-12-08"]["horas"] == 0
    assert dias["2026-12-09"]["horas"] == 12
    assert dias["2026-12-12"]["horas"] == 8  # sábado 06-14
    assert dias["2026-12-13"]["horas"] == 0  # domingo
    # Servicio 24 h: festivo incluido
    dias25 = {d["fecha"]: d for d in admin.get(f"/api/capacidad/matriz/puestos/{puestos['25']['id']}/requerimiento").json()["data"]}
    assert dias25["2026-12-08"]["horas"] == 24


def test_proyectar_y_corregir(admin):
    pid = importar_matriz(admin).json()["data"]["periodo_id"]
    puestos = admin.get(f"/api/capacidad/matriz/periodos/{pid}/puestos").json()["data"]
    mp = next(p for p in puestos if p["puesto"]["codigo"] == "25")
    admin.post(f"/api/capacidad/matriz/puestos/{mp['id']}/excepciones", json={"fecha": "2026-09-20", "sin_servicio": True})

    r = admin.post(f"/api/capacidad/matriz/periodos/{pid}/proyectar", json={"copiar_excepciones": False})
    assert r.status_code == 201
    nuevo = r.json()["data"]
    assert (nuevo["anio"], nuevo["mes"], nuevo["estado"]) == (2026, 10, "borrador")

    oct_ = {p["puesto"]["codigo"]: p for p in admin.get(f"/api/capacidad/matriz/periodos/{nuevo['id']}/puestos").json()["data"]}
    assert len(oct_) == len(puestos)
    assert oct_["25"]["excepciones"] == []

    # Corregir solo lo que cambió en octubre
    r = admin.patch(f"/api/capacidad/matriz/puestos/{oct_['25']['id']}", json={
        "hombres": "1.5", "franjas": [{"dias": 127, "inicio": "18:00", "fin": "06:00", "cantidad": 1}]})
    assert r.status_code == 200 and r.json()["data"]["hombres"] == "1.50"
    # Septiembre no cambia
    sep25 = next(p for p in admin.get(f"/api/capacidad/matriz/periodos/{pid}/puestos").json()["data"] if p["puesto"]["codigo"] == "25")
    assert sep25["hombres"] == "3.00" and len(sep25["franjas"]) == 2

    assert admin.post(f"/api/capacidad/matriz/periodos/{pid}/proyectar", json={}).status_code == 409


def test_periodo_cerrado_no_se_edita(admin):
    pid = importar_matriz(admin).json()["data"]["periodo_id"]
    mp = admin.get(f"/api/capacidad/matriz/periodos/{pid}/puestos").json()["data"][0]
    assert admin.put(f"/api/capacidad/matriz/periodos/{pid}/estado", json={"estado": "cerrado"}).status_code == 200
    r = admin.patch(f"/api/capacidad/matriz/puestos/{mp['id']}", json={"hombres": "2"})
    assert r.status_code == 409


def test_catalogo_de_turnos(admin):
    r = admin.post("/api/capacidad/catalogos/turnos/importar", files=archivo(xlsx(HORARIOS)))
    assert r.status_code == 200 and r.json()["data"]["turnos"] == 6
    turnos = {t["codigo"]: t for t in admin.get("/api/capacidad/catalogos/turnos").json()["data"]}
    assert len(turnos["T.P."]["franjas"]) == 2
    assert turnos["Z"]["clase"] == "descanso"


def test_carga_programacion(admin):
    importar_matriz(admin)
    admin.post("/api/capacidad/catalogos/turnos/importar", files=archivo(xlsx(HORARIOS)))
    filas = programacion({
        "25": ["[VAC]", "18:00 - 06:00", "Z", "L", "06:00 - 18:00"],
        "47-A": ["06:00 - 18:00", "IND", "XYZ"],
        "07": ["[IEG]"],
        "2843-7G": ["06:00 - 18:00"],
    })
    r = admin.post("/api/capacidad/programacion/cargas", files=archivo(xlsx(filas), "ReporteAsignacionResumido.xlsx"))
    assert r.status_code == 201, r.text
    resumen = r.json()["data"]["resumen"]
    assert resumen["filas"] == 4
    assert resumen["dias_por_clase"] == {"novedad": 3, "trabajo": 4, "descanso": 2, "desconocido": 1}
    assert resumen["codigos_desconocidos"] == [{"codigo": "XYZ", "veces": 1}]
    assert [p["codigo"] for p in resumen["puestos_sin_equivalencia"]] == ["2843-7G"]

    # 47-A se resolvió a 47A (exacta) y 07 a la bolsa; 2843-7G queda por aclarar
    aclarar = admin.get("/api/capacidad/maestros/por-aclarar").json()["data"]
    assert [a["codigo_siesa"] for a in aclarar] == ["2843-7G"]

    # El usuario asigna la equivalencia manual y la fila queda resuelta
    puesto = next(p for p in admin.get("/api/capacidad/maestros/puestos?q=25").json()["data"] if p["codigo"] == "25")
    admin.put("/api/capacidad/maestros/equivalencias", json={"codigo_siesa": "2843-7G", "puesto_id": puesto["id"]})
    assert admin.get("/api/capacidad/maestros/por-aclarar").json()["data"] == []


def test_carga_sin_catalogo(admin):
    r = admin.post("/api/capacidad/programacion/cargas", files=archivo(xlsx(programacion({"25": ["Z"]}))))
    assert r.status_code == 400 and "catálogo" in r.json()["error"]["message"]


def test_archivo_no_excel_rechazado(admin):
    r = admin.post("/api/capacidad/programacion/cargas", files={"archivo": ("x.xlsx", b"hola mundo", "application/octet-stream")})
    assert r.status_code == 415
    r = admin.post("/api/capacidad/programacion/cargas", files={"archivo": ("x.csv", b"a,b", "text/csv")})
    assert r.status_code == 415


def test_nomina_no_puede_editar_matriz(admin):
    roles = {r["nombre"]: r["id"] for r in admin.get("/api/roles").json()["data"]}
    admin.post("/api/usuarios", json={"username": "nom", "nombre": "Nómina", "password": "clave-segura-1",
                                      "roles": [roles["Nómina"]]})
    pid = importar_matriz(admin).json()["data"]["periodo_id"]
    admin.post("/api/auth/logout")
    entrar(admin, "nom", "clave-segura-1")
    assert admin.get(f"/api/capacidad/matriz/periodos/{pid}/puestos").status_code == 200
    assert admin.post(f"/api/capacidad/matriz/periodos/{pid}/proyectar", json={}).status_code == 403
    assert date(2026, 9, 1)  # noqa
