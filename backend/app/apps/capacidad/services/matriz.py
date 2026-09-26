import calendar
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal, InvalidOperation

import holidays
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.apps.capacidad.models import MatrizExcepcion, MatrizFranja, MatrizPeriodo, MatrizPuesto, Puesto, Ubicacion
from app.apps.capacidad.models.maestros import BOLSA, OPERATIVO
from app.apps.capacidad.models.matriz import BORRADOR
from app.apps.capacidad.services import jornada
from app.apps.capacidad.services.codigos import canonico, limpiar
from app.apps.capacidad.services.excel import leer_filas, texto

# Columnas de la matriz (A..K)
C_PODER, C_INTERNO, C_NIT, C_NOMBRE, C_HOMBRES, C_SECUENCIA, C_DESC, C_CIUDAD, C_JORNADA = range(9)

BOLSAS = {"5": "DISPONIBLES", "6": "RELEVANTES", "7": "INCAPACITADOS", "8": "VACACIONES"}


class ErrorMatriz(ValueError):
    pass


def _hombres(valor: object) -> tuple[Decimal, str | None]:
    s = texto(valor).replace(" ", "")
    if not s:
        return Decimal(0), None
    # Error de digitación conocido: "15," en lugar de "1,5"
    if re.fullmatch(r"\d\d,", s):
        s = f"{s[0]},{s[1]}"
        aviso = f"Hombres '{texto(valor)}' interpretado como {s}"
    else:
        aviso = None
    try:
        return Decimal(s.replace(",", ".")), aviso
    except InvalidOperation:
        return Decimal(0), f"Hombres '{texto(valor)}' no es un número"


def _codigos_unicos(filas: list[list[object]]) -> list[str]:
    """Código interno de cada fila, resolviendo repetidos: 86, 86 → 86, 86-1 (99, 99, 99 → 99, 99-1, 99-2)."""
    usados: set[str] = {canonico(f[C_INTERNO]) for f in filas}
    vistos: set[str] = set()
    codigos = []
    for f in filas:
        cod = limpiar(f[C_INTERNO])
        can = canonico(cod)
        if can in vistos:
            n = 1
            while canonico(f"{cod}-{n}") in usados:
                n += 1
            cod = f"{cod}-{n}"
            can = canonico(cod)
            usados.add(can)
        vistos.add(can)
        codigos.append(cod)
    return codigos


@dataclass
class ResultadoImportacion:
    periodo_id: int
    ubicaciones: int
    puestos: int
    requieren_revision: int
    excluidos: int
    avisos: list[str]


def importar_matriz(db: Session, contenido: bytes, anio: int, mes: int) -> ResultadoImportacion:
    if db.scalar(select(MatrizPeriodo).where(MatrizPeriodo.anio == anio, MatrizPeriodo.mes == mes)):
        raise ErrorMatriz(f"Ya existe la matriz de {mes:02d}/{anio}")

    filas = leer_filas(contenido)
    inicio = next((i for i, f in enumerate(filas) if any(texto(c).upper() == "HOMBRES" for c in f)), None)
    if inicio is None:
        raise ErrorMatriz("No se encontró la fila de encabezados (columna HOMBRES)")
    datos = [list(f) + [None] * 11 for f in filas[inicio + 1 :] if len(f) > C_INTERNO and texto(f[C_INTERNO])]

    avisos: list[str] = []
    ubicaciones = {u.codigo: u for u in db.scalars(select(Ubicacion))}
    puestos = {canonico(p.codigo): p for p in db.scalars(select(Puesto))}
    periodo = MatrizPeriodo(anio=anio, mes=mes, estado=BORRADOR)
    db.add(periodo)

    for f, codigo in zip(datos, _codigos_unicos(datos)):
        poder = canonico(f[C_PODER]) or canonico(codigo).split("-")[0]
        ubi = ubicaciones.get(poder)
        if ubi is None:
            ubi = Ubicacion(codigo=poder, nombre=texto(f[C_NOMBRE]) or poder)
            db.add(ubi)
            ubicaciones[poder] = ubi
        ubi.nit = texto(f[C_NIT]) or ubi.nit
        ubi.ciudad = texto(f[C_CIUDAD]) or ubi.ciudad

        hombres, aviso = _hombres(f[C_HOMBRES])
        if aviso:
            avisos.append(f"{codigo}: {aviso}")
        es_bolsa = canonico(codigo) in BOLSAS and not hombres
        prop = jornada.proponer(texto(f[C_SECUENCIA]), texto(f[C_JORNADA]), float(hombres))

        puesto = puestos.get(canonico(codigo))
        if puesto is None:
            puesto = Puesto(codigo=codigo, ubicacion=ubi)
            db.add(puesto)
            puestos[canonico(codigo)] = puesto
        puesto.descripcion = texto(f[C_DESC]) or texto(f[C_NOMBRE])
        puesto.tipo = BOLSA if es_bolsa else OPERATIVO
        puesto.excluido = prop.excluido
        puesto.activo = True
        if es_bolsa:
            continue

        mp = MatrizPuesto(
            periodo=periodo,
            puesto=puesto,
            hombres=hombres,
            secuencia=texto(f[C_SECUENCIA]),
            jornada=texto(f[C_JORNADA]),
            incluye_festivos=prop.incluye_festivos,
            requiere_revision=prop.revisar and not prop.excluido,
            nota=prop.nota,
            franjas=[MatrizFranja(dias=fr.dias, inicio=fr.inicio, fin=fr.fin, cantidad=fr.cantidad) for fr in prop.franjas],
        )
        db.add(mp)

    _asegurar_bolsas(db, ubicaciones, puestos)
    db.commit()
    return ResultadoImportacion(
        periodo_id=periodo.id,
        ubicaciones=len({p.puesto.ubicacion_id for p in periodo.puestos}),
        puestos=len(periodo.puestos),
        requieren_revision=sum(p.requiere_revision for p in periodo.puestos),
        excluidos=sum(p.puesto.excluido for p in periodo.puestos),
        avisos=avisos,
    )


