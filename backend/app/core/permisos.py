"""Permisos de la plataforma.

Los permisos del núcleo están aquí; cada app aporta los suyos (con su prefijo) en su manifest.
Los roles y su asignación a usuarios son dinámicos y se administran desde la aplicación.
"""

PERMISOS_NUCLEO: dict[str, tuple[str, str]] = {
    # código: (módulo, descripción)
    "usuarios.ver": ("Administración", "Ver usuarios"),
    "usuarios.gestionar": ("Administración", "Crear, editar, desactivar usuarios y restablecer su acceso"),
    "roles.ver": ("Administración", "Ver roles y permisos"),
    "roles.gestionar": ("Administración", "Crear y editar roles y sus permisos"),
    "auditoria.ver": ("Administración", "Consultar la bitácora de auditoría"),
}


def todos_los_permisos() -> dict[str, tuple[str, str]]:
    from app.apps import APPS

    permisos = dict(PERMISOS_NUCLEO)
    for app in APPS:
        permisos.update({c: (f"{app.nombre} · {m}", d) for c, (m, d) in app.permisos.items()})
    return permisos


def roles_base() -> dict[str, tuple[str, list[str]]]:
    from app.apps import APPS

    roles: dict[str, tuple[str, list[str]]] = {"Administrador": ("Acceso total a la plataforma", list(todos_los_permisos()))}
    for app in APPS:
        roles.update(app.roles_base)
    return roles
