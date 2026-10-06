"""Empresas del holding: cada una con sus datos en su propio esquema y sus desarrollos habilitados."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select

from app.api.deps import DbSession, require
from app.apps import APPS
from app.core.auditoria import auditar
from app.core.empresas import esquema_de, preparar_esquema
from app.core.respuestas import ApiError, ApiResponse, ok
from app.models import Empresa, EmpresaApp, Usuario, UsuarioEmpresaApp
from app.schemas.seguridad import EmpresaCrear, EmpresaEditar, EmpresaOut

router = APIRouter(prefix="/empresas", tags=["empresas"])
CODIGOS_APPS = {a.codigo for a in APPS}


def _validar_apps(apps: list[str]) -> list[str]:
    malas = sorted(set(apps) - CODIGOS_APPS)
    if malas:
        raise ApiError(400, f"Desarrollos desconocidos: {', '.join(malas)}")
    return sorted(set(apps))


def _out(db: DbSession, e: Empresa) -> EmpresaOut:
    usuarios = db.scalar(select(func.count(func.distinct(UsuarioEmpresaApp.usuario_id))).where(UsuarioEmpresaApp.empresa_id == e.id)) or 0
    return EmpresaOut.model_validate(e).model_copy(update={"usuarios": usuarios})


@router.get("", response_model=ApiResponse[list[EmpresaOut]])
def listar(db: DbSession, _=Depends(require("usuarios.ver"))):
    """Empresas con sus desarrollos habilitados (también para asignar accesos a los usuarios)."""
    apps = [{"codigo": a.codigo, "nombre": a.nombre} for a in APPS]
    return ok([_out(db, e) for e in db.scalars(select(Empresa).order_by(Empresa.nombre))], apps=apps)


@router.post("", response_model=ApiResponse[EmpresaOut], status_code=201)
def crear(data: EmpresaCrear, request: Request, db: DbSession, actual: Usuario = Depends(require("empresas.gestionar"))):
    if db.scalar(select(Empresa).where(Empresa.codigo == data.codigo)):
        raise ApiError(409, f"Ya existe una empresa con el código {data.codigo}")
    apps = _validar_apps(data.apps)
    e = Empresa(codigo=data.codigo, nombre=data.nombre.strip(), esquema=esquema_de(data.codigo), apps=[EmpresaApp(app=a) for a in apps])
    db.add(e)
    db.flush()
    # Quien la crea entra a sus desarrollos para poder configurarlos
    for a in apps:
        db.add(UsuarioEmpresaApp(usuario_id=actual.id, empresa_id=e.id, app=a))
    auditar(db, request, "empresa_creada", actual.id, codigo=e.codigo, nombre=e.nombre, apps=apps)
    db.commit()
    preparar_esquema(db, e)  # su propio esquema con todas las tablas, vacías salvo la configuración inicial
    return ok(_out(db, e))


@router.patch("/{empresa_id}", response_model=ApiResponse[EmpresaOut])
def editar(empresa_id: int, data: EmpresaEditar, request: Request, db: DbSession, actual: Usuario = Depends(require("empresas.gestionar"))):
    e = db.get(Empresa, empresa_id)
    if e is None:
        raise ApiError(404, "Empresa no encontrada")
    cambios: dict = {}
    if data.nombre is not None and data.nombre.strip() != e.nombre:
        cambios["nombre"] = [e.nombre, data.nombre.strip()]
        e.nombre = data.nombre.strip()
    if data.activa is not None and data.activa != e.activa:
        cambios["activa"] = data.activa
        e.activa = data.activa
    if data.apps is not None:
        apps = _validar_apps(data.apps)
        if apps != e.codigos_apps:
            cambios["apps"] = [e.codigos_apps, apps]
            e.apps = [x for x in e.apps if x.app in apps] + [EmpresaApp(app=a) for a in apps if a not in e.codigos_apps]
    auditar(db, request, "empresa_editada", actual.id, codigo=e.codigo, cambios=cambios)
    db.commit()
    db.refresh(e)
    return ok(_out(db, e))
