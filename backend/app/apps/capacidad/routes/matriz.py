import calendar
from datetime import datetime, timezone
from io import BytesIO

import xlsxwriter

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import case, func, select

from app.api.deps import DbSession, require
from app.core.archivos import leer_xlsx
from app.core.auditoria import auditar
from app.core.rate_limit import limitar
from app.core.paginacion import Paginacion, paginar_consulta, paginar_lista
from app.core.respuestas import ApiError, ApiResponse, ok
from app.apps.capacidad.models import MatrizExcepcion, MatrizFranja, MatrizPeriodo, MatrizPuesto, Puesto, Ubicacion, Usuario
from app.apps.capacidad.models.matriz import CERRADO
from app.apps.capacidad.schemas.f1 import (
    DiaRequerido, EstadoIn, ExcepcionIn, ExcepcionOut, FranjaHorario, ImportacionOut, MatrizPuestoEditar,
    MatrizPuestoOut, PeriodoOut, ProyectarIn, ResumenPeriodo,
)
from app.apps.capacidad.services import matriz as svc

router = APIRouter(prefix="/matriz", tags=["matriz comercial"])

escritura = [Depends(limitar("matriz-escritura", 60, 60))]


def _periodo(db: DbSession, periodo_id: int) -> MatrizPeriodo:
    p = db.get(MatrizPeriodo, periodo_id)
    if p is None:
        raise ApiError(404, "Periodo no encontrado")
    return p


def _editable(p: MatrizPeriodo) -> None:
    if p.estado == CERRADO:
        raise ApiError(409, f"La matriz de {p.mes:02d}/{p.anio} está cerrada y no se puede modificar")
    # Toda edición marca la matriz como modificada: los análisis previos quedan desactualizados
    p.actualizado_en = datetime.now(timezone.utc)


def _matriz_puesto(db: DbSession, mp_id: int) -> MatrizPuesto:
    mp = db.get(MatrizPuesto, mp_id)
    if mp is None:
        raise ApiError(404, "Puesto de la matriz no encontrado")
    return mp


@router.get("/periodos", response_model=ApiResponse[list[ResumenPeriodo]])
def listar_periodos(db: DbSession, _=Depends(require("capacidad.matriz.ver"))):
    stats = {
        pid: (n, h or 0, r or 0)
        for pid, n, h, r in db.execute(
            select(MatrizPuesto.periodo_id, func.count(), func.sum(MatrizPuesto.hombres),
                   func.sum(case((MatrizPuesto.requiere_revision.is_(True), 1), else_=0)))
            .group_by(MatrizPuesto.periodo_id)
        )
    }
    excluidos = dict(db.execute(
        select(MatrizPuesto.periodo_id, func.count()).join(MatrizPuesto.puesto).where(Puesto.excluido.is_(True))
        .group_by(MatrizPuesto.periodo_id)
    ).all())
    periodos = db.scalars(select(MatrizPeriodo).order_by(MatrizPeriodo.anio.desc(), MatrizPeriodo.mes.desc()))
    return ok([
        ResumenPeriodo(**PeriodoOut.model_validate(p).model_dump(), puestos=stats.get(p.id, (0, 0, 0))[0],
                       hombres=stats.get(p.id, (0, 0, 0))[1], requieren_revision=stats.get(p.id, (0, 0, 0))[2],
                       excluidos=excluidos.get(p.id, 0))
        for p in periodos
    ])


@router.post("/importar", response_model=ApiResponse[ImportacionOut], status_code=201,
             dependencies=[Depends(limitar("importar", 10, 60))])
async def importar(request: Request, db: DbSession, archivo: UploadFile = File(...),
                   anio: int = Form(..., ge=2020, le=2100), mes: int = Form(..., ge=1, le=12),
                   actual: Usuario = Depends(require("capacidad.matriz.gestionar"))):
    contenido = await leer_xlsx(archivo)
    try:
        r = svc.importar_matriz(db, contenido, anio, mes)
    except svc.ErrorMatriz as e:
        raise ApiError(409, str(e)) from e
    auditar(db, request, "matriz_importada", actual.id, archivo=archivo.filename, anio=anio, mes=mes, puestos=r.puestos)
    db.commit()
    return ok(ImportacionOut(**r.__dict__))


