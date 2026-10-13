"""Respaldo de la base comercial: maestros y matriz comercial de todos los meses, en un JSON.

Sirve para llevar la base de una instalación a otra (p. ej. del equipo local a producción). Todo se
identifica por código (ubicación, puesto, horario, novedad, mes), nunca por los ids internos de la base,
que cambian entre instalaciones. Restaurar no borra nada que no venga en el respaldo:
- Maestros: crea los que faltan y actualiza los existentes con los datos del respaldo.
- Matriz: cada mes se crea; si ya existe, se reemplaza solo si está en borrador (uno aprobado o cerrado
  no se toca: hay que desaprobarlo primero).
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.apps.capacidad.models import (
    MatrizExcepcion, MatrizFranja, MatrizPeriodo, MatrizPuesto, Novedad, Puesto, PuestoEquivalencia, Turno, TurnoFranja, Ubicacion,
)
from app.apps.capacidad.models.matriz import BORRADOR

VERSION = 1


class RespaldoInvalido(ValueError):
    pass


def _h(t: time | None) -> str | None:
    return t.strftime("%H:%M") if t else None


def exportar(db: Session) -> dict:
    ubicaciones = list(db.scalars(select(Ubicacion).order_by(Ubicacion.codigo)))
    puestos = list(db.scalars(select(Puesto).order_by(Puesto.codigo)))
    periodos = list(db.scalars(select(MatrizPeriodo).order_by(MatrizPeriodo.anio, MatrizPeriodo.mes)))
    return {
        "tipo": "base_comercial", "version": VERSION, "generado": datetime.now(timezone.utc).isoformat(),
        "ubicaciones": [{"codigo": u.codigo, "nombre": u.nombre, "nit": u.nit, "ciudad": u.ciudad} for u in ubicaciones],
        "puestos": [{"codigo": p.codigo, "ubicacion": p.ubicacion.codigo, "descripcion": p.descripcion, "tipo": p.tipo,
                     "excluido": p.excluido, "activo": p.activo} for p in puestos],
        "equivalencias": [{"codigo_siesa": e.codigo_siesa, "puesto": e.puesto.codigo, "origen": e.origen}
                          for e in db.scalars(select(PuestoEquivalencia).order_by(PuestoEquivalencia.codigo_siesa))],
        "turnos": [{"codigo": t.codigo, "descripcion": t.descripcion, "clase": t.clase,
                    "franjas": [[_h(f.inicio), _h(f.fin)] for f in t.franjas]}
                   for t in db.scalars(select(Turno).order_by(Turno.codigo))],
        "novedades": [{"codigo": n.codigo, "descripcion": n.descripcion, "requiere_cubrimiento": n.requiere_cubrimiento}
                      for n in db.scalars(select(Novedad).order_by(Novedad.codigo))],
        "periodos": [{
            "anio": p.anio, "mes": p.mes, "estado": p.estado,
            "puestos": [{
                "puesto": mp.puesto.codigo, "hombres": float(mp.hombres), "secuencia": mp.secuencia, "jornada": mp.jornada,
                "incluye_festivos": mp.incluye_festivos, "requiere_revision": mp.requiere_revision, "nota": mp.nota,
                "franjas": [{"dias": f.dias, "inicio": _h(f.inicio), "fin": _h(f.fin), "cantidad": f.cantidad} for f in mp.franjas],
                "excepciones": [{"fecha": x.fecha.isoformat(), "sin_servicio": x.sin_servicio, "inicio": _h(x.inicio),
                                 "fin": _h(x.fin), "cantidad": x.cantidad, "observacion": x.observacion} for x in mp.excepciones],
            } for mp in sorted(p.puestos, key=lambda m: m.puesto.codigo)],
        } for p in periodos],
    }


@dataclass
class Resultado:
    creados: dict[str, int] = field(default_factory=dict)
    actualizados: dict[str, int] = field(default_factory=dict)
    meses_restaurados: list[str] = field(default_factory=list)
    meses_omitidos: list[str] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)

    def contar(self, tipo: str, nuevo: bool) -> None:
        destino = self.creados if nuevo else self.actualizados
        destino[tipo] = destino.get(tipo, 0) + 1


def _hora(v: str | None) -> time | None:
    return time.fromisoformat(v) if v else None


def restaurar(db: Session, datos: dict) -> Resultado:
    if not isinstance(datos, dict) or datos.get("tipo") != "base_comercial":
        raise RespaldoInvalido("El archivo no es un respaldo de la base comercial")
    if datos.get("version") != VERSION:
        raise RespaldoInvalido(f"Versión de respaldo no compatible: {datos.get('version')}")
    r = Resultado()
    try:
        ubicaciones = {u.codigo: u for u in db.scalars(select(Ubicacion))}
        for x in datos.get("ubicaciones", []):
            u = ubicaciones.get(x["codigo"])
            r.contar("ubicaciones", u is None)
            if u is None:
                u = ubicaciones[x["codigo"]] = Ubicacion(codigo=x["codigo"])
                db.add(u)
            u.nombre, u.nit, u.ciudad = x["nombre"], x.get("nit"), x.get("ciudad")
        db.flush()

        puestos = {p.codigo: p for p in db.scalars(select(Puesto))}
        for x in datos.get("puestos", []):
            ubicacion = ubicaciones.get(x["ubicacion"])
            if ubicacion is None:
                r.advertencias.append(f"Puesto {x['codigo']}: la ubicación {x['ubicacion']} no está en el respaldo; se omitió")
                continue
            p = puestos.get(x["codigo"])
            r.contar("puestos", p is None)
            if p is None:
                p = puestos[x["codigo"]] = Puesto(codigo=x["codigo"])
                db.add(p)
            p.ubicacion_id, p.descripcion, p.tipo = ubicacion.id, x.get("descripcion", ""), x.get("tipo", p.tipo)
            p.excluido, p.activo = bool(x.get("excluido")), bool(x.get("activo", True))
        db.flush()

        equivalencias = {e.codigo_siesa: e for e in db.scalars(select(PuestoEquivalencia))}
        for x in datos.get("equivalencias", []):
            p = puestos.get(x["puesto"])
            if p is None:
                continue
            e = equivalencias.get(x["codigo_siesa"])
            r.contar("equivalencias", e is None)
            if e is None:
                e = equivalencias[x["codigo_siesa"]] = PuestoEquivalencia(codigo_siesa=x["codigo_siesa"])
                db.add(e)
            e.puesto_id, e.origen = p.id, x["origen"]

        turnos = {t.codigo: t for t in db.scalars(select(Turno))}
        for x in datos.get("turnos", []):
            t = turnos.get(x["codigo"])
            r.contar("horarios", t is None)
            if t is None:
                t = turnos[x["codigo"]] = Turno(codigo=x["codigo"])
                db.add(t)
            t.descripcion, t.clase = x.get("descripcion", ""), x.get("clase", t.clase)
            t.franjas = [TurnoFranja(orden=i, inicio=_hora(a), fin=_hora(b)) for i, (a, b) in enumerate(x.get("franjas", []))]

        novedades = {n.codigo: n for n in db.scalars(select(Novedad))}
        for x in datos.get("novedades", []):
            n = novedades.get(x["codigo"])
            r.contar("novedades", n is None)
            if n is None:
                n = novedades[x["codigo"]] = Novedad(codigo=x["codigo"])
                db.add(n)
            n.descripcion, n.requiere_cubrimiento = x["descripcion"], bool(x.get("requiere_cubrimiento", True))
        db.flush()

        for x in datos.get("periodos", []):
            etiqueta = f"{x['mes']:02d}/{x['anio']}"
            p = db.scalar(select(MatrizPeriodo).where(MatrizPeriodo.anio == x["anio"], MatrizPeriodo.mes == x["mes"]))
            if p is not None and p.estado != BORRADOR and p.puestos:
                r.meses_omitidos.append(f"{etiqueta}: ya existe y está {p.estado} (desapruébela para reemplazarla)")
                continue
            if p is None:
                p = MatrizPeriodo(anio=x["anio"], mes=x["mes"])
                db.add(p)
            p.estado = x.get("estado", BORRADOR)
            p.actualizado_en = datetime.now(timezone.utc)
            nuevos = []
            for mp in x.get("puestos", []):
                puesto = puestos.get(mp["puesto"])
                if puesto is None:
                    r.advertencias.append(f"{etiqueta}: el puesto {mp['puesto']} no existe; se omitió")
                    continue
                nuevos.append(MatrizPuesto(
                    puesto_id=puesto.id, hombres=Decimal(str(mp.get("hombres", 0))), secuencia=mp.get("secuencia", ""),
                    jornada=mp.get("jornada", ""), incluye_festivos=bool(mp.get("incluye_festivos", True)),
                    requiere_revision=bool(mp.get("requiere_revision")), nota=mp.get("nota", ""),
                    franjas=[MatrizFranja(dias=f["dias"], inicio=_hora(f["inicio"]), fin=_hora(f["fin"]), cantidad=f["cantidad"])
                             for f in mp.get("franjas", [])],
                    excepciones=[MatrizExcepcion(fecha=date.fromisoformat(e["fecha"]), sin_servicio=bool(e.get("sin_servicio")),
                                                 inicio=_hora(e.get("inicio")), fin=_hora(e.get("fin")), cantidad=e.get("cantidad", 1),
                                                 observacion=e.get("observacion", "")) for e in mp.get("excepciones", [])],
                ))
            p.puestos = []
            db.flush()  # borra los puestos anteriores antes de insertar los del respaldo (único por mes y puesto)
            p.puestos = nuevos
            db.flush()
            r.meses_restaurados.append(f"{etiqueta} ({len(nuevos)} puestos, {p.estado})")
    except (KeyError, TypeError, ValueError) as e:
        raise RespaldoInvalido(f"El respaldo está incompleto o dañado: {e}") from e
    return r
