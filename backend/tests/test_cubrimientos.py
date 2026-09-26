from tests.conftest import entrar, archivo, xlsx
from tests.test_f1 import HORARIOS, importar_matriz

D, N = "06:00 - 18:00", "18:00 - 06:00"


def reporte(personas: list[tuple[str, str, str, dict[int, str]]]) -> bytes:
    """Excel de SIESA con filas (cedula, nombre, puesto, {dia: codigo}) del 15 al 20 de septiembre."""
    enc = ["C.C. Empleado", "NOMBRE EMPLEADO", "UBICACION", "DESCRIPCION UBICACION", "PUESTO", "DESCRIPCION PUESTO"]
    enc += [str(d) for d in range(1, 32)]
    filas = [["Compañia", "SERVIGPODER"], ["Desde", "2026-09-15"], ["Hasta", "2026-09-20"], enc]
    for cedula, nombre, puesto, dias in personas:
        fila = [cedula, nombre, puesto.split("-")[0], "UBIC", puesto, "DESC"] + [None] * 31
        for dia, codigo in dias.items():
            fila[5 + dia] = codigo
        filas.append(fila)
    return xlsx(filas)


ESCENARIO = [
    # Titulares del puesto 25 (servicio 24 h)
    ("1", "TITULAR A", "25", {15: D, 16: D, 17: N, 18: N, 19: "Z", 20: "L"}),
    ("2", "TITULAR B", "25", {15: "[VAC]", 16: N, 17: D, 18: D, 19: N, 20: N}),
    # R es titular en 47-A y el 15 cubre la noche de B (vacaciones) → justificado por novedad
    ("3", "RELEVO R", "47-A", {16: D, 17: D, 18: D, 19: D, 20: D}),
    ("3", "RELEVO R", "25", {15: N}),
    # S es titular en 47-A y el 19 cubre el día de A (descanso) → justificado por descanso
    ("4", "RELEVO S", "47-A", {15: N, 16: N, 17: N}),
    ("4", "RELEVO S", "25", {19: D}),
    # Y trabaja el 15 en 47-A y además de día en 25, donde A ya está → doble turno con exceso → pendiente
    ("5", "EXTRA Y", "47-A", {15: D, 16: "Z", 17: "L", 18: D}),
    ("5", "EXTRA Y", "25", {15: D}),
    # P está en la bolsa de disponibles: el 15 sin puesto; el 16 en bolsa pero cubre 47-A
    ("6", "DISPONIBLE P", "05", {15: D, 16: D}),
    ("6", "DISPONIBLE P", "47-A", {16: N}),
]


def _cargar(admin):
    importar_matriz(admin)
    admin.post("/api/capacidad/catalogos/turnos/importar", files=archivo(xlsx(HORARIOS)))
    r = admin.post("/api/capacidad/programacion/cargas", files=archivo(reporte(ESCENARIO)))
    assert r.status_code == 201, r.text
    return r.json()["meta"]["extra"]["analisis_id"]


def _por_persona(lista):
    return {(c["nombre"], c["fecha"][8:]): c for c in lista}


def test_cubrimientos_justificados_y_pendientes(admin):
    analisis_id = _cargar(admin)
    r = admin.get(f"/api/capacidad/cubrimientos/{analisis_id}").json()
    cubs = _por_persona(r["data"])
    assert set(cubs) == {("RELEVO R", "15"), ("RELEVO S", "19"), ("EXTRA Y", "15")}

    rr = cubs[("RELEVO R", "15")]
    assert (rr["motivo"], rr["estado"], rr["puesto_titular"]) == ("novedad", "justificado", "47A")
    assert rr["referencia"][0]["nombre"] == "TITULAR B" and rr["referencia"][0]["codigo"] == "VAC"

    rs = cubs[("RELEVO S", "19")]
    assert (rs["motivo"], rs["estado"]) == ("descanso", "justificado")

    ry = cubs[("EXTRA Y", "15")]
    assert ry["estado"] == "pendiente" and ry["genera_exceso"] and ry["doble_turno"]
    assert float(ry["horas"]) == 12
    assert r["meta"]["extra"]["por_estado"]["pendiente"] == 1

    resumen = admin.get(f"/api/capacidad/analisis/{analisis_id}").json()["data"]["resumen"]
    assert resumen["cubrimientos"] == 3 and resumen["cubrimientos_pendiente"] == 1


def test_nomina_aprueba_rechaza_y_se_conserva_al_recalcular(admin):
    analisis_id = _cargar(admin)
    cubs = _por_persona(admin.get(f"/api/capacidad/cubrimientos/{analisis_id}").json()["data"])
    y = cubs[("EXTRA Y", "15")]

    # Rechazar exige comentario
    r = admin.post(f"/api/capacidad/cubrimientos/{analisis_id}/decidir", json={"ids": [y["id"]], "estado": "rechazado"})
    assert r.status_code == 400
    r = admin.post(f"/api/capacidad/cubrimientos/{analisis_id}/decidir",
                   json={"ids": [y["id"]], "estado": "rechazado", "comentario": "No autorizado por operaciones"})
    assert r.status_code == 200

    # Al recalcular se genera un análisis nuevo y la decisión se mantiene
    nuevo = admin.post("/api/capacidad/analisis", json={"anio": 2026, "mes": 9}).json()["data"]["id"]
    y2 = _por_persona(admin.get(f"/api/capacidad/cubrimientos/{nuevo}").json()["data"])[("EXTRA Y", "15")]
    assert (y2["estado"], y2["comentario"], y2["decidido_por"]) == ("rechazado", "No autorizado por operaciones", "Administrador")

    # Deshacer la decisión vuelve al estado automático
    admin.post(f"/api/capacidad/cubrimientos/{nuevo}/decidir", json={"ids": [y2["id"]], "estado": "pendiente"})
    y3 = _por_persona(admin.get(f"/api/capacidad/cubrimientos/{nuevo}").json()["data"])[("EXTRA Y", "15")]
    assert y3["estado"] == "pendiente" and y3["comentario"] is None


def test_programador_no_puede_aprobar(admin):
    analisis_id = _cargar(admin)
    roles = {r["nombre"]: r["id"] for r in admin.get("/api/roles").json()["data"]}
    admin.post("/api/usuarios", json={"username": "prog", "nombre": "Programador", "password": "clave-segura-1",
                                      "roles": [roles["Programador"]]})
    cid = admin.get(f"/api/capacidad/cubrimientos/{analisis_id}").json()["data"][0]["id"]
    admin.post("/api/auth/logout")
    entrar(admin, "prog", "clave-segura-1")
    assert admin.get(f"/api/capacidad/cubrimientos/{analisis_id}").status_code == 200
    r = admin.post(f"/api/capacidad/cubrimientos/{analisis_id}/decidir", json={"ids": [cid], "estado": "aprobado"})
    assert r.status_code == 403


def test_personas_en_bolsa(admin):
    analisis_id = _cargar(admin)
    r = admin.get(f"/api/capacidad/cubrimientos/{analisis_id}/bolsas").json()
    assert [p["nombre"] for p in r["data"]] == ["DISPONIBLE P"]
    p = r["data"][0]
    assert p["dias_sin_puesto"] == ["2026-09-15"] and p["horas_sin_puesto"] == 12 and p["dias_en_puesto"] == 1
