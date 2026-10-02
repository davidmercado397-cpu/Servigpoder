"""Validación de nómina: periodos, carga de archivos, alertas, revisión y configuración."""

from io import BytesIO
from typing import Literal

import xlsxwriter
from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import DbSession, require
from app.core.archivos import leer_xlsx
from app.core.auditoria import auditar
from app.core.paginacion import Paginacion, paginar_consulta
from app.core.rate_limit import limitar
from app.core.respuestas import ApiError, ApiResponse, ok
from app.models import Usuario
from app.apps.nomina.models import (
    ARCHIVOS, ERROR, MENSUAL, JUSTIFICADA, PENDIENTE, NomAlerta, NomArchivo, NomCodigo, NomDecision, NomGrupo,
    NomPeriodo, NomPersona, NomPuestoDecision,
)
from app.apps.nomina.services import motor, servicio

router = APIRouter(prefix="/nomina", tags=["validación de nómina"])
VER, CARGAR, REVISAR, CONFIGURAR = "nomina.ver", "nomina.cargar", "nomina.revisar", "nomina.configurar"
MESES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _periodo(db: Session, periodo_id: int) -> NomPeriodo:
    p = db.get(NomPeriodo, periodo_id)
    if p is None:
        raise ApiError(404, "Periodo no encontrado")
    return p


def _periodo_out(db: Session, p: NomPeriodo, completo: bool = False) -> dict:
    archivos = {a.tipo: {"nombre": a.nombre, "registros": a.registros, "cargado_en": a.cargado_en}
                for a in db.scalars(select(NomArchivo).where(NomArchivo.periodo_id == p.id))}
    resumen = {k: v for k, v in (p.resumen or {}).items() if k != "sin_modalidad_lista"}
    pendientes = db.scalar(select(func.count()).select_from(NomAlerta).outerjoin(NomDecision, _union_decision()).where(
        NomAlerta.periodo_id == p.id, NomAlerta.tipo.not_in(motor.INFORMATIVAS),
        or_(NomDecision.id.is_(None), NomDecision.estado == PENDIENTE))) or 0
    out = {"id": p.id, "anio": p.anio, "mes": p.mes, "nomina": p.nomina, "nombre": _nombre(p), "calculado_en": p.calculado_en,
           "archivos": archivos, "alertas": resumen.get("alertas", 0), "pendientes": pendientes,
           "personas": resumen.get("personas", {}), "revisiones": len(p.historial or []),
           "requeridos": list(servicio.archivos_del_periodo(p))}
    if completo:
        out["resumen"] = resumen
        out["faltan"] = servicio.faltantes(db, p)
        out["tipos"] = {k: {"titulo": t, "severidad": s, "grupo": g} for k, (t, s, g) in motor.TIPOS.items()}
        out["nombres_archivo"] = servicio.NOMBRES_ARCHIVO
        out["historial"] = list(reversed(p.historial or []))
    return out


def _nombre(p: NomPeriodo) -> str:
    mes = f"{MESES[p.mes]} {p.anio}"
    return f"Mensual · {mes}" if p.nomina == MENSUAL else f"Quincenal · 2.ª quincena de {mes}"


def _union_decision():
    return (NomDecision.periodo_id == NomAlerta.periodo_id) & (NomDecision.nomina == NomAlerta.nomina) & \
        (NomDecision.cedula == NomAlerta.cedula) & (NomDecision.tipo == NomAlerta.tipo) & (NomDecision.referencia == NomAlerta.referencia)


# --- Periodos y archivos -----------------------------------------------------------------------------

class PeriodoIn(BaseModel):
    anio: int = Field(ge=2020, le=2100)
    mes: int = Field(ge=1, le=12)
    nomina: Literal["quincenal", "mensual"]


@router.get("/periodos", response_model=ApiResponse[list[dict]])
def listar(db: DbSession, p: Paginacion, _=Depends(require(VER))):
    periodos, meta = paginar_consulta(db, select(NomPeriodo).order_by(NomPeriodo.anio.desc(), NomPeriodo.mes.desc(), NomPeriodo.nomina), p)
    return ok([_periodo_out(db, x) for x in periodos], **meta)


