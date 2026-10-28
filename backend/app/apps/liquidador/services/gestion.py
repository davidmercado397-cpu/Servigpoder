"""Gestión humana de SERA: incapacidades (con su diagnóstico CIE-10), restricciones médicas y casos jurídicos
(derechos de petición, tutelas, demandas). Es un repositorio de consulta: nada de esto afecta la nómina.

Importación del formato de caracterización de ausentismo (FT-SST-023):
- Hojas «REGISTRO INCAPACIDADES …»: una fila por incapacidad. La misma incapacidad (documento, fechas y CIE) puede
  estar en dos hojas (el histórico y el año): se carga una vez. Los días se calculan con las fechas.
- «RECOMENDACIONES O RESTRICCIONES»: restricciones con su vigencia y, en otro bloque, los casos oncológicos.
- «DERECHOS, TUTELAS, DEMANDAS»: cada caso con sus fechas de contestación como seguimiento.
Las incapacidades prolongadas no se importan: se calculan sumando cada incapacidad con sus prórrogas.
Volver a importar actualiza lo que ya existe (no duplica ni borra los soportes adjuntos). El archivo no se guarda.
"""

import csv
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.apps.liquidador.models import LiqCaso, LiqCasoActuacion, LiqCie, LiqEmpleado, LiqIncapacidad, LiqRestriccion
from app.apps.liquidador.services.personal import ErrorArchivo, Indice, _Informe, _abrir, _fecha, _norm, _texto, documento

DATOS_CIE = Path(__file__).resolve().parent.parent / "datos" / "cie10.csv"

NOVEDADES = {"incapacidad": "Incapacidad", "licencia_maternidad": "Licencia de maternidad", "licencia_paternidad": "Licencia de paternidad",
             "calamidad": "Calamidad", "otra": "Otra"}
ORIGENES = {"enfermedad_general": "Enfermedad general", "accidente_trabajo": "Accidente de trabajo",
            "enfermedad_laboral": "Enfermedad laboral", "accidente_transito": "Accidente de tránsito"}
SOPORTES = {"fisico": "Física", "escaneado": "Escaneada", "virtual": "Virtual"}
TIPOS_RESTRICCION = {"restriccion": "Restricción", "recomendacion": "Recomendación", "oncologico": "Caso oncológico"}
TIPOS_CASO = {"derecho_peticion": "Derecho de petición", "tutela": "Tutela", "desacato": "Incidente de desacato", "demanda": "Demanda",
              "orden_judicial": "Orden judicial", "acoso_laboral": "Acoso laboral", "otro": "Otro"}
ESTADOS_CASO = {"abierto": "Abierto", "contestado": "Contestado", "cerrado": "Cerrado"}

# Días acumulados (incapacidad inicial + prórrogas) desde los que se avisa. Una incapacidad continúa la anterior
# (prórroga) si empieza a más tardar 30 días después de que esta terminó y es por la misma enfermedad: marcada como
# prórroga o con la misma categoría CIE (los 3 primeros caracteres: T240 y T242). Decreto 1427 de 2022.
ALERTAS_ACUMULADO = ((540, "Supera 540 días acumulados"), (180, "Supera 180 días acumulados"))
PAUSA_PRORROGA = 30


# --- Catálogo CIE-10 ---

def sembrar_cie(db: Session) -> None:
    """Carga el catálogo la primera vez que se usa (no en el arranque: son 12.000 códigos)."""
    if db.scalar(select(LiqCie.codigo).limit(1)) is not None:
        return
    with DATOS_CIE.open(encoding="utf-8") as f:
        filas = list(csv.reader(f))[1:]
    db.add_all(LiqCie(codigo=c, descripcion=d[:300]) for c, d in filas)
    db.flush()


def codigos_cie(texto: object) -> list[str]:
    """Códigos de una celda («S400,S220», «J00X», «y09»): en mayúsculas y sin la X de relleno (J00X = J00)."""
    codigos = []
    for parte in re.split(r"[,;/ ]+", str(texto or "").upper()):
        c = re.sub(r"[^A-Z0-9]", "", parte)
        if len(c) == 4 and c.endswith("X"):
            c = c[:3]
        if c and c not in codigos:
            codigos.append(c)
    return codigos


def catalogo(db: Session, codigos: set[str]) -> dict[str, str]:
    if not codigos:
        return {}
    sembrar_cie(db)
    return dict(db.execute(select(LiqCie.codigo, LiqCie.descripcion).where(LiqCie.codigo.in_(codigos))).all())


