from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import DbSession, require
from app.models import Permiso, Rol
from app.schemas.seguridad import PermisoOut, RolIn, RolOut

router = APIRouter(tags=["roles"])


def rol_out(rol: Rol) -> RolOut:
    return RolOut(
        id=rol.id,
        nombre=rol.nombre,
        descripcion=rol.descripcion,
        permisos=sorted(p.codigo for p in rol.permisos),
    )


def _aplicar(db: DbSession, rol: Rol, data: RolIn) -> None:
    permisos = list(db.scalars(select(Permiso).where(Permiso.codigo.in_(data.permisos))))
    if len(permisos) != len(set(data.permisos)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Algún permiso no existe")
    rol.nombre = data.nombre.strip()
    rol.descripcion = data.descripcion.strip()
    rol.permisos = permisos


@router.get("/permisos", response_model=list[PermisoOut], dependencies=[Depends(require("roles.ver"))])
def listar_permisos(db: DbSession) -> list[Permiso]:
    return list(db.scalars(select(Permiso).order_by(Permiso.modulo, Permiso.codigo)))


@router.get("/roles", response_model=list[RolOut], dependencies=[Depends(require("roles.ver"))])
def listar_roles(db: DbSession) -> list[RolOut]:
    return [rol_out(r) for r in db.scalars(select(Rol).order_by(Rol.nombre))]


@router.post(
    "/roles",
    response_model=RolOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require("roles.gestionar"))],
)
def crear_rol(data: RolIn, db: DbSession) -> RolOut:
    if db.scalar(select(Rol).where(Rol.nombre == data.nombre.strip())):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un rol con ese nombre")
    rol = Rol()
    _aplicar(db, rol, data)
    db.add(rol)
    db.commit()
    return rol_out(rol)


@router.put("/roles/{rol_id}", response_model=RolOut, dependencies=[Depends(require("roles.gestionar"))])
def editar_rol(rol_id: int, data: RolIn, db: DbSession) -> RolOut:
    rol = db.get(Rol, rol_id)
    if rol is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rol no encontrado")
    otro = db.scalar(select(Rol).where(Rol.nombre == data.nombre.strip(), Rol.id != rol_id))
    if otro:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un rol con ese nombre")
    _aplicar(db, rol, data)
    db.commit()
    return rol_out(rol)


@router.delete("/roles/{rol_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require("roles.gestionar"))])
def eliminar_rol(rol_id: int, db: DbSession) -> None:
    rol = db.get(Rol, rol_id)
    if rol is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rol no encontrado")
    if rol.nombre == "Administrador":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El rol Administrador no se puede eliminar")
    db.delete(rol)
    db.commit()