@router.post("/periodos", response_model=ApiResponse[dict], status_code=201)
def crear(data: PeriodoIn, request: Request, db: DbSession, actual: Usuario = Depends(require(CARGAR))):
    if db.scalar(select(NomPeriodo).where(NomPeriodo.anio == data.anio, NomPeriodo.mes == data.mes, NomPeriodo.nomina == data.nomina)):
        raise ApiError(409, f"Ya existe la revisión de la nómina {data.nomina} de {MESES[data.mes]} {data.anio}")
    p = NomPeriodo(anio=data.anio, mes=data.mes, nomina=data.nomina, resumen={}, historial=[])
    db.add(p)
    db.flush()
    auditar(db, request, "nom_periodo_creado", actual.id, periodo=f"{data.mes:02d}/{data.anio}", nomina=data.nomina)
    db.commit()
    return ok(_periodo_out(db, p, completo=True))


@router.get("/periodos/{periodo_id}", response_model=ApiResponse[dict])
def ver(periodo_id: int, db: DbSession, _=Depends(require(VER))):
    return ok(_periodo_out(db, _periodo(db, periodo_id), completo=True))


@router.delete("/periodos/{periodo_id}", response_model=ApiResponse[dict])
def eliminar(periodo_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(CARGAR))):
    p = _periodo(db, periodo_id)
    for modelo in (NomAlerta, NomPersona, NomDecision, NomArchivo):
        db.query(modelo).filter(modelo.periodo_id == p.id).delete()
    auditar(db, request, "nom_periodo_eliminado", actual.id, periodo=f"{p.mes:02d}/{p.anio}")
    db.delete(p)
    db.commit()
    return ok({"eliminado": periodo_id})


@router.post("/periodos/{periodo_id}/archivos/{tipo}", response_model=ApiResponse[dict], dependencies=[Depends(limitar("nom_carga", 30, 60))])
async def cargar_archivo(periodo_id: int, tipo: str, request: Request, db: DbSession, archivo: UploadFile = File(...),
                         actual: Usuario = Depends(require(CARGAR))):
    """Carga un archivo del periodo (reemplaza el anterior del mismo tipo) y recalcula si ya están todos."""
    p = _periodo(db, periodo_id)
    if tipo not in ARCHIVOS:
        raise ApiError(404, "Tipo de archivo desconocido")
    nombre = (archivo.filename or "")[:255]
    contenido = await leer_xlsx(archivo)
    try:
        info = servicio.cargar(db, p, tipo, contenido, nombre, actual.id)
        calculado = None
        if not servicio.faltantes(db, p):
            motivo = "Nueva carga de la nómina" if tipo == p.nomina else f"Archivo actualizado: {servicio.NOMBRES_ARCHIVO[tipo]}"
            calculado = servicio.recalcular(db, p, motivo)
    except servicio.ErrorValidacion as e:
        db.rollback()
        raise ApiError(422, str(e), "ARCHIVO_INVALIDO") from e
    auditar(db, request, "nom_archivo_cargado", actual.id, periodo=f"{p.mes:02d}/{p.anio}", tipo=tipo, archivo=nombre, **info)
    db.commit()
    return ok({"periodo": _periodo_out(db, p, completo=True), **info, "calculado": calculado is not None})


@router.delete("/periodos/{periodo_id}/archivos/{tipo}", response_model=ApiResponse[dict])
def quitar_archivo(periodo_id: int, tipo: str, request: Request, db: DbSession, actual: Usuario = Depends(require(CARGAR))):
    p = _periodo(db, periodo_id)
    db.query(NomArchivo).filter(NomArchivo.periodo_id == p.id, NomArchivo.tipo == tipo).delete()
    auditar(db, request, "nom_archivo_quitado", actual.id, periodo=f"{p.mes:02d}/{p.anio}", tipo=tipo)
    db.commit()
    return ok(_periodo_out(db, p, completo=True))


