"""Asistente de IA del liquidador: revisa y explica las horas contadas de cada quincena.

Herramientas de SOLO LECTURA que verifican los permisos de quien pregunta.
"""

import json
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core import ia
from app.core.config import get_settings
from app.core.ia import herramienta
from app.models import Usuario
from app.apps.liquidador.dominio.tipos import CONCEPT_LABELS, DAY_LABELS, DayType, HourConcept
from app.apps.liquidador.models import LiqDia, LiqEmpleado, LiqPeriodo, LiqResultado, LiqTurno
from app.apps.liquidador.services import festivos as svc_festivos
from app.apps.liquidador.services.calculo import clase_de
from app.apps.liquidador.services.turnos import parametros

MAX_FILAS = 40
CONCEPTOS = {c.value: n for c, n in CONCEPT_LABELS.items()}
TIPOS_DIA = {d.value: n for d, n in DAY_LABELS.items()}
CLASES = {"trabajado": "días trabajados", "descanso_pago": "descansos pagos (Z)", "libre": "libres (L)",
          "ausencia": "ausencias (AUS)", "incapacidad": "incapacidades", "novedad": "días con novedad (vacaciones, licencias…)"}

INSTRUCCIONES = """Eres el asistente del "Liquidador de horas", una aplicación interna de una empresa de seguridad \
privada en Colombia que cuenta las horas de los turnos de cada empleado por quincena. Respondes en español, claro \
y breve, a la persona que carga el Excel, revisa y aprueba cada quincena. La aplicación NO calcula salarios: solo \
horas y días.

Usa SIEMPRE las herramientas para consultar los datos reales; nunca inventes cifras. Cuando expliques un total, \
muestra de qué días y turnos sale (p. ej. "13 turnos A × 7 h = 91 h diurnas ordinarias"). Si falta la quincena o \
la persona, usa la quincena más reciente o pregunta.

Cómo funciona el cálculo:
1. Quincena 1 = días 1 al 15; quincena 2 = del 16 al fin de mes. Se carga un Excel con la cédula (columna A), el \
nombre (columna B) y un código de turno por día. Cargar de nuevo reemplaza lo anterior; una quincena cerrada no se \
puede cambiar hasta reabrirla.
2. Cada turno se configura con hora de inicio, horas ordinarias y horas extras (la hora fin es informativa). Las \
horas se reparten seguidas desde la hora de inicio: primero las ordinarias y luego las extras. Lo diurno va de \
06:00 a la hora de inicio nocturna (parámetro, hoy normalmente 19:00) y lo nocturno de esa hora a las 06:00.
3. Cada fecha se clasifica en 8 tipos de día: ordinario, sábado, sábado festivo, domingo, domingo antes de \
festivo, festivo, antes de festivo y festivo antes de festivo. Si el turno cruza la medianoche, las horas después \
de las 00:00 toman la categoría del día siguiente (normal, domingo o festivo).
4. Con eso sale una matriz de 12 conceptos × 8 tipos de día por turno. "Diurnas ordinarias" cuenta TODAS las horas \
ordinarias del turno (diurnas y nocturnas); los recargos (nocturno, dominical, festivo) marcan cuáles de esas horas \
llevan recargo, por eso no se suman a las ordinarias. Las extras se separan en diurnas o nocturnas y ordinarias, \
dominicales o festivas.
5. Festivos: calendario nacional de Colombia con ajustes manuales (agregar o quitar fechas).
6. Conteo de días: Z = descanso pago, L = libre, AUS = ausencia, turnos marcados como incapacidad = incapacidades, \
turnos con horas = días trabajados y cualquier otro código sin horas (V, LR, LNR, SUS, AI, LM…) = días con novedad.
7. El archivo de liquidación trae por persona las 12 columnas de horas y los conteos de días.

La información es confidencial e interna. Si te piden modificar datos, cargar o cerrar una quincena, indica en qué \
pantalla se hace."""


class SinPermiso(Exception):
    pass


@dataclass
class Contexto:
    db: Session
    usuario: Usuario
    datos_personales: bool

    def exigir(self, permiso: str) -> None:
        if permiso not in self.usuario.permisos:
            raise SinPermiso(permiso)

    def persona(self, documento: str, nombre: str) -> dict:
        if self.datos_personales:
            return {"documento": documento, "nombre": nombre}
        return {"persona": f"Persona-{abs(hash(documento)) % 10_000:04d}"}