# --- Prórrogas y días acumulados ---

@dataclass
class Acumulado:
    dias: int  # días de la incapacidad inicial más sus prórrogas hasta este registro
    inicio: date  # fecha de inicio de la incapacidad inicial
    alerta: str | None


def acumulados(incapacidades: list[LiqIncapacidad]) -> dict[int, Acumulado]:
    """Por cada incapacidad, los días acumulados de su cadena (inicial + prórrogas) hasta ella. Los días que se cruzan
    entre dos incapacidades cuentan una vez. Las licencias no se encadenan."""
    por_persona: dict[str, list[LiqIncapacidad]] = defaultdict(list)
    for x in incapacidades:
        if x.novedad == "incapacidad":
            por_persona[x.documento].append(x)
    out: dict[int, Acumulado] = {}
    for lista in por_persona.values():
        total, inicio, fin, categorias = 0, None, None, set()
        for x in sorted(lista, key=lambda x: (x.desde, x.id)):
            propias = {c[:3] for c in (x.cie or "").split(",") if c}
            sigue = fin is not None and x.desde <= fin + timedelta(days=PAUSA_PRORROGA + 1) and (x.prorroga or propias & categorias)
            if sigue:
                total += max(0, (x.hasta - max(x.desde, fin + timedelta(days=1))).days + 1)
                fin, categorias = max(fin, x.hasta), categorias | propias
            else:
                total, inicio, fin, categorias = x.dias, x.desde, x.hasta, propias
            out[x.id] = Acumulado(total, inicio, next((t for d, t in ALERTAS_ACUMULADO if total > d), None))
    return out


def empleado_de(db: Session, doc: str) -> LiqEmpleado | None:
    return Indice(db.scalars(select(LiqEmpleado))).buscar(doc)


# --- Importación ---

def _hoja(libro, prefijo: str):
    return [h for h in libro.worksheets if _norm(h.title).startswith(prefijo)]


def _columnas(fila: tuple, mapa: tuple[tuple[str, str], ...]) -> dict[str, int]:
    """Encabezado → campo (por prefijo normalizado). Si un encabezado se repite, el segundo va a `<campo>_2`."""
    cols: dict[str, int] = {}
    for i, celda in enumerate(fila):
        clave = _norm(celda)
        for prefijo, campo in mapa:
            if clave.startswith(prefijo):
                cols[campo if campo not in cols else f"{campo}_2"] = i
                break
    return cols


def _valor(fila: tuple, cols: dict[str, int], campo: str):
    i = cols.get(campo)
    return fila[i] if i is not None and i < len(fila) else None


_COL_INCAPACIDAD = (
    ("IDENTIFICACION", "documento"), ("CEDULA", "documento"), ("NOMBRE", "nombre"), ("PUESTO", "puesto"), ("NOVEDAD", "novedad"),
    ("ORIGEN", "origen"), ("INICIAL", "tipo"), ("FECHA DE INICIO", "desde"), ("FECHA DE FIN", "hasta"), ("DIAS", "dias"),
    ("EPS", "entidad"), ("CODIGO", "cie"), ("DIAGNOSTICO", "diagnostico"), ("OBSERVACION", "observacion"),
)
_COL_RESTRICCION = (("CEDULA", "documento"), ("IDENTIFICACION", "documento"), ("NOMBRE", "nombre"), ("PUESTO", "puesto"),
                    ("NOVEDAD", "novedad"), ("FECHA DE INICIO", "desde"), ("FECHA DE FIN", "hasta"), ("DIAGNOSTICO", "diagnostico"))
_COL_CASO = (("CC", "documento"), ("CEDULA", "documento"), ("NOMBRE", "nombre"), ("ENTIDAD", "asunto"), ("FECHA RECIBIDO", "recibido"),
             ("FECHA DE CONTESTACION", "contestacion"), ("MEDIO", "medio"), ("CORREO", "contacto"), ("OBSERVACION", "observacion"))


def novedad_de(texto: object) -> str | None:
    t = _norm(texto)
    if not t:
        return "incapacidad"
    for clave, novedad in (("MATERNIDAD", "licencia_maternidad"), ("PATERNIDAD", "licencia_paternidad"), ("CALAMIDAD", "calamidad"),
                           ("NCAPACIDAD", "incapacidad")):
        if clave in t:
            return novedad
    return None


