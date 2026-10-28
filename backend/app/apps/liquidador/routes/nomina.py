"""Nómina del liquidador: tarifas (% de recargos y valores de ley por vigencia), salario de cada
empleado, préstamos y embargos, auxilios no prestacionales, vacaciones y la descarga del archivo de nómina de un periodo."""

from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import or_, select

from app.api.deps import DbSession, require
from app.core.auditoria import auditar
from app.core.paginacion import Paginacion, paginar_consulta, paginar_lista
from app.core.rate_limit import limitar
from app.core.respuestas import ApiError, ApiResponse, ok
from app.models import Usuario
from app.apps.liquidador.models import CERRADA, LiqAuxilio, LiqDescuento, LiqEmpleado, LiqPeriodo, LiqResultado, LiqTarifa, LiqVacacionBase
from app.apps.liquidador.schemas import (
    AuxilioIn, AuxilioOut, ConfiguracionEmpleadoIn, DescuentoIn, DescuentoOut, PromedioVacacionesIn, SalarioIn, TarifaIn, TarifaOut,
    VacacionesEmpleadoIn,
)
from app.apps.liquidador.services import calculo, exportar, reportes
from app.apps.liquidador.services.nomina import descontado, porcentajes_de_ley

router = APIRouter(tags=["liquidador: nómina"])
VER = "liquidador.nomina.ver"
GESTIONAR = "liquidador.nomina.gestionar"
AVISO = "Los periodos ya calculados cambian solo si se recalculan; los cerrados no cambian."


# --- Tarifas por vigencia ---

@router.get("/tarifas", response_model=ApiResponse[list[TarifaOut]])
def listar_tarifas(db: DbSession, _=Depends(require(VER))):
    tarifas = db.scalars(select(LiqTarifa).order_by(LiqTarifa.vigente_desde.desc()))
    hoy = date.today()
    vigente = db.scalar(select(LiqTarifa.id).where(LiqTarifa.vigente_desde <= hoy).order_by(LiqTarifa.vigente_desde.desc()).limit(1))
    return ok([TarifaOut.model_validate(t) for t in tarifas], vigente_id=vigente,
              ley={"dominical_80": porcentajes_de_ley(80), "dominical_90": porcentajes_de_ley(90),
                   "dominical_100": porcentajes_de_ley(100)})


def _guardar_tarifa(t: LiqTarifa, data: TarifaIn) -> None:
    t.vigente_desde, t.smlmv, t.auxilio_transporte = data.vigente_desde, data.smlmv, data.auxilio_transporte
    t.horas_mes, t.salud_pct, t.pension_pct = data.horas_mes, data.salud_pct, data.pension_pct
    t.porcentajes = {k: float(v) for k, v in data.porcentajes.items()}
    t.nota = data.nota.strip()


def _fecha_libre(db: DbSession, fecha: date, excepto: int | None = None) -> None:
    otra = db.scalar(select(LiqTarifa).where(LiqTarifa.vigente_desde == fecha))
    if otra and otra.id != excepto:
        raise ApiError(409, f"Ya hay una tarifa vigente desde el {fecha.isoformat()}")


