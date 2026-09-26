"""Alertas (F4): situaciones que requieren atención, evaluadas sobre el último análisis."""

import calendar
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Analisis, AnalisisDia, AnalisisPuesto, Cubrimiento, CubrimientoDecision, MatrizPeriodo, Parametro,
    ProgramacionCarga, ProgramacionFila, Puesto, PuestoEquivalencia,
)
from app.models.analisis import HUECO, MIXTO
from app.models.cubrimientos import PENDIENTE
from app.models.matriz import BORRADOR
from app.services.matriz import siguiente_mes

ZONA = ZoneInfo("America/Bogota")

PARAMETROS_BASE: dict[str, tuple[str, str]] = {
    "umbral_cobertura": ("95", "Cobertura mínima esperada (%). Por debajo se genera alerta crítica"),
    "dias_alerta_hueco": ("3", "Días hacia adelante (desde hoy) en los que se alertan puestos con hueco"),
    "dias_aviso_proyeccion": ("7", "Días antes de fin de mes para avisar que falta proyectar la matriz del mes siguiente"),
    "horas_programacion_vieja": ("30", "Horas sin una carga nueva de programación antes de avisar"),
}

CRITICA, ADVERTENCIA, INFO = "critica", "advertencia", "info"


@dataclass
class Alerta:
    nivel: str
    titulo: str
    detalle: str
    enlace: str | None = None
    items: list[dict] = field(default_factory=list)
    clave: str = ""  # identificador estable para contadores del menú
    valor: int = 0


def hoy() -> date:
    return datetime.now(ZONA).date()


def sembrar_parametros(db: Session) -> None:
    existentes = set(db.scalars(select(Parametro.clave)))
    for clave, (valor, desc) in PARAMETROS_BASE.items():
        if clave not in existentes:
            db.add(Parametro(clave=clave, valor=valor, descripcion=desc))


def parametros(db: Session) -> dict[str, float]:
    valores = {p.clave: p.valor for p in db.scalars(select(Parametro))}
    return {k: float(valores.get(k, v)) for k, (v, _) in PARAMETROS_BASE.items()}


