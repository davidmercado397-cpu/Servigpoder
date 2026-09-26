"""Turnos del liquidador y su matriz de horas (generada, nunca digitada)."""

from datetime import time
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.apps.liquidador.dominio.matriz import build_shift_matrix
from app.apps.liquidador.models import LiqParametros, LiqTurno

DATOS_INICIALES = Path(__file__).resolve().parent.parent / "datos" / "turnos_iniciales.txt"
HORA_NOCTURNA_POR_DEFECTO = 19


def parametros(db: Session) -> LiqParametros:
    p = db.get(LiqParametros, 1)
    if p is None:
        p = LiqParametros(id=1, hora_inicio_nocturna=HORA_NOCTURNA_POR_DEFECTO)
        db.add(p)
        db.flush()
    return p


def aplicar_matriz(turno: LiqTurno, hora_nocturna: int) -> None:
    turno.matriz = build_shift_matrix(turno.horas_ordinarias, turno.horas_extras, turno.hora_inicio, hora_nocturna)
    flag_modified(turno, "matriz")


def guardar(db: Session, turno: LiqTurno, *, codigo: str, nombre: str, hora_inicio: time, hora_fin: time,
            horas_ordinarias: Decimal, horas_extras: Decimal, remunerado: bool, incapacidad: bool) -> LiqTurno:
    """Crea o actualiza un turno. La incapacidad nunca es remunerada ni genera horas."""
    if incapacidad:
        remunerado, horas_ordinarias, horas_extras = False, Decimal("0"), Decimal("0")
    turno.codigo = codigo.strip().upper()
    turno.nombre = nombre.strip()
    turno.hora_inicio, turno.hora_fin = hora_inicio, hora_fin
    turno.horas_ordinarias, turno.horas_extras = horas_ordinarias, horas_extras
    turno.remunerado, turno.incapacidad = remunerado, incapacidad
    aplicar_matriz(turno, parametros(db).hora_inicio_nocturna)
    if turno.id is None:
        db.add(turno)
    db.flush()
    return turno


def regenerar_todos(db: Session, hora_nocturna: int) -> int:
    """Recalcula la matriz de todos los turnos cuando cambia la hora nocturna."""
    turnos = list(db.scalars(select(LiqTurno)))
    for t in turnos:
        aplicar_matriz(t, hora_nocturna)
    db.flush()
    return len(turnos)


def por_codigo(db: Session) -> dict[str, LiqTurno]:
    return {t.codigo.upper(): t for t in db.scalars(select(LiqTurno))}


def sembrar(db: Session) -> None:
    """Parámetros y, solo si no hay ningún turno, la configuración de turnos de la app original."""
    parametros(db)
    if db.scalar(select(LiqTurno.id).limit(1)) is not None:
        return
    lineas = DATOS_INICIALES.read_text(encoding="utf-8").splitlines()[1:]
    for linea in lineas:
        codigo, nombre, inicio, fin, ordinarias, extras, remunerado, incapacidad = linea.split("|")
        guardar(db, LiqTurno(), codigo=codigo, nombre=nombre, hora_inicio=time.fromisoformat(inicio),
                hora_fin=time.fromisoformat(fin), horas_ordinarias=Decimal(ordinarias), horas_extras=Decimal(extras),
                remunerado=remunerado == "1", incapacidad=incapacidad == "1")
    db.flush()
