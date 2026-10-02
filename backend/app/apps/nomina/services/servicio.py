"""Orquestación: carga de archivos, catálogos dinámicos (códigos y grupos) y recálculo de un periodo."""

from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.apps.nomina.models import (
    ADMINISTRATIVO, CONTRATOS, CUOTAS, EXCLUIDO, MAESTROS, MENSUAL, MODALIDADES, PROGRAMACION, QUINCENAL, UBICACIONES,
    VALIDAR, NomAlerta, NomDecision, NomArchivo, NomCodigo, NomGrupo, NomParametros, NomPeriodo, NomPersona, NomPuestoDecision,
)
from app.apps.nomina.services import lectores, motor

NOMBRES_ARCHIVO = {
    MODALIDADES: "Maestro de modalidades", UBICACIONES: "Ubicaciones y puestos con modalidad", CONTRATOS: "Contratos",
    CUOTAS: "Maestro de cuotas", PROGRAMACION: "Programación del mes", QUINCENAL: "Nómina quincenal", MENSUAL: "Nómina mensual",
}
LECTORES = {
    MODALIDADES: lectores.modalidades, UBICACIONES: lectores.ubicaciones, CONTRATOS: lectores.contratos,
    CUOTAS: lectores.cuotas, PROGRAMACION: lectores.programacion, QUINCENAL: lectores.nomina, MENSUAL: lectores.nomina,
}

CODIGOS_BASE = {
    # código: (descripción, descuenta, vacaciones)
    "Z": ("Descanso", False, False), "L": ("Libre", False, False), "IND": ("Inducción", False, False),
    "IND NOCHE": ("Inducción nocturna", False, False), "IND CORP": ("Inducción corporativa", False, False),
    "VAC": ("Vacaciones", True, True), "PRV": ("Programado a vacaciones", True, True),
    "LNR": ("Licencia no remunerada", True, False), "LRM": ("Licencia remunerada", True, False), "LIC": ("Licencia", True, False),
    "LUT": ("Licencia por luto", True, False), "IEG": ("Incapacidad por enfermedad general", True, False),
    "AT": ("Accidente de trabajo", True, False), "AUS": ("Ausencia", True, False), "PSA": ("Permiso sindical", True, False),
    "PSB": ("Permiso sindical", True, False),
}
GRUPOS_BASE = {
    "OPERATIVOS CON VARIABLE": VALIDAR, "ADMINISTRATIVOS/COMERCIALES": ADMINISTRATIVO,
    "OPERATIVOS ECOPETROL": EXCLUIDO, "OPERATIVOS FULL": EXCLUIDO, "APRENDIZ SENA": EXCLUIDO,
}


class ErrorValidacion(ValueError):
    pass


def parametros(db: Session) -> NomParametros:
    p = db.get(NomParametros, 1)
    if p is None:
        p = NomParametros(id=1)
        db.add(p)
        db.flush()
    return p


def _lista(texto: str) -> set[str]:
    return {x.strip() for x in (texto or "").split(",") if x.strip()}


def parametros_motor(p: NomParametros) -> motor.Parametros:
    return motor.Parametros(
        tolerancia=float(p.tolerancia), smlmv=float(p.smlmv), auxilio_transporte=float(p.auxilio_transporte),
        horas_dia=float(p.horas_dia), solo_primera_quincena=_lista(p.solo_primera_quincena),
        excluidos_base_embargo=_lista(p.excluidos_base_embargo), embargos_sin_minimo=_lista(p.embargos_sin_minimo),
        equivalencias_cuotas=equivalencias(p.equivalencias_cuotas), conceptos_ajuste=_lista(p.conceptos_ajuste),
    )


def equivalencias(texto: str) -> dict[str, list[str]]:
    """'152=129, 160=161+162' → {'152': ['129'], '160': ['161', '162']}"""
    res: dict[str, list[str]] = {}
    for par in (texto or "").split(","):
        if "=" in par:
            cuota, nomina = par.split("=", 1)
            destinos = [x.strip() for x in nomina.split("+") if x.strip()]
            if cuota.strip() and destinos:
                res[cuota.strip()] = destinos
    return res