@router.get("/periodos/{periodo_id}/puestos", response_model=ApiResponse[list[MatrizPuestoOut]])
def puestos_periodo(periodo_id: int, db: DbSession, p: Paginacion, solo_revision: bool = False,
                    q: str = Query("", max_length=100), _=Depends(require("capacidad.matriz.ver"))):
    _periodo(db, periodo_id)
    consulta = (select(MatrizPuesto).join(MatrizPuesto.puesto).join(Puesto.ubicacion)
                .where(MatrizPuesto.periodo_id == periodo_id).order_by(Ubicacion.codigo, Puesto.codigo))
    if solo_revision:
        consulta = consulta.where(MatrizPuesto.requiere_revision.is_(True))
    if q.strip():
        patron = f"%{q.strip()}%"
        consulta = consulta.where(Puesto.codigo.ilike(patron) | Puesto.descripcion.ilike(patron) | Ubicacion.nombre.ilike(patron))
    lista, meta = paginar_consulta(db, consulta, p)
    return ok(lista, **meta)


@router.patch("/puestos/{mp_id}", response_model=ApiResponse[MatrizPuestoOut], dependencies=escritura)
def editar_puesto(mp_id: int, data: MatrizPuestoEditar, request: Request, db: DbSession,
                  actual: Usuario = Depends(require("capacidad.matriz.gestionar"))):
    mp = _matriz_puesto(db, mp_id)
    _editable(mp.periodo)
    cambios = data.model_dump(exclude_unset=True)
    for campo in ("hombres", "secuencia", "incluye_festivos", "requiere_revision", "nota"):
        if campo in cambios and cambios[campo] is not None:
            setattr(mp, campo, cambios[campo])
    if data.franjas is not None:
        mp.franjas = [MatrizFranja(**f.model_dump()) for f in data.franjas]
    auditar(db, request, "matriz_puesto_editado", actual.id, periodo_id=mp.periodo_id, puesto=mp.puesto.codigo,
            campos=sorted(cambios))
    db.commit()
    db.refresh(mp)
    return ok(mp)


@router.post("/puestos/{mp_id}/excepciones", response_model=ApiResponse[ExcepcionOut], status_code=201, dependencies=escritura)
def agregar_excepcion(mp_id: int, data: ExcepcionIn, request: Request, db: DbSession,
                      actual: Usuario = Depends(require("capacidad.matriz.gestionar"))):
    mp = _matriz_puesto(db, mp_id)
    _editable(mp.periodo)
    if (data.fecha.year, data.fecha.month) != (mp.periodo.anio, mp.periodo.mes):
        raise ApiError(400, "La fecha debe estar dentro del mes de la matriz")
    exc = MatrizExcepcion(matriz_puesto_id=mp.id, **data.model_dump())
    db.add(exc)
    auditar(db, request, "matriz_excepcion_creada", actual.id, puesto=mp.puesto.codigo, fecha=str(data.fecha))
    db.commit()
    return ok(exc)


@router.delete("/excepciones/{exc_id}", response_model=ApiResponse[None], dependencies=escritura)
def eliminar_excepcion(exc_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require("capacidad.matriz.gestionar"))):
    exc = db.get(MatrizExcepcion, exc_id)
    if exc is None:
        raise ApiError(404, "Excepción no encontrada")
    mp = _matriz_puesto(db, exc.matriz_puesto_id)
    _editable(mp.periodo)
    auditar(db, request, "matriz_excepcion_eliminada", actual.id, puesto=mp.puesto.codigo, fecha=str(exc.fecha))
    db.delete(exc)
    db.commit()
    return ok()


@router.post("/periodos/{periodo_id}/proyectar", response_model=ApiResponse[PeriodoOut], status_code=201,
             dependencies=[Depends(limitar("proyectar", 5, 60))])
