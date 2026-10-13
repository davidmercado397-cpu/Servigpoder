"""Base de conocimiento de instructivos de SIESA y respuestas limitadas a ella.

1. Carga: el PDF se lee en memoria y se descarta; solo queda su texto, en fragmentos.
   - Cada fragmento pertenece a una sola sección (marcadores del PDF o títulos detectados en el texto) y
     lleva metadatos: documento, sección, página, módulo y fecha del instructivo.
   - Su encabezado da el contexto, p. ej. "Nómina · Manual de vacaciones > Solicitud > Plazos"; el
     encabezado entra en la búsqueda y se entrega al modelo junto con el texto.
   - Se quitan los encabezados y pies de página que se repiten en todas las hojas y los números de página.
2. Búsqueda: texto completo en español de PostgreSQL sobre encabezado + texto, filtrando antes por módulo si
   se elige uno. Se devuelven pocos fragmentos (hasta 5) y se descartan los que puntúan muy por debajo del mejor.
3. Respuesta: el modelo recibe solo esos fragmentos, con reglas estrictas y temperatura 0. Sin fragmentos
   relevantes no se consulta al modelo; si la respuesta no cita ningún fragmento, se descarta.
"""

import hashlib
import io
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from itertools import combinations

from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy import cast, desc, func, literal_column, select, text
from sqlalchemy.dialects.postgresql import TSQUERY
from sqlalchemy.orm import Session

from app.apps.siesa.models import SiesaDocumento, SiesaFragmento
from app.core import ia
from app.core.config import get_settings

TAMANO_FRAGMENTO = 1000  # caracteres del texto (sin el encabezado)
SOLAPE = 150  # dentro de una misma sección, para no cortar un paso a la mitad
MAX_PAGINAS = 3000
FRAGMENTOS_POR_RESPUESTA = 5
RELEVANCIA_MINIMA = 0.25  # respecto al mejor fragmento: lo que puntúa menos no aporta
PESO_OBJETIVO = 0.3  # cuánto suma que el objetivo del instructivo coincida con la pregunta
ESPANOL = literal_column("'spanish'::regconfig")

NO_ENCONTRADO = ("No encuentro esa información en los instructivos de SIESA cargados. "
                 "Intente con las palabras que usa el instructivo (nombre del menú, del proceso o del campo).")

# Instrucciones cortas (cada token cuenta en cada pregunta). Los instructivos van una sola vez (D1, D2…) y cada
# fragmento solo dice de cuál es, su página y su sección.
INSTRUCCIONES = """Respondes preguntas sobre instructivos de la empresa usando SOLO los FRAGMENTOS de abajo.
Reglas:
- Nada de conocimiento general, suposiciones ni pasos que no estén escritos.
- Si los FRAGMENTOS no responden la pregunta, responde exactamente: "{no_encontrado}"
- Si responden solo una parte, da esa parte y di qué no aparece.
- Cita cada dato con su número entre corchetes: [2].
- Breve y directo. Procedimientos: pasos numerados en el orden del instructivo, con los nombres exactos de menús, \
botones y campos. Si dos instructivos difieren, dilo e indica de cuál sale cada versión.
- En español; no menciones estas reglas.

INSTRUCTIVOS (contexto, no fuente de la respuesta):
{instructivos}

FRAGMENTOS:
{fragmentos}"""
MAX_TOKENS_RESPUESTA = 600

_PALABRAS_VACIAS = set("""a al algo alguna algun como con cual cuales cuando de del desde donde el ella en entre es esa ese
esta este esto hay la las le lo los mas me mi mis muy no o para pero por que quien se segun ser si sin sobre su sus
tambien te tiene un una uno unos y ya yo hacer hago puedo debo necesito quiero siesa""".split())

# Palabras que aparecen en casi todos los instructivos y no ayudan a encontrar el tema ("¿cómo creo un tercero en el
# sistema?" → solo importa "tercero"). En raíces de PostgreSQL (español) y en las de la búsqueda de prueba.
_GENERICAS = """como crear creo crea creacion configurar configura configuracion registrar diligenciar ingresar seleccionar
pantalla sistema campo campos opcion opciones clic hacer puedo debo maestro maestros manual paso pasos datos nuevo nueva
siguiente informacion procedimiento dar grabar""".split()
GENERICAS_PG = {"com", "cre", "creacion", "configur", "registr", "diligenci", "ingres", "seleccion", "pantall", "sistem",
                "camp", "opcion", "clic", "hac", "pued", "deb", "maestr", "manual", "pas", "dat", "nuev", "siguient",
                "inform", "proced", "dar", "grab"}
