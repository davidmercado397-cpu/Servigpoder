from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select

from app.api.deps import DbSession, require
from app.core.auditoria import auditar
from app.core.rate_limit import limitar
from app.core.paginacion import Paginacion, paginar_consulta, paginar_lista
from app.core.respuestas import ApiError, ApiResponse, ok
from app.core.security import hash_password
from app.models import Empresa, Rol, Usuario, UsuarioEmpresaApp
from app.schemas.seguridad import UsuarioCrear, UsuarioEditar, UsuarioOut

router = APIRouter(prefix="/usuarios", tags=["usuarios"])

gestionar = [Depends(limitar("usuarios-escritura", 30, 60))]


def _roles(db: DbSession, ids: list[int]) -> list[Rol]:
    roles = list(db.scalars(select(Rol).where(Rol.id.in_(ids)))) if ids else []
    if len(roles) != len(set(ids)):
        raise ApiError(400, "Algún rol no existe")
    return roles


def _accesos(db: DbSession, datos: dict[str, list[str]]) -> list[UsuarioEmpresaApp]:
    """{"sera": ["liquidador"], …} → filas de acceso; solo empresas existentes y desarrollos habilitados en ellas."""
    empresas = {e.codigo: e for e in db.scalars(select(Empresa).where(Empresa.codigo.in_(list(datos))))} if datos else {}
    filas = []
    for codigo, apps in datos.items():
        e = empresas.get(codigo)
        if e is None:
            raise ApiError(400, f"La empresa {codigo} no existe")
        no_habilitadas = sorted(set(apps) - set(e.codigos_apps))
        if no_habilitadas:
            raise ApiError(400, f"{e.nombre} no tiene habilitado: {', '.join(no_habilitadas)}")
        filas += [UsuarioEmpresaApp(empresa_id=e.id, app=a, empresa=e) for a in sorted(set(apps))]
    return filas


def _resumen_accesos(user: Usuario) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for x in user.accesos:
        out.setdefault(x.empresa.codigo, []).append(x.app)
    return {k: sorted(v) for k, v in sorted(out.items())}


@router.get("", response_model=ApiResponse[list[UsuarioOut]])
def listar(db: DbSession, p: Paginacion, q: str = Query("", max_length=100), _=Depends(require("usuarios.ver"))):
    consulta = select(Usuario).order_by(Usuario.nombre)
    if q.strip():
        patron = f"%{q.strip()}%"
        consulta = consulta.where(Usuario.username.ilike(patron) | Usuario.nombre.ilike(patron))
    usuarios, meta = paginar_consulta(db, consulta, p)
    return ok(usuarios, **meta)


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
        accesos=_accesos(db, data.accesos),
        debe_cambiar_password=True,  # contraseña temporal: la cambia en su primer ingreso
    )
    db.add(user)
    db.flush()
    auditar(db, request, "usuario_creado", actual.id, usuario=username, roles=[r.nombre for r in user.roles],
            accesos=_resumen_accesos(user))
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
        user.debe_cambiar_password = user.id != actual.id  # restablecida por un administrador: es temporal
        cambios.append("password")
    if data.activo is not None and data.activo != user.activo:
        user.activo = data.activo
        cambios.append("activo")
    if data.roles is not None:
        user.roles = _roles(db, data.roles)
        cambios.append("roles")
    detalle: dict = {}
    if data.accesos is not None:
        antes = _resumen_accesos(user)
        nuevos = _accesos(db, data.accesos)
        clave = {(x.empresa_id, x.app) for x in nuevos}
        user.accesos = [x for x in user.accesos if (x.empresa_id, x.app) in clave] +             [x for x in nuevos if (x.empresa_id, x.app) not in {(y.empresa_id, y.app) for y in user.accesos}]
        db.flush()
        if _resumen_accesos(user) != antes:
            cambios.append("accesos")
            detalle = {"accesos_antes": antes, "accesos_despues": _resumen_accesos(user)}
    # Contraseña, estado o roles cambiados: se cierran las sesiones abiertas del usuario
    if {"password", "activo", "roles"} & set(cambios) and user.id != actual.id:
        user.sesion_version += 1
    auditar(db, request, "usuario_editado", actual.id, usuario=user.username, campos=cambios, **detalle)
    db.commit()
    return ok(user)


@router.post("/{usuario_id}/restablecer-mfa", response_model=ApiResponse[UsuarioOut], dependencies=gestionar)
def restablecer_mfa(usuario_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require("usuarios.gestionar"))):
    """Para quien perdió el teléfono y sus códigos: en su próximo ingreso configurará la MFA de nuevo."""
    user = db.get(Usuario, usuario_id)
    if user is None:
        raise ApiError(404, "Usuario no encontrado")
    user.mfa_activo, user.mfa_secreto, user.mfa_ultimo_paso, user.mfa_recuperacion = False, None, None, []
    user.sesion_version += 1  # cierra sus sesiones abiertas
    auditar(db, request, "mfa_restablecida", actual.id, usuario=user.username)
    db.commit()
    return ok(user)
