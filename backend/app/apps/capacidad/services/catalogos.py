from collections import defaultdict

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.apps.capacidad.models import Novedad, Turno, TurnoFranja
from app.apps.capacidad.models.maestros import DESCANSO, TRABAJO
from app.apps.capacidad.services.excel import a_hora, leer_filas, texto

# Novedades conocidas de SIESA. La inducción y el permiso sindical vienen en el
# catálogo de horarios como turnos, pero la persona no está en el puesto.
NOVEDADES_BASE: dict[str, str] = {
    "VAC": "Vacaciones",
    "PRV": "Programado a vacaciones",
    "LNR": "Licencia no remunerada",
    "LRM": "Licencia remunerada",
    "LIC": "Licencia",
    "LUT": "Licencia de luto",
    "IEG": "Incapacidad por enfermedad general",
    "AT": "Accidente de trabajo",
    "AUS": "Ausencia",
    "IND": "Inducción (día)",
    "IND NOCHE": "Inducción (noche)",
    "PSA": "Permiso sindical turno A",
    "PSB": "Permiso sindical turno B",
}


def sembrar_novedades(db: Session) -> None:
    existentes = set(db.scalars(select(Novedad.codigo)))
    for codigo, desc in NOVEDADES_BASE.items():
        if codigo not in existentes:
            db.add(Novedad(codigo=codigo, descripcion=desc, requiere_cubrimiento=True))


def importar_turnos(db: Session, contenido: bytes) -> int:
    """Reemplaza el catálogo con el Excel de horarios de SIESA (GenConsultaMaestroGrid).

    Un mismo código puede venir en varias filas: es un turno partido con varias franjas.
    """
    filas = leer_filas(contenido)
    if not filas:
        raise ValueError("El archivo está vacío")
    enc = [texto(c).lower() for c in filas[0]]
    try:
        i_cod, i_desc, i_tipo = enc.index("código"), enc.index("descripción"), enc.index("tipo jornada")
        i_ent, i_sal = enc.index("entrada"), enc.index("salida")
    except ValueError as e:
        raise ValueError("Encabezados esperados: Código, Descripción, Tipo jornada, Entrada, Salida") from e

    por_codigo: dict[str, list[list[object]]] = defaultdict(list)
    for f in filas[1:]:
        if texto(f[i_cod]):
            por_codigo[texto(f[i_cod])].append(f)

    db.execute(delete(TurnoFranja))
    db.execute(delete(Turno))
    for codigo, grupo in por_codigo.items():
        es_descanso = texto(grupo[0][i_tipo]).lower() == "descanso"
        turno = Turno(codigo=codigo, descripcion=texto(grupo[0][i_desc]), clase=DESCANSO if es_descanso else TRABAJO)
        if not es_descanso:
            turno.franjas = [
                TurnoFranja(orden=n, inicio=a_hora(f[i_ent]), fin=a_hora(f[i_sal])) for n, f in enumerate(grupo)
            ]
        db.add(turno)
    db.commit()
    return len(por_codigo)