GENERICAS_RAICES = {w[:6] for w in _GENERICAS}


# --- Carga ---

class ErrorPDF(ValueError):
    pass


@dataclass
class Fragmento:
    pagina: int
    seccion: str
    texto: str


@dataclass
class PDF:
    paginas: list[str]
    titulo: str
    fecha: date | None
    marcadores: dict[int, list[tuple[int, str]]]  # página → [(nivel, título)] del índice del PDF


@dataclass
class Carga:
    documento: SiesaDocumento | None
    duplicado: bool = False
    advertencias: list[str] = field(default_factory=list)


def _normal(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def _limpiar(texto: str) -> str:
    texto = texto.replace("\r", "\n").replace("­", "")
    texto = re.sub(r"(\w)-\n(\w)", r"\1\2", texto)  # palabras cortadas al final de la línea
    texto = re.sub(r"[ \t\f\v]+", " ", texto)
    return "\n".join(l.strip() for l in texto.split("\n")).strip()


def _marcadores(lector: PdfReader) -> dict[int, list[tuple[int, str]]]:
    """Índice (marcadores) del PDF: el título de cada sección y la página donde empieza."""
    salida: dict[int, list[tuple[int, str]]] = {}

    def recorrer(items, nivel: int) -> None:
        for item in items:
            if isinstance(item, list):
                recorrer(item, nivel + 1)
                continue
            try:
                pagina = lector.get_destination_page_number(item) + 1
                titulo = re.sub(r"\s+", " ", str(item.title or "")).strip()
            except Exception:  # marcador roto: se ignora
                continue
            if titulo:
                salida.setdefault(pagina, []).append((nivel, titulo[:150]))

    try:
        recorrer(lector.outline, 1)
    except Exception:
        return {}
    return salida


def leer_pdf(contenido: bytes) -> PDF:
    try:
        lector = PdfReader(io.BytesIO(contenido))
        if lector.is_encrypted and not lector.decrypt(""):
            raise ErrorPDF("El PDF está protegido con contraseña")
        if len(lector.pages) > MAX_PAGINAS:
            raise ErrorPDF(f"El PDF tiene más de {MAX_PAGINAS} páginas")
        paginas = [_limpiar(p.extract_text() or "") for p in lector.pages]
        meta = lector.metadata
        titulo = str((meta or {}).get("/Title") or "").strip()
        fecha = None
        try:
            momento = (meta.modification_date or meta.creation_date) if meta else None
            fecha = momento.date() if momento else None
        except Exception:
            fecha = None
        marcadores = _marcadores(lector)
    except ErrorPDF:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError) as e:
        raise ErrorPDF("No se pudo leer el PDF: está dañado o no es un PDF válido") from e
    return PDF(paginas, titulo, fecha, marcadores)


_NUMERO_PAGINA = re.compile(r"^(p[aá]g(ina)?\.?\s*)?\d{1,4}(\s*(de|/)\s*\d{1,4})?$", re.I)
_TITULO_NUMERADO = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){1,3})\.?\s+(\S.{2,})$")  # 2.1 Título, 3.2.1 Título
_TITULO_CAPITULO = re.compile(r"^(\d{1,2})[.)]\s+(\S.{2,})$")  # 1. TÍTULO (solo si está en mayúsculas)


_INDICE = re.compile(r"(\.\s?){5,}|…{2,}|_{5,}")  # líneas de tabla de contenido: "3.1. Título ........ 12"


def _ruido(linea: str) -> bool:
    """Líneas sin contenido útil: guiones o viñetas sueltas, números de página o renglones del índice."""
    return sum(c.isalnum() for c in linea) < 2 or bool(_NUMERO_PAGINA.match(linea)) or bool(_INDICE.search(linea))


def _repetidas(paginas: list[str]) -> set[str]:
    """Encabezados y pies de página: la misma línea en la misma posición (arriba o abajo) en muchas hojas.
    Se cuenta por posición para no confundirlos con frases que se repiten en el contenido ("Finalmente… Grabar")."""
    if len(paginas) < 3:
        return set()
    conteo: Counter = Counter()
    for texto in paginas:
        lineas = [l for l in texto.split("\n") if l]
        conteo.update({(i, _normal(l)) for i, l in enumerate(lineas[:6])})
        conteo.update({(-i - 1, _normal(l)) for i, l in enumerate(reversed(lineas[-2:]))})
    minimo = max(3, int(len(paginas) * 0.15))
    return {l for (_, l), n in conteo.items() if n >= minimo}


