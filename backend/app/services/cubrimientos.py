"""Cubrimientos y turnos adicionales (F3).

Un **cubrimiento** es un turno de trabajo de una persona en un puesto donde no es
titular (su puesto titular es donde más turnos tiene en el mes). Para cada uno se
busca la razón automáticamente:

1. **novedad**: ese día un titular del puesto tiene una novedad que requiere
   cubrimiento (VAC, IEG, LNR, IND, PSA…), registrada en cualquier fila (incluida la
   bolsa 07 de incapacitados).
2. **descanso**: ese día un titular del puesto está en descanso (Z/L): es el relevo.

Queda **justificado** si tiene razón y no genera exceso ese día; en otro caso queda
**pendiente** para que nómina lo apruebe o rechace. También se marca el **doble
turno**: la persona trabaja ese mismo día en otro puesto.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Analisis, AnalisisDia, AnalisisPuesto, Cubrimiento, Novedad, ProgramacionDia, ProgramacionFila, Puesto
from app.models.analisis import EXCESO, MIXTO
from app.models.cubrimientos import JUSTIFICADO, MOTIVO_DESCANSO, MOTIVO_NOVEDAD, MOTIVO_SIN, PENDIENTE
from app.models.maestros import BOLSA, DESCANSO, TRABAJO
from app.models.programacion import NOVEDAD
from app.services.bloques import bloques as _bloques
from app.services.codigos import canonico
from app.services.bloques import hora_texto as _t
from app.services.matriz import horas



@dataclass
class Registro:
    cedula: str
    nombre: str
    puesto_id: int | None
    fecha: date
    codigo: str
    clase: str


def registros_carga(db: Session, carga_id: int) -> list[Registro]:
    filas = db.execute(
        select(ProgramacionFila.cedula, ProgramacionFila.nombre, ProgramacionFila.puesto_id,
               ProgramacionDia.fecha, ProgramacionDia.codigo, ProgramacionDia.clase)
        .join(ProgramacionDia, ProgramacionDia.fila_id == ProgramacionFila.id)
        .where(ProgramacionFila.carga_id == carga_id)
    ).all()
    return [Registro(*f) for f in filas]


def titulares(registros: list[Registro], puestos: dict[int, Puesto]) -> dict[str, int]:
    """Puesto titular de cada persona: el puesto operativo donde más días trabaja en el mes."""
    conteo: dict[str, Counter] = defaultdict(Counter)
    for r in registros:
        if r.clase == TRABAJO and r.puesto_id and puestos[r.puesto_id].tipo != BOLSA:
            conteo[r.cedula][r.puesto_id] += 1
    return {c: cnt.most_common(1)[0][0] for c, cnt in conteo.items()}


def detectar(db: Session, analisis: Analisis, registros: list[Registro], puestos: dict[int, Puesto],
             titular: dict[str, int], franjas_turno: dict[str, list]) -> Counter:
    horas_turno = horas_por_turno(franjas_turno)
    novedades_cubrir = set(db.scalars(select(Novedad.codigo).where(Novedad.requiere_cubrimiento.is_(True))))

    # Qué hace cada persona cada día (en cualquier fila)
    por_persona_dia: dict[tuple[str, date], list[Registro]] = defaultdict(list)
    for r in registros:
        por_persona_dia[(r.cedula, r.fecha)].append(r)

    titulares_de: dict[int, list[str]] = defaultdict(list)
    for cedula, pid in titular.items():
        titulares_de[pid].append(cedula)
    nombre = {r.cedula: r.nombre for r in registros}

    # Bloques de 30 min con exceso, por puesto y día (a partir de los tramos del análisis)
    con_exceso: dict[tuple[int, date], set[int]] = defaultdict(set)
    for pid, f, detalle in db.execute(
        select(AnalisisPuesto.puesto_id, AnalisisDia.fecha, AnalisisDia.detalle)
        .join(AnalisisDia, AnalisisDia.analisis_puesto_id == AnalisisPuesto.id)
        .where(AnalisisPuesto.analisis_id == analisis.id, AnalisisDia.estado.in_([EXCESO, MIXTO]))
    ):
        for t in detalle:
            if t["tipo"] == EXCESO:
                con_exceso[(pid, f)].update(_bloques(_t(t["inicio"]), _t(t["fin"])))

    conteo: Counter = Counter()
    for r in registros:
        if r.clase != TRABAJO or r.puesto_id is None:
            continue
        p = puestos[r.puesto_id]
        if p.tipo == BOLSA or p.excluido or titular.get(r.cedula) == r.puesto_id:
            continue

        ref_novedad, ref_descanso = [], []
        for t in titulares_de.get(r.puesto_id, []):
            for x in por_persona_dia.get((t, r.fecha), []):
                if x.clase == NOVEDAD and x.codigo in novedades_cubrir:
                    ref_novedad.append({"cedula": t, "nombre": nombre.get(t, ""), "codigo": x.codigo})
                elif x.clase == DESCANSO and x.puesto_id == r.puesto_id:
                    ref_descanso.append({"cedula": t, "nombre": nombre.get(t, ""), "codigo": x.codigo})
        if ref_novedad:
            motivo, referencia = MOTIVO_NOVEDAD, ref_novedad
        elif ref_descanso:
            motivo, referencia = MOTIVO_DESCANSO, ref_descanso
        else:
            motivo, referencia = MOTIVO_SIN, []

        # Genera exceso solo si sus horas se cruzan con horas sobrantes del puesto ese día
        bloques_turno = {b for i, f in franjas_turno.get(r.codigo, []) for b in _bloques(i, f)}
        genera_exceso = bool(bloques_turno & con_exceso.get((r.puesto_id, r.fecha), set()))
        doble = any(
            x.clase == TRABAJO and x.puesto_id not in (None, r.puesto_id) and puestos[x.puesto_id].tipo != BOLSA
            for x in por_persona_dia[(r.cedula, r.fecha)]
        )
        estado = JUSTIFICADO if motivo != MOTIVO_SIN and not genera_exceso else PENDIENTE
        tit = titular.get(r.cedula)
        db.add(Cubrimiento(
            analisis_id=analisis.id, puesto_id=r.puesto_id, fecha=r.fecha, cedula=r.cedula, nombre=r.nombre,
            codigo_turno=r.codigo, horas=Decimal(str(round(horas_turno.get(r.codigo, 0), 1))),
            puesto_titular=puestos[tit].codigo if tit else None, motivo=motivo, referencia=referencia,
            genera_exceso=genera_exceso, doble_turno=doble, estado_auto=estado,
        ))
        conteo["cubrimientos"] += 1
        conteo[f"cubrimientos_{estado}"] += 1
        conteo[f"cubrimientos_{motivo}"] += 1
        if doble:
            conteo["cubrimientos_doble_turno"] += 1
    return conteo


def horas_por_turno(franjas: dict[str, list]) -> dict[str, float]:
    return {codigo: sum(horas(i, f) for i, f in fr) for codigo, fr in franjas.items()}


@dataclass
class PersonaBolsa:
    cedula: str
    nombre: str
    bolsas: list[str]
    dias_sin_puesto: list[str]
    horas_sin_puesto: float
    dias_en_puesto: int


BOLSAS_REPORTE = {"5", "6"}  # disponibles y relevantes


def personas_en_bolsa(db: Session, carga_id: int, horas_turno: dict[str, float], todas: bool = False) -> list[PersonaBolsa]:
    """Personas con turnos de trabajo en una bolsa los días que no cubren ningún puesto.

    Por defecto solo las bolsas 05 (disponibles) y 06 (relevantes); `todas` incluye 07, 08…
    """
    puestos = {p.id: p for p in db.scalars(select(Puesto))}
    registros = registros_carga(db, carga_id)
    en_puesto: set[tuple[str, date]] = set()
    dias_puesto: Counter = Counter()
    for r in registros:
        if r.clase == TRABAJO and r.puesto_id and puestos[r.puesto_id].tipo != BOLSA:
            en_puesto.add((r.cedula, r.fecha))
            dias_puesto[r.cedula] += 1

    resultado: dict[str, PersonaBolsa] = {}
    for r in registros:
        if r.clase != TRABAJO or not r.puesto_id or puestos[r.puesto_id].tipo != BOLSA:
            continue
        if not todas and canonico(puestos[r.puesto_id].codigo) not in BOLSAS_REPORTE:
            continue
        if (r.cedula, r.fecha) in en_puesto:
            continue  # ese día sí cubre un puesto: válido
        pb = resultado.setdefault(r.cedula, PersonaBolsa(r.cedula, r.nombre, [], [], 0, dias_puesto[r.cedula]))
        bolsa = f"{puestos[r.puesto_id].codigo} {puestos[r.puesto_id].descripcion}".strip()
        if bolsa not in pb.bolsas:
            pb.bolsas.append(bolsa)
        pb.dias_sin_puesto.append(r.fecha.isoformat())
        pb.horas_sin_puesto += horas_turno.get(r.codigo, 0)
    for pb in resultado.values():
        pb.dias_sin_puesto.sort()
        pb.horas_sin_puesto = round(pb.horas_sin_puesto, 1)
    return sorted(resultado.values(), key=lambda p: (-len(p.dias_sin_puesto), p.nombre))
