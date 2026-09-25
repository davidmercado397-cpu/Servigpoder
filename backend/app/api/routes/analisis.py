from collections import Counter, defaultdict
from datetime import datetime, timezone
from io import BytesIO

import xlsxwriter
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import DbSession, require
from app.core.auditoria import auditar
from app.core.rate_limit import limitar
from app.core.respuestas import ApiError, ApiResponse, ok
from app.models import (
    Analisis, AnalisisDia, AnalisisPuesto, MatrizPeriodo, MatrizPuesto, ProgramacionCarga, ProgramacionDia,
    ProgramacionFila, Puesto, Ubicacion, Usuario,
)
from app.models.maestros import BOLSA, TRABAJO
from app.schemas.analisis import (
    AnalisisIn, AnalisisOut, DetallePuesto, DiaAnalisisOut, MesDisponible, PersonaPuesto, PuestoAnalisisOut,
)
from app.schemas.f1 import FranjaOut
from app.services import cobertura
from app.services.matriz import festivos

router = APIRouter(prefix="/analisis", tags=["análisis"])

ESTADOS = {"ok", "hueco", "exceso", "mixto"}
ORDENES = {
    "descubiertas": AnalisisPuesto.horas_descubiertas.desc(),
    "exceso": AnalisisPuesto.horas_exceso.desc(),
    "puesto": Puesto.codigo.asc(),
}


def _analisis(db: DbSession, analisis_id: int) -> Analisis:
    a = db.get(Analisis, analisis_id)
    if a is None:
        raise ApiError(404, "Análisis no encontrado")
    return a


def _utc(t: datetime) -> datetime:
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _out(db: DbSession, a: Analisis) -> AnalisisOut:
    out = AnalisisOut.model_validate(a)
    periodo = db.get(MatrizPeriodo, a.periodo_id)
    carga = db.get(ProgramacionCarga, a.carga_id)
    ultima = cobertura.ultima_carga(db, carga.anio, carga.mes)
    if ultima and ultima.id != carga.id:
        out.desactualizado, out.motivo_desactualizado = True, "Hay una carga de programación más reciente"
    elif periodo and periodo.actualizado_en and _utc(periodo.actualizado_en) > _utc(a.generado_en):
        out.desactualizado, out.motivo_desactualizado = True, "La matriz comercial cambió después del análisis"
    return out


@router.get("/meses", response_model=ApiResponse[list[MesDisponible]])
def meses(db: DbSession, _=Depends(require("analisis.ver"))):
    """Meses con programación cargada (última carga de cada mes) y su análisis, si existe."""
    cargas = db.scalars(select(ProgramacionCarga).order_by(ProgramacionCarga.id.desc()))
    periodos = {(p.anio, p.mes) for p in db.scalars(select(MatrizPeriodo))}
    vistos: set[tuple[int, int]] = set()
    lista = []
    for c in cargas:
        if (c.anio, c.mes) in vistos:
            continue
        vistos.add((c.anio, c.mes))
        a_id = db.scalar(select(Analisis.id).where(Analisis.carga_id == c.id))
        lista.append(MesDisponible(anio=c.anio, mes=c.mes, carga_id=c.id, desde=c.desde, hasta=c.hasta,
                                   analisis_id=a_id, tiene_matriz=(c.anio, c.mes) in periodos))
    return ok(sorted(lista, key=lambda m: (m.anio, m.mes), reverse=True))


@router.post("", response_model=ApiResponse[AnalisisOut], status_code=201,
             dependencies=[Depends(limitar("analisis", 6, 60))])
def calcular(data: AnalisisIn, request: Request, db: DbSession, actual: Usuario = Depends(require("analisis.ver"))):
    if data.carga_id:
        carga = db.get(ProgramacionCarga, data.carga_id)
    elif data.anio and data.mes:
        carga = cobertura.ultima_carga(db, data.anio, data.mes)
    else:
        raise ApiError(400, "Indique la carga o el mes a analizar")
    if carga is None:
        raise ApiError(404, "No hay programación cargada para ese mes")
    try:
        a = cobertura.analizar(db, carga, actual.id)
    except cobertura.ErrorAnalisis as e:
        raise ApiError(409, str(e)) from e
    auditar(db, request, "analisis_calculado", actual.id, carga_id=carga.id, analisis_id=a.id)
    db.commit()
    return ok(_out(db, a))


@router.get("/{analisis_id}", response_model=ApiResponse[AnalisisOut])
def obtener(analisis_id: int, db: DbSession, _=Depends(require("analisis.ver"))):
    return ok(_out(db, _analisis(db, analisis_id)))


