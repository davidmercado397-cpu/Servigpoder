"""Bloques de 30 minutos usados para comparar vendido vs programado."""

from datetime import time

BLOQUE_MIN = 30
BLOQUES_DIA = 24 * 60 // BLOQUE_MIN


def bloques(inicio: time, fin: time) -> range:
    """Bloques desde las 00:00 del día; si fin <= inicio la franja pasa al día siguiente."""
    a = (inicio.hour * 60 + inicio.minute) // BLOQUE_MIN
    b = (fin.hour * 60 + fin.minute) // BLOQUE_MIN
    if b <= a:
        b += BLOQUES_DIA
    return range(a, b)


def hora_texto(hhmm: str) -> time:
    h, m = hhmm.split(":")
    return time(int(h) % 24, int(m))