def _json(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _etiquetar(horas: dict) -> dict:
    return {CONCEPTOS.get(k, k): round(v, 2) for k, v in horas.items() if v}


def _periodo(ctx: Contexto, anio: int | None, mes: int | None, quincena: int | None) -> LiqPeriodo:
    q = select(LiqPeriodo).order_by(LiqPeriodo.anio.desc(), LiqPeriodo.mes.desc(), LiqPeriodo.quincena.desc())
    if anio:
        q = q.where(LiqPeriodo.anio == anio)
    if mes:
        q = q.where(LiqPeriodo.mes == mes)
    if quincena:
        q = q.where(LiqPeriodo.quincena == quincena)
    p = ctx.db.scalar(q.limit(1))
    if p is None:
        raise LookupError("No hay una quincena con esos datos. Use estado_datos para ver las quincenas.")
    return p


def _etiqueta(p: LiqPeriodo) -> dict:
    return {"quincena": f"{p.anio}-{p.mes:02d} Q{p.quincena}", "desde": p.desde, "hasta": p.hasta, "estado": p.estado,
            "enlace": f"/liquidador/quincenas/{p.id}"}


def crear_herramientas(ctx: Contexto) -> list[ia.Herramienta]:
    def envolver(fn) -> str:
        try:
            return _json(fn())
        except SinPermiso as e:
            return _json({"error": f"El usuario no tiene el permiso '{e}' para consultar esta información."})
        except LookupError as e:
            return _json({"error": str(e)})

    @herramienta
    def estado_datos() -> str:
        """Quincenas creadas (estado, archivo cargado, personas), número de turnos y la hora de inicio nocturna."""
        def f():
            ctx.exigir("liquidador.periodos.ver")
            conteo = dict(ctx.db.execute(select(LiqResultado.periodo_id, func.count()).group_by(LiqResultado.periodo_id)).all())
            periodos = ctx.db.scalars(select(LiqPeriodo).order_by(LiqPeriodo.anio.desc(), LiqPeriodo.mes.desc(),
                                                                  LiqPeriodo.quincena.desc()).limit(24))
            return {"hoy": date.today(), "hora_inicio_nocturna": parametros(ctx.db).hora_inicio_nocturna,
                    "turnos": ctx.db.scalar(select(func.count()).select_from(LiqTurno)),
                    "quincenas": [_etiqueta(p) | {"archivo": p.archivo, "personas": conteo.get(p.id, 0),
                                                  "advertencias_de_carga": len(p.advertencias or [])} for p in periodos]}
        return envolver(f)

    @herramienta
    def resumen_quincena(anio: int | None = None, mes: int | None = None, quincena: int | None = None) -> str:
        """Totales de una quincena: horas por concepto, días por tipo, personas, advertencias de la carga y las
        personas con más horas o más días con novedad.

        Args:
            anio: Año (p. ej. 2026). Omitir para la quincena más reciente.
            mes: Mes 1-12.
            quincena: 1 (días 1-15) o 2 (16 a fin de mes).
        """
        def f():
            ctx.exigir("liquidador.periodos.ver")
            p = _periodo(ctx, anio, mes, quincena)
            res = list(ctx.db.scalars(select(LiqResultado).where(LiqResultado.periodo_id == p.id)))
            horas: dict[str, float] = {}
            dias: dict[str, int] = {}
            for r in res:
                for k, v in r.horas.items():
                    horas[k] = horas.get(k, 0) + v
                for k, v in r.dias.items():
                    dias[k] = dias.get(k, 0) + v
            mas_horas = sorted(res, key=lambda r: -float(r.total_horas))[:10]
            mas_novedad = [r for r in sorted(res, key=lambda r: -r.dias.get("novedad", 0)) if r.dias.get("novedad")][:10]
            return {**_etiqueta(p), "archivo": p.archivo, "personas": len(res), "horas": _etiquetar(horas),
                    "dias": {CLASES[k]: v for k, v in dias.items() if v},
                    "advertencias_de_carga": (p.advertencias or [])[:20], "total_advertencias": len(p.advertencias or []),
                    "mas_horas_trabajadas": [ctx.persona(r.empleado.documento, r.empleado.nombre) | {"horas": float(r.total_horas)} for r in mas_horas],
                    "mas_dias_con_novedad": [ctx.persona(r.empleado.documento, r.empleado.nombre) | {"dias": r.dias["novedad"]} for r in mas_novedad]}
        return envolver(f)

    @herramienta
    def detalle_persona(documento: str, anio: int | None = None, mes: int | None = None, quincena: int | None = None) -> str:
        """Día a día de una persona en una quincena: turno, tipo de día (y si es festivo) y horas por concepto, con
        sus totales. Sirve para explicar de dónde sale cada número del archivo de liquidación.

        Args:
            documento: Cédula de la persona.
            anio: Año. Omitir para la quincena más reciente.
            mes: Mes 1-12.
            quincena: 1 o 2.
        """
        def f():
            ctx.exigir("liquidador.periodos.ver")
            p = _periodo(ctx, anio, mes, quincena)
            emp = ctx.db.scalar(select(LiqEmpleado).where(LiqEmpleado.documento == documento.strip()))
            r = emp and ctx.db.scalar(select(LiqResultado).where(LiqResultado.periodo_id == p.id, LiqResultado.empleado_id == emp.id))
            if not r:
                raise LookupError(f"La cédula {documento} no tiene turnos en la quincena {p.anio}-{p.mes:02d} Q{p.quincena}.")
            fest = svc_festivos.conjunto(ctx.db, p.desde, p.hasta)
            dias = ctx.db.scalars(select(LiqDia).where(LiqDia.periodo_id == p.id, LiqDia.empleado_id == emp.id).order_by(LiqDia.fecha))
            return {**_etiqueta(p), **ctx.persona(emp.documento, emp.nombre), "totales_horas": _etiquetar(r.horas),
                    "horas_trabajadas": float(r.total_horas), "dias": {CLASES[k]: v for k, v in r.dias.items() if v},
                    "dia_a_dia": [{"fecha": d.fecha, "turno": d.codigo, "nombre_turno": d.turno.nombre,
                                   "tipo_dia": TIPOS_DIA.get(d.tipo_dia, d.tipo_dia), "festivo": d.fecha in fest,
                                   "clase": CLASES.get(d.clase, d.clase), "horas": _etiquetar(d.horas)} for d in dias]}
        return envolver(f)

    @herramienta
    def explicar_turno(codigo: str) -> str:
        """Configuración de un turno (inicio, fin informativo, horas ordinarias y extras, checks) y su matriz de horas
        por concepto para cada tipo de día.

        Args:
            codigo: Código del turno, p. ej. "D", "N", "A12" o "Z".
        """
        def f():
            ctx.exigir("liquidador.turnos.ver")
            t = ctx.db.scalar(select(LiqTurno).where(LiqTurno.codigo == codigo.strip().upper()))
            if t is None:
                raise LookupError(f"No existe el turno '{codigo}'.")
            matriz = {TIPOS_DIA[d.value]: _etiquetar({c.value: (t.matriz or {}).get(c.value, {}).get(d.value, 0) for c in HourConcept})
                      for d in DayType}
            return {"codigo": t.codigo, "nombre": t.nombre, "hora_inicio": t.hora_inicio, "hora_fin_informativa": t.hora_fin,
                    "horas_ordinarias": float(t.horas_ordinarias), "horas_extras": float(t.horas_extras),
                    "remunerado": t.remunerado, "incapacidad": t.incapacidad, "activo": t.activo,
                    "cuenta_como": CLASES[clase_de(t)], "hora_inicio_nocturna": parametros(ctx.db).hora_inicio_nocturna,
                    "matriz_por_tipo_de_dia": matriz, "enlace": "/liquidador/turnos"}
        return envolver(f)

    @herramienta
    def buscar_personas(texto: str) -> str:
        """Busca personas por cédula o nombre.

        Args:
            texto: Parte de la cédula o del nombre.
        """
        def f():
            ctx.exigir("liquidador.periodos.ver")
            patron = f"%{texto.strip()}%"
            filas = ctx.db.scalars(select(LiqEmpleado).where(or_(LiqEmpleado.documento.ilike(patron), LiqEmpleado.nombre.ilike(patron)))
                                   .order_by(LiqEmpleado.documento).limit(MAX_FILAS))
            return [ctx.persona(e.documento, e.nombre) | {"cargo": e.cargo} for e in filas]
        return envolver(f)

    @herramienta
    def festivos_del_mes(anio: int, mes: int) -> str:
        """Festivos vigentes de un mes (calendario nacional con los ajustes manuales).

        Args:
            anio: Año.
            mes: Mes 1-12.
        """
        def f():
            ctx.exigir("liquidador.turnos.ver")
            return [x for x in svc_festivos.del_anio(ctx.db, anio) if x["fecha"].month == mes]
        return envolver(f)

    return [estado_datos, resumen_quincena, detalle_persona, explicar_turno, buscar_personas, festivos_del_mes]


def responder(db: Session, usuario: Usuario, mensajes: list[dict]) -> ia.Respuesta:
    ctx = Contexto(db, usuario, get_settings().asistente_datos_personales)
    return ia.conversar(INSTRUCCIONES, mensajes, crear_herramientas(ctx))