@router.get("/{analisis_id}/puestos", response_model=ApiResponse[list[PuestoAnalisisOut]])
def puestos(analisis_id: int, db: DbSession, estado: str = Query("", max_length=20), ciudad: str = Query("", max_length=80),
            q: str = Query("", max_length=100), orden: str = Query("descubiertas", max_length=20),
            limite: int = Query(1000, ge=1, le=5000), _=Depends(require("analisis.ver"))):
    _analisis(db, analisis_id)
    consulta = (select(AnalisisPuesto).join(AnalisisPuesto.puesto).join(Puesto.ubicacion)
                .where(AnalisisPuesto.analisis_id == analisis_id))
    if estado:
        if estado == "fijos":
            # Puestos cuyos titulares no coinciden con los hombres presupuestados
            consulta = consulta.where((AnalisisPuesto.fijos > AnalisisPuesto.hombres + 0.5) | (AnalisisPuesto.fijos < AnalisisPuesto.hombres - 0.5))
        elif estado in ESTADOS:
            consulta = consulta.where(AnalisisPuesto.estado == estado)
        elif estado == "con_hallazgo":
            consulta = consulta.where(AnalisisPuesto.estado != "ok")
        elif estado == "sin_programacion":
            consulta = consulta.where(AnalisisPuesto.personas == 0, AnalisisPuesto.horas_requeridas > 0)
    if ciudad:
        consulta = consulta.where(Ubicacion.ciudad.ilike(ciudad))
    if q.strip():
        patron = f"%{q.strip()}%"
        consulta = consulta.where(Puesto.codigo.ilike(patron) | Puesto.descripcion.ilike(patron) | Ubicacion.nombre.ilike(patron))
    consulta = consulta.order_by(ORDENES.get(orden, ORDENES["descubiertas"]), Puesto.codigo).limit(limite)
    lista = list(db.scalars(consulta).unique())
    return ok(lista, total=len(lista))


@router.get("/{analisis_id}/puestos/{puesto_id}", response_model=ApiResponse[DetallePuesto])
def detalle_puesto(analisis_id: int, puesto_id: int, db: DbSession, _=Depends(require("analisis.ver"))):
    a = _analisis(db, analisis_id)
    ap = db.scalar(select(AnalisisPuesto).where(AnalisisPuesto.analisis_id == a.id, AnalisisPuesto.puesto_id == puesto_id))
    if ap is None:
        raise ApiError(404, "El puesto no está en este análisis")
    mp = db.scalar(select(MatrizPuesto).where(MatrizPuesto.periodo_id == a.periodo_id, MatrizPuesto.puesto_id == puesto_id))
    carga = db.get(ProgramacionCarga, a.carga_id)

    filas = list(db.scalars(select(ProgramacionFila).where(ProgramacionFila.carga_id == carga.id, ProgramacionFila.puesto_id == puesto_id)))
    cedulas = {f.cedula for f in filas}

    # Puesto titular de cada persona (donde más trabaja en el mes)
    trabajos = db.execute(
        select(ProgramacionFila.cedula, Puesto.codigo, Puesto.tipo)
        .join(ProgramacionDia, ProgramacionDia.fila_id == ProgramacionFila.id)
        .join(Puesto, Puesto.id == ProgramacionFila.puesto_id)
        .where(ProgramacionFila.carga_id == carga.id, ProgramacionFila.cedula.in_(cedulas), ProgramacionDia.clase == TRABAJO)
    ).all()
    conteo: dict[str, Counter] = defaultdict(Counter)
    for cedula, codigo, tipo in trabajos:
        if tipo != BOLSA:
            conteo[cedula][codigo] += 1
    titular = {c: cnt.most_common(1)[0][0] for c, cnt in conteo.items()}

    personas: dict[str, PersonaPuesto] = {}
    for f in filas:
        p = personas.setdefault(f.cedula, PersonaPuesto(
            cedula=f.cedula, nombre=f.nombre, titular=titular.get(f.cedula) == ap.puesto.codigo,
            puesto_titular=titular.get(f.cedula), dias={}, clases={}))
        for d in f.dias:
            p.dias[d.fecha.isoformat()] = d.codigo
            p.clases[d.fecha.isoformat()] = d.clase
    orden = sorted(personas.values(), key=lambda p: (not p.titular, p.nombre))

    dias = db.scalars(select(AnalisisDia).where(AnalisisDia.analisis_puesto_id == ap.id).order_by(AnalisisDia.fecha))
    return ok(DetallePuesto(
        resumen=PuestoAnalisisOut.model_validate(ap),
        franjas=[FranjaOut.model_validate(f) for f in mp.franjas] if mp else [],
        incluye_festivos=mp.incluye_festivos if mp else None,
        festivos={d.isoformat(): n for d, n in festivos(carga.anio, carga.mes).items()},
        dias=[DiaAnalisisOut.model_validate(d) for d in dias],
        personas=orden,
    ))