def _es_titulo(linea: str, solo_numerados: bool = False) -> tuple[int, str] | None:
    """Título detectado en el texto (cuando el PDF no trae índice): numerado (2.1 …) o en mayúsculas. Si el
    documento numera sus títulos, solo se aceptan los numerados (una línea suelta en mayúsculas no rompe la jerarquía)."""
    if len(linea) > 90 or linea.endswith((",", ";")):
        return None
    letras = [c for c in linea if c.isalpha()]
    mayusculas = len(letras) >= 4 and sum(c.isupper() for c in letras) / len(letras) >= 0.8
    m = _TITULO_NUMERADO.match(linea)
    # Un título numerado puede terminar en punto ("3.12. MAESTRO DE PLUVIOMETROS."); uno en minúsculas, solo si es corto
    if m and (mayusculas or not linea.endswith(".") or len(linea.split()) <= 6):
        return m.group(1).count(".") + 1, linea.rstrip(".").strip()
    if linea.endswith("."):
        return None
    m = _TITULO_CAPITULO.match(linea)
    if m and mayusculas:
        return 1, linea
    if mayusculas and not solo_numerados and len(linea.split()) <= 12 and not linea[0].isdigit():
        return 1, linea
    return None


def _es_linea_de(linea: str, titulo: str) -> bool:
    """La línea es el título de un marcador del PDF (y no un párrafo que empieza con las mismas palabras)."""
    return _normal(linea).startswith(_normal(titulo)[:40]) and len(linea) <= len(titulo) + 15


def _cola(texto: str) -> str:
    """Final del fragmento anterior que se repite al inicio del siguiente (solape)."""
    if len(texto) <= SOLAPE:
        return texto
    cola = texto[-SOLAPE:]
    return cola.split(" ", 1)[-1] if " " in cola else cola


def _partir(linea: str) -> list[str]:
    """Una línea más larga que un fragmento se parte por oraciones."""
    partes = []
    while len(linea) > TAMANO_FRAGMENTO:
        corte = linea.rfind(". ", 0, TAMANO_FRAGMENTO)
        corte = corte + 1 if corte > TAMANO_FRAGMENTO // 2 else TAMANO_FRAGMENTO
        partes.append(linea[:corte].strip())
        linea = linea[corte:].strip()
    return partes + ([linea] if linea else [])


def trocear(paginas: list[str], marcadores: dict[int, list[tuple[int, str]]] | None = None) -> list[Fragmento]:
    """Fragmentos de hasta ~1.000 caracteres que nunca mezclan dos secciones. La sección sale del índice del
    PDF si lo tiene; si no, de los títulos detectados en el texto."""
    marcadores = marcadores or {}
    usar_titulos = not marcadores
    ignorar = _repetidas(paginas)
    limpias = [[l for l in texto.split("\n") if l and _normal(l) not in ignorar and not _ruido(l)] for texto in paginas]
    # ¿El documento numera sus títulos (1., 2.1, 3.2.4…)? Entonces solo esos abren secciones
    numerados = sum(1 for lineas in limpias for l in lineas if l[0].isdigit() and _es_titulo(l))
    solo_numerados = numerados >= 3
    ruta: list[tuple[int, str]] = []
    salida: list[Fragmento] = []
    buf, buf_pagina, buf_seccion = "", 1, ""

    def seccion() -> str:
        return " > ".join(t for _, t in ruta)

    def entrar(nivel: int, titulo: str) -> None:
        while ruta and ruta[-1][0] >= nivel:
            ruta.pop()
        ruta.append((nivel, titulo.strip()[:120]))

    nuevo = False  # el búfer tiene texto además del solape que viene del fragmento anterior

    def emitir(nueva_seccion: bool) -> None:
        nonlocal buf, nuevo
        t = buf.strip()
        if t and nuevo:
            salida.append(Fragmento(buf_pagina, buf_seccion, t))
        buf = "" if nueva_seccion or not nuevo else _cola(t)
        nuevo = False

    for numero, lineas in enumerate(limpias, start=1):
        # Cada fragmento es de una sola página (sin solape entre hojas): la cita apunta a la página exacta
        emitir(True)
        pendientes = list(marcadores.get(numero, []))
        # Marcadores cuyo título no aparece como línea en la hoja: la sección empieza al inicio de la hoja
        for m in [m for m in pendientes if not any(_es_linea_de(l, m[1]) for l in lineas)]:
            emitir(True)
            entrar(*m)
            pendientes.remove(m)
        for linea in lineas:
            titulos = [m for m in pendientes if _es_linea_de(linea, m[1])]
            if not titulos and usar_titulos:
                titulos = [t] if (t := _es_titulo(linea, solo_numerados)) else []
            if titulos:
                emitir(True)
                for m in titulos:  # una línea puede abrir varios niveles ("Cierre" > "Cierre mensual")
                    entrar(*m)
                    if m in pendientes:
                        pendientes.remove(m)
                continue
            for parte in _partir(linea):
                if not nuevo:
                    buf_pagina, buf_seccion = numero, seccion()
                if buf and len(buf) + len(parte) + 1 > TAMANO_FRAGMENTO:
                    emitir(False)
                    buf_pagina, buf_seccion = numero, seccion()
                buf = f"{buf}\n{parte}" if buf else parte
                nuevo = True
    emitir(True)
    return [f for f in salida if len(f.texto) >= 20 or f.seccion]


