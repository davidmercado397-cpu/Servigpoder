"""Catálogo de permisos del sistema.

Los permisos son fijos (los define el código); los roles y su asignación a
usuarios son dinámicos y se administran desde la aplicación.
"""

PERMISOS: dict[str, tuple[str, str]] = {
    # código: (módulo, descripción)
    "usuarios.ver": ("Administración", "Ver usuarios"),
    "usuarios.gestionar": ("Administración", "Crear, editar y desactivar usuarios"),
    "roles.ver": ("Administración", "Ver roles y permisos"),
    "roles.gestionar": ("Administración", "Crear y editar roles y sus permisos"),
    "maestros.ver": ("Maestros", "Ver ubicaciones, puestos, catálogos y equivalencias"),
    "maestros.gestionar": ("Maestros", "Editar ubicaciones, puestos, catálogos y equivalencias"),
    "matriz.ver": ("Matriz comercial", "Ver la matriz comercial"),
    "matriz.gestionar": ("Matriz comercial", "Editar, proyectar y aprobar la matriz comercial"),
    "programacion.cargar": ("Programación", "Cargar el Excel de programación de SIESA"),
    "analisis.ver": ("Análisis", "Ver tablero, cobertura, hallazgos y reportes"),
    "cubrimientos.aprobar": ("Nómina", "Aprobar o rechazar cubrimientos y turnos adicionales"),
}

ROLES_BASE: dict[str, tuple[str, list[str]]] = {
    "Administrador": ("Acceso total al sistema", list(PERMISOS)),
    "Programador": (
        "Carga la programación, mantiene la matriz y analiza la cobertura",
        [
            "maestros.ver",
            "maestros.gestionar",
            "matriz.ver",
            "matriz.gestionar",
            "programacion.cargar",
            "analisis.ver",
        ],
    ),
    "Nómina": (
        "Revisa y aprueba cubrimientos y turnos adicionales",
        ["maestros.ver", "matriz.ver", "analisis.ver", "cubrimientos.aprobar"],
    ),
}
