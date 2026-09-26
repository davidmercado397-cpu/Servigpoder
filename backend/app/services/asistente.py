"""Asistente de IA (F6): responde preguntas sobre de dónde salen los datos de los tableros.

Seguridad:
- Las herramientas son de SOLO LECTURA y reutilizan los servicios existentes; nunca SQL libre.
- Cada herramienta verifica el permiso del usuario que pregunta: el asistente solo ve lo que
  su rol puede ver.
- La clave de la API vive en el servidor (ANTHROPIC_API_KEY); el navegador nunca la ve.
"""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

import anthropic
from anthropic import beta_tool
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    Analisis, AnalisisDia, AnalisisPuesto, Cubrimiento, CubrimientoDecision, MatrizPeriodo, MatrizPuesto,
    ProgramacionCarga, ProgramacionFila, Puesto, Ubicacion, Usuario,
)
from app.services import alertas as svc_alertas
from app.services import historico as svc_historico
from app.services.codigos import canonico
from app.services.cubrimientos import registros_carga, titulares
from app.services.matriz import festivos

log = logging.getLogger("app.asistente")

MAX_ITERACIONES = 10
MAX_FILAS = 40
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

INSTRUCCIONES = """Eres el asistente de análisis de "Capacidad Operativa", la aplicación interna de Servigpoder \
(empresa de vigilancia y seguridad privada en Colombia) que controla la programación de personal exportada \
de SIESA contra lo vendido a los clientes. Respondes en español, de forma clara y breve, a programadores y a \
la especialista de nómina.

Tu trabajo es explicar de dónde salen los números de los tableros y qué significan, usando SIEMPRE las \
herramientas para consultar los datos reales. Nunca inventes cifras: si una herramienta no trae el dato, dilo. \
Cuando des un número, explica cómo se calcula con los valores concretos (por ejemplo: "cobertura = 1 − 24.121 h \
descubiertas ÷ 232.076 h vendidas = 89,6 %"). Si la pregunta es ambigua (qué mes, qué puesto), usa el mes más \
reciente con análisis o pide el dato que falta. Cuando menciones un puesto, incluye su código y ubicación.

Cómo funciona el sistema (metodología):

1. Matriz comercial (lo vendido): por cada puesto y mes tiene hombres presupuestados, secuencia (4x2, 6x1, 5x2…), \
franjas de cobertura por día de la semana (p. ej. L-D 06:00-18:00 y 18:00-06:00 = servicio 24 h), si incluye \
festivos (si no, los festivos de Colombia no requieren cobertura) y excepciones de días puntuales. Cada mes se \
proyecta al siguiente y se corrige solo lo que cambia. Estados: borrador, aprobado, cerrado.
2. Hombres esperados = turnos diarios × (días del ciclo ÷ días trabajados). 4x2 24 h: 2 × 6/4 = 3; 4x2 solo \
noche: 1,5; 6x1 de 16 h: 2 × 7/6 ≈ 2,3.
3. Programación (lo programado): el Excel "ReporteAsignacionResumido" de SIESA, una fila por empleado y puesto, \
un código por día. Clases: trabajo (horarios del catálogo de SIESA, p. ej. 06:00 - 18:00), descanso (Z, L) y \
novedad (VAC vacaciones, PRV programado a vacaciones, LNR licencia no remunerada, LRM licencia remunerada, LIC, \
LUT luto, IEG incapacidad, AT accidente de trabajo, AUS ausencia, IND/IND NOCHE inducción, PSA/PSB permiso \
sindical). Las novedades NO cuentan como cobertura. Los sufijos * y ** son solo de nómina. Los códigos de puesto \
de SIESA se cruzan con la matriz por equivalencias (exacta, aproximada o manual); los que no cruzan quedan "por \
aclarar" y sus turnos no entran a la cobertura. Cada carga es una foto; se analiza la más reciente del mes.
4. Motor de cobertura: cada puesto se evalúa en bloques de 30 minutos comparando personas vendidas contra \
personas programadas trabajando. Faltante = horas descubiertas (hueco); sobrante = horas en exceso. Un turno que \
cruza la medianoche (18:00-06:00) cuenta completo en el día en que empieza. Estado del día: cubierto, hueco, \
exceso, o mixto (hueco y exceso el mismo día, p. ej. 2 personas de día y ninguna de noche). Cobertura % = \
1 − horas descubiertas ÷ horas vendidas.
5. Titular: el puesto donde la persona tiene más días trabajados en el mes. Se compara el número de titulares de \
cada puesto con los hombres presupuestados (diferencia mayor a 0,5 = alerta).
6. Cubrimientos: turnos de una persona en un puesto donde no es titular. Se justifican solos si ese día un \
titular del puesto tiene una novedad que requiere cubrimiento (motivo "novedad") o está de descanso (motivo \
"descanso", relevo), y el turno no se cruza con horas en exceso. Si no, quedan pendientes para que nómina los \
apruebe o rechace (el rechazo exige comentario). Doble turno = la persona trabaja ese día en otro puesto.
7. Personas en bolsa: turnos en las bolsas 05 disponibles o 06 relevantes los días en que la persona no cubre \
ningún puesto.
8. Alertas: cobertura bajo el umbral, huecos en los próximos días, cubrimientos pendientes, puestos por aclarar, \
matriz en borrador o sin proyectar, programación sin actualizar.

La información es confidencial e interna: no sugieras compartirla fuera de la empresa. Si te piden modificar \
datos, aprobar cubrimientos o algo fuera de consultar y explicar, indica en qué pantalla de la aplicación se hace."""


