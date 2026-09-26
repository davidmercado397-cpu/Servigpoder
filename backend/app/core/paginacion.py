"""Paginación estándar de listados.

Parámetros de consulta: `pagina` (desde 1) y `tamano` (50, 100 o 150 filas; 150 es el máximo).
La respuesta lleva en `meta.extra`: total, pagina, tamano y paginas.
"""

from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Query
from sqlalchemy import Select, func
from sqlalchemy.orm import Session

from app.core.respuestas import ApiError

TAMANOS = (50, 100, 150)


@dataclass(frozen=True)
class Pagina:
    pagina: int
    tamano: int

    @property
    def offset(self) -> int:
        return (self.pagina - 1) * self.tamano

    def meta(self, total: int) -> dict[str, int]:
        return {"total": total, "pagina": self.pagina, "tamano": self.tamano,
                "paginas": max(1, -(-total // self.tamano))}


def _paginacion(pagina: int = Query(1, ge=1, le=1_000_000), tamano: int = Query(50)) -> Pagina:
    if tamano not in TAMANOS:
        raise ApiError(422, "El tamaño de página debe ser 50, 100 o 150", "DATOS_INVALIDOS")
    return Pagina(pagina, tamano)


Paginacion = Annotated[Pagina, Depends(_paginacion)]


def paginar_consulta(db: Session, consulta: Select, p: Pagina) -> tuple[list[Any], dict[str, int]]:
    """Ejecuta la consulta solo para la página pedida y cuenta el total (mismos filtros, sin orden)."""
    total = db.scalar(consulta.with_only_columns(func.count(), maintain_column_froms=True).order_by(None)) or 0
    items = list(db.scalars(consulta.limit(p.tamano).offset(p.offset)).unique())
    return items, p.meta(total)


def paginar_lista(lista: list[Any], p: Pagina) -> tuple[list[Any], dict[str, int]]:
    return lista[p.offset:p.offset + p.tamano], p.meta(len(lista))