def encabezado(titulo: str, seccion: str, modulo: str = "") -> str:
    """Contexto del fragmento: "Nómina · Manual de vacaciones > Solicitud > Plazos"."""
    ruta = " > ".join(x for x in (titulo, seccion) if x)
    return f"{modulo} · {ruta}"[:500] if modulo else ruta[:500]


def actualizar_encabezados(doc: SiesaDocumento) -> None:
    for f in doc.partes:
        f.encabezado = encabezado(doc.titulo, f.seccion, doc.modulo)


def objetivo_del_texto(fragmentos: list[Fragmento]) -> str:
    """Si el instructivo trae su propia sección "Objetivo", su texto es el objetivo inicial (editable)."""
    for f in fragmentos:
        ultima = f.seccion.split(" > ")[-1] if f.seccion else ""
        if re.fullmatch(r"(\d+(\.\d+)*\.?\s*)?objetivos?(\s+general(es)?)?[:.]?", _normal(ultima).strip()):
            return re.sub(r"\s+", " ", f.texto).strip()[:600]
    return ""


def cargar(db: Session, nombre: str, contenido: bytes, usuario_id: int | None, modulo: str = "") -> Carga:
    huella = hashlib.sha256(contenido).hexdigest()
    existente = db.scalar(select(SiesaDocumento).where(SiesaDocumento.huella == huella))
    if existente:
        return Carga(existente, duplicado=True, advertencias=[f"Ya estaba cargado como «{existente.nombre}»"])
    pdf = leer_pdf(contenido)
    fragmentos = trocear(pdf.paginas, pdf.marcadores)
    sin_texto = sum(1 for p in pdf.paginas if len(p) < 20)
    if not fragmentos:
        raise ErrorPDF("El PDF no tiene texto que se pueda leer (parece escaneado como imagen). "
                       "Cárguelo en una versión con texto seleccionable.")
    titulo = (pdf.titulo or re.sub(r"\s+", " ", re.sub(r"\.pdf$", "", nombre, flags=re.I).replace("_", " ")).strip())[:255]
    doc = SiesaDocumento(nombre=nombre[:255], titulo=titulo, huella=huella, modulo=modulo.strip()[:80], fecha=pdf.fecha,
                         objetivo=objetivo_del_texto(fragmentos),
                         paginas=len(pdf.paginas), paginas_sin_texto=sin_texto, fragmentos=len(fragmentos),
                         caracteres=sum(len(f.texto) for f in fragmentos), cargado_por=usuario_id)
    doc.partes = [SiesaFragmento(pagina=f.pagina, orden=i, seccion=f.seccion[:300], texto=f.texto,
                                 encabezado=encabezado(titulo, f.seccion, doc.modulo)) for i, f in enumerate(fragmentos)]
    db.add(doc)
    db.flush()
    advertencias = []
    if sin_texto:
        advertencias.append(f"{sin_texto} de {len(pdf.paginas)} páginas no tienen texto (imágenes o escaneadas): su contenido no se podrá consultar")
    if not any(f.seccion for f in fragmentos):
        advertencias.append("No se encontraron secciones (el PDF no tiene índice ni títulos reconocibles): se usará solo el nombre del documento como contexto")
    return Carga(doc, advertencias=advertencias)