def _asegurar_bolsas(db: Session, ubicaciones: dict[str, Ubicacion], puestos: dict[str, Puesto]) -> None:
    """Los puestos bolsa (05, 06, 07, 08) existen aunque no estén en la matriz."""
    for cod, nombre in BOLSAS.items():
        if cod in puestos:
            puestos[cod].tipo = BOLSA
            continue
        ubi = ubicaciones.get(cod) or Ubicacion(codigo=cod, nombre=nombre)
        ubicaciones[cod] = ubi
        p = Puesto(codigo=cod.zfill(2), ubicacion=ubi, descripcion=nombre, tipo=BOLSA)
        db.add(p)
        puestos[cod] = p


def siguiente_mes(anio: int, mes: int) -> tuple[int, int]:
    return (anio + 1, 1) if mes == 12 else (anio, mes + 1)


def proyectar(db: Session, periodo: MatrizPeriodo, copiar_excepciones: bool = False) -> MatrizPeriodo:
    """Copia la matriz al mes siguiente como borrador. Solo se proyectan puestos activos."""
    anio, mes = siguiente_mes(periodo.anio, periodo.mes)
    if db.scalar(select(MatrizPeriodo).where(MatrizPeriodo.anio == anio, MatrizPeriodo.mes == mes)):
        raise ErrorMatriz(f"Ya existe la matriz de {mes:02d}/{anio}")
    nuevo = MatrizPeriodo(anio=anio, mes=mes, estado=BORRADOR, proyectado_desde_id=periodo.id)
    db.add(nuevo)
    for mp in periodo.puestos:
        if not mp.puesto.activo:
            continue
        copia = MatrizPuesto(
            periodo=nuevo,
            puesto_id=mp.puesto_id,
            hombres=mp.hombres,
            secuencia=mp.secuencia,
            jornada=mp.jornada,
            incluye_festivos=mp.incluye_festivos,
            requiere_revision=mp.requiere_revision,
            nota=mp.nota,
            franjas=[MatrizFranja(dias=f.dias, inicio=f.inicio, fin=f.fin, cantidad=f.cantidad) for f in mp.franjas],
        )
        if copiar_excepciones:
            copia.excepciones = [_mover_excepcion(e, anio, mes) for e in mp.excepciones if _dia_existe(e.fecha.day, anio, mes)]
        db.add(copia)
    db.commit()
    return nuevo


def _dia_existe(dia: int, anio: int, mes: int) -> bool:
    return dia <= calendar.monthrange(anio, mes)[1]


def _mover_excepcion(e: MatrizExcepcion, anio: int, mes: int) -> MatrizExcepcion:
    return MatrizExcepcion(
        fecha=date(anio, mes, e.fecha.day),
        sin_servicio=e.sin_servicio,
        inicio=e.inicio,
        fin=e.fin,
        cantidad=e.cantidad,
        observacion=e.observacion,
    )


def festivos(anio: int, mes: int) -> dict[date, str]:
    return {d: n for d, n in holidays.Colombia(years=anio).items() if d.month == mes}


@dataclass
class FranjaDia:
    inicio: time
    fin: time
    cantidad: int


def requerimiento(mp: MatrizPuesto, anio: int, mes: int, fest: dict[date, str] | None = None) -> dict[date, list[FranjaDia]]:
    """Cobertura vendida de cada día del mes para un puesto."""
    fest = festivos(anio, mes) if fest is None else fest
    excepciones: dict[date, list[MatrizExcepcion]] = defaultdict(list)
    for e in mp.excepciones:
        excepciones[e.fecha].append(e)

    dias: dict[date, list[FranjaDia]] = {}
    for d in range(1, calendar.monthrange(anio, mes)[1] + 1):
        fecha = date(anio, mes, d)
        req: list[FranjaDia] = []
        if mp.incluye_festivos or fecha not in fest:
            bit = 1 << fecha.weekday()
            req = [FranjaDia(f.inicio, f.fin, f.cantidad) for f in mp.franjas if f.dias & bit]
        for e in excepciones.get(fecha, []):
            if e.sin_servicio:
                req = []
            elif e.inicio is not None and e.fin is not None:
                req.append(FranjaDia(e.inicio, e.fin, e.cantidad))
        dias[fecha] = req
    return dias


def horas(inicio: time, fin: time) -> float:
    a = inicio.hour + inicio.minute / 60
    b = fin.hour + fin.minute / 60
    return (b - a) % 24 or 24.0