def sembrar(db: Session) -> None:
    parametros(db)
    existentes = set(db.scalars(select(NomCodigo.codigo)))
    for cod, (desc, descuenta, vac) in CODIGOS_BASE.items():
        if cod not in existentes:
            db.add(NomCodigo(codigo=cod, descripcion=desc, descuenta=descuenta, vacaciones=vac, revisado=True))
    grupos = set(db.scalars(select(NomGrupo.nombre)))
    for nombre, trat in GRUPOS_BASE.items():
        if nombre not in grupos:
            db.add(NomGrupo(nombre=nombre, tratamiento=trat, revisado=True))
    db.flush()


def _registrar_codigos(db: Session, datos: dict) -> int:
    """Códigos nuevos de la programación: se crean con el valor por defecto y quedan por revisar."""
    existentes = set(db.scalars(select(NomCodigo.codigo)))
    nuevos = 0
    for f in datos["filas"]:
        for crudo in f["dias"].values():
            cod = lectores.codigo_programacion(crudo).upper()
            if cod and cod not in existentes:
                d = motor.codigo_por_defecto(crudo)
                es_horario = bool(motor._HORARIO.match(crudo))
                db.add(NomCodigo(codigo=cod[:40], descripcion="Horario" if es_horario else "", descuenta=d.descuenta,
                                 vacaciones=d.vacaciones, revisado=es_horario))
                existentes.add(cod)
                nuevos += 1
    return nuevos


def _registrar_grupos(db: Session, datos: dict) -> int:
    existentes = set(db.scalars(select(NomGrupo.nombre)))
    nuevos = 0
    for c in datos.values():
        if c["grupo"] and c["grupo"] not in existentes:
            db.add(NomGrupo(nombre=c["grupo"][:80], tratamiento=VALIDAR, revisado=False))
            existentes.add(c["grupo"])
            nuevos += 1
    return nuevos


def _registros(tipo: str, datos) -> int:
    if tipo == PROGRAMACION:
        return len(datos["filas"])
    if tipo in (QUINCENAL, MENSUAL):
        return len(datos["personas"])
    return len(datos)


def archivos_del_periodo(periodo: NomPeriodo) -> tuple[str, ...]:
    """Todo periodo exige los maestros, la programación y su nómina (quincenal o mensual)."""
    return (*MAESTROS, periodo.nomina)


def cargar(db: Session, periodo: NomPeriodo, tipo: str, contenido: bytes, nombre: str, usuario_id: int | None) -> dict:
    if tipo not in archivos_del_periodo(periodo):
        raise ErrorValidacion(f"Este periodo es de nómina {periodo.nomina}: no recibe el archivo '{NOMBRES_ARCHIVO.get(tipo, tipo)}'")
    try:
        datos = LECTORES[tipo](contenido)
    except lectores.ErrorArchivo as e:
        raise ErrorValidacion(str(e)) from e
    if tipo == PROGRAMACION:
        desde = datetime.fromisoformat(datos["desde"]).date()
        if (desde.year, desde.month) != (periodo.anio, periodo.mes):
            raise ErrorValidacion(f"La programación es de {desde:%m/%Y} y el periodo es {periodo.mes:02d}/{periodo.anio}")
    extra = {}
    if tipo == PROGRAMACION:
        extra["codigos_nuevos"] = _registrar_codigos(db, datos)
    if tipo == CONTRATOS:
        extra["grupos_nuevos"] = _registrar_grupos(db, datos)
    arch = db.scalar(select(NomArchivo).where(NomArchivo.periodo_id == periodo.id, NomArchivo.tipo == tipo))
    if arch is None:
        arch = NomArchivo(periodo_id=periodo.id, tipo=tipo)
        db.add(arch)
    arch.nombre, arch.datos, arch.registros = nombre[:255], datos, _registros(tipo, datos)
    arch.cargado_en, arch.cargado_por = datetime.now(timezone.utc), usuario_id
    db.flush()
    return {"registros": arch.registros, **extra}


