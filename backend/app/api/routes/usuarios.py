from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, require
from app.core.security import hash_password
from app.models import Rol, Usuario
from app.schemas.seguridad import UsuarioCrear, UsuarioEditar, UsuarioOut

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


def _roles(db: DbSession, ids: list[int]) -> list[Rol]:
    roles = list(db.scalars(select(Rol).where(Rol.id.in_(ids)))) if ids else []
    if len(roles) != len(set(ids)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Algún rol no existe")
    return roles


@router.get("", response_model=list[UsuarioOut], dependencies=[Depends(require("usuarios.ver"))])
def listar(db: DbSession) -> list[Usuario]:
    return list(db.scalars(select(Usuario).order_by(Usuario.nombre)))


@router.post(
    "",
    response_model=UsuarioOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require("usuarios.gestionar"))],
)
def crear(data: UsuarioCrear, db: DbSession) -> Usuario:
    username = data.username.strip().lower()
    if db.scalar(select(Usuario).where(Usuario.username == username)):
        raise HTTPException(status.HTTP_409_CONFLICT, "El usuario ya existe")
    user = Usuario(
        username=username,
        nombre=data.nombre.strip(),
        email=data.email,
        password_hash=hash_password(data.password),
        roles=_roles(db, data.roles),
    )
    db.add(user)
    db.commit()
    return user


@router.patch("/{usuario_id}", response_model=UsuarioOut, dependencies=[Depends(require("usuarios.gestionar"))])
def editar(usuario_id: int, data: UsuarioEditar, db: DbSession, actual: CurrentUser) -> Usuario:
    user = db.get(Usuario, usuario_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    if user.id == actual.id and data.activo is False:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No puede desactivar su propio usuario")
    if data.nombre is not None:
        user.nombre = data.nombre.strip()
    if data.email is not None:
        user.email = data.email or None
    if data.password:
        user.password_hash = hash_password(data.password)
    if data.activo is not None:
        user.activo = data.activo
    if data.roles is not None:
        user.roles = _roles(db, data.roles)
    db.commit()
    return user