def origen_de(texto: object) -> tuple[str | None, bool]:
    """(origen, reconocido). Vacío es válido (licencias)."""
    t = re.sub(r"[^A-Z]", "", _norm(texto))
    if not t:
        return None, True
    if t in ("EG", "COMUN", "ENFERMEDADGENERAL"):
        return "enfermedad_general", True
    if t in ("AT", "ACCIDENTEDETRABAJO", "ACCIDENTELABORAL"):
        return "accidente_trabajo", True
    if t in ("EL", "ENFERMEDADLABORAL"):
        return "enfermedad_laboral", True
    if "TRANSITO" in t or t == "SOAT":
        return "accidente_transito", True
    return None, False


def tipo_caso(asunto: str) -> str:
    t = _norm(asunto)
    for clave, tipo in (("DESACATO", "desacato"), ("TUTELA", "tutela"), ("ACOSO", "acoso_laboral"), ("PETICION", "derecho_peticion"),
                        ("DEMANDA", "demanda"), ("JUZGADO", "orden_judicial"), ("EMBARGO", "orden_judicial")):
        if clave in t:
            return tipo
    return "otro"


_FECHA_TEXTO = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{2,4})")


def fechas_en(valor: object) -> list[date]:
    if isinstance(valor, datetime):
        return [valor.date()]
    if isinstance(valor, date):
        return [valor]
    fechas = []
    for d, m, a in _FECHA_TEXTO.findall(str(valor or "")):
        anio = int(a) + (2000 if len(a) == 2 else 0)
        try:
            fechas.append(date(anio, int(m), int(d)))
        except ValueError:
            continue
    return fechas


def importar_ausentismo(db: Session, contenido: bytes, salud: bool = True, juridico: bool = True, usuario_id: int | None = None) -> dict:
    libro = _abrir(contenido)
    informe = _Informe()
    indice = Indice(db.scalars(select(LiqEmpleado)))
    resumen: dict = {"hallazgos": informe.hallazgos}

    def persona(hoja: str, num: int, fila: tuple, cols: dict) -> tuple[str | None, LiqEmpleado | None, str]:
        doc, _ = documento(_valor(fila, cols, "documento"))
        if doc is None:
            return None, None, ""
        e = indice.buscar(doc)
        nombre = _texto(_valor(fila, cols, "nombre"), 200) or (e.nombre if e else doc)
        return (e.documento if e else doc), e, nombre

    def puesto(valor, e: LiqEmpleado | None) -> str | None:
        p = _texto(valor, 200)
        return (e.puesto if e else None) if not p or p.startswith("#") else p

    if salud:
        resumen["incapacidades"] = _importar_incapacidades(db, libro, informe, persona, puesto, usuario_id)
        resumen["restricciones"] = _importar_restricciones(db, libro, informe, persona, puesto, usuario_id)
    if juridico:
        resumen["casos"] = _importar_casos(db, libro, informe, persona, usuario_id)
    if not any(v["leidas"] for k, v in resumen.items() if k != "hallazgos"):
        raise ErrorArchivo("El archivo no tiene las hojas del formato de ausentismo (REGISTRO INCAPACIDADES, "
                           "RECOMENDACIONES O RESTRICCIONES o DERECHOS, TUTELAS, DEMANDAS) con datos.")
    db.flush()
    return resumen


