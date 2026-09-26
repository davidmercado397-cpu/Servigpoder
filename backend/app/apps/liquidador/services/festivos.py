"""Festivos de Colombia (librería `holidays`) con ajustes manuales que tienen prioridad."""

from datetime import date, timedelta
from functools import lru_cache

import holidays
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.apps.liquidador.models import LiqFestivoAjuste


@lru_cache(maxsize=16)
def nacionales(anio: int) -> dict[date, str]:
    return dict(holidays.country_holidays("CO", years=anio))


def conjunto(db: Session, desde: date, hasta: date) -> set[date]:
    """Fechas festivas efectivas entre `desde` y `hasta` (incluidas), ya con los ajustes."""
    fechas = {d for anio in range(desde.year, hasta.year + 1) for d in nacionales(anio) if desde <= d <= hasta}
    for aj in db.scalars(select(LiqFestivoAjuste).where(LiqFestivoAjuste.fecha >= desde, LiqFestivoAjuste.fecha <= hasta)):
        (fechas.add if aj.es_festivo else fechas.discard)(aj.fecha)
    return fechas


def es_festivo(db: Session, fecha: date) -> bool:
    return fecha in conjunto(db, fecha, fecha)


def del_anio(db: Session, anio: int) -> list[dict]:
    """Festivos del año para la pantalla: nacionales (vigentes o quitados) y agregados a mano."""
    base = nacionales(anio)
    ajustes = {a.fecha: a for a in db.scalars(select(LiqFestivoAjuste).where(
        LiqFestivoAjuste.fecha >= date(anio, 1, 1), LiqFestivoAjuste.fecha <= date(anio, 12, 31)))}
    items = []
    for fecha, nombre in sorted(base.items()):
        aj = ajustes.get(fecha)
        quitado = aj is not None and not aj.es_festivo
        items.append({"fecha": fecha, "descripcion": (aj.descripcion if aj and aj.descripcion else nombre),
                      "origen": "quitado" if quitado else "nacional", "ajuste_id": aj.id if aj else None, "vigente": not quitado})
    for fecha, aj in ajustes.items():
        if aj.es_festivo and fecha not in base:
            items.append({"fecha": fecha, "descripcion": aj.descripcion or "Festivo manual", "origen": "manual",
                          "ajuste_id": aj.id, "vigente": True})
    return sorted(items, key=lambda i: i["fecha"])


def ajustar(db: Session, fecha: date, es: bool, descripcion: str | None) -> LiqFestivoAjuste:
    aj = db.scalar(select(LiqFestivoAjuste).where(LiqFestivoAjuste.fecha == fecha))
    if aj is None:
        aj = LiqFestivoAjuste(fecha=fecha, es_festivo=es, descripcion=descripcion)
        db.add(aj)
    else:
        aj.es_festivo, aj.descripcion = es, descripcion
    db.flush()
    return aj


def rango_con_dia_siguiente(desde: date, hasta: date) -> tuple[date, date]:
    """El tipo de día depende también de si mañana es festivo."""
    return desde, hasta + timedelta(days=1)