@router.post("/periodos/{periodo_id}/recalcular", response_model=ApiResponse[dict], dependencies=[Depends(limitar("nom_calculo", 10, 60))])
def recalcular(periodo_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(CARGAR))):
    p = _periodo(db, periodo_id)
    try:
        servicio.recalcular(db, p, "Recálculo manual")
    except servicio.ErrorValidacion as e:
        raise ApiError(422, str(e)) from e
    auditar(db, request, "nom_recalculado", actual.id, periodo=f"{p.mes:02d}/{p.anio}")
    db.commit()
    return ok(_periodo_out(db, p, completo=True))


# --- Alertas -----------------------------------------------------------------------------------------

def _consulta_alertas(periodo_id: int, tipo: str, nomina: str, estado: str, severidad: str, q: str, solo_nuevas: bool = False,
                      excluir_tipo: str = ""):
    consulta = (select(NomAlerta, NomDecision).outerjoin(NomDecision, _union_decision())
                .where(NomAlerta.periodo_id == periodo_id)
                .order_by(case((NomAlerta.severidad == "alta", 0), (NomAlerta.severidad == "media", 1), else_=2), NomAlerta.tipo, NomAlerta.nombre))
    if tipo:
        consulta = consulta.where(NomAlerta.tipo.in_(tipo.split(",")))
    if nomina:
        consulta = consulta.where(NomAlerta.nomina == nomina)
    if severidad:
        consulta = consulta.where(NomAlerta.severidad == severidad)
    if solo_nuevas:
        consulta = consulta.where(NomAlerta.nueva.is_(True))
    if excluir_tipo:
        consulta = consulta.where(NomAlerta.tipo.not_in(excluir_tipo.split(",")))
    if estado == PENDIENTE:
        consulta = consulta.where(or_(NomDecision.id.is_(None), NomDecision.estado == PENDIENTE))
    elif estado:
        consulta = consulta.where(NomDecision.estado == estado)
    if q.strip():
        patron = f"%{q.strip()}%"
        consulta = consulta.where(or_(NomAlerta.cedula.ilike(patron), NomAlerta.nombre.ilike(patron), NomAlerta.mensaje.ilike(patron)))
    return consulta


def _alerta_out(a: NomAlerta, d: NomDecision | None) -> dict:
    return {"id": a.id, "nomina": a.nomina, "cedula": a.cedula, "nombre": a.nombre, "tipo": a.tipo, "titulo": motor.TIPOS[a.tipo][0],
            "grupo": motor.TIPOS[a.tipo][2], "referencia": a.referencia, "severidad": a.severidad, "mensaje": a.mensaje,
            "esperado": float(a.esperado) if a.esperado is not None else None, "pagado": float(a.pagado) if a.pagado is not None else None,
            "nueva": a.nueva, "estado": d.estado if d else PENDIENTE, "comentario": d.comentario if d else "",
            "decidido_en": d.decidido_en if d else None}


@router.get("/periodos/{periodo_id}/alertas", response_model=ApiResponse[list[dict]])
def alertas(periodo_id: int, db: DbSession, p: Paginacion, tipo: str = Query("", max_length=400), nomina: str = "",
            estado: str = "", severidad: str = "", q: str = Query("", max_length=100), solo_nuevas: bool = False,
            excluir_tipo: str = Query("", max_length=400), _=Depends(require(VER))):
    _periodo(db, periodo_id)
    consulta = _consulta_alertas(periodo_id, tipo, nomina, estado, severidad, q, solo_nuevas, excluir_tipo)
    total = db.scalar(select(func.count()).select_from(consulta.order_by(None).subquery())) or 0
    filas = db.execute(consulta.limit(p.tamano).offset(p.offset)).all()
    return ok([_alerta_out(a, d) for a, d in filas], **p.meta(total))


class ItemDecision(BaseModel):
    nomina: str
    cedula: str
    tipo: str
    referencia: str = ""


