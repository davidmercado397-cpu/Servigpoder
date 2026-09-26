"""Modelos del núcleo de la plataforma (acceso, usuarios, roles, auditoría).

Los modelos de cada desarrollo viven en app/apps/<app>/models.
"""

from app.models.seguridad import Auditoria, Permiso, Rol, Usuario, rol_permiso, usuario_rol

__all__ = ["Auditoria", "Permiso", "Rol", "Usuario", "rol_permiso", "usuario_rol"]
