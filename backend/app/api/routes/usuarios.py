from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select

from app.api.deps import DbSession, require
from app.core.auditoria import auditar
from app.core.rate_limit import limitar
from app.core.respuestas import ApiError, ApiResponse, ok
from app.core.security import hash_password
from app.models import Rol, Usuario
from app.schemas.seguridad import UsuarioCrear, UsuarioEditar, UsuarioOut

router = APIRouter(prefix="/usuarios", tags=["usuarios"])

gestionar = [Depends(limitar("usuarios-escritura", 30, 60))]


def _roles(db: DbSession, ids: list[int]) -> list[Rol]:
    roles = list(db.scalars(select(Rol).where(Rol.id.in_(ids)))) if ids else []
    if len(roles) != len(set(ids)):
        raise ApiError(400, "Algún rol no existe")
    return roles


@router.get("", response_model=ApiResponse[list[UsuarioOut]])
def listar(db: DbSession, _=Depends(require("usuarios.ver"))):
    usuarios = list(db.scalars(select(Usuario).order_by(Usuario.nombre)))
    return ok(usuarios, total=len(usuarios))


@router.post("", response_model=ApiResponse[UsuarioOut], status_code=201, dependencies=gestionar)
def crear(data: UsuarioCrear, request: Request, db: DbSession, actual: Usuario = Depends(require("usuarios.gestionar"))):
    username = data.username.strip().lower()
    if db.scalar(select(Usuario).where(func.lower(Usuario.username) == username)):
        raise ApiError(409, "El usuario ya existe")
    user = Usuario(
        username=username,
        nombre=data.nombre.strip(),
        email=data.email,
        password_hash=hash_password(data.password),
        roles=_roles(db, data.roles),
    )
    db.add(user)
    db.flush()
    auditar(db, request, "usuario_creado", actual.id, usuario=username, roles=[r.nombre for r in user.roles])
    db.commit()
    return ok(user)


@router.patch("/{usuario_id}", response_model=ApiResponse[UsuarioOut], dependencies=gestionar)
def editar(usuario_id: int, data: UsuarioEditar, request: Request, db: DbSession,
           actual: Usuario = Depends(require("usuarios.gestionar"))):
    user = db.get(Usuario, usuario_id)
    if user is None:
        raise ApiError(404, "Usuario no encontrado")
    if user.id == actual.id and data.activo is False:
        raise ApiError(400, "No puede desactivar su propio usuario")

    cambios: list[str] = []
    if data.nombre is not None:
        user.nombre = data.nombre.strip()
        cambios.append("nombre")
    if "email" in data.model_fields_set:
        user.email = data.email
        cambios.append("email")
    if data.password:
        user.password_hash = hash_password(data.password)
        cambios.append("password")
    if data.activo is not None and data.activo != user.activo:
        user.activo = data.activo
        cambios.append("activo")
    if data.roles is not None:
        user.roles = _roles(db, data.roles)
        cambios.append("roles")
    # Contraseña, estado o roles cambiados: se cierran las sesiones abiertas del usuario
    if {"password", "activo", "roles"} & set(cambios) and user.id != actual.id:
        user.sesion_version += 1
    auditar(db, request, "usuario_editado", actual.id, usuario=user.username, campos=cambios)
    db.commit()
    return ok(user)