class DecisionIn(BaseModel):
    items: list[ItemDecision] = Field(min_length=1, max_length=500)
    estado: Literal["pendiente", "revisada", "justificada", "error"]
    comentario: str = Field(default="", max_length=1000)


@router.put("/periodos/{periodo_id}/alertas/decision", response_model=ApiResponse[dict], dependencies=[Depends(limitar("nom_decision", 60, 60))])
def decidir(periodo_id: int, data: DecisionIn, request: Request, db: DbSession, actual: Usuario = Depends(require(REVISAR))):
    _periodo(db, periodo_id)
    if data.estado in (JUSTIFICADA, ERROR) and not data.comentario.strip():
        raise ApiError(422, "Escriba un comentario para justificar o marcar como error")
    for it in data.items:
        d = db.scalar(select(NomDecision).where(NomDecision.periodo_id == periodo_id, NomDecision.nomina == it.nomina,
                                                NomDecision.cedula == it.cedula, NomDecision.tipo == it.tipo, NomDecision.referencia == it.referencia))
        if d is None:
            d = NomDecision(periodo_id=periodo_id, nomina=it.nomina, cedula=it.cedula, tipo=it.tipo, referencia=it.referencia)
            db.add(d)
        d.estado, d.comentario, d.usuario_id = data.estado, data.comentario.strip(), actual.id
    auditar(db, request, "nom_alertas_revisadas", actual.id, periodo_id=periodo_id, estado=data.estado, cantidad=len(data.items))
    db.commit()
    return ok({"actualizadas": len(data.items)})


# --- Personas ----------------------------------------------------------------------------------------

@router.get("/periodos/{periodo_id}/personas", response_model=ApiResponse[list[dict]])
def personas(periodo_id: int, db: DbSession, p: Paginacion, q: str = Query("", max_length=100), nomina: str = "",
             con_alertas: bool = False, _=Depends(require(VER))):
    consulta = select(NomPersona).where(NomPersona.periodo_id == periodo_id).order_by(NomPersona.alertas.desc(), NomPersona.nombre)
    if q.strip():
        patron = f"%{q.strip()}%"
        consulta = consulta.where(or_(NomPersona.cedula.ilike(patron), NomPersona.nombre.ilike(patron)))
    if nomina:
        consulta = consulta.where(NomPersona.nomina == nomina)
    if con_alertas:
        consulta = consulta.where(NomPersona.alertas > 0)
    lista, meta = paginar_consulta(db, consulta, p)
    return ok([{"nomina": x.nomina, "cedula": x.cedula, "nombre": x.nombre, "grupo": x.grupo, "alertas": x.alertas,
                "dias_pagables": x.detalle["conteo"]["pagables"], "dias_salario": x.detalle["dias_salario"],
                "novedad": x.detalle["conteo"]["novedad"], "neto": x.detalle["neto"]} for x in lista], **meta)


@router.get("/periodos/{periodo_id}/personas/{nomina}/{cedula}", response_model=ApiResponse[dict])
def persona(periodo_id: int, nomina: str, cedula: str, db: DbSession, _=Depends(require(VER))):
    x = db.scalar(select(NomPersona).where(NomPersona.periodo_id == periodo_id, NomPersona.nomina == nomina, NomPersona.cedula == cedula))
    if x is None:
        raise ApiError(404, "La persona no está en esa nómina del periodo")
    filas = db.execute(_consulta_alertas(periodo_id, "", nomina, "", "", "").where(NomAlerta.cedula == cedula)).all()
    return ok({**x.detalle, "alertas_lista": [_alerta_out(a, d) for a, d in filas]})


# --- Puestos sin modalidad ---------------------------------------------------------------------------

@router.get("/periodos/{periodo_id}/sin-modalidad", response_model=ApiResponse[list[dict]])
def sin_modalidad(periodo_id: int, db: DbSession, _=Depends(require(VER))):
    p = _periodo(db, periodo_id)
    decisiones = {(d.ubicacion, d.puesto): d for d in db.scalars(select(NomPuestoDecision))}
    res = []
    for x in (p.resumen or {}).get("sin_modalidad_lista", []):
        d = decisiones.get((x["ubicacion"], x["puesto"]))
        res.append({**x, "estado": d.estado if d else PENDIENTE, "comentario": d.comentario if d else ""})
    return ok(res)


