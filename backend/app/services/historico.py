"""Histórico y comparación de cargas (F4)."""

from collections import Counter
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Analisis, AnalisisPuesto, ProgramacionCarga, ProgramacionDia, ProgramacionFila, Puesto

AGREGADO, ELIMINADO, CAMBIADO = "agregado", "eliminado", "cambiado"
LIMITE_CAMBIOS = 3000


@dataclass
class Cambio:
    tipo: str
    cedula: str
    nombre: str
    puesto: str
    fecha: date
    antes: str | None
    despues: str | None


def _mapa(db: Session, carga_id: int) -> tuple[dict[tuple[str, str, date], str], dict[str, str]]:
    filas = db.execute(
        select(ProgramacionFila.cedula, ProgramacionFila.nombre, ProgramacionFila.puesto_siesa, ProgramacionDia.fecha, ProgramacionDia.codigo)
        .join(ProgramacionDia, ProgramacionDia.fila_id == ProgramacionFila.id)
        .where(ProgramacionFila.carga_id == carga_id)
    ).all()
    mapa, nombres = {}, {}
    for cedula, nombre, puesto, fecha, codigo in filas:
        mapa[(cedula, puesto, fecha)] = codigo
        nombres[cedula] = nombre
    return mapa, nombres


def comparar(db: Session, anterior: ProgramacionCarga, actual: ProgramacionCarga) -> dict:
    """Cambios celda a celda entre dos cargas: turnos agregados, eliminados o cambiados."""
    a, nombres_a = _mapa(db, anterior.id)
    b, nombres_b = _mapa(db, actual.id)
    nombres = nombres_a | nombres_b
    # Solo se comparan los días que ambas cargas cubren
    desde, hasta = max(anterior.desde, actual.desde), min(anterior.hasta, actual.hasta)

    cambios: list[Cambio] = []
    for clave in sorted(set(a) | set(b), key=lambda k: (k[2], k[1], k[0])):
        cedula, puesto, fecha = clave
        if not desde <= fecha <= hasta:
            continue
        va, vb = a.get(clave), b.get(clave)
        if va == vb:
            continue
        tipo = AGREGADO if va is None else ELIMINADO if vb is None else CAMBIADO
        cambios.append(Cambio(tipo, cedula, nombres.get(cedula, ""), puesto, fecha, va, vb))

    conteo = Counter(c.tipo for c in cambios)
    return {
        "anterior": anterior.id,
        "actual": actual.id,
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "total": len(cambios),
        "por_tipo": dict(conteo),
        "personas": len({c.cedula for c in cambios}),
        "puestos": len({c.puesto for c in cambios}),
        "cambios": [c.__dict__ | {"fecha": c.fecha.isoformat()} for c in cambios[:LIMITE_CAMBIOS]],
        "truncado": len(cambios) > LIMITE_CAMBIOS,
        "impacto": impacto(db, anterior, actual),
    }


def impacto(db: Session, anterior: ProgramacionCarga, actual: ProgramacionCarga) -> list[dict]:
    """Puestos cuya cobertura cambió entre los análisis de ambas cargas."""
    aa = db.scalar(select(Analisis.id).where(Analisis.carga_id == anterior.id))
    ab = db.scalar(select(Analisis.id).where(Analisis.carga_id == actual.id))
    if not aa or not ab:
        return []

    def horas(analisis_id: int) -> dict[int, tuple[float, float]]:
        return {pid: (float(d), float(e)) for pid, d, e in db.execute(
            select(AnalisisPuesto.puesto_id, AnalisisPuesto.horas_descubiertas, AnalisisPuesto.horas_exceso)
            .where(AnalisisPuesto.analisis_id == analisis_id))}

    ha, hb = horas(aa), horas(ab)
    codigos = {p.id: p.codigo for p in db.scalars(select(Puesto))}
    res = []
    for pid in set(ha) | set(hb):
        da, ea = ha.get(pid, (0, 0))
        db_, eb = hb.get(pid, (0, 0))
        if (da, ea) != (db_, eb):
            res.append({"puesto_id": pid, "puesto": codigos.get(pid, "?"), "descubiertas_antes": da, "descubiertas_despues": db_,
                        "exceso_antes": ea, "exceso_despues": eb})
    return sorted(res, key=lambda r: -abs(r["descubiertas_despues"] - r["descubiertas_antes"]))


def historico(db: Session) -> list[dict]:
    """Indicadores de cada carga analizada, agrupables por mes."""
    filas = db.execute(
        select(ProgramacionCarga, Analisis).outerjoin(Analisis, Analisis.carga_id == ProgramacionCarga.id)
        .order_by(ProgramacionCarga.anio.desc(), ProgramacionCarga.mes.desc(), ProgramacionCarga.id.desc())
    ).all()
    res = []
    for carga, analisis in filas:
        r = analisis.resumen if analisis else {}
        res.append({
            "carga_id": carga.id, "anio": carga.anio, "mes": carga.mes, "desde": carga.desde.isoformat(),
            "hasta": carga.hasta.isoformat(), "cargado_en": carga.cargado_en.isoformat(), "archivo": carga.archivo,
            "analisis_id": analisis.id if analisis else None,
            **{k: r.get(k) for k in ("cobertura_pct", "requeridas", "descubiertas", "exceso", "puestos", "puestos_hueco",
                                     "puestos_exceso", "puestos_mixto", "cubrimientos", "cubrimientos_pendiente")},
        })
    return res
