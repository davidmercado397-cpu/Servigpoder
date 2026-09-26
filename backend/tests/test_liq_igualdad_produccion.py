"""Igualdad con la app original en producción.

Las huellas se tomaron de la pantalla de cada turno en producción (matriz de 12 conceptos × 8 tipos de
día, con un decimal, hora nocturna 19:00). La versión nueva debe generar exactamente la misma matriz
para los 129 turnos que se cargan como configuración inicial.
"""

from datetime import time
from decimal import Decimal
from pathlib import Path

from app.apps.liquidador.dominio.matriz import build_shift_matrix
from app.apps.liquidador.dominio.tipos import DayType, HourConcept
from app.apps.liquidador.services.turnos import DATOS_INICIALES

HUELLAS = Path(__file__).parent / "datos" / "liq_huellas_matrices_produccion.txt"


def _fnv(texto: str) -> str:
    h = 0x811C9DC5
    for c in texto.encode():
        h = ((h ^ c) * 0x01000193) & 0xFFFFFFFF
    return f"{h:08x}"


def _huella(matriz: dict) -> str:
    valores = [f"{matriz[c.value][d.value]:.1f}" for c in HourConcept for d in DayType]
    return f"{_fnv(','.join(valores))}:{len(valores)}"


def test_matrices_de_los_129_turnos_iguales_a_produccion():
    esperadas = dict(x.split(":", 1) for x in HUELLAS.read_text().split())
    calculadas = {}
    for linea in DATOS_INICIALES.read_text(encoding="utf-8").splitlines()[1:]:
        codigo, _, inicio, _, ordinarias, extras, _, incapacidad = linea.split("|")
        o, e = (Decimal(0), Decimal(0)) if incapacidad == "1" else (Decimal(ordinarias), Decimal(extras))
        calculadas[codigo] = _huella(build_shift_matrix(o, e, time.fromisoformat(inicio), 19))
    assert len(esperadas) == len(calculadas) == 129
    distintas = {c: (calculadas[c], esperadas.get(c)) for c in calculadas if calculadas[c] != esperadas.get(c)}
    assert distintas == {}