def faltantes(db: Session, periodo: NomPeriodo) -> list[str]:
    tipos = set(db.scalars(select(NomArchivo.tipo).where(NomArchivo.periodo_id == periodo.id)))
    return [NOMBRES_ARCHIVO[t] for t in archivos_del_periodo(periodo) if t not in tipos]


def _claves(db: Session, periodo_id: int) -> set[tuple[str, str, str]]:
    return {(a.cedula, a.tipo, a.referencia) for a in db.scalars(select(NomAlerta).where(NomAlerta.periodo_id == periodo_id))}


def recalcular(db: Session, periodo: NomPeriodo, motivo: str = "Recálculo") -> dict:
    falta = faltantes(db, periodo)
    if falta:
        raise ErrorValidacion("Faltan archivos para calcular: " + ", ".join(falta))
    datos = {a.tipo: a.datos for a in db.scalars(select(NomArchivo).where(NomArchivo.periodo_id == periodo.id))
             if a.tipo in archivos_del_periodo(periodo)}
    codigos = {c.codigo: motor.Codigo(c.descuenta, c.vacaciones) for c in db.scalars(select(NomCodigo))}
    grupos = {g.nombre: g.tratamiento for g in db.scalars(select(NomGrupo))}
    aprobados = {(d.ubicacion, d.puesto) for d in db.scalars(select(NomPuestoDecision).where(NomPuestoDecision.estado == "aprobado"))}
    try:
        r = motor.calcular(periodo.anio, periodo.mes, datos, codigos, grupos, aprobados, parametros_motor(parametros(db)))
    except ValueError as e:
        raise ErrorValidacion(str(e)) from e

    anteriores = _claves(db, periodo.id)
    db.execute(delete(NomAlerta).where(NomAlerta.periodo_id == periodo.id))
    db.execute(delete(NomPersona).where(NomPersona.periodo_id == periodo.id))
    db.add_all(NomPersona(periodo_id=periodo.id, nomina=x["nomina"], cedula=x["cedula"], nombre=x["nombre"][:200],
                          grupo=x["grupo"][:80], alertas=x["alertas"], detalle=x) for x in r.personas)
    # El historial compara solo alertas reales (las informativas de vacaciones no son errores)
    anteriores = {k for k in anteriores if k[1] not in motor.INFORMATIVAS}
    actuales = {(a.cedula, a.tipo, a.referencia[:40]) for a in r.alertas if not a.informativa}
    primera = not periodo.historial
    db.add_all(NomAlerta(periodo_id=periodo.id, nomina=a.nomina, cedula=a.cedula, nombre=a.nombre[:200], tipo=a.tipo,
                         referencia=a.referencia[:40], severidad=a.severidad, mensaje=a.mensaje, esperado=a.esperado,
                         pagado=a.pagado, datos=a.datos,
                         nueva=not primera and not a.informativa and (a.cedula, a.tipo, a.referencia[:40]) not in anteriores)
               for a in r.alertas)
    # Revisión: qué se corrigió, qué persiste y qué apareció frente al cálculo anterior
    corregidas = anteriores - actuales
    marcadas_error = {(d.cedula, d.tipo, d.referencia) for d in db.scalars(select(NomDecision).where(
        NomDecision.periodo_id == periodo.id, NomDecision.estado == "error"))}
    nomina = datos.get(periodo.nomina) or {}
    periodo.historial = [*periodo.historial, {
        "n": len(periodo.historial) + 1, "fecha": datetime.now(timezone.utc).isoformat(), "motivo": motivo,
        "archivo_nomina": next((a.nombre for a in db.scalars(select(NomArchivo).where(
            NomArchivo.periodo_id == periodo.id, NomArchivo.tipo == periodo.nomina))), ""),
        "personas": len(nomina.get("personas", {})), "alertas": len(actuales),
        "corregidas": 0 if primera else len(corregidas), "persisten": 0 if primera else len(actuales & anteriores),
        "nuevas": 0 if primera else len(actuales - anteriores),
        "errores_corregidos": len(corregidas & marcadas_error),
    }]
    periodo.resumen = {**r.resumen, "sin_modalidad_lista": r.puestos_sin_modalidad}
    periodo.calculado_en = datetime.now(timezone.utc)
    db.flush()
    return r.resumen
