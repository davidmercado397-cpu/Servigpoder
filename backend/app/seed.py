"""Sincroniza permisos, crea roles base y el administrador inicial.

Es idempotente: se ejecuta en cada arranque del contenedor.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.apps import APPS
from app.core.permisos import roles_base, todos_los_permisos
from app.core.security import hash_password
from app.models import Permiso, Rol, Usuario


def seed(db: Session) -> None:
    existentes = {p.codigo: p for p in db.scalars(select(Permiso))}
    for codigo, (modulo, descripcion) in todos_los_permisos().items():
        p = existentes.get(codigo)
        if p is None:
            db.add(Permiso(codigo=codigo, modulo=modulo, descripcion=descripcion))
        else:
            p.modulo, p.descripcion = modulo, descripcion
    db.flush()

    permisos = {p.codigo: p for p in db.scalars(select(Permiso))}
    for nombre, (descripcion, codigos) in roles_base().items():
        rol = db.scalar(select(Rol).where(Rol.nombre == nombre))
        if rol is None:
            db.add(Rol(nombre=nombre, descripcion=descripcion, permisos=[permisos[c] for c in codigos]))
        elif nombre == "Administrador":
            # El administrador siempre conserva todos los permisos, incluidos los nuevos.
            rol.permisos = list(permisos.values())
    db.flush()

    # Carga inicial de cada app (catálogos, parámetros…)
    for app in APPS:
        if app.seed:
            app.seed(db)

    if db.scalar(select(Usuario).limit(1)) is None:
        s = get_settings()
        admin_rol = db.scalar(select(Rol).where(Rol.nombre == "Administrador"))
        db.add(
            Usuario(
                username=s.admin_username.strip().lower(),
                nombre=s.admin_nombre,
                password_hash=hash_password(s.admin_password),
                roles=[admin_rol],
            )
        )
    db.commit()


if __name__ == "__main__":
    with SessionLocal() as session:
        seed(session)
    print("Seed completado")
