"""Empresas: cada una con sus datos en su propio esquema de PostgreSQL.

- Las tablas del núcleo (usuarios, roles, empresas, auditoría) están en `public` y son compartidas.
- Las tablas de los desarrollos (BaseEmpresa) se declaran en el esquema simbólico `empresa`; en cada
  petición a un desarrollo se traduce al esquema de la empresa elegida (`schema_translate_map`).
  Sin empresa elegida, una consulta a una tabla de un desarrollo falla: nunca cae en otra empresa.
- La empresa elegida viaja en una cookie y se valida en cada petición contra los accesos del usuario.
"""

import re
from collections import defaultdict
from collections.abc import Callable

from fastapi import Depends, Request, Response
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import BaseEmpresa, traduccion
from app.core.respuestas import ApiError
from app.models import Empresa, Usuario

COOKIE_EMPRESA = "empresa"
PATRON_CODIGO = re.compile(r"^[a-z][a-z0-9]{1,19}$")

# Empresas con las que arranca la plataforma: los datos que existían eran de Servigpoder, salvo los del
# Liquidador de horas, que son de SERA (migración 0014).
EMPRESAS_INICIALES = (
    ("servigpoder", "Servigpoder", ("capacidad", "nomina", "reporte")),
    ("sera", "SERA", ("liquidador",)),
)


def esquema_de(codigo: str) -> str:
    if not PATRON_CODIGO.match(codigo):
        raise ValueError("Código de empresa inválido")
    return f"emp_{codigo}"


def accesos(user: Usuario) -> dict[str, set[str]]:
    """Desarrollos a los que el usuario entra en cada empresa: lo marcado en su usuario, si la empresa está
    activa, tiene el desarrollo habilitado y los roles del usuario dan algún permiso en él."""
    from app.apps import APPS

    visibles = {a.codigo for a in APPS if a.visible_para(user.permisos)}
    out: dict[str, set[str]] = defaultdict(set)
    for x in user.accesos:
        e = x.empresa
        if e.activa and x.app in visibles and x.app in e.codigos_apps:
            out[e.codigo].add(x.app)
    return dict(out)


def empresas_del_usuario(db: Session, user: Usuario) -> list[tuple[Empresa, list[str]]]:
    mios = accesos(user)
    empresas = db.scalars(select(Empresa).where(Empresa.codigo.in_(list(mios))).order_by(Empresa.nombre)) if mios else []
    return [(e, sorted(mios[e.codigo])) for e in empresas]


def empresa_elegida(request: Request, db: Session, user: Usuario) -> Empresa | None:
    """La de la cookie si el usuario tiene acceso a ella; si no, la primera de sus empresas."""
    lista = empresas_del_usuario(db, user)
    codigo = request.cookies.get(COOKIE_EMPRESA)
    return next((e for e, _ in lista if e.codigo == codigo), lista[0][0] if lista else None)


def fijar_cookie(response: Response, codigo: str) -> None:
    response.set_cookie(COOKIE_EMPRESA, codigo, max_age=365 * 24 * 3600, httponly=True,
                        secure=get_settings().cookie_secure, samesite="strict", path="/")


def usar_empresa(db: Session, request: Request, empresa: Empresa) -> None:
    """Desde aquí, las tablas de los desarrollos de esta sesión son las del esquema de la empresa."""
    db.commit()  # cierra la transacción de la autenticación (solo lecturas del núcleo)
    db.bind = db.get_bind().execution_options(**traduccion(empresa.esquema))
    request.state.empresa = empresa.codigo


def acceso_app(app_codigo: str) -> Callable:
    """Dependencia de las rutas de un desarrollo: valida el acceso a la empresa y apunta la sesión a ella."""
    from app.api.deps import CurrentUser, DbSession

    def dependencia(request: Request, db: DbSession, user: CurrentUser) -> Empresa:
        mios = accesos(user)
        con_app = sorted(c for c, apps in mios.items() if app_codigo in apps)
        elegida = request.cookies.get(COOKIE_EMPRESA)
        if elegida and elegida in mios:
            if app_codigo not in mios[elegida]:
                raise ApiError(403, "Este desarrollo no está disponible para usted en la empresa seleccionada", "SIN_ACCESO_EMPRESA")
            codigo = elegida
        elif len(con_app) == 1:
            codigo = con_app[0]
        elif not con_app:
            raise ApiError(403, "No tiene acceso a este desarrollo en ninguna empresa", "SIN_ACCESO_EMPRESA")
        else:
            raise ApiError(409, "Seleccione la empresa con la que va a trabajar", "EMPRESA_REQUERIDA")
        empresa = db.scalar(select(Empresa).where(Empresa.codigo == codigo))
        usar_empresa(db, request, empresa)
        return empresa

    return dependencia


def cargar_modelos() -> None:
    """Registra en BaseEmpresa las tablas de todos los desarrollos (el seed corre sin importar las rutas)."""
    import importlib
    import importlib.util

    from app.apps import APPS

    for app in APPS:
        modulo = f"app.apps.{app.codigo}.models"
        if importlib.util.find_spec(modulo):
            importlib.import_module(modulo)


def preparar_esquema(db: Session, empresa: Empresa) -> None:
    """Crea el esquema de la empresa con las tablas de todos los desarrollos (las que falten) y sus datos
    iniciales (turnos, parámetros, catálogos). Es idempotente: se ejecuta en cada arranque."""
    from app.apps import APPS

    cargar_modelos()
    esquema = esquema_de(empresa.codigo)
    con = db.connection()
    if con.dialect.name == "sqlite":  # pruebas: un esquema es una base adjunta en memoria
        if esquema not in {fila[1] for fila in con.exec_driver_sql("PRAGMA database_list")}:
            con.exec_driver_sql(f"ATTACH DATABASE ':memory:' AS {esquema}")
    else:
        con.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{esquema}"'))
    BaseEmpresa.metadata.create_all(con.execution_options(**traduccion(esquema)))
    db.commit()
    with Session(bind=db.get_bind().execution_options(**traduccion(esquema)), autoflush=False, expire_on_commit=False) as s:
        for app in APPS:
            if app.seed:
                app.seed(s)
        s.commit()


def esquemas(con) -> list[str]:
    """Esquemas de todas las empresas: para aplicar en cada uno las migraciones de tablas de un desarrollo."""
    return [fila[0] for fila in con.execute(text("select esquema from empresa order by id"))]


def dependencias_app(app_codigo: str) -> list:
    return [Depends(acceso_app(app_codigo))]
