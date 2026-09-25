from datetime import date, time

from app.services.cobertura import BLOQUES_DIA, Linea, evaluar
from tests.conftest import archivo, xlsx
from tests.test_f1 import HORARIOS, importar_matriz, programacion

D15, D16 = date(2026, 9, 15), date(2026, 9, 16)
BASE15 = 14 * BLOQUES_DIA  # 15 de septiembre, contando desde el 1


def _servicio_24h(linea: Linea, fecha: date, base: int) -> None:
    linea.vender(base, fecha, time(6), time(18), 1)
    linea.vender(base, fecha, time(18), time(6), 1)


def test_cobertura_completa():
    l = Linea()
    _servicio_24h(l, D15, BASE15)
    l.programar(BASE15, D15, time(6), time(18))
    l.programar(BASE15, D15, time(18), time(6))
    d = evaluar(l, D15, D15)[D15]
    assert (d.requeridas, d.programadas, d.descubiertas, d.exceso, d.estado) == (24, 24, 0, 0, "ok")


def test_dos_de_dia_y_ninguno_de_noche():
    """El caso del usuario: 2 personas de 06 a 18 y nadie de 18 a 06 → 12 h de hueco y 12 h de exceso."""
    l = Linea()
    _servicio_24h(l, D15, BASE15)
    l.programar(BASE15, D15, time(6), time(18))
    l.programar(BASE15, D15, time(6), time(18))
    d = evaluar(l, D15, D15)[D15]
    assert (d.descubiertas, d.exceso, d.estado) == (12, 12, "mixto")
    assert {(t["tipo"], t["inicio"], t["fin"], t["personas"]) for t in d.detalle} == {
        ("exceso", "06:00", "18:00", 1), ("hueco", "18:00", "06:00", 1)}


def test_turno_nocturno_se_atribuye_al_dia_que_empieza():
    l = Linea()
    _servicio_24h(l, D15, BASE15)
    _servicio_24h(l, D16, BASE15 + BLOQUES_DIA)
    l.programar(BASE15, D15, time(6), time(18))
    l.programar(BASE15, D15, time(18), time(6))
    l.programar(BASE15 + BLOQUES_DIA, D16, time(6), time(18))
    dias = evaluar(l, D15, D16)
    assert dias[D15].estado == "ok"  # la noche del 15 termina el 16 pero es del 15
    assert (dias[D16].descubiertas, dias[D16].estado) == (12, "hueco")


def test_programado_sin_venta_es_exceso():
    l = Linea()
    l.programar(BASE15, D15, time(8), time(17))
    d = evaluar(l, D15, D15)[D15]
    assert (d.requeridas, d.exceso, d.estado) == (0, 9, "exceso")


def test_turno_partido():
    l = Linea()
    l.vender(BASE15, D15, time(5, 30), time(20, 30), 1)
    l.programar(BASE15, D15, time(5, 30), time(12))
    l.programar(BASE15, D15, time(14, 30), time(20, 30))
    d = evaluar(l, D15, D15)[D15]
    assert d.descubiertas == 2.5 and [(t["inicio"], t["fin"]) for t in d.detalle] == [("12:00", "14:30")]


def _preparar(admin, dias):
    importar_matriz(admin)
    admin.post("/api/catalogos/turnos/importar", files=archivo(xlsx(HORARIOS)))
    return admin.post("/api/programacion/cargas", files=archivo(xlsx(programacion(dias))))


def test_analisis_automatico_al_cargar(admin):
    # Puesto 25 (24 h): cada día solo hay turno de día; la noche queda descubierta
    r = _preparar(admin, {"25": ["06:00 - 18:00", "06:00 - 18:00", "Z"], "25-X": ["06:00 - 18:00", "18:00 - 06:00"]})
    assert r.status_code == 201
    analisis_id = r.json()["meta"]["extra"]["analisis_id"]
    assert analisis_id

    a = admin.get(f"/api/analisis/{analisis_id}").json()["data"]
    assert a["desactualizado"] is False
    assert a["resumen"]["cobertura_pct"] is not None

    lista = admin.get(f"/api/analisis/{analisis_id}/puestos?q=25").json()["data"]
    p25 = next(p for p in lista if p["puesto"]["codigo"] == "25")
    assert p25["estado"] == "hueco" and p25["dias_hueco"] >= 2

    puesto_id = p25["puesto"]["id"]
    det = admin.get(f"/api/analisis/{analisis_id}/puestos/{puesto_id}").json()["data"]
    dia15 = next(d for d in det["dias"] if d["fecha"] == "2026-09-15")
    assert dia15["estado"] == "hueco" and float(dia15["horas_descubiertas"]) == 12
    assert len(det["franjas"]) == 2 and det["personas"]


def test_analisis_desactualizado_al_editar_matriz(admin):
    r = _preparar(admin, {"25": ["06:00 - 18:00"]})
    analisis_id = r.json()["meta"]["extra"]["analisis_id"]
    periodo_id = admin.get("/api/matriz/periodos").json()["data"][0]["id"]
    mp = next(p for p in admin.get(f"/api/matriz/periodos/{periodo_id}/puestos").json()["data"] if p["puesto"]["codigo"] == "25")
    admin.patch(f"/api/matriz/puestos/{mp['id']}", json={"incluye_festivos": False})
    a = admin.get(f"/api/analisis/{analisis_id}").json()["data"]
    assert a["desactualizado"] is True and "matriz" in a["motivo_desactualizado"]

    nuevo = admin.post("/api/analisis", json={"anio": 2026, "mes": 9}).json()["data"]
    assert nuevo["desactualizado"] is False


def test_sin_matriz_no_analiza(admin):
    admin.post("/api/catalogos/turnos/importar", files=archivo(xlsx(HORARIOS)))
    r = admin.post("/api/programacion/cargas", files=archivo(xlsx(programacion({"25": ["Z"]}))))
    assert r.status_code == 201 and r.json()["meta"]["extra"]["analisis_id"] is None
    r = admin.post("/api/analisis", json={"anio": 2026, "mes": 9})
    assert r.status_code == 409 and "matriz" in r.json()["error"]["message"]


def test_exportar_excel(admin):
    analisis_id = _preparar(admin, {"25": ["06:00 - 18:00"]}).json()["meta"]["extra"]["analisis_id"]
    r = admin.get(f"/api/analisis/{analisis_id}/exportar")
    assert r.status_code == 200
    assert r.content[:4] == b"PK\x03\x04"
    assert "attachment" in r.headers["content-disposition"]