def evaluar(db: Session, fecha: date | None = None) -> list[dict]:
    fecha = fecha or hoy()
    prm = parametros(db)
    alertas: list[Alerta] = []

    carga = db.scalar(select(ProgramacionCarga).where(ProgramacionCarga.anio == fecha.year, ProgramacionCarga.mes == fecha.month)
                      .order_by(ProgramacionCarga.id.desc()).limit(1))
    periodo = db.scalar(select(MatrizPeriodo).where(MatrizPeriodo.anio == fecha.year, MatrizPeriodo.mes == fecha.month))

    # Matriz del mes
    if periodo is None:
        alertas.append(Alerta(CRITICA, "No hay matriz comercial para este mes",
                              "Sin matriz no se puede medir la cobertura. Proyecte la del mes anterior o impórtela.", "/matriz"))
    elif periodo.estado == BORRADOR:
        alertas.append(Alerta(INFO, "La matriz de este mes sigue en borrador", "Revísela y apruébela.", "/matriz"))

    # Proyección del mes siguiente
    dias_restantes = calendar.monthrange(fecha.year, fecha.month)[1] - fecha.day
    anio_sig, mes_sig = siguiente_mes(fecha.year, fecha.month)
    if dias_restantes <= prm["dias_aviso_proyeccion"] and not db.scalar(
        select(MatrizPeriodo.id).where(MatrizPeriodo.anio == anio_sig, MatrizPeriodo.mes == mes_sig)
    ):
        alertas.append(Alerta(ADVERTENCIA, "Falta proyectar la matriz del mes siguiente",
                              f"Quedan {dias_restantes} días del mes y aún no existe la matriz de {mes_sig:02d}/{anio_sig}.", "/matriz"))

    # Programación
    if carga is None:
        alertas.append(Alerta(CRITICA, "No hay programación cargada para este mes",
                              "Suba el reporte de asignación de SIESA.", "/programacion"))
    else:
        cargado = carga.cargado_en if carga.cargado_en.tzinfo else carga.cargado_en.replace(tzinfo=timezone.utc)
        horas = (datetime.now(timezone.utc) - cargado).total_seconds() / 3600
        if horas > prm["horas_programacion_vieja"]:
            alertas.append(Alerta(ADVERTENCIA, "La programación no se ha actualizado",
                                  f"La última carga tiene {int(horas)} horas. Las novedades del día pueden no estar reflejadas.",
                                  "/programacion"))
        sin_puesto = db.scalar(select(func.count(func.distinct(ProgramacionFila.puesto_siesa)))
                               .where(ProgramacionFila.carga_id == carga.id, ProgramacionFila.puesto_id.is_(None)))
        aproximadas = db.scalar(select(func.count()).select_from(PuestoEquivalencia).where(PuestoEquivalencia.origen == "aproximada"))
        if sin_puesto or aproximadas:
            alertas.append(Alerta(ADVERTENCIA, "Puestos de SIESA por aclarar",
                                  f"{sin_puesto} códigos sin equivalencia y {aproximadas} por confirmar: sus turnos no entran a la cobertura.",
                                  "/maestros", clave="por_aclarar", valor=sin_puesto + aproximadas))

    analisis = db.scalar(select(Analisis).where(Analisis.carga_id == carga.id)) if carga else None
    if carga and periodo and analisis is None:
        alertas.append(Alerta(ADVERTENCIA, "La cobertura del mes no está calculada", "Calcule el análisis.", "/cobertura"))

    if analisis:
        r = analisis.resumen
        pct = r.get("cobertura_pct")
        if pct is not None and pct < prm["umbral_cobertura"]:
            alertas.append(Alerta(CRITICA, f"Cobertura del {pct} %",
                                  f"Está por debajo del mínimo de {prm['umbral_cobertura']:g} %: {r.get('descubiertas', 0):,.0f} horas vendidas sin cubrir.",
                                  "/cobertura"))
        periodo_mod = periodo.actualizado_en if periodo and periodo.actualizado_en.tzinfo else (
            periodo.actualizado_en.replace(tzinfo=timezone.utc) if periodo else None)
        generado = analisis.generado_en if analisis.generado_en.tzinfo else analisis.generado_en.replace(tzinfo=timezone.utc)
        if periodo_mod and periodo_mod > generado:
            alertas.append(Alerta(ADVERTENCIA, "El análisis está desactualizado",
                                  "La matriz cambió después del último cálculo. Recalcule la cobertura.", "/cobertura"))

        # Huecos de hoy y los próximos días
        hasta = fecha + timedelta(days=int(prm["dias_alerta_hueco"]))
        huecos = db.execute(
            select(Puesto.id, Puesto.codigo, AnalisisDia.fecha, AnalisisDia.horas_descubiertas, AnalisisDia.detalle)
            .join(AnalisisPuesto, AnalisisPuesto.puesto_id == Puesto.id)
            .join(AnalisisDia, AnalisisDia.analisis_puesto_id == AnalisisPuesto.id)
            .where(AnalisisPuesto.analisis_id == analisis.id, AnalisisDia.estado.in_([HUECO, MIXTO]),
                   AnalisisDia.fecha >= fecha, AnalisisDia.fecha <= hasta)
            .order_by(AnalisisDia.fecha, AnalisisDia.horas_descubiertas.desc())
        ).all()
        if huecos:
            alertas.append(Alerta(
                CRITICA, f"{len({h[0] for h in huecos})} puestos con hueco entre hoy y el {hasta.isoformat()}",
                "Horas vendidas sin nadie programado en los próximos días.", "/cobertura",
                [{"puesto_id": pid, "puesto": cod, "fecha": f.isoformat(), "horas": float(h),
                  "franjas": ", ".join(f"{t['inicio']}-{t['fin']}" for t in det if t["tipo"] == "hueco")}
                 for pid, cod, f, h, det in huecos[:50]],
            ))

        # Cubrimientos pendientes de nómina (sin decisión)
        decididos = {(d.cedula, d.puesto_id, d.fecha) for d in db.scalars(
            select(CubrimientoDecision).where(CubrimientoDecision.anio == r["anio"], CubrimientoDecision.mes == r["mes"]))}
        pendientes = [c for c in db.scalars(select(Cubrimiento).where(Cubrimiento.analisis_id == analisis.id,
                                                                     Cubrimiento.estado_auto == PENDIENTE))
                      if (c.cedula, c.puesto_id, c.fecha) not in decididos]
        if pendientes:
            alertas.append(Alerta(ADVERTENCIA, f"{len(pendientes)} cubrimientos pendientes de revisión de nómina",
                                  f"{sum(float(c.horas) for c in pendientes):,.0f} horas sin justificación automática.", "/cubrimientos",
                                  clave="cubrimientos_pendientes", valor=len(pendientes)))

    orden = {CRITICA: 0, ADVERTENCIA: 1, INFO: 2}
    return [asdict(a) for a in sorted(alertas, key=lambda a: orden[a.nivel])]
