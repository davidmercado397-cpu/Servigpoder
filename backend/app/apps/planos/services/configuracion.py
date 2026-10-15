"""Configuración editable de los planos: catálogos de entidades, alias, correcciones y salario mínimo.
Carga inicial desde los CSV de app/apps/planos/datos (idempotente: no pisa lo que el usuario cambió)."""

import csv
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.apps.planos.models import PlanoAlias, PlanoCorreccion, PlanoEntidad, PlanoSalarioMinimo
from app.apps.planos.services.comun import normalizar
from app.apps.planos.services.dane import ALIAS_CIUDAD, ALIAS_DEPARTAMENTO, DATOS, ResolverDane
from app.apps.planos.services.entidades import CATALOGOS, Codificador

SALARIO_MINIMO_INICIAL = {2026: 1750905}


def _csv(nombre: str) -> list[dict]:
    with open(DATOS / nombre, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def sembrar(db: Session) -> None:
    if db.scalar(select(PlanoEntidad).limit(1)) is None:
        for r in _csv("entidades.csv"):
            db.add(PlanoEntidad(catalogo=r["catalogo"], codigo=r["codigo"], descripcion=r["descripcion"], observacion=r["observacion"]))
    if db.scalar(select(PlanoAlias).limit(1)) is None:
        for r in _csv("alias_entidades.csv"):
            db.add(PlanoAlias(catalogo=r["catalogo"], texto=normalizar(r["texto"]), codigo=r["codigo"], nota=r["nota"]))
        for (pais, texto), codigo in ALIAS_DEPARTAMENTO.items():
            db.add(PlanoAlias(catalogo="DEPARTAMENTO", pais=pais, texto=texto, codigo=codigo))
        for (pais, depto, texto), codigo in ALIAS_CIUDAD.items():
            db.add(PlanoAlias(catalogo="CIUDAD", pais=pais, departamento=depto, texto=texto, codigo=codigo))
    for anio, valor in SALARIO_MINIMO_INICIAL.items():
        if db.get(PlanoSalarioMinimo, anio) is None:
            db.add(PlanoSalarioMinimo(anio=anio, valor=valor))
    db.flush()


def resolver_dane(db: Session) -> ResolverDane:
    alias = db.scalars(select(PlanoAlias).where(PlanoAlias.catalogo.in_(("DEPARTAMENTO", "CIUDAD")))).all()
    return ResolverDane({(a.pais, a.texto): a.codigo for a in alias if a.catalogo == "DEPARTAMENTO"},
                        {(a.pais, a.departamento, a.texto): a.codigo for a in alias if a.catalogo == "CIUDAD"})


def codificador(db: Session) -> Codificador:
    catalogos: dict[str, dict[str, str]] = {c: {} for c in CATALOGOS}
    for e in db.scalars(select(PlanoEntidad)):
        catalogos.setdefault(e.catalogo, {})[e.codigo] = e.descripcion
    alias = {(a.catalogo, a.texto): a.codigo for a in db.scalars(select(PlanoAlias).where(PlanoAlias.catalogo.in_(CATALOGOS)))}
    return Codificador(catalogos, alias)


def correcciones(db: Session, plano: str) -> dict[tuple[str, str], str]:
    return {(c.cedula, c.columna): c.valor for c in db.scalars(select(PlanoCorreccion).where(PlanoCorreccion.plano == plano))}


def salario_minimo(db: Session, anio: int | None = None) -> int | None:
    s = db.get(PlanoSalarioMinimo, anio or date.today().year)
    return s.valor if s else None