def proyectar(periodo_id: int, data: ProyectarIn, request: Request, db: DbSession,
              actual: Usuario = Depends(require("capacidad.matriz.gestionar"))):
    origen = _periodo(db, periodo_id)
    try:
        nuevo = svc.proyectar(db, origen, data.copiar_excepciones)
    except svc.ErrorMatriz as e:
        raise ApiError(409, str(e)) from e
    auditar(db, request, "matriz_proyectada", actual.id, desde=f"{origen.mes:02d}/{origen.anio}",
            hacia=f"{nuevo.mes:02d}/{nuevo.anio}")
    db.commit()
    return ok(nuevo)


@router.put("/periodos/{periodo_id}/estado", response_model=ApiResponse[PeriodoOut], dependencies=escritura)
def cambiar_estado(periodo_id: int, data: EstadoIn, request: Request, db: DbSession,
                   actual: Usuario = Depends(require("capacidad.matriz.gestionar"))):
    p = _periodo(db, periodo_id)
    if p.estado == CERRADO:
        raise ApiError(409, "Un periodo cerrado no cambia de estado")
    if data.estado == p.estado:
        raise ApiError(409, f"La matriz ya está en estado {p.estado}")
    anterior, p.estado = p.estado, data.estado
    auditar(db, request, "matriz_estado", actual.id, periodo=f"{p.mes:02d}/{p.anio}", de=anterior, a=data.estado)
    db.commit()
    return ok(p)


DIAS_SEMANA = ["L", "M", "X", "J", "V", "S", "D"]


def _dias_texto(mascara: int) -> str:
    nombres = {127: "L-D", 31: "L-V", 63: "L-S", 96: "S-D"}
    return nombres.get(mascara) or " ".join(d for i, d in enumerate(DIAS_SEMANA) if mascara & (1 << i))


def _franja_texto(dias: int, inicio, fin, cantidad: int) -> str:
    rango = "24 h" if inicio == fin else f"{inicio:%H:%M}-{fin:%H:%M}"
    return f"{_dias_texto(dias)} {rango}" + (f" x{cantidad}" if cantidad > 1 else "")