@router.post("/tarifas", response_model=ApiResponse[TarifaOut], status_code=201)
def crear_tarifa(data: TarifaIn, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    _fecha_libre(db, data.vigente_desde)
    t = LiqTarifa()
    _guardar_tarifa(t, data)
    db.add(t)
    db.flush()
    auditar(db, request, "liq_tarifa_creada", actual.id, vigente_desde=data.vigente_desde.isoformat())
    db.commit()
    return ok(TarifaOut.model_validate(t), aviso=AVISO)


@router.put("/tarifas/{tarifa_id}", response_model=ApiResponse[TarifaOut])
def editar_tarifa(tarifa_id: int, data: TarifaIn, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    t = db.get(LiqTarifa, tarifa_id)
    if t is None:
        raise ApiError(404, "Tarifa no encontrada")
    _fecha_libre(db, data.vigente_desde, t.id)
    antes = TarifaOut.model_validate(t).model_dump(mode="json")
    _guardar_tarifa(t, data)
    db.flush()
    auditar(db, request, "liq_tarifa_editada", actual.id, antes=antes, despues=TarifaOut.model_validate(t).model_dump(mode="json"))
    db.commit()
    return ok(TarifaOut.model_validate(t), aviso=AVISO)


@router.delete("/tarifas/{tarifa_id}", response_model=ApiResponse[dict])
def eliminar_tarifa(tarifa_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    t = db.get(LiqTarifa, tarifa_id)
    if t is None:
        raise ApiError(404, "Tarifa no encontrada")
    if len(list(db.scalars(select(LiqTarifa.id)))) == 1:
        raise ApiError(409, "Debe quedar al menos una tarifa")
    auditar(db, request, "liq_tarifa_eliminada", actual.id, vigente_desde=t.vigente_desde.isoformat())
    db.delete(t)
    db.commit()
    return ok({"eliminada": tarifa_id})


# --- Salario de cada empleado ---

@router.put("/empleados/{empleado_id}/salario", response_model=ApiResponse[dict])
def salario(empleado_id: int, data: SalarioIn, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    e = db.get(LiqEmpleado, empleado_id)
    if e is None:
        raise ApiError(404, "Empleado no encontrado")
    antes = float(e.salario) if e.salario is not None else None
    e.salario = data.salario
    auditar(db, request, "liq_salario_editado", actual.id, documento=e.documento, antes=antes,
            despues=float(data.salario) if data.salario is not None else None)
    db.commit()
    return ok({"id": e.id, "salario": float(e.salario) if e.salario is not None else None}, aviso=AVISO)


# --- Préstamos y embargos ---

def _descuento_out(x: LiqDescuento, ya: dict) -> DescuentoOut:
    hecho = float(ya.get(x.id, 0))
    return DescuentoOut(
        id=x.id, empleado_id=x.empleado_id, documento=x.empleado.documento, nombre=x.empleado.nombre, tipo=x.tipo,
        descripcion=x.descripcion, valor_mensual=float(x.valor_mensual) if x.valor_mensual is not None else None,
        porcentaje=float(x.porcentaje) if x.porcentaje is not None else None,
        monto_total=float(x.monto_total) if x.monto_total is not None else None, desde=x.desde, hasta=x.hasta,
        quincena=x.quincena or "ambas",
        activo=x.activo, descontado=hecho, saldo=max(float(x.monto_total) - hecho, 0) if x.monto_total is not None else None)


@router.get("/descuentos", response_model=ApiResponse[list[DescuentoOut]])
def listar_descuentos(db: DbSession, p: Paginacion, q: str = Query("", max_length=100),
                      estado: str = Query("todos", pattern="^(todos|activos|inactivos)$"), _=Depends(require(VER))):
    consulta = select(LiqDescuento).join(LiqEmpleado).order_by(LiqEmpleado.nombre, LiqDescuento.desde)
    if q.strip():
        patron = f"%{q.strip()}%"
        consulta = consulta.where(or_(LiqEmpleado.documento.ilike(patron), LiqEmpleado.nombre.ilike(patron),
                                      LiqDescuento.descripcion.ilike(patron)))
    if estado != "todos":
        consulta = consulta.where(LiqDescuento.activo.is_(estado == "activos"))
    lista, meta = paginar_consulta(db, consulta, p)
    ya = descontado(db, {x.id for x in lista})
    return ok([_descuento_out(x, ya) for x in lista], **meta)


def _empleado_por_documento(db: DbSession, documento: str) -> LiqEmpleado:
    e = db.scalar(select(LiqEmpleado).where(LiqEmpleado.documento == documento.strip()))
    if e is None:
        raise ApiError(404, f"No hay un empleado con documento {documento.strip()}. Los empleados se crean al cargar el Excel de turnos.")
    return e


def _guardar_descuento(x: LiqDescuento, data: DescuentoIn, empleado: LiqEmpleado) -> None:
    x.empleado_id, x.tipo, x.descripcion = empleado.id, data.tipo, data.descripcion.strip()
    x.valor_mensual, x.porcentaje, x.monto_total = data.valor_mensual, data.porcentaje, data.monto_total
    x.desde, x.hasta, x.activo, x.quincena = data.desde, data.hasta, data.activo, data.quincena


@router.post("/descuentos", response_model=ApiResponse[DescuentoOut], status_code=201)
def crear_descuento(data: DescuentoIn, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    e = _empleado_por_documento(db, data.documento)
    x = LiqDescuento()
    _guardar_descuento(x, data, e)
    db.add(x)
    db.flush()
    db.refresh(x)
    auditar(db, request, "liq_descuento_creado", actual.id, documento=e.documento, tipo=x.tipo, descripcion=x.descripcion)
    db.commit()
    return ok(_descuento_out(x, {}), aviso=AVISO)


@router.put("/descuentos/{descuento_id}", response_model=ApiResponse[DescuentoOut])
def editar_descuento(descuento_id: int, data: DescuentoIn, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    x = db.get(LiqDescuento, descuento_id)
    if x is None:
        raise ApiError(404, "Descuento no encontrado")
    e = _empleado_por_documento(db, data.documento)
    _guardar_descuento(x, data, e)
    db.flush()
    db.refresh(x)
    auditar(db, request, "liq_descuento_editado", actual.id, documento=e.documento, tipo=x.tipo, descripcion=x.descripcion, activo=x.activo)
    db.commit()
    return ok(_descuento_out(x, descontado(db, {x.id})), aviso=AVISO)


@router.delete("/descuentos/{descuento_id}", response_model=ApiResponse[dict])
def eliminar_descuento(descuento_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    x = db.get(LiqDescuento, descuento_id)
    if x is None:
        raise ApiError(404, "Descuento no encontrado")
    if descontado(db, {x.id}).get(x.id):
        raise ApiError(409, "Este descuento ya se aplicó en algún periodo: desactívelo en lugar de eliminarlo")
    auditar(db, request, "liq_descuento_eliminado", actual.id, documento=x.empleado.documento, descripcion=x.descripcion)
    db.delete(x)
    db.commit()
    return ok({"eliminado": descuento_id})


# --- Auxilios no prestacionales ---

def pagado_auxilios(db: DbSession, ids: set[int]) -> dict[int, float]:
    """Lo que ya se pagó de cada auxilio en los periodos calculados."""
    total: dict[int, float] = {}
    if not ids:
        return total
    for nomina in db.scalars(select(LiqResultado.nomina)):
        for x in (nomina or {}).get("auxilios", []):
            if x.get("id") in ids:
                total[x["id"]] = total.get(x["id"], 0.0) + float(x.get("valor", 0))
    return total


def _auxilio_out(x: LiqAuxilio, pagado: dict) -> AuxilioOut:
    return AuxilioOut(id=x.id, empleado_id=x.empleado_id, documento=x.empleado.documento, nombre=x.empleado.nombre,
                      descripcion=x.descripcion, valor_mensual=float(x.valor_mensual), desde=x.desde, hasta=x.hasta,
                      quincena=x.quincena or "ambas", activo=x.activo, pagado=float(pagado.get(x.id, 0)))


@router.get("/auxilios", response_model=ApiResponse[list[AuxilioOut]])
def listar_auxilios(db: DbSession, p: Paginacion, q: str = Query("", max_length=100),
                    estado: str = Query("todos", pattern="^(todos|activos|inactivos)$"), _=Depends(require(VER))):
    consulta = select(LiqAuxilio).join(LiqEmpleado).order_by(LiqEmpleado.nombre, LiqAuxilio.desde)
    if q.strip():
        patron = f"%{q.strip()}%"
        consulta = consulta.where(or_(LiqEmpleado.documento.ilike(patron), LiqEmpleado.nombre.ilike(patron),
                                      LiqAuxilio.descripcion.ilike(patron)))
    if estado != "todos":
        consulta = consulta.where(LiqAuxilio.activo.is_(estado == "activos"))
    lista, meta = paginar_consulta(db, consulta, p)
    pagado = pagado_auxilios(db, {x.id for x in lista})
    return ok([_auxilio_out(x, pagado) for x in lista], **meta)


def _guardar_auxilio(x: LiqAuxilio, data: AuxilioIn, empleado: LiqEmpleado) -> None:
    x.empleado_id, x.descripcion, x.valor_mensual = empleado.id, data.descripcion.strip(), data.valor_mensual
    x.desde, x.hasta, x.quincena, x.activo = data.desde, data.hasta, data.quincena, data.activo


@router.post("/auxilios", response_model=ApiResponse[AuxilioOut], status_code=201)
def crear_auxilio(data: AuxilioIn, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    e = _empleado_por_documento(db, data.documento)
    x = LiqAuxilio()
    _guardar_auxilio(x, data, e)
    db.add(x)
    db.flush()
    db.refresh(x)
    auditar(db, request, "liq_auxilio_creado", actual.id, documento=e.documento, descripcion=x.descripcion,
            valor_mensual=float(x.valor_mensual), quincena=x.quincena)
    db.commit()
    return ok(_auxilio_out(x, {}), aviso=AVISO)


@router.put("/auxilios/{auxilio_id}", response_model=ApiResponse[AuxilioOut])
def editar_auxilio(auxilio_id: int, data: AuxilioIn, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    x = db.get(LiqAuxilio, auxilio_id)
    if x is None:
        raise ApiError(404, "Auxilio no encontrado")
    e = _empleado_por_documento(db, data.documento)
    _guardar_auxilio(x, data, e)
    db.flush()
    db.refresh(x)
    auditar(db, request, "liq_auxilio_editado", actual.id, documento=e.documento, descripcion=x.descripcion,
            valor_mensual=float(x.valor_mensual), quincena=x.quincena, activo=x.activo)
    db.commit()
    return ok(_auxilio_out(x, pagado_auxilios(db, {x.id})), aviso=AVISO)


@router.delete("/auxilios/{auxilio_id}", response_model=ApiResponse[dict])
def eliminar_auxilio(auxilio_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    x = db.get(LiqAuxilio, auxilio_id)
    if x is None:
        raise ApiError(404, "Auxilio no encontrado")
    if pagado_auxilios(db, {x.id}).get(x.id):
        raise ApiError(409, "Este auxilio ya se pagó en algún periodo: desactívelo en lugar de eliminarlo")
    auditar(db, request, "liq_auxilio_eliminado", actual.id, documento=x.empleado.documento, descripcion=x.descripcion)
    db.delete(x)
    db.commit()
    return ok({"eliminado": auxilio_id})


# --- Vacaciones ---

@router.put("/empleados/{empleado_id}/vacaciones", response_model=ApiResponse[dict])
def vacaciones_empleado(empleado_id: int, data: VacacionesEmpleadoIn, request: Request, db: DbSession,
                        actual: Usuario = Depends(require(GESTIONAR))):
    """Días hábiles para vacaciones, fecha de ingreso y días hábiles disfrutados antes del liquidador."""
    e = db.get(LiqEmpleado, empleado_id)
    if e is None:
        raise ApiError(404, "Empleado no encontrado")
    e.dias_habiles = "".join(str(d) for d in data.dias_habiles)
    e.fecha_ingreso, e.vacaciones_previas = data.fecha_ingreso, data.vacaciones_previas
    auditar(db, request, "liq_vacaciones_empleado", actual.id, documento=e.documento, dias_habiles=e.dias_habiles,
            fecha_ingreso=data.fecha_ingreso.isoformat() if data.fecha_ingreso else None,
            vacaciones_previas=float(data.vacaciones_previas))
    db.commit()
    return ok({"id": e.id}, aviso=AVISO)


@router.put("/empleados/{empleado_id}/configuracion", response_model=ApiResponse[dict])
def configuracion_empleado(empleado_id: int, data: ConfiguracionEmpleadoIn, request: Request, db: DbSession,
                           actual: Usuario = Depends(require(GESTIONAR))):
    """Clase de riesgo ARL y vacaciones (días hábiles, fecha de ingreso y días disfrutados antes del liquidador)."""
    e = db.get(LiqEmpleado, empleado_id)
    if e is None:
        raise ApiError(404, "Empleado no encontrado")
    antes = e.arl_clase
    e.arl_clase = data.arl_clase
    auditar(db, request, "liq_arl_empleado", actual.id, documento=e.documento, antes=antes, despues=data.arl_clase)
    return vacaciones_empleado(empleado_id, data, request, db, actual)


def _vacacion_out(r: LiqResultado, editable: bool) -> dict:
    return {"empleado_id": r.empleado_id, "documento": r.empleado.documento, "nombre": r.empleado.nombre,
            "editable": editable, **(r.nomina or {}).get("vacaciones", {}),
            "alertas": [x for x in (r.nomina or {}).get("alertas", []) if "vacaciones" in x]}


@router.get("/periodos/{periodo_id}/vacaciones", response_model=ApiResponse[list[dict]])
def vacaciones_periodo(periodo_id: int, db: DbSession, _=Depends(require(VER))):
    """Quienes tienen vacaciones en el periodo, con su base (salario + promedio) y lo liquidado."""
    p = db.get(LiqPeriodo, periodo_id)
    if p is None:
        raise ApiError(404, "Periodo no encontrado")
    filas = [r for r in db.scalars(select(LiqResultado).where(LiqResultado.periodo_id == p.id))
             if (r.nomina or {}).get("vacaciones")]
    return ok([_vacacion_out(r, p.estado != CERRADA) for r in sorted(filas, key=lambda r: r.empleado.nombre)])


@router.put("/periodos/{periodo_id}/vacaciones/{empleado_id}", response_model=ApiResponse[dict])
def promedio_vacaciones(periodo_id: int, empleado_id: int, data: PromedioVacacionesIn, request: Request, db: DbSession,
                        actual: Usuario = Depends(require(GESTIONAR))):
    """Fija el promedio variable de las vacaciones (vacío = el sugerido) y recalcula el periodo."""
    p = db.get(LiqPeriodo, periodo_id)
    if p is None:
        raise ApiError(404, "Periodo no encontrado")
    if p.estado == CERRADA:
        raise ApiError(409, "El periodo está cerrado. Reábralo para hacer cambios.", "PERIODO_CERRADO")
    r = db.scalar(select(LiqResultado).where(LiqResultado.periodo_id == p.id, LiqResultado.empleado_id == empleado_id))
    if r is None or not (r.nomina or {}).get("vacaciones"):
        raise ApiError(404, "El empleado no tiene vacaciones en este periodo")
    x = db.scalar(select(LiqVacacionBase).where(LiqVacacionBase.periodo_id == p.id, LiqVacacionBase.empleado_id == empleado_id))
    if data.promedio is None:
        if x is not None:
            db.delete(x)
    elif x is None:
        db.add(LiqVacacionBase(periodo_id=p.id, empleado_id=empleado_id, promedio=data.promedio))
    else:
        x.promedio = data.promedio
    db.flush()
    calculo.calcular(db, p)
    auditar(db, request, "liq_vacaciones_promedio", actual.id, periodo=p.id, documento=r.empleado.documento,
            promedio=float(data.promedio) if data.promedio is not None else None)
    db.commit()
    r = db.scalar(select(LiqResultado).where(LiqResultado.periodo_id == p.id, LiqResultado.empleado_id == empleado_id))
    return ok(_vacacion_out(r, True), aviso="Se recalculó la nómina del periodo con el nuevo promedio.")


# --- Archivo de nómina del periodo ---

@router.get("/periodos/{periodo_id}/nomina", dependencies=[Depends(limitar("exportar", 10, 60))])
def descargar_nomina(periodo_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(VER))):
    from app.apps.liquidador.routes.periodos import _archivo

    p = db.get(LiqPeriodo, periodo_id)
    if p is None:
        raise ApiError(404, "Periodo no encontrado")
    if any(not r.nomina for r in p.resultados):
        raise ApiError(409, "El periodo se calculó antes de existir la nómina: recalcúlelo para descargarla")
    contenido, tipo, nombre = exportar.nomina(db, p)
    auditar(db, request, "liq_nomina_descargada", actual.id, periodo=p.etiqueta)
    db.commit()
    return _archivo(contenido, tipo, nombre)


# --- Pagado por mes ---

@router.get("/reportes/pagado", response_model=ApiResponse[list[dict]])
def pagado_por_mes(db: DbSession, p: Paginacion, anio: int = Query(ge=2020, le=2100), mes: int = Query(ge=1, le=12),
                   q: str = Query("", max_length=100), _=Depends(require(VER))):
    """Lo pagado en el mes: suma de las nóminas cerradas (1.ª y 2.ª quincena o mensual), por nómina y por persona."""
    datos = reportes.pagado(db, anio, mes)
    personas = datos["personas"]
    if q.strip():
        t = q.strip().lower()
        personas = [x for x in personas if t in x["documento"].lower() or t in x["nombre"].lower()]
    pagina, meta = paginar_lista(personas, p)
    return ok(pagina, **meta, nominas=datos["nominas"], totales=datos["totales"], abiertas=datos["abiertas"])


@router.get("/reportes/pagado/excel", dependencies=[Depends(limitar("exportar", 10, 60))])
def pagado_por_mes_excel(request: Request, db: DbSession, anio: int = Query(ge=2020, le=2100), mes: int = Query(ge=1, le=12),
                         actual: Usuario = Depends(require(VER))):
    from app.apps.liquidador.routes.periodos import _archivo

    contenido, tipo, nombre = reportes.excel(db, anio, mes)
    auditar(db, request, "liq_pagado_mes_descargado", actual.id, mes=f"{anio}-{mes:02d}")
    db.commit()
    return _archivo(contenido, tipo, nombre)
