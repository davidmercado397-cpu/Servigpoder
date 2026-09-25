"""Interpreta el texto libre de la matriz (columnas SECUENCIA y JORNADAS) y
propone las franjas de cobertura vendidas.

Es una propuesta inicial: todo lo que no se reconoce con seguridad queda
marcado para revisión y el programador lo corrige en la matriz comercial.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import time

from app.models.matriz import TODOS_LOS_DIAS

L_V = 0b0011111
L_S = 0b0111111
SABADO = 0b0100000

DIA = (time(6), time(18))
NOCHE = (time(18), time(6))


@dataclass
class Franja:
    dias: int
    inicio: time
    fin: time
    cantidad: int = 1


@dataclass
class Propuesta:
    franjas: list[Franja] = field(default_factory=list)
    incluye_festivos: bool = True
    excluido: bool = False
    revisar: bool = False
    nota: str = ""


def _normalizar(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.upper()).strip()


_HORA = r"(\d{1,2})(?::\s?(\d{2}))?"


def _horas(texto: str) -> list[tuple[time, time]]:
    """Pares hora-hora explícitos en el texto: '06:00 a 14:00', '8:30 A 17:30', '14:00 22:00'."""
    rangos = []
    for m in re.finditer(rf"{_HORA}\s*(?:H\s*)?(A|-)?\s*{_HORA}", texto):
        h1, m1, sep, h2, m2 = m.groups()
        a, b = int(h1), int(h2)
        if a > 24 or b > 24:
            continue
        # Sin separador ("14:00 22:00") ambas horas deben traer minutos
        if sep is None and (m1 is None or m2 is None):
            continue
        # Horas sin minutos ("8 A18") solo si forman un turno razonable; descarta "16 HORAS", "2 A 3"
        if m1 is None and m2 is None and not 4 <= (b - a) % 24 <= 16:
            continue
        rangos.append((time(a % 24, int(m1 or 0)), time(b % 24, int(m2 or 0))))
    return rangos


def _dias(texto: str) -> int | None:
    if re.search(r"LUNES ?A ?VIERNES|LUN A VIER|L-V|DE LAV|LAV\b", texto):
        return L_V
    if re.search(r"LUNES ?A ?SABADO|LUNESA SABADO|L-S", texto):
        return L_S
    if re.search(r"LUNES ?A ?DOMINGO|LUNESA DOMINGO|L-D|DE LAD|LAD\b", texto):
        return TODOS_LOS_DIAS
    return None


def proponer(secuencia: str, jornada: str, hombres: float) -> Propuesta:
    sec = _normalizar(secuencia)
    jor = _normalizar(jornada)
    p = Propuesta()

    if sec in {"N/A", "JUS"} or "MODALIDAD FIJA" in jor or "4DIA 2 DESCANSO 4 NOCHE" in sec:
        p.excluido = True
        p.nota = "Excluido del control (escolta, coordinador o supervisor)"
        return p

    # 6x1 y 5x2 describen la rotación del personal, no los días del servicio;
    # si el texto no dice los días se asume servicio todos los días.
    dias = _dias(jor) or TODOS_LOS_DIAS

    # Recepción: lunes a viernes 6-18 y sábados 6-14
    m_sab = re.search(rf"SABADOS? (?:DE )?{_HORA}\s*(?:A|-)\s*{_HORA}", jor)
    if m_sab and dias == L_V:
        base = _horas(jor[: m_sab.start()])
        h1, m1, h2, m2 = m_sab.groups()
        sabado = (time(int(h1) % 24, int(m1 or 0)), time(int(h2) % 24, int(m2 or 0)))
        p.franjas = [Franja(L_V, *(base[0] if base else DIA)), Franja(SABADO, *sabado)]
        p.incluye_festivos = False
        return p

    rangos = _horas(jor)
    horas_texto = re.search(r"\b(\d{1,2}) ?(?:HORAS|HRAS|HRS)\b", jor)

    if re.search(r"TURNO 8 HORAS B ?- ?A ?- ?C|TURNOS? A ?- ?B ?- ?C", jor):
        # Tres turnos de 8 horas (A 06-14, B 14-22, C 22-06): cobertura de 24 horas
        p.franjas = [Franja(dias, time(6), time(6))]
    elif "TERNA NORMAL" in jor or (not jor and hombres >= 3 and "4X2" in sec):
        p.franjas = [Franja(dias, *DIA), Franja(dias, *NOCHE)]
    elif rangos:
        # Rangos contiguos (06-14 y 14-22) se unen en una sola franja
        unidos: list[tuple[time, time]] = []
        for ini, fin in rangos:
            if unidos and unidos[-1][1] == ini:
                unidos[-1] = (unidos[-1][0], fin)
            else:
                unidos.append((ini, fin))
        p.franjas = [Franja(dias, ini, fin) for ini, fin in unidos]
        if len(unidos) > 1:
            p.revisar = True
            p.nota = "Varias franjas: verificar que correspondan a lo vendido"
    elif re.search(r"NOCHE|NOCTURN", jor):
        p.franjas = [Franja(dias, *NOCHE)]
    elif re.search(r"DIURN|DIA\b|SOLO DIA", jor) or (horas_texto and horas_texto.group(1) == "12"):
        p.franjas = [Franja(dias, *DIA)]
    else:
        p.revisar = True
        p.nota = f"No se pudo interpretar la jornada '{jornada}'"
        return p

    p.incluye_festivos = dias == TODOS_LOS_DIAS and "SIN FESTIVO" not in jor

    # Coherencia con los hombres presupuestados según la secuencia
    esperados = hombres_esperados(sec, p.franjas)
    if esperados is not None and hombres and abs(esperados - hombres) > 0.35:
        p.revisar = True
        p.nota = (p.nota + "; " if p.nota else "") + (
            f"Hombres presupuestados {hombres:g} vs {esperados:.1f} esperados por la secuencia"
        )
    return p


def _horas_franja(ini: time, fin: time) -> float:
    a = ini.hour + ini.minute / 60
    b = fin.hour + fin.minute / 60
    return (b - a) % 24 or 24


def hombres_esperados(secuencia: str, franjas: list[Franja]) -> float | None:
    """Personas necesarias = turnos diarios × (días del ciclo / días trabajados).

    4x2 24 h: 2 turnos × 6/4 = 3 · 4x2 solo noche: 1 × 6/4 = 1,5 · 6x1 16 h: 2 × 7/6 = 2,3
    """
    m = re.search(r"(\d)\s*X\s*(\d)", secuencia.upper())
    if not m or not franjas:
        return None
    trabajo, descanso = int(m.group(1)), int(m.group(2))
    horas_dia = sum(_horas_franja(f.inicio, f.fin) * f.cantidad * bin(f.dias).count("1") for f in franjas) / 7
    return horas_dia / _horas_turno(franjas) * (trabajo + descanso) / trabajo


def _horas_turno(franjas: list[Franja]) -> float:
    if any(f.inicio == f.fin for f in franjas):
        return 8  # 24 horas en tres turnos A-B-C
    h = max(_horas_franja(f.inicio, f.fin) for f in franjas)
    # Los servicios de 16 h (y de 8 h) se cubren con turnos de 8 h; el resto con un turno por franja
    return 8 if h in (8, 16) else min(h, 12) if h >= 12 else h