class PuestoDecisionIn(BaseModel):
    ubicacion: str = Field(max_length=40)
    puesto: str = Field(max_length=40)
    estado: Literal["aprobado", "error", "pendiente"]
    comentario: str = Field(default="", max_length=1000)


@router.put("/puestos-sin-modalidad", response_model=ApiResponse[dict])
def decidir_puesto(data: PuestoDecisionIn, request: Request, db: DbSession, periodo_id: int | None = None,
                   actual: Usuario = Depends(require(REVISAR))):
    """Aprobado = el puesto no lleva modalidad (vale para todos los meses); error = corregir en SIESA."""
    d = db.scalar(select(NomPuestoDecision).where(NomPuestoDecision.ubicacion == data.ubicacion, NomPuestoDecision.puesto == data.puesto))
    if data.estado == PENDIENTE:
        if d:
            db.delete(d)
    else:
        if data.estado == ERROR and not data.comentario.strip():
            raise ApiError(422, "Escriba qué se debe corregir en SIESA")
        if d is None:
            d = NomPuestoDecision(ubicacion=data.ubicacion, puesto=data.puesto)
            db.add(d)
        d.estado, d.comentario, d.usuario_id = data.estado, data.comentario.strip(), actual.id
    db.flush()
    if periodo_id:  # aprobar cambia lo esperado: se recalcula el periodo que se está viendo
        try:
            servicio.recalcular(db, _periodo(db, periodo_id), f"Puesto {data.puesto}: {data.estado}")
        except servicio.ErrorValidacion:
            pass
    auditar(db, request, "nom_puesto_sin_modalidad", actual.id, ubicacion=data.ubicacion, puesto=data.puesto, estado=data.estado)
    db.commit()
    return ok({"ok": True})


# --- Configuración: códigos, grupos y parámetros -----------------------------------------------------

class CodigoIn(BaseModel):
    descripcion: str = Field(default="", max_length=120)
    descuenta: bool
    vacaciones: bool = False


@router.get("/codigos", response_model=ApiResponse[list[dict]])
def codigos(db: DbSession, p: Paginacion, q: str = Query("", max_length=60), por_revisar: bool = False, _=Depends(require(VER))):
    consulta = select(NomCodigo).order_by(NomCodigo.revisado, NomCodigo.codigo)
    if q.strip():
        consulta = consulta.where(or_(NomCodigo.codigo.ilike(f"%{q.strip()}%"), NomCodigo.descripcion.ilike(f"%{q.strip()}%")))
    if por_revisar:
        consulta = consulta.where(NomCodigo.revisado.is_(False))
    lista, meta = paginar_consulta(db, consulta, p)
    pendientes = db.scalar(select(func.count()).select_from(NomCodigo).where(NomCodigo.revisado.is_(False))) or 0
    return ok([{"codigo": c.codigo, "descripcion": c.descripcion, "descuenta": c.descuenta, "vacaciones": c.vacaciones,
                "revisado": c.revisado} for c in lista], **meta, por_revisar=pendientes)


@router.put("/codigos/{codigo}", response_model=ApiResponse[dict])
def guardar_codigo(codigo: str, data: CodigoIn, request: Request, db: DbSession, actual: Usuario = Depends(require(CONFIGURAR))):
    c = db.get(NomCodigo, codigo)
    if c is None:
        raise ApiError(404, "Código no encontrado")
    antes = {"descuenta": c.descuenta, "vacaciones": c.vacaciones}
    c.descripcion, c.descuenta, c.vacaciones, c.revisado = data.descripcion.strip(), data.descuenta, data.vacaciones, True
    auditar(db, request, "nom_codigo", actual.id, codigo=codigo, antes=antes, despues=data.model_dump())
    db.commit()
    return ok({"codigo": c.codigo, "descripcion": c.descripcion, "descuenta": c.descuenta, "vacaciones": c.vacaciones, "revisado": True})


