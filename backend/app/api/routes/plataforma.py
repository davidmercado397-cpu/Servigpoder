from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, require
from app.apps import APPS
from app.core.auditoria import auditar
from app.core.empresas import accesos, empresa_elegida, fijar_cookie
from app.core.paginacion import Paginacion, paginar_consulta, paginar_lista
from app.core.respuestas import ApiError, ApiResponse, ok
from app.schemas.seguridad import ElegirEmpresa
from app.models import Auditoria, Usuario

router = APIRouter(prefix="/plataforma", tags=["plataforma"])


class AppOut(BaseModel):
    codigo: str
    nombre: str
    descripcion: str
    icono: str
    color: str
    ruta: str


@router.get("/apps", response_model=ApiResponse[list[AppOut]])
def mis_apps(request: Request, db: DbSession, user: CurrentUser):
    """Desarrollos a los que el usuario entra en la empresa elegida."""
    empresa = empresa_elegida(request, db, user)
    mias = accesos(user).get(empresa.codigo, set()) if empresa else set()
    return ok([AppOut(codigo=a.codigo, nombre=a.nombre, descripcion=a.descripcion, icono=a.icono, color=a.color,
                      ruta=f"/{a.codigo}") for a in APPS if a.codigo in mias], empresa=empresa.codigo if empresa else None)


@router.post("/empresa", response_model=ApiResponse[dict])
def elegir_empresa(data: ElegirEmpresa, request: Request, response: Response, db: DbSession, user: CurrentUser):
    """Cambia la empresa con la que se trabaja (solo una a la que el usuario tenga acceso)."""
    if data.codigo not in accesos(user):
        raise ApiError(403, "No tiene acceso a esa empresa", "SIN_ACCESO_EMPRESA")
    fijar_cookie(response, data.codigo)
    request.state.empresa = data.codigo
    auditar(db, request, "empresa_elegida", user.id)
    db.commit()
    return ok({"empresa": data.codigo, "apps": sorted(accesos(user)[data.codigo])})


class AuditoriaOut(BaseModel):
    id: int
    fecha: datetime
    usuario: str | None
    accion: str
    detalle: dict
    ip: str
    request_id: str
    empresa: str | None = None


@router.get("/auditoria", response_model=ApiResponse[list[AuditoriaOut]])
def auditoria(db: DbSession, accion: str = Query("", max_length=60), usuario: str = Query("", max_length=60),
              desde: date | None = None, hasta: date | None = None, p: Paginacion = None,
              _=Depends(require("auditoria.ver"))):
    """Bitácora de seguridad y cambios, la más reciente primero."""
    q = select(Auditoria, Usuario.username).outerjoin(Usuario, Usuario.id == Auditoria.usuario_id).order_by(Auditoria.id.desc())
    if accion:
        q = q.where(Auditoria.accion.ilike(f"%{accion}%"))
    if usuario:
        q = q.where(Usuario.username.ilike(f"%{usuario}%"))
    if desde:
        q = q.where(Auditoria.fecha >= datetime.combine(desde, time.min))
    if hasta:
        q = q.where(Auditoria.fecha < datetime.combine(hasta + timedelta(days=1), time.min))
    total = db.scalar(q.with_only_columns(func.count(), maintain_column_froms=True).order_by(None)) or 0
    filas = db.execute(q.limit(p.tamano).offset(p.offset)).all()
    return ok([AuditoriaOut(id=a.id, fecha=a.fecha, usuario=u or a.detalle.get("username"), accion=a.accion,
                            detalle=a.detalle or {}, ip=a.ip, request_id=a.request_id, empresa=a.empresa) for a, u in filas], **p.meta(total))
