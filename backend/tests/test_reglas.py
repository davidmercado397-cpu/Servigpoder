from datetime import time

import pytest

from app.services.codigos import canonico, compacto
from app.services.jornada import L_S, L_V, SABADO, proponer
from app.models.matriz import TODOS_LOS_DIAS
from app.services.programacion import normalizar_codigo


@pytest.mark.parametrize(
    "a,b",
    [("47A", "47-A"), ("3 - 1", "03-1"), ("03", "3"), ("283-9H", "283-9h"), ("31-1.", "31-1")],
)
def test_codigos_equivalentes(a, b):
    assert canonico(a) == canonico(b)


def test_codigos_distintos_no_colisionan():
    assert canonico("03-1") != canonico("31")
    assert compacto("283-151") == compacto("283-15-1")
    assert canonico("283-151") != canonico("283-15-1")


def test_normalizar_codigo():
    assert normalizar_codigo("[VAC]") == "VAC"
    assert normalizar_codigo(" IND  NOCHE ") == "IND NOCHE"
    assert normalizar_codigo("06:00 - 18:00*") == "06:00 - 18:00*"


def test_terna_normal_24h():
    p = proponer("4x2 (2dia 2 noche 2 descanso)", "TERNA NORMAL", 3)
    assert [(f.inicio, f.fin, f.dias) for f in p.franjas] == [(time(6), time(18), TODOS_LOS_DIAS), (time(18), time(6), TODOS_LOS_DIAS)]
    assert p.incluye_festivos and not p.revisar


def test_solo_noche():
    p = proponer("4x2", "solo noche de lunesa domingo", 1.5)
    assert [(f.inicio, f.fin) for f in p.franjas] == [(time(18), time(6))]
    assert not p.revisar


def test_recepcion_lunes_a_viernes_y_sabado():
    p = proponer("6 x1", "lunes a viernes 6:00 18:00 sabados 6:00 a 14: 00", 1)
    assert [(f.dias, f.inicio, f.fin) for f in p.franjas] == [(L_V, time(6), time(18)), (SABADO, time(6), time(14))]
    assert not p.incluye_festivos


def test_16_horas_se_une():
    p = proponer("6X1", "SERVICIO DE 16 HORAS 06:00 a 14:00 14:00 22:00", 2.3)
    assert [(f.inicio, f.fin) for f in p.franjas] == [(time(6), time(22))]
    assert not p.revisar


def test_diurno_lunes_a_sabado():
    p = proponer("6X1", "SOLO DIURNO LUNES A SABADO", 1)
    assert p.franjas[0].dias == L_S and not p.incluye_festivos


def test_hombres_incoherentes_se_marcan():
    p = proponer("4x2", "TERNA NORMAL", 5)
    assert p.revisar and "esperados" in p.nota


def test_excluidos():
    assert proponer("N/A", "SE PAGA CON MODALIDA FIJA", 1).excluido
    assert proponer("4x2 (4dia 2 descanso 4 noche)", "CUATRO DE DIA", 13).excluido


def test_jornada_desconocida_requiere_revision():
    assert proponer("4x2", "algo raro", 1).revisar


def test_tres_turnos_de_8_horas():
    p = proponer("6X1", "TURNO 8 HORAS B - A - C", 3.5)
    assert [(f.inicio, f.fin) for f in p.franjas] == [(time(6), time(6))]
    assert not p.revisar


def test_lun_a_vier_sin_festivos_con_horas_sin_minutos():
    p = proponer("5X2", "8 HRAS DE LUN A VIER SIN FESTIVOS 6 A 14", 1.4)
    assert [(f.dias, f.inicio, f.fin) for f in p.franjas] == [(L_V, time(6), time(14))]
    assert not p.incluye_festivos


def test_12_horas_sin_rango_es_diurno():
    p = proponer("5X2", "12 HRAS DE LUN A VIER SIN FESTIVOS", 1)
    assert [(f.dias, f.inicio, f.fin) for f in p.franjas] == [(L_V, time(6), time(18))]
