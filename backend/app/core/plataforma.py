"""Contrato de un desarrollo (app) dentro de la plataforma.

Cada app vive en `app/apps/<codigo>/` y publica un `APP = App(...)` en su `manifest.py`.
El núcleo se encarga del acceso, los usuarios, los roles y la auditoría; la app aporta sus
permisos (siempre con el prefijo `<codigo>.`), sus roles base, sus rutas y su carga inicial.
Un usuario ve una app en el portal si tiene al menos un permiso de esa app.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from fastapi import APIRouter
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class App:
    codigo: str  # identificador y prefijo de rutas y permisos: /api/<codigo>, /<codigo>
    nombre: str
    descripcion: str
    icono: str  # nombre de ícono de lucide (p. ej. "shield-check")
    color: str  # color de acento de la tarjeta en el portal
    permisos: dict[str, tuple[str, str]]  # código: (módulo, descripción)
    roles_base: dict[str, tuple[str, list[str]]] = field(default_factory=dict)
    router: Callable[[], APIRouter] | None = None
    seed: Callable[[Session], None] | None = None

    def __post_init__(self) -> None:
        malos = [p for p in self.permisos if not p.startswith(f"{self.codigo}.")]
        if malos:
            raise ValueError(f"Los permisos de la app '{self.codigo}' deben empezar por '{self.codigo}.': {malos}")

    def visible_para(self, permisos: set[str]) -> bool:
        return any(p.startswith(f"{self.codigo}.") for p in permisos)