@router.get("/periodos/{periodo_id}/exportar", dependencies=[Depends(limitar("exportar", 10, 60))])
def exportar(periodo_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require("capacidad.matriz.ver"))):
    """La matriz comercial del mes en Excel: un puesto por fila, sus franjas y las excepciones."""
    p = _periodo(db, periodo_id)
    fest = svc.festivos(p.anio, p.mes)
    mps = list(db.scalars(select(MatrizPuesto).join(MatrizPuesto.puesto).join(Puesto.ubicacion)
                          .where(MatrizPuesto.periodo_id == p.id).order_by(Ubicacion.codigo, Puesto.codigo)).unique())

    buf = BytesIO()
    libro = xlsxwriter.Workbook(buf, {"in_memory": True})
    negrita = libro.add_format({"bold": True, "bg_color": "#D9EAFF", "text_wrap": True, "valign": "top"})
    numero = libro.add_format({"num_format": "#,##0.0"})

    hoja = libro.add_worksheet("Matriz")
    enc = ["PODER", "Ubicación", "Ciudad", "Puesto", "Descripción", "Tipo", "Excluido", "Hombres", "Secuencia",
           "Cobertura vendida", "Incluye festivos", "Horas vendidas en el mes", "Días con servicio", "Excepciones",
           "Por revisar", "Nota", "Jornada original (matriz)"]
    hoja.write_row(0, 0, enc, negrita)
    for i, mp in enumerate(mps, start=1):
        pu = mp.puesto
        dias = svc.requerimiento(mp, p.anio, p.mes, fest)
        horas_mes = sum(svc.horas(f.inicio, f.fin) * f.cantidad for fr in dias.values() for f in fr)
        hoja.write_row(i, 0, [
            pu.ubicacion.codigo, pu.ubicacion.nombre, pu.ubicacion.ciudad or "", pu.codigo, pu.descripcion, pu.tipo,
            "Sí" if pu.excluido else "No", float(mp.hombres), mp.secuencia,
            "; ".join(_franja_texto(f.dias, f.inicio, f.fin, f.cantidad) for f in mp.franjas),
            "Sí" if mp.incluye_festivos else "No", horas_mes, sum(1 for fr in dias.values() if fr), len(mp.excepciones),
            "Sí" if mp.requiere_revision else "No", mp.nota, mp.jornada,
        ])
        hoja.write_number(i, 7, float(mp.hombres), numero)
        hoja.write_number(i, 11, horas_mes, numero)
    hoja.autofilter(0, 0, max(len(mps), 1), len(enc) - 1)
    hoja.freeze_panes(1, 4)
    for col, ancho in enumerate([10, 34, 14, 10, 30, 10, 9, 9, 12, 36, 10, 12, 10, 11, 10, 30, 40]):
        hoja.set_column(col, col, ancho)

    hoja = libro.add_worksheet("Franjas")
    hoja.write_row(0, 0, ["Puesto", "Ubicación", "Días", "Inicio", "Fin", "Personas", "Horas por día"], negrita)
    fila = 1
    for mp in mps:
        for f in mp.franjas:
            hoja.write_row(fila, 0, [mp.puesto.codigo, mp.puesto.ubicacion.nombre, _dias_texto(f.dias), f"{f.inicio:%H:%M}",
                                     f"{f.fin:%H:%M}", f.cantidad, svc.horas(f.inicio, f.fin) * f.cantidad])
            fila += 1
    hoja.autofilter(0, 0, max(fila - 1, 1), 6)
    hoja.freeze_panes(1, 0)
    hoja.set_column(0, 0, 10)
    hoja.set_column(1, 1, 34)

    hoja = libro.add_worksheet("Excepciones")
    hoja.write_row(0, 0, ["Puesto", "Ubicación", "Fecha", "Sin servicio", "Inicio", "Fin", "Personas", "Observación"], negrita)
    fila = 1
    for mp in mps:
        for e in mp.excepciones:
            hoja.write_row(fila, 0, [mp.puesto.codigo, mp.puesto.ubicacion.nombre, e.fecha.isoformat(), "Sí" if e.sin_servicio else "No",
                                     f"{e.inicio:%H:%M}" if e.inicio else "", f"{e.fin:%H:%M}" if e.fin else "", e.cantidad, e.observacion])
            fila += 1
    hoja.set_column(1, 1, 34)
    hoja.set_column(7, 7, 40)

    hoja = libro.add_worksheet("Festivos del mes")
    hoja.write_row(0, 0, ["Fecha", "Festivo"], negrita)
    for i, (d, n) in enumerate(sorted(fest.items()), start=1):
        hoja.write_row(i, 0, [d.isoformat(), n])
    hoja.set_column(1, 1, 40)
    libro.close()

    auditar(db, request, "matriz_exportada", actual.id, periodo=f"{p.mes:02d}/{p.anio}")
    db.commit()
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="matriz_comercial_{p.anio}-{p.mes:02d}_{p.estado}.xlsx"'})


@router.get("/puestos/{mp_id}/requerimiento", response_model=ApiResponse[list[DiaRequerido]])
def requerimiento(mp_id: int, db: DbSession, _=Depends(require("capacidad.matriz.ver"))):
    """Calendario del mes: cobertura vendida por día (aplica festivos y excepciones)."""
    mp = _matriz_puesto(db, mp_id)
    anio, mes = mp.periodo.anio, mp.periodo.mes
    fest = svc.festivos(anio, mes)
    dias = svc.requerimiento(mp, anio, mes, fest)
    return ok([
        DiaRequerido(fecha=d, festivo=fest.get(d), franjas=[FranjaHorario(inicio=f.inicio, fin=f.fin) for f in fr],
                     horas=sum(svc.horas(f.inicio, f.fin) * f.cantidad for f in fr))
        for d, fr in dias.items()
    ], dias_mes=calendar.monthrange(anio, mes)[1])


@router.get("/festivos", response_model=ApiResponse[dict[str, str]])
def festivos(anio: int = Query(..., ge=2020, le=2100), mes: int = Query(..., ge=1, le=12), _=Depends(require("capacidad.matriz.ver"))):
    return ok({d.isoformat(): n for d, n in svc.festivos(anio, mes).items()})
