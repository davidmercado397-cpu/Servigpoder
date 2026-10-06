"""Nómina del liquidador: tarifas (% de recargos y valores de ley por vigencia), salario de cada
empleado, préstamos y embargos, y la descarga del archivo de nómina de un periodo."""

from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import or_, select

from app.api.deps import DbSession, require
from app.core.auditoria import auditar
from app.core.paginacion import Paginacion, paginar_consulta
from app.core.rate_limit import limitar
from app.core.respuestas import ApiError, ApiResponse, ok
from app.models import Usuario
from app.apps.liquidador.models import LiqDescuento, LiqEmpleado, LiqPeriodo, LiqTarifa
from app.apps.liquidador.schemas import DescuentoIn, DescuentoOut, SalarioIn, TarifaIn, TarifaOut
from app.apps.liquidador.services import exportar
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
    x.desde, x.hasta, x.activo = data.desde, data.hasta, data.activo


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