class GrupoIn(BaseModel):
    tratamiento: Literal["validar", "administrativo", "excluido"]


@router.get("/grupos", response_model=ApiResponse[list[dict]])
def grupos(db: DbSession, _=Depends(require(VER))):
    return ok([{"nombre": g.nombre, "tratamiento": g.tratamiento, "revisado": g.revisado}
               for g in db.scalars(select(NomGrupo).order_by(NomGrupo.revisado, NomGrupo.nombre))])


@router.put("/grupos/{nombre}", response_model=ApiResponse[dict])
def guardar_grupo(nombre: str, data: GrupoIn, request: Request, db: DbSession, actual: Usuario = Depends(require(CONFIGURAR))):
    g = db.get(NomGrupo, nombre)
    if g is None:
        raise ApiError(404, "Grupo no encontrado")
    auditar(db, request, "nom_grupo", actual.id, grupo=nombre, antes=g.tratamiento, despues=data.tratamiento)
    g.tratamiento, g.revisado = data.tratamiento, True
    db.commit()
    return ok({"nombre": g.nombre, "tratamiento": g.tratamiento, "revisado": True})


class ParametrosIn(BaseModel):
    tolerancia: float = Field(ge=0, le=1_000_000)
    smlmv: float = Field(gt=0, le=100_000_000)
    auxilio_transporte: float = Field(ge=0, le=10_000_000)
    horas_dia: float = Field(gt=0, le=24)
    solo_primera_quincena: str = Field(default="", max_length=200, pattern=r"^[\d,\s]*$")
    excluidos_base_embargo: str = Field(default="", max_length=200, pattern=r"^[\d,\s]*$")
    embargos_sin_minimo: str = Field(default="", max_length=200, pattern=r"^[\d,\s]*$")
    equivalencias_cuotas: str = Field(default="", max_length=200, pattern=r"^[\d,=+\s]*$")
    conceptos_ajuste: str = Field(default="", max_length=200, pattern=r"^[\d,\s]*$")


def _parametros_out(p) -> dict:
    return {k: (float(getattr(p, k)) if k in ("tolerancia", "smlmv", "auxilio_transporte", "horas_dia") else getattr(p, k))
            for k in ParametrosIn.model_fields}


@router.get("/parametros", response_model=ApiResponse[dict])
def ver_parametros(db: DbSession, _=Depends(require(VER))):
    p = servicio.parametros(db)
    db.commit()
    return ok(_parametros_out(p))


@router.put("/parametros", response_model=ApiResponse[dict])
def guardar_parametros(data: ParametrosIn, request: Request, db: DbSession, actual: Usuario = Depends(require(CONFIGURAR))):
    p = servicio.parametros(db)
    antes = _parametros_out(p)
    for k, v in data.model_dump().items():
        setattr(p, k, v)
    auditar(db, request, "nom_parametros", actual.id, antes=antes, despues=data.model_dump())
    db.commit()
    return ok(_parametros_out(p))


# --- Informe en Excel --------------------------------------------------------------------------------