def _importar_incapacidades(db, libro, informe, persona, puesto, usuario_id) -> dict:
    hojas = _hoja(libro, "REGISTRO INCAPACIDADES")
    existentes = {(x.documento, x.desde, x.hasta, x.cie or ""): x for x in db.scalars(select(LiqIncapacidad))}
    vistas: dict[tuple, tuple[str, int]] = {}
    cuenta = {"leidas": 0, "creadas": 0, "actualizadas": 0, "repetidas": 0, "en_varias_hojas": 0}
    todos_cie: set[str] = set()
    pendientes: list[tuple[LiqIncapacidad, str, int, list[str]]] = []
    marcadas_prorroga: set[tuple] = set()
    for hoja in hojas:
        filas = hoja.iter_rows(values_only=True)
        cols: dict[str, int] = {}
        for num, fila in enumerate(filas, start=1):
            if not cols:
                if any(_norm(c).startswith("IDENTIFICACION") for c in fila if c is not None):
                    cols = _columnas(fila, _COL_INCAPACIDAD)
                continue
            doc, e, nombre = persona(hoja.title, num, fila, cols)
            if doc is None:
                continue
            cuenta["leidas"] += 1
            desde, ok_d = _fecha(_valor(fila, cols, "desde"))
            hasta, ok_h = _fecha(_valor(fila, cols, "hasta"))
            if not desde or not hasta or not ok_d or not ok_h:
                informe(hoja.title, num, doc, "Sin fecha de inicio o de fin válida: no se cargó")
                continue
            if hasta < desde:
                informe(hoja.title, num, doc, "La fecha de fin es anterior a la de inicio: no se cargó")
                continue
            cie = codigos_cie(_valor(fila, cols, "cie"))
            clave = (doc, desde, hasta, ",".join(cie))
            if clave in vistas:
                hoja_ant, fila_ant = vistas[clave]
                if hoja_ant == hoja.title:
                    cuenta["repetidas"] += 1
                    informe(hoja.title, num, doc, f"Repetida: es la misma de la fila {fila_ant} (mismas fechas y CIE); se cargó una vez")
                else:
                    cuenta["en_varias_hojas"] += 1
                    if "PRORROGA" in _norm(_valor(fila, cols, "tipo")):
                        marcadas_prorroga.add(clave)
                continue
            vistas[clave] = (hoja.title, num)

            dias = (hasta - desde).days + 1
            dias_excel = _valor(fila, cols, "dias")
            if isinstance(dias_excel, (int, float)) and int(dias_excel) != dias:
                informe(hoja.title, num, doc, f"El Excel dice {int(dias_excel)} días y por las fechas son {dias}: se usan las fechas")
            novedad = novedad_de(_valor(fila, cols, "novedad"))
            if novedad is None:
                informe(hoja.title, num, doc, f"Novedad «{_texto(_valor(fila, cols, 'novedad'))}» no reconocida: quedó como «Otra»")
                novedad = "otra"
            origen, reconocido = origen_de(_valor(fila, cols, "origen"))
            if not reconocido:
                informe(hoja.title, num, doc, f"Origen «{_texto(_valor(fila, cols, 'origen'))}» no reconocido: quedó vacío")
            obs = _texto(_valor(fila, cols, "observacion"), 300)
            soporte = {"ESCANEADA": "escaneado", "FISICA": "fisico", "VIRTUAL": "virtual"}.get(_norm(obs))
            if soporte or _norm(obs) in ("NUEVO", "PRORROGA"):
                obs = None
            x = existentes.get(clave)
            if x is None:
                x = LiqIncapacidad(documento=doc, desde=desde, hasta=hasta, origen_registro="libro", creado_por=usuario_id)
                db.add(x)
                cuenta["creadas"] += 1
            else:
                cuenta["actualizadas"] += 1
            x.nombre, x.empleado_id, x.puesto = nombre, e.id if e else None, puesto(_valor(fila, cols, "puesto"), e)
            x.novedad, x.origen, x.prorroga, x.dias = novedad, origen, "PRORROGA" in _norm(_valor(fila, cols, "tipo")), dias
            x.entidad = _texto(_norm(_valor(fila, cols, "entidad")), 80)
            x.cie, x.diagnostico = ",".join(cie)[:60] or None, _texto(_valor(fila, cols, "diagnostico"), 300)
            x.soporte, x.observacion = soporte or x.soporte, obs
            todos_cie.update(cie)
            pendientes.append((x, hoja.title, num, cie))
    # Diagnósticos: los códigos que no están en el catálogo se reportan; sin texto, se toma el del catálogo
    nombres = catalogo(db, todos_cie)
    for x, hoja, num, cie in pendientes:
        x.prorroga = x.prorroga or (x.documento, x.desde, x.hasta, ",".join(cie)) in marcadas_prorroga
        faltan = [c for c in cie if c not in nombres]
        if faltan:
            informe(hoja, num, x.documento, f"Código CIE {', '.join(faltan)} no está en el catálogo CIE-10")
        if not cie:
            informe(hoja, num, x.documento, "Sin código CIE")
        if not x.diagnostico and cie and cie[0] in nombres:
            x.diagnostico = nombres[cie[0]]
    return cuenta