class SinPermiso(Exception):
    pass


@dataclass
class Contexto:
    db: Session
    usuario: Usuario
    datos_personales: bool
    herramientas_usadas: list[str] = field(default_factory=list)

    def exigir(self, permiso: str) -> None:
        if permiso not in self.usuario.permisos:
            raise SinPermiso(permiso)

    def persona(self, cedula: str, nombre: str) -> dict:
        if self.datos_personales:
            return {"nombre": nombre, "cedula": cedula}
        return {"persona": f"Persona-{abs(hash(cedula)) % 10_000:04d}"}


def _json(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _num(v: object) -> float:
    return round(float(v or 0), 1)


def _carga_y_analisis(ctx: Contexto, anio: int | None, mes: int | None) -> tuple[ProgramacionCarga, Analisis | None]:
    q = select(ProgramacionCarga).order_by(ProgramacionCarga.id.desc())
    if anio and mes:
        q = q.where(ProgramacionCarga.anio == anio, ProgramacionCarga.mes == mes)
    carga = ctx.db.scalar(q.limit(1))
    if carga is None:
        raise LookupError("No hay programación cargada" + (f" para {mes:02d}/{anio}" if anio and mes else ""))
    analisis = ctx.db.scalar(select(Analisis).where(Analisis.carga_id == carga.id))
    return carga, analisis


def _puesto(ctx: Contexto, codigo: str) -> Puesto:
    can = canonico(codigo)
    for p in ctx.db.scalars(select(Puesto)):
        if canonico(p.codigo) == can:
            return p
    raise LookupError(f"No existe el puesto '{codigo}'. Use buscar_puestos para encontrar el código.")


def crear_herramientas(ctx: Contexto) -> list:
    """Herramientas de solo lectura, ligadas al usuario que pregunta."""

    def envolver(nombre: str, fn: Callable[[], object]) -> str:
        ctx.herramientas_usadas.append(nombre)
        try:
            return _json(fn())
        except SinPermiso as e:
            return _json({"error": f"El usuario no tiene el permiso '{e}' para consultar esta información."})
        except LookupError as e:
            return _json({"error": str(e)})

    @beta_tool
    def resumen_cobertura(anio: int | None = None, mes: int | None = None) -> str:
        """Indicadores del análisis de cobertura de un mes: cobertura %, horas vendidas, programadas, descubiertas
        y en exceso, puestos por estado, titulares vs hombres, cubrimientos y resumen por ciudad.

        Args:
            anio: Año (p. ej. 2026). Omitir para el mes más reciente con programación.
            mes: Mes 1-12. Omitir para el mes más reciente con programación.
        """
        def f():
            ctx.exigir("analisis.ver")
            carga, a = _carga_y_analisis(ctx, anio, mes)
            if a is None:
                return {"aviso": "La programación de ese mes no tiene análisis calculado (falta matriz o recalcular)."}
            periodo = ctx.db.get(MatrizPeriodo, a.periodo_id)
            return {"analisis_id": a.id, "carga_id": carga.id, "archivo": carga.archivo, "cargado_en": carga.cargado_en,
                    "calculado_en": a.generado_en, "estado_matriz": periodo.estado if periodo else None,
                    "enlace_tablero": "/cobertura", **a.resumen}
        return envolver("resumen_cobertura", f)

    @beta_tool
    def listar_puestos(estado: str = "con_hallazgo", ciudad: str = "", orden: str = "descubiertas",
                       anio: int | None = None, mes: int | None = None) -> str:
        """Lista de puestos del análisis de cobertura con sus horas descubiertas, en exceso, hombres y titulares.

        Args:
            estado: con_hallazgo, hueco, exceso, mixto, ok, fijos (titulares distintos a hombres) o todos.
            ciudad: Filtrar por ciudad (p. ej. CALI). Vacío para todas.
            orden: descubiertas, exceso o codigo.
            anio: Año. Omitir para el mes más reciente.
            mes: Mes 1-12. Omitir para el mes más reciente.
        """
        def f():
            ctx.exigir("analisis.ver")
            _, a = _carga_y_analisis(ctx, anio, mes)
            if a is None:
                return {"aviso": "Sin análisis para ese mes."}
            q = (select(AnalisisPuesto).join(AnalisisPuesto.puesto).join(Puesto.ubicacion)
                 .where(AnalisisPuesto.analisis_id == a.id))
            if estado in {"hueco", "exceso", "mixto", "ok"}:
                q = q.where(AnalisisPuesto.estado == estado)
            elif estado == "con_hallazgo":
                q = q.where(AnalisisPuesto.estado != "ok")
            elif estado == "fijos":
                q = q.where((AnalisisPuesto.fijos > AnalisisPuesto.hombres + 0.5) | (AnalisisPuesto.fijos < AnalisisPuesto.hombres - 0.5))
            if ciudad:
                q = q.where(Ubicacion.ciudad.ilike(ciudad))
            ordenes = {"exceso": AnalisisPuesto.horas_exceso.desc(), "codigo": Puesto.codigo.asc()}
            q = q.order_by(ordenes.get(orden, AnalisisPuesto.horas_descubiertas.desc()))
            filas = list(ctx.db.scalars(q).unique())
            return {"total": len(filas), "mostrando": min(len(filas), MAX_FILAS), "puestos": [
                {"codigo": ap.puesto.codigo, "ubicacion": ap.puesto.ubicacion.nombre, "ciudad": ap.puesto.ubicacion.ciudad,
                 "descripcion": ap.puesto.descripcion, "estado": ap.estado, "hombres": _num(ap.hombres), "titulares": ap.fijos,
                 "personas": ap.personas, "horas_vendidas": _num(ap.horas_requeridas), "horas_descubiertas": _num(ap.horas_descubiertas),
                 "horas_exceso": _num(ap.horas_exceso), "dias_hueco": ap.dias_hueco, "dias_exceso": ap.dias_exceso,
                 "enlace": f"/cobertura/{ap.puesto_id}?analisis={a.id}"}
                for ap in filas[:MAX_FILAS]]}
        return envolver("listar_puestos", f)

    @beta_tool
    def buscar_puestos(texto: str) -> str:
        """Busca puestos por código, descripción o nombre de la ubicación (cliente).

        Args:
            texto: Parte del código o del nombre, p. ej. "220", "Filandia" o "SENA".
        """
        def f():
            ctx.exigir("analisis.ver")
            patron = f"%{texto.strip()}%"
            filas = list(ctx.db.scalars(select(Puesto).join(Puesto.ubicacion).where(
                Puesto.codigo.ilike(patron) | Puesto.descripcion.ilike(patron) | Ubicacion.nombre.ilike(patron)
            ).order_by(Puesto.codigo).limit(MAX_FILAS)).unique())
            return [{"codigo": p.codigo, "ubicacion": p.ubicacion.nombre, "ciudad": p.ubicacion.ciudad, "descripcion": p.descripcion,
                     "tipo": p.tipo, "excluido": p.excluido, "activo": p.activo} for p in filas]
        return envolver("buscar_puestos", f)

    @beta_tool
    def detalle_puesto(codigo: str, anio: int | None = None, mes: int | None = None) -> str:
        """Detalle de un puesto: lo vendido en la matriz (franjas, festivos, hombres), el resultado de cada día con
        hallazgo (horas y tramos que faltan o sobran), las personas programadas (titular o apoyo) y sus turnos.

        Args:
            codigo: Código del puesto (PODER interno), p. ej. "220" o "47-A".
            anio: Año. Omitir para el mes más reciente.
            mes: Mes 1-12. Omitir para el mes más reciente.
        """
        def f():
            ctx.exigir("analisis.ver")
            p = _puesto(ctx, codigo)
            carga, a = _carga_y_analisis(ctx, anio, mes)
            periodo = ctx.db.scalar(select(MatrizPeriodo).where(MatrizPeriodo.anio == carga.anio, MatrizPeriodo.mes == carga.mes))
            mp = ctx.db.scalar(select(MatrizPuesto).where(MatrizPuesto.periodo_id == periodo.id, MatrizPuesto.puesto_id == p.id)) if periodo else None
            fest = festivos(carga.anio, carga.mes)
            res: dict = {
                "puesto": {"codigo": p.codigo, "ubicacion": p.ubicacion.nombre, "ciudad": p.ubicacion.ciudad,
                           "descripcion": p.descripcion, "tipo": p.tipo, "excluido": p.excluido},
                "programacion": {"desde": carga.desde, "hasta": carga.hasta},
                "vendido": None if mp is None else {
                    "hombres": _num(mp.hombres), "secuencia": mp.secuencia, "jornada_original": mp.jornada,
                    "incluye_festivos": mp.incluye_festivos, "requiere_revision": mp.requiere_revision, "nota": mp.nota,
                    "franjas": [{"dias_mascara": fr.dias, "dias": [DIAS[i] for i in range(7) if fr.dias & (1 << i)],
                                 "inicio": fr.inicio, "fin": fr.fin, "personas": fr.cantidad} for fr in mp.franjas],
                    "excepciones": [{"fecha": e.fecha, "sin_servicio": e.sin_servicio, "inicio": e.inicio, "fin": e.fin,
                                     "observacion": e.observacion} for e in mp.excepciones],
                },
                "festivos_del_mes": {d.isoformat(): n for d, n in fest.items()},
            }
            if mp is None:
                res["aviso_matriz"] = "El puesto no está en la matriz comercial de ese mes: todo lo programado cuenta como exceso."
            if a:
                ap = ctx.db.scalar(select(AnalisisPuesto).where(AnalisisPuesto.analisis_id == a.id, AnalisisPuesto.puesto_id == p.id))
                if ap:
                    res["resultado"] = {"estado": ap.estado, "hombres": _num(ap.hombres), "titulares": ap.fijos, "personas": ap.personas,
                                        "horas_vendidas": _num(ap.horas_requeridas), "horas_programadas": _num(ap.horas_programadas),
                                        "horas_descubiertas": _num(ap.horas_descubiertas), "horas_exceso": _num(ap.horas_exceso),
                                        "enlace": f"/cobertura/{p.id}?analisis={a.id}"}
                    dias = ctx.db.scalars(select(AnalisisDia).where(AnalisisDia.analisis_puesto_id == ap.id,
                                                                    AnalisisDia.estado.in_(["hueco", "exceso", "mixto"])).order_by(AnalisisDia.fecha))
                    res["dias_con_hallazgo"] = [{"fecha": d.fecha, "dia": DIAS[d.fecha.weekday()], "estado": d.estado,
                                                  "horas_vendidas": _num(d.horas_requeridas), "horas_programadas": _num(d.horas_programadas),
                                                  "tramos": d.detalle} for d in dias]
            # Personas programadas en el puesto y sus códigos por día
            registros = registros_carga(ctx.db, carga.id)
            puestos = {x.id: x for x in ctx.db.scalars(select(Puesto))}
            tit = titulares(registros, puestos)
            personas: dict[str, dict] = {}
            for r in registros:
                if r.puesto_id != p.id:
                    continue
                t = tit.get(r.cedula)
                pr = personas.setdefault(r.cedula, {**ctx.persona(r.cedula, r.nombre), "titular": t == p.id,
                                                    "puesto_titular": puestos[t].codigo if t else None, "turnos": {}})
                pr["turnos"][r.fecha.isoformat()] = r.codigo
            res["personas"] = list(personas.values())
            return res
        return envolver("detalle_puesto", f)

    @beta_tool
    def cubrimientos(codigo_puesto: str = "", estado: str = "", anio: int | None = None, mes: int | None = None) -> str:
        """Cubrimientos (turnos fuera del puesto titular) con su motivo, si generan exceso o doble turno, y su
        estado final (justificado automáticamente, pendiente, aprobado o rechazado por nómina con comentario).

        Args:
            codigo_puesto: Código del puesto para filtrar. Vacío para todos.
            estado: pendiente, justificado, aprobado o rechazado. Vacío para todos.
            anio: Año. Omitir para el mes más reciente.
            mes: Mes 1-12. Omitir para el mes más reciente.
        """
        def f():
            ctx.exigir("analisis.ver")
            carga, a = _carga_y_analisis(ctx, anio, mes)
            if a is None:
                return {"aviso": "Sin análisis para ese mes."}
            q = select(Cubrimiento).where(Cubrimiento.analisis_id == a.id).order_by(Cubrimiento.fecha)
            if codigo_puesto:
                q = q.where(Cubrimiento.puesto_id == _puesto(ctx, codigo_puesto).id)
            decisiones = {(d.cedula, d.puesto_id, d.fecha): d for d in ctx.db.scalars(
                select(CubrimientoDecision).where(CubrimientoDecision.anio == carga.anio, CubrimientoDecision.mes == carga.mes))}
            lista = []
            for c in ctx.db.scalars(q).unique():
                d = decisiones.get((c.cedula, c.puesto_id, c.fecha))
                final = d.estado if d else c.estado_auto
                if estado and final != estado:
                    continue
                lista.append({"fecha": c.fecha, "puesto": c.puesto.codigo, **ctx.persona(c.cedula, c.nombre),
                              "puesto_titular": c.puesto_titular, "turno": c.codigo_turno, "horas": _num(c.horas),
                              "motivo": c.motivo, "cubre_a": [ctx.persona(r["cedula"], r["nombre"]) | {"codigo": r["codigo"]} for r in c.referencia],
                              "genera_exceso": c.genera_exceso, "doble_turno": c.doble_turno, "estado": final,
                              "comentario_nomina": d.comentario if d else None})
            conteo: dict[str, int] = {}
            for x in lista:
                conteo[x["estado"]] = conteo.get(x["estado"], 0) + 1
            return {"total": len(lista), "por_estado": conteo, "horas": _num(sum(x["horas"] for x in lista)),
                    "mostrando": min(len(lista), MAX_FILAS), "cubrimientos": lista[:MAX_FILAS], "enlace": "/cubrimientos"}
        return envolver("cubrimientos", f)

    @beta_tool
    def comparar_cargas() -> str:
        """Compara la última carga de programación con la anterior del mismo mes: turnos agregados, eliminados o
        cambiados (novedades de programación) y los puestos cuya cobertura cambió."""
        def f():
            ctx.exigir("analisis.ver")
            actual = ctx.db.scalar(select(ProgramacionCarga).order_by(ProgramacionCarga.id.desc()).limit(1))
            if actual is None:
                raise LookupError("No hay cargas de programación")
            anterior = ctx.db.scalar(select(ProgramacionCarga).where(
                ProgramacionCarga.anio == actual.anio, ProgramacionCarga.mes == actual.mes, ProgramacionCarga.id < actual.id)
                .order_by(ProgramacionCarga.id.desc()).limit(1))
            if anterior is None:
                raise LookupError("Solo hay una carga en el mes: no hay con qué comparar")
            c = svc_historico.comparar(ctx.db, anterior, actual)
            cambios = [{k: v for k, v in x.items() if k not in ("cedula", "nombre")} | ctx.persona(x["cedula"], x["nombre"])
                       for x in c["cambios"][:MAX_FILAS]]
            return {**{k: c[k] for k in ("anterior", "actual", "desde", "hasta", "total", "por_tipo", "personas", "puestos")},
                    "cambios": cambios, "impacto": c["impacto"][:MAX_FILAS], "enlace": "/historico"}
        return envolver("comparar_cargas", f)

    @beta_tool
    def alertas_actuales() -> str:
        """Alertas vigentes del sistema, ordenadas por gravedad (crítica, advertencia, información)."""
        def f():
            ctx.exigir("analisis.ver")
            return [{k: v for k, v in x.items() if k != "items"} | {"primeros_items": x["items"][:15]}
                    for x in svc_alertas.evaluar(ctx.db)]
        return envolver("alertas_actuales", f)

    @beta_tool
    def estado_datos() -> str:
        """Qué datos hay cargados: meses con matriz (y su estado), cargas de programación y puestos por aclarar."""
        def f():
            ctx.exigir("analisis.ver")
            periodos = [{"anio": p.anio, "mes": p.mes, "estado": p.estado} for p in
                        ctx.db.scalars(select(MatrizPeriodo).order_by(MatrizPeriodo.anio.desc(), MatrizPeriodo.mes.desc()))]
            cargas = [{"carga_id": c.id, "anio": c.anio, "mes": c.mes, "desde": c.desde, "hasta": c.hasta, "cargado_en": c.cargado_en}
                      for c in ctx.db.scalars(select(ProgramacionCarga).order_by(ProgramacionCarga.id.desc()).limit(10))]
            ultima = cargas[0]["carga_id"] if cargas else None
            sin_puesto = ctx.db.scalar(select(func.count(func.distinct(ProgramacionFila.puesto_siesa))).where(
                ProgramacionFila.carga_id == ultima, ProgramacionFila.puesto_id.is_(None))) if ultima else 0
            return {"hoy": date.today(), "matrices": periodos, "cargas_recientes": cargas, "puestos_sin_equivalencia": sin_puesto}
        return envolver("estado_datos", f)

    return [resumen_cobertura, listar_puestos, buscar_puestos, detalle_puesto, cubrimientos, comparar_cargas,
            alertas_actuales, estado_datos]


class AsistenteNoConfigurado(Exception):
    pass


@dataclass
class Respuesta:
    texto: str
    herramientas: list[str]
    tokens_entrada: int
    tokens_salida: int
    modelo: str


def cliente() -> anthropic.Anthropic:
    s = get_settings()
    if not s.anthropic_api_key:
        raise AsistenteNoConfigurado()
    return anthropic.Anthropic(api_key=s.anthropic_api_key, max_retries=2, timeout=120.0)


def responder(db: Session, usuario: Usuario, mensajes: list[dict], client: anthropic.Anthropic | None = None) -> Respuesta:
    """Ejecuta el ciclo del agente (Tool Runner del SDK) y devuelve el texto final."""
    s = get_settings()
    client = client or cliente()
    ctx = Contexto(db, usuario, s.asistente_datos_personales)
    extra: dict = {}
    if s.asistente_fallbacks:
        # Si el modelo declina por una política de seguridad, la API reintenta con un modelo de respaldo
        extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}

    runner = client.beta.messages.tool_runner(
        model=s.asistente_modelo,
        max_tokens=16000,
        max_iterations=MAX_ITERACIONES,
        system=INSTRUCCIONES,
        cache_control={"type": "ephemeral"},  # instrucciones y herramientas fijas: se cachean entre preguntas
        tools=crear_herramientas(ctx),
        messages=mensajes,
        **extra,
    )
    ultimo = None
    entrada = salida = 0
    for mensaje in runner:
        ultimo = mensaje
        entrada += mensaje.usage.input_tokens or 0
        salida += mensaje.usage.output_tokens or 0
    if ultimo is None:
        raise RuntimeError("El asistente no produjo respuesta")
    if ultimo.stop_reason == "refusal":
        texto = "No puedo responder esa pregunta. Reformúlela en relación con la programación, la matriz o la cobertura."
    else:
        texto = "\n".join(b.text for b in ultimo.content if b.type == "text").strip()
        if ultimo.stop_reason == "max_tokens":
            texto += "\n\n_(Respuesta recortada por longitud. Haga una pregunta más específica.)_"
    return Respuesta(texto or "No encontré información para responder.", ctx.herramientas_usadas, entrada, salida, ultimo.model)