@router.get("/periodos/{periodo_id}/informe", dependencies=[Depends(limitar("exportar", 10, 60))])
def informe(periodo_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(VER))):
    p = _periodo(db, periodo_id)
    filas = db.execute(_consulta_alertas(p.id, "", "", "", "", "")).all()
    buf = BytesIO()
    libro = xlsxwriter.Workbook(buf, {"in_memory": True})
    negrita = libro.add_format({"bold": True, "bg_color": "#D9EAFF", "text_wrap": True, "valign": "top"})
    dinero = libro.add_format({"num_format": "#,##0"})

    hoja = libro.add_worksheet("Resumen")
    hoja.write_row(0, 0, ["Alerta", "Grupo", "Severidad", "Quincenal", "Mensual", "Pendientes"], negrita)
    por_tipo: dict[str, list] = {}
    for a, d in filas:
        x = por_tipo.setdefault(a.tipo, [0, 0, 0])
        x[0 if a.nomina == "quincenal" else 1] += 1
        x[2] += (d is None or d.estado == PENDIENTE)
    for i, (t, (q, m, pend)) in enumerate(sorted(por_tipo.items(), key=lambda kv: -sum(kv[1][:2])), start=1):
        titulo, sev, grupo = motor.TIPOS[t]
        hoja.write_row(i, 0, [titulo, grupo, sev, q, m, pend])
    hoja.set_column(0, 0, 55)
    hoja.set_column(1, 5, 14)

    hoja = libro.add_worksheet("Revisiones")
    hoja.write_row(0, 0, ["Revisión", "Fecha", "Motivo", "Archivo de nómina", "Personas", "Alertas", "Corregidas", "Persisten", "Nuevas"], negrita)
    for i, h in enumerate(p.historial or [], start=1):
        hoja.write_row(i, 0, [h["n"], h["fecha"][:16].replace("T", " "), h["motivo"], h["archivo_nomina"], h["personas"], h["alertas"],
                              h["corregidas"], h["persisten"], h["nuevas"]])
    hoja.set_column(1, 3, 28)

    hoja = libro.add_worksheet("Alertas")
    enc = ["Nómina", "Cédula", "Nombre", "Grupo", "Alerta", "Severidad", "Concepto", "Detalle", "Esperado", "Pagado", "Diferencia",
           "Estado", "Comentario", "Nueva en la última carga"]
    hoja.write_row(0, 0, enc, negrita)
    for i, (a, d) in enumerate(filas, start=1):
        esperado = float(a.esperado) if a.esperado is not None else None
        pagado = float(a.pagado) if a.pagado is not None else None
        hoja.write_row(i, 0, [a.nomina, a.cedula, a.nombre, motor.TIPOS[a.tipo][2], motor.TIPOS[a.tipo][0], a.severidad, a.referencia, a.mensaje])
        for col, v in ((8, esperado), (9, pagado), (10, (pagado - esperado) if esperado is not None and pagado is not None else None)):
            if v is not None:
                hoja.write_number(i, col, v, dinero)
        hoja.write_row(i, 11, [d.estado if d else PENDIENTE, d.comentario if d else "", "Sí" if a.nueva else ""])
    hoja.autofilter(0, 0, max(len(filas), 1), len(enc) - 1)
    hoja.freeze_panes(1, 3)
    for col, ancho in enumerate([10, 13, 34, 18, 40, 9, 9, 70, 12, 12, 12, 11, 30]):
        hoja.set_column(col, col, ancho)

    hoja = libro.add_worksheet("Puestos sin modalidad")
    decisiones = {(d.ubicacion, d.puesto): d for d in db.scalars(select(NomPuestoDecision))}
    hoja.write_row(0, 0, ["Ubicación", "Nombre ubicación", "Puesto", "Nombre puesto", "Motivo", "Personas", "Días programados", "Estado", "Comentario"], negrita)
    for i, x in enumerate((p.resumen or {}).get("sin_modalidad_lista", []), start=1):
        d = decisiones.get((x["ubicacion"], x["puesto"]))
        motivo = {"sin_modalidad": "Sin modalidad en puesto ni ubicación", "no_esta_en_maestro": "No está en el maestro de ubicaciones",
                  "modalidad_desconocida": f"Modalidad '{x['modalidad_texto']}' no está en el maestro de modalidades"}[x["motivo"]]
        hoja.write_row(i, 0, [x["ubicacion"], x["ubicacion_nombre"], x["puesto"], x["puesto_nombre"], motivo, x["personas"], x["dias"],
                              d.estado if d else PENDIENTE, d.comentario if d else ""])
    hoja.set_column(0, 8, 18)
    libro.close()

    auditar(db, request, "nom_informe", actual.id, periodo=f"{p.mes:02d}/{p.anio}")
    db.commit()
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="validacion_nomina_{p.nomina}_{p.anio}-{p.mes:02d}.xlsx"'})