def _importar_restricciones(db, libro, informe, persona, puesto, usuario_id) -> dict:
    cuenta = {"leidas": 0, "creadas": 0, "actualizadas": 0}
    existentes = {(x.documento, x.tipo, x.desde): x for x in db.scalars(select(LiqRestriccion))}
    for hoja in _hoja(libro, "RECOMENDACIONES"):
        cols: dict[str, int] = {}
        tipo_bloque = "restriccion"
        for num, fila in enumerate(hoja.iter_rows(values_only=True), start=1):
            primera = _norm(fila[0] if fila else None)
            if "ONCOLOG" in primera:
                tipo_bloque, cols = "oncologico", {}
                continue
            if primera in ("CEDULA", "IDENTIFICACION", "CC"):
                cols = _columnas(fila, _COL_RESTRICCION)
                continue
            if not cols:
                continue
            doc, e, nombre = persona(hoja.title, num, fila, cols)
            if doc is None:
                continue
            cuenta["leidas"] += 1
            tipo = tipo_bloque
            if tipo == "restriccion" and "RECOMENDACION" in _norm(_valor(fila, cols, "novedad")):
                tipo = "recomendacion"
            desde, _ = _fecha(_valor(fila, cols, "desde"))
            hasta, _ = _fecha(_valor(fila, cols, "hasta"))
            x = existentes.get((doc, tipo, desde))
            if x is None:
                x = LiqRestriccion(documento=doc, tipo=tipo, desde=desde, origen_registro="libro", creado_por=usuario_id)
                db.add(x)
                existentes[(doc, tipo, desde)] = x
                cuenta["creadas"] += 1
            else:
                cuenta["actualizadas"] += 1
            diagnostico = _texto(_valor(fila, cols, "diagnostico"), 300)
            cie = codigos_cie(diagnostico) if diagnostico and re.fullmatch(r"[A-Za-z]\d{2,3}[Xx]?([,; ]+[A-Za-z]\d{2,3}[Xx]?)*", diagnostico) else []
            x.nombre, x.empleado_id, x.puesto, x.hasta = nombre, e.id if e else None, puesto(_valor(fila, cols, "puesto"), e), hasta
            x.cie = ",".join(cie) or x.cie
            x.diagnostico = None if cie else diagnostico or x.diagnostico
            x.observacion = _texto(_valor(fila, cols, "novedad_2"), 300) or x.observacion
            if cie:
                nombres = catalogo(db, set(cie))
                x.diagnostico = x.diagnostico or nombres.get(cie[0])
    return cuenta


def _importar_casos(db, libro, informe, persona, usuario_id) -> dict:
    cuenta = {"leidas": 0, "creadas": 0, "actualizadas": 0, "abiertos": 0}
    existentes = {(x.documento, x.asunto, x.recibido): x for x in db.scalars(select(LiqCaso))}
    for hoja in _hoja(libro, "DERECHOS"):
        cols: dict[str, int] = {}
        for num, fila in enumerate(hoja.iter_rows(values_only=True), start=1):
            if _norm(fila[0] if fila else None) in ("CC", "CEDULA", "IDENTIFICACION"):
                cols = _columnas(fila, _COL_CASO)
                continue
            if not cols:
                continue
            doc, e, nombre = persona(hoja.title, num, fila, cols)
            if doc is None:
                continue
            cuenta["leidas"] += 1
            asunto = _texto(_valor(fila, cols, "asunto"), 300) or "Sin asunto"
            recibido, ok_r = _fecha(_valor(fila, cols, "recibido"))
            if recibido is None or not ok_r:
                informe(hoja.title, num, doc, "Sin fecha de recibido válida: no se cargó")
                continue
            x = existentes.get((doc, asunto, recibido))
            if x is None:
                x = LiqCaso(documento=doc, asunto=asunto, recibido=recibido, origen_registro="libro", creado_por=usuario_id)
                db.add(x)
                existentes[(doc, asunto, recibido)] = x
                cuenta["creadas"] += 1
            else:
                cuenta["actualizadas"] += 1
            x.nombre, x.empleado_id, x.tipo = nombre, e.id if e else None, tipo_caso(asunto)
            x.contacto = _texto(_valor(fila, cols, "contacto"), 200)
            medio = _texto(_valor(fila, cols, "medio"), 60)
            contestacion = _valor(fila, cols, "contestacion")
            fechas = fechas_en(contestacion)
            notas = [t for t in (_texto(_valor(fila, cols, "observacion"), 2000),) if t]
            texto_contestacion = _texto(contestacion, 300) if not isinstance(contestacion, (datetime, date)) else None
            if not fechas and texto_contestacion and _norm(texto_contestacion) != "ABIERTO":
                notas.insert(0, texto_contestacion)
            x.observacion = "\n".join(notas) or None
            ya = {(a.fecha, a.descripcion) for a in x.actuaciones}
            for f in fechas:
                if (f, "Contestación") not in ya:
                    x.actuaciones.append(LiqCasoActuacion(fecha=f, descripcion="Contestación", medio=medio))
            if x.estado != "cerrado":
                x.estado = "contestado" if x.actuaciones else "abierto"
            cuenta["abiertos"] += x.estado == "abierto"
    return cuenta
