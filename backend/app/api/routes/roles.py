from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from app.api.deps import DbSession, require
from app.core.auditoria import auditar
from app.core.rate_limit import limitar
from app.core.respuestas import ApiError, ApiResponse, ok
from app.models import Permiso, Rol, Usuario
from app.schemas.seguridad import PermisoOut, RolIn, RolOut

router = APIRouter(tags=["roles"])

gestionar = [Depends(limitar("roles-escritura", 30, 60))]


def rol_out(rol: Rol) -> RolOut:
    return RolOut(id=rol.id, nombre=rol.nombre, descripcion=rol.descripcion, permisos=sorted(p.codigo for p in rol.permisos))


def _aplicar(db: DbSession, rol: Rol, data: RolIn) -> None:
    permisos = list(db.scalars(select(Permiso).where(Permiso.codigo.in_(data.permisos))))
    if len(permisos) != len(set(data.permisos)):
        raise ApiError(400, "Algún permiso no existe")
    rol.nombre = data.nombre.strip()
    rol.descripcion = data.descripcion.strip()
    rol.permisos = permisos


def _nombre_libre(db: DbSession, nombre: str, excluir_id: int | None = None) -> None:
    q = select(Rol).where(Rol.nombre == nombre.strip())
    if excluir_id:
        q = q.where(Rol.id != excluir_id)
    if db.scalar(q):
        raise ApiError(409, "Ya existe un rol con ese nombre")


@router.get("/permisos", response_model=ApiResponse[list[PermisoOut]])
def listar_permisos(db: DbSession, _=Depends(require("roles.ver"))):
    return ok(list(db.scalars(select(Permiso).order_by(Permiso.modulo, Permiso.codigo))))


@router.get("/roles", response_model=ApiResponse[list[RolOut]])
def listar_roles(db: DbSession, _=Depends(require("roles.ver"))):
    return ok([rol_out(r) for r in db.scalars(select(Rol).order_by(Rol.nombre))])


@router.post("/roles", response_model=ApiResponse[RolOut], status_code=201, dependencies=gestionar)
def crear_rol(data: RolIn, request: Request, db: DbSession, actual: Usuario = Depends(require("roles.gestionar"))):
    _nombre_libre(db, data.nombre)
    rol = Rol()
    _aplicar(db, rol, data)
    db.add(rol)
    auditar(db, request, "rol_creado", actual.id, rol=rol.nombre, permisos=data.permisos)
    db.commit()
    return ok(rol_out(rol))


@router.put("/roles/{rol_id}", response_model=ApiResponse[RolOut], dependencies=gestionar)
def editar_rol(rol_id: int, data: RolIn, request: Request, db: DbSession, actual: Usuario = Depends(require("roles.gestionar"))):
    rol = db.get(Rol, rol_id)
    if rol is None:
        raise ApiError(404, "Rol no encontrado")
    if rol.nombre == "Administrador" and data.nombre.strip() != "Administrador":
        raise ApiError(400, "El rol Administrador no se puede renombrar")
    _nombre_libre(db, data.nombre, rol_id)
    _aplicar(db, rol, data)
    if rol.nombre == "Administrador":
        # El administrador conserva siempre todos los permisos
        rol.permisos = list(db.scalars(select(Permiso)))
    auditar(db, request, "rol_editado", actual.id, rol=rol.nombre, permisos=sorted(p.codigo for p in rol.permisos))
    db.commit()
    return ok(rol_out(rol))


@router.delete("/roles/{rol_id}", response_model=ApiResponse[None], dependencies=gestionar)
def eliminar_rol(rol_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require("roles.gestionar"))):
    rol = db.get(Rol, rol_id)
    if rol is None:
        raise ApiError(404, "Rol no encontrado")
    if rol.nombre == "Administrador":
        raise ApiError(400, "El rol Administrador no se puede eliminar")
    auditar(db, request, "rol_eliminado", actual.id, rol=rol.nombre)
    db.delete(rol)
    db.commit()
    return ok()