@router.get("/{analisis_id}/exportar", dependencies=[Depends(limitar("exportar", 10, 60))])
def exportar(analisis_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require("analisis.ver"))):
    a = _analisis(db, analisis_id)
    r = a.resumen
    buf = BytesIO()
    libro = xlsxwriter.Workbook(buf, {"in_memory": True})
    negrita = libro.add_format({"bold": True, "bg_color": "#D9EAFF"})

    hoja = libro.add_worksheet("Resumen")
    filas_resumen = [
        ("Periodo", f"{r['desde']} a {r['hasta']}"), ("Cobertura (%)", r.get("cobertura_pct")),
        ("Horas vendidas", r.get("requeridas", 0)), ("Horas programadas", r.get("programadas", 0)),
        ("Horas descubiertas", r.get("descubiertas", 0)), ("Horas en exceso", r.get("exceso", 0)),
        ("Puestos analizados", r.get("puestos", 0)), ("Puestos con hueco", r.get("puestos_hueco", 0)),
        ("Puestos con exceso", r.get("puestos_exceso", 0)), ("Puestos con hueco y exceso", r.get("puestos_mixto", 0)),
        ("Puestos sin matriz", r.get("puestos_sin_matriz", 0)),
        ("Puestos vendidos sin programación", r.get("puestos_sin_programacion", 0)), ("Hombres presupuestados", r.get("hombres", 0)),
        ("Titulares programados", r.get("fijos", 0)), ("Filas sin puesto (por aclarar)", r.get("filas_sin_puesto", 0)),
    ]
    for i, (k, v) in enumerate(filas_resumen):
        hoja.write(i, 0, k, negrita)
        hoja.write(i, 1, v)
    hoja.set_column(0, 0, 32)

    hoja = libro.add_worksheet("Puestos")
    enc = ["PODER", "Ubicación", "Ciudad", "Puesto", "Descripción", "Estado", "Hombres", "Titulares", "Personas",
           "Horas vendidas", "Horas programadas", "Horas descubiertas", "Horas exceso", "Días con hueco", "Días con exceso"]
    hoja.write_row(0, 0, enc, negrita)
    aps = list(db.scalars(select(AnalisisPuesto).where(AnalisisPuesto.analisis_id == a.id)
                          .order_by(AnalisisPuesto.horas_descubiertas.desc())).unique())
    for i, ap in enumerate(aps, start=1):
        p = ap.puesto
        hoja.write_row(i, 0, [p.ubicacion.codigo, p.ubicacion.nombre, p.ubicacion.ciudad or "", p.codigo, p.descripcion,
                              ap.estado, float(ap.hombres), ap.fijos, ap.personas, float(ap.horas_requeridas),
                              float(ap.horas_programadas), float(ap.horas_descubiertas), float(ap.horas_exceso),
                              ap.dias_hueco, ap.dias_exceso])
    hoja.autofilter(0, 0, len(aps), len(enc) - 1)
    hoja.freeze_panes(1, 0)

    hoja = libro.add_worksheet("Hallazgos por día")
    hoja.write_row(0, 0, ["Puesto", "Ubicación", "Fecha", "Estado", "Horas descubiertas", "Horas exceso", "Detalle"], negrita)
    fila = 1
    por_id = {ap.id: ap for ap in aps}
    for d in db.scalars(select(AnalisisDia).where(AnalisisDia.analisis_puesto_id.in_(por_id), AnalisisDia.estado.in_(["hueco", "exceso", "mixto"]))
                        .order_by(AnalisisDia.analisis_puesto_id, AnalisisDia.fecha)):
        ap = por_id[d.analisis_puesto_id]
        detalle = "; ".join(f"{t['tipo']} {t['inicio']}-{t['fin']} ({t['personas']} pers.)" for t in d.detalle)
        hoja.write_row(fila, 0, [ap.puesto.codigo, ap.puesto.ubicacion.nombre, d.fecha.isoformat(), d.estado,
                                 float(d.horas_descubiertas), float(d.horas_exceso), detalle])
        fila += 1
    hoja.autofilter(0, 0, max(fila - 1, 1), 6)
    hoja.freeze_panes(1, 0)
    libro.close()

    auditar(db, request, "analisis_exportado", actual.id, analisis_id=a.id)
    db.commit()
    nombre = f"cobertura_{r['anio']}-{r['mes']:02d}_analisis{a.id}.xlsx"
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="{nombre}"'})