# --- Búsqueda ---

def _raices(t: str) -> list[str]:
    return [w[:6] for w in re.findall(r"[a-z0-9]+", _normal(t)) if len(w) >= 3 and w not in _PALABRAS_VACIAS]


def _relevantes(puntuados: list[tuple[float, SiesaFragmento]], limite: int) -> list[SiesaFragmento]:
    """Pocos pero buenos: hasta `limite`, sin los que puntúan muy por debajo del mejor."""
    if not puntuados:
        return []
    mejor = puntuados[0][0]
    return [f for p, f in puntuados[:limite] if p >= mejor * RELEVANCIA_MINIMA]


def _niveles(terminos: list[str]) -> list[list[tuple[str, ...]]]:
    """Exigencia de la búsqueda: primero todos los términos juntos; si no hay, todos menos uno (con 3 o más).
    Con uno o dos términos no se relaja: mejor "no está" que fragmentos que solo comparten una palabra."""
    niveles = [[tuple(terminos)]]
    if len(terminos) >= 3:
        niveles.append(list(combinations(terminos, len(terminos) - 1)))
    return niveles


def _q(lexema: str) -> str:
    return "'" + lexema.replace("'", "''") + "'"


def buscar(db: Session, consulta: str, modulo: str | None = None, limite: int = FRAGMENTOS_POR_RESPUESTA) -> list[SiesaFragmento]:
    """Fragmentos que contienen los términos importantes de la pregunta (sin palabras genéricas como "crear",
    "pantalla" o "sistema"), ordenados por relevancia; el objetivo de su instructivo suma."""
    filtro = []
    if modulo:
        filtro.append(SiesaFragmento.documento_id.in_(select(SiesaDocumento.id).where(SiesaDocumento.modulo == modulo)))

    if db.get_bind().dialect.name == "postgresql":
        lexemas = re.findall(r"'([^']+)'", db.execute(text("select plainto_tsquery('spanish', :q)::text"), {"q": consulta}).scalar() or "")
        terminos = list(dict.fromkeys(l for l in lexemas if l not in GENERICAS_PG))
        if not terminos:
            return []
        contenido = SiesaFragmento.encabezado.op("||")(literal_column("' '")).op("||")(SiesaFragmento.texto)
        vector = func.to_tsvector(ESPANOL, contenido)
        cualquiera = cast(" | ".join(_q(t) for t in terminos), TSQUERY)  # para el puntaje
        objetivo = func.ts_rank_cd(func.to_tsvector(ESPANOL, SiesaDocumento.objetivo), cualquiera)
        rango = (func.ts_rank_cd(vector, cualquiera) + PESO_OBJETIVO * objetivo).label("rango")
        for grupos in _niveles(terminos):
            exige = cast(" | ".join("(" + " & ".join(_q(t) for t in g) + ")" for g in grupos), TSQUERY)
            filas = db.execute(select(SiesaFragmento, rango).join(SiesaDocumento, SiesaDocumento.id == SiesaFragmento.documento_id)
                               .where(vector.op("@@")(exige), *filtro)
                               .order_by(desc("rango"), SiesaFragmento.id).limit(limite)).all()
            if filas:
                return _relevantes([(float(r), f) for f, r in filas], limite)
        return []

    # Pruebas (SQLite): las mismas reglas con raíces de palabras y peso por rareza
    terminos = [r for r in dict.fromkeys(_raices(consulta)) if r not in GENERICAS_RAICES]
    if not terminos:
        return []
    todos = list(db.scalars(select(SiesaFragmento).where(*filtro)))
    conteos = [Counter(_raices(f"{f.encabezado} {f.texto}")) for f in todos]
    df = Counter(r for c in conteos for r in terminos if c[r])
    for grupos in _niveles(terminos):
        puntajes = []
        for f, c in zip(todos, conteos):
            if not any(all(c[t] for t in g) for g in grupos):
                continue
            p = sum((1 + math.log(c[r])) * math.log(1 + len(todos) / df[r]) for r in terminos if c[r])
            p += PESO_OBJETIVO * len(set(terminos) & set(_raices(f.documento.objetivo or "")))
            puntajes.append((p, f))
        if puntajes:
            puntajes.sort(key=lambda x: (-x[0], x[1].id))
            return _relevantes(puntajes, limite)
    return []


