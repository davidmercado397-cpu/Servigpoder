"""Motor de cobertura: cruza lo vendido (matriz comercial) con lo programado (SIESA).

Cada puesto se evalúa en bloques de 30 minutos. En cada bloque se compara cuántas
personas se vendieron contra cuántas están programadas trabajando:

- bloque con menos personas que las vendidas → horas **descubiertas** (hueco)
- bloque con más personas que las vendidas   → horas en **exceso**

Los bloques se atribuyen al día en que empieza la franja: el turno 18:00-06:00 del
día 16 cuenta completo en el 16, aunque termine el 17.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    Analisis, AnalisisDia, AnalisisPuesto, MatrizPeriodo, MatrizPuesto, ProgramacionCarga, ProgramacionDia,
    ProgramacionFila, Puesto, Turno,
)
from app.models.analisis import EXCESO, HUECO, MIXTO, OK, SIN_SERVICIO
from app.models.maestros import BOLSA, TRABAJO
from app.services import cubrimientos
from app.services.bloques import BLOQUE_MIN, BLOQUES_DIA
from app.services.bloques import bloques as _bloques
from app.services.matriz import festivos, requerimiento

class ErrorAnalisis(ValueError):
    pass


def _hora(bloque: int) -> str:
    m = (bloque % BLOQUES_DIA) * BLOQUE_MIN
    return f"{m // 60:02d}:{m % 60:02d}"


@dataclass
class Linea:
    """Línea de tiempo de un puesto: personas vendidas y programadas por bloque."""

    requerido: Counter = field(default_factory=Counter)
    programado: Counter = field(default_factory=Counter)
    dueno: dict[int, date] = field(default_factory=dict)  # bloque → día al que se atribuye

    def vender(self, base: int, fecha: date, inicio: time, fin: time, cantidad: int) -> None:
        for b in _bloques(inicio, fin):
            self.requerido[base + b] += cantidad
            self.dueno[base + b] = fecha

    def programar(self, base: int, fecha: date, inicio: time, fin: time) -> None:
        for b in _bloques(inicio, fin):
            self.programado[base + b] += 1
            self.dueno.setdefault(base + b, fecha)


@dataclass
class ResultadoDia:
    requeridas: float = 0
    programadas: float = 0
    descubiertas: float = 0
    exceso: float = 0
    detalle: list[dict] = field(default_factory=list)

    @property
    def estado(self) -> str:
        if self.descubiertas and self.exceso:
            return MIXTO
        if self.descubiertas:
            return HUECO
        if self.exceso:
            return EXCESO
        return SIN_SERVICIO if not self.requeridas and not self.programadas else OK


def evaluar(linea: Linea, desde: date, hasta: date) -> dict[date, ResultadoDia]:
    dias: dict[date, ResultadoDia] = {desde + timedelta(n): ResultadoDia() for n in range((hasta - desde).days + 1)}
    tramo: dict | None = None  # tramo abierto de hueco/exceso para el detalle

    for b in sorted(set(linea.requerido) | set(linea.programado)):
        fecha = linea.dueno[b]
        dia = dias.get(fecha)
        req, prog = linea.requerido[b], linea.programado[b]
        tipo, n = (HUECO, req - prog) if prog < req else (EXCESO, prog - req) if prog > req else (None, 0)
        if dia is None:
            tramo = None
            continue
        h = BLOQUE_MIN / 60
        dia.requeridas += req * h
        dia.programadas += prog * h
        if tipo == HUECO:
            dia.descubiertas += n * h
        elif tipo == EXCESO:
            dia.exceso += n * h

        # Agrupa bloques contiguos del mismo tipo y diferencia en tramos legibles
        if tipo and tramo and tramo["_fin"] == b and tramo["tipo"] == tipo and tramo["personas"] == n and tramo["_dia"] == fecha:
            tramo["_fin"] = b + 1
            tramo["fin"] = _hora(b + 1)
        elif tipo:
            tramo = {"tipo": tipo, "personas": n, "inicio": _hora(b), "fin": _hora(b + 1), "_fin": b + 1, "_dia": fecha}
            dia.detalle.append(tramo)
        else:
            tramo = None

    for dia in dias.values():
        for t in dia.detalle:
            t.pop("_fin", None)
            t.pop("_dia", None)
    return dias


def _estado_puesto(dias_hueco: int, dias_exceso: int) -> str:
    if dias_hueco and dias_exceso:
        return MIXTO
    return HUECO if dias_hueco else EXCESO if dias_exceso else OK


def _d(x: float) -> Decimal:
    return Decimal(str(round(x, 1)))


def ultima_carga(db: Session, anio: int, mes: int) -> ProgramacionCarga | None:
    return db.scalar(
        select(ProgramacionCarga).where(ProgramacionCarga.anio == anio, ProgramacionCarga.mes == mes)
        .order_by(ProgramacionCarga.id.desc()).limit(1)
    )


def analizar(db: Session, carga: ProgramacionCarga, usuario_id: int | None = None) -> Analisis:
    periodo = db.scalar(select(MatrizPeriodo).where(MatrizPeriodo.anio == carga.anio, MatrizPeriodo.mes == carga.mes))
    if periodo is None:
        raise ErrorAnalisis(f"No existe matriz comercial para {carga.mes:02d}/{carga.anio}. Impórtela o proyéctela primero.")

    desde, hasta = carga.desde, carga.hasta
    inicio_mes = date(carga.anio, carga.mes, 1)
    fest = festivos(carga.anio, carga.mes)

    franjas_turno = {t.codigo: [(f.inicio, f.fin) for f in t.franjas] for t in db.scalars(select(Turno)) if t.clase == TRABAJO}
    puestos = {p.id: p for p in db.scalars(select(Puesto))}
    matriz = {mp.puesto_id: mp for mp in db.scalars(select(MatrizPuesto).where(MatrizPuesto.periodo_id == periodo.id))}

    # Todo lo programado en la carga; los días trabajados en puestos del maestro alimentan la cobertura
    registros = cubrimientos.registros_carga(db, carga.id)
    en_puesto = [(r.cedula, r.puesto_id, r.fecha, r.codigo) for r in registros if r.clase == TRABAJO and r.puesto_id]
    titular = cubrimientos.titulares(registros, puestos)

    lineas: dict[int, Linea] = defaultdict(Linea)
    personas: dict[int, set[str]] = defaultdict(set)
    for cedula, pid, fecha, codigo in en_puesto:
        p = puestos[pid]
        if p.tipo == BOLSA or p.excluido:
            continue
        base = (fecha - inicio_mes).days * BLOQUES_DIA
        for ini, fin in franjas_turno.get(codigo, []):
            lineas[pid].programar(base, fecha, ini, fin)
        personas[pid].add(cedula)

    for pid, mp in matriz.items():
        if puestos[pid].excluido or puestos[pid].tipo == BOLSA:
            continue
        for fecha, franjas in requerimiento(mp, carga.anio, carga.mes, fest).items():
            base = (fecha - inicio_mes).days * BLOQUES_DIA
            for f in franjas:
                lineas[pid].vender(base, fecha, f.inicio, f.fin, f.cantidad)

    # Un análisis por carga: se reemplaza el anterior
    db.execute(delete(Analisis).where(Analisis.carga_id == carga.id))
    analisis = Analisis(carga_id=carga.id, periodo_id=periodo.id, usuario_id=usuario_id,
                        generado_en=datetime.now(timezone.utc))
    db.add(analisis)

    fijos = Counter(titular.values())
    tot = Counter()
    por_ciudad: dict[str, Counter] = defaultdict(Counter)
    for pid in set(matriz) | set(lineas):
        p = puestos[pid]
        if p.excluido or p.tipo == BOLSA:
            continue
        dias = evaluar(lineas[pid], desde, hasta)
        dh = sum(1 for d in dias.values() if d.descubiertas)
        de = sum(1 for d in dias.values() if d.exceso)
        mp = matriz.get(pid)
        ap = AnalisisPuesto(
            puesto_id=pid,
            hombres=mp.hombres if mp else Decimal(0),
            fijos=fijos.get(pid, 0),
            personas=len(personas.get(pid, ())),
            horas_requeridas=_d(sum(d.requeridas for d in dias.values())),
            horas_programadas=_d(sum(d.programadas for d in dias.values())),
            horas_descubiertas=_d(sum(d.descubiertas for d in dias.values())),
            horas_exceso=_d(sum(d.exceso for d in dias.values())),
            dias_hueco=dh,
            dias_exceso=de,
            estado=_estado_puesto(dh, de),
        )
        ap.dias = [
            AnalisisDia(fecha=f, horas_requeridas=_d(d.requeridas), horas_programadas=_d(d.programadas),
                        horas_descubiertas=_d(d.descubiertas), horas_exceso=_d(d.exceso), estado=d.estado, detalle=d.detalle)
            for f, d in dias.items()
        ]
        analisis.puestos.append(ap)

        ciudad = (p.ubicacion.ciudad or "Sin ciudad").upper()
        for clave, valor in (("requeridas", ap.horas_requeridas), ("programadas", ap.horas_programadas),
                             ("descubiertas", ap.horas_descubiertas), ("exceso", ap.horas_exceso)):
            tot[clave] += float(valor)
            por_ciudad[ciudad][clave] += float(valor)
        tot[f"puestos_{ap.estado}"] += 1
        if mp and not ap.personas and ap.horas_requeridas:
            # Vendido pero nadie programado: puesto cerrado o código distinto en SIESA
            tot["puestos_sin_programacion"] += 1
        tot["puestos"] += 1
        por_ciudad[ciudad]["puestos"] += 1
        por_ciudad[ciudad][f"puestos_{ap.estado}"] += 1
        if not mp:
            tot["puestos_sin_matriz"] += 1
        else:
            tot["hombres"] += float(mp.hombres)
            if ap.fijos > float(mp.hombres) + 0.5:
                tot["puestos_fijos_de_mas"] += 1
            elif ap.fijos < float(mp.hombres) - 0.5:
                tot["puestos_fijos_de_menos"] += 1
        tot["fijos"] += ap.fijos

    # Cubrimientos y turnos adicionales (F3), con el análisis de días ya guardado
    db.flush()
    tot.update(cubrimientos.detectar(db, analisis, registros, puestos, titular, franjas_turno))

    requeridas = tot["requeridas"]
    analisis.resumen = {
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "anio": carga.anio,
        "mes": carga.mes,
        "cobertura_pct": round(100 * (1 - tot["descubiertas"] / requeridas), 1) if requeridas else None,
        **{k: round(v, 1) if isinstance(v, float) else v for k, v in tot.items()},
        "filas_sin_puesto": db.scalar(
            select(func.count()).select_from(ProgramacionFila)
            .where(ProgramacionFila.carga_id == carga.id, ProgramacionFila.puesto_id.is_(None))
        ),
        "por_ciudad": {
            c: {k: round(v, 1) if isinstance(v, float) else v for k, v in vals.items()}
            | {"cobertura_pct": round(100 * (1 - vals["descubiertas"] / vals["requeridas"]), 1) if vals["requeridas"] else None}
            for c, vals in sorted(por_ciudad.items())
        },
    }
    db.commit()
    return analisis
