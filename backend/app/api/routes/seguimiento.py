"""F4: alertas, histórico, comparación de cargas y parámetros."""

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DbSession, require
from app.core.auditoria import auditar
from app.core.rate_limit import limitar
from app.core.respuestas import ApiError, ApiResponse, ok
from app.models import Parametro, ProgramacionCarga, Usuario
from app.services import alertas as svc_alertas
from app.services import historico as svc_historico

router = APIRouter(tags=["seguimiento"])


class ParametroOut(BaseModel):
    clave: str
    valor: str
    descripcion: str


class ParametroIn(BaseModel):
    valor: str = Field(min_length=1, max_length=50, pattern=r"^\d+(\.\d+)?$")


@router.get("/alertas", response_model=ApiResponse[list[dict]])
def alertas(db: DbSession, _=Depends(require("analisis.ver"))):
    lista = svc_alertas.evaluar(db)
    return ok(lista, fecha=svc_alertas.hoy().isoformat(), total=len(lista))


@router.get("/historico", response_model=ApiResponse[list[dict]])
def historico(db: DbSession, _=Depends(require("analisis.ver"))):
    return ok(svc_historico.historico(db))


@router.get("/programacion/comparar", response_model=ApiResponse[dict], dependencies=[Depends(limitar("comparar", 20, 60))])
def comparar(db: DbSession, actual: int | None = Query(None), anterior: int | None = Query(None),
             _=Depends(require("analisis.ver"))):
    """Compara dos cargas. Sin parámetros: la última carga contra la anterior del mismo mes."""
    carga_b = db.get(ProgramacionCarga, actual) if actual else db.scalar(
        select(ProgramacionCarga).order_by(ProgramacionCarga.id.desc()).limit(1))
    if carga_b is None:
        raise ApiError(404, "No hay cargas de programación")
    if anterior:
        carga_a = db.get(ProgramacionCarga, anterior)
    else:
        carga_a = db.scalar(select(ProgramacionCarga).where(
            ProgramacionCarga.anio == carga_b.anio, ProgramacionCarga.mes == carga_b.mes, ProgramacionCarga.id < carga_b.id)
            .order_by(ProgramacionCarga.id.desc()).limit(1))
    if carga_a is None:
        raise ApiError(404, "No hay una carga anterior del mismo mes para comparar")
    if (carga_a.anio, carga_a.mes) != (carga_b.anio, carga_b.mes):
        raise ApiError(400, "Solo se comparan cargas del mismo mes")
    return ok(svc_historico.comparar(db, carga_a, carga_b))


@router.get("/parametros", response_model=ApiResponse[list[ParametroOut]])
def listar_parametros(db: DbSession, _=Depends(require("analisis.ver"))):
    return ok(list(db.scalars(select(Parametro).order_by(Parametro.clave))))


@router.put("/parametros/{clave}", response_model=ApiResponse[ParametroOut])
def guardar_parametro(clave: str, data: ParametroIn, request: Request, db: DbSession,
                      actual: Usuario = Depends(require("parametros.gestionar"))):
    p = db.get(Parametro, clave)
    if p is None:
        raise ApiError(404, "Parámetro no encontrado")
    anterior, p.valor = p.valor, data.valor
    auditar(db, request, "parametro_editado", actual.id, clave=clave, de=anterior, a=data.valor)
    db.commit()
    return ok(p)