def modulos(db: Session) -> list[str]:
    return [m for m in db.scalars(select(SiesaDocumento.modulo).distinct().order_by(SiesaDocumento.modulo)) if m]


# --- Respuesta ---

@dataclass
class Resultado:
    texto: str
    encontrado: bool
    fuentes: list[dict]
    respuesta_ia: ia.Respuesta | None = None


def _consulta(mensajes: list[dict]) -> str:
    """La pregunta actual; si es corta (p. ej. "¿y para anularlo?"), se le suma la pregunta anterior."""
    preguntas = [m["content"] for m in mensajes if m["role"] == "user"]
    actual = preguntas[-1]
    if len(_raices(actual)) < 4 and len(preguntas) > 1:
        return f"{preguntas[-2]} {actual}"
    return actual


def _referencias(fragmentos: list[SiesaFragmento]) -> dict[int, str]:
    """Referencia corta de cada instructivo consultado (D1, D2…), en orden de aparición."""
    refs: dict[int, str] = {}
    for f in fragmentos:
        refs.setdefault(f.documento_id, f"D{len(refs) + 1}")
    return refs


def _bloque(i: int, f: SiesaFragmento, ref: str) -> str:
    seccion = f" · {f.seccion}" if f.seccion else ""
    return f"[{i}] {ref} p.{f.pagina}{seccion}\n{f.texto}"


def _instructivos(fragmentos: list[SiesaFragmento], refs: dict[int, str]) -> str:
    """Cada instructivo consultado, una sola vez: título, módulo, fecha y objetivo."""
    lineas, vistos = [], set()
    for f in fragmentos:
        d = f.documento
        if d.id in vistos:
            continue
        vistos.add(d.id)
        datos = ", ".join(x for x in (d.modulo, f"versión {d.fecha:%d/%m/%Y}" if d.fecha else "") if x)
        objetivo = f" Objetivo: {d.objetivo.strip()}" if (d.objetivo or "").strip() else ""
        lineas.append(f"{refs[d.id]}: {d.titulo}{f' ({datos})' if datos else ''}.{objetivo}")
    return "\n".join(lineas)


def _historial(mensajes: list[dict]) -> list[dict]:
    """Solo lo necesario para entender la pregunta actual: la pregunta y respuesta anteriores (recortada) y la actual."""
    previos = mensajes[:-1][-2:]
    return [{**m, "content": m["content"][:400]} if m["role"] == "assistant" else m for m in previos] + mensajes[-1:]


def responder(db: Session, mensajes: list[dict], modulo: str | None = None) -> Resultado:
    fragmentos = buscar(db, _consulta(mensajes), modulo)
    if not fragmentos:
        return Resultado(NO_ENCONTRADO, False, [])  # sin consultar al modelo: 0 tokens
    refs = _referencias(fragmentos)
    bloque = "\n\n".join(_bloque(i, f, refs[f.documento_id]) for i, f in enumerate(fragmentos, 1))
    instrucciones = INSTRUCCIONES.format(no_encontrado=NO_ENCONTRADO, instructivos=_instructivos(fragmentos, refs), fragmentos=bloque)
    r = ia.completar(instrucciones, _historial(mensajes), modelo=get_settings().siesa_modelo, max_tokens=MAX_TOKENS_RESPUESTA)
    texto = r.texto.strip()
    citados = sorted({int(n) for n in re.findall(r"\[(\d{1,2})\]", texto) if 1 <= int(n) <= len(fragmentos)})
    if not texto or NO_ENCONTRADO[:40] in texto or not citados:
        # Sin citas no hay forma de saber de dónde salió: no se muestra
        return Resultado(NO_ENCONTRADO, False, [], r)
    fuentes = []
    for n in citados:
        f = fragmentos[n - 1]
        fuentes.append({"n": n, "documento": f.documento.titulo, "archivo": f.documento.nombre, "pagina": f.pagina,
                        "seccion": f.seccion, "modulo": f.documento.modulo, "objetivo": f.documento.objetivo or "",
                        "fecha": f.documento.fecha.isoformat() if f.documento.fecha else None, "extracto": f.texto[:600]})
    return Resultado(texto, True, fuentes, r)
