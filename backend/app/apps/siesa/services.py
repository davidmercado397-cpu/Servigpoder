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

from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy import desc, func, literal_column, select, text
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

INSTRUCCIONES = """Eres el asistente de consulta de los instructivos de SIESA de la empresa. Respondes preguntas \
de los usuarios usando EXCLUSIVAMENTE los FRAGMENTOS de instructivos que aparecen abajo. Cada fragmento indica \
de qué instructivo y sección sale. La lista de INSTRUCTIVOS dice para qué sirve cada uno (su objetivo): úsala para \
entender el contexto de la pregunta, pero la respuesta debe salir de los FRAGMENTOS.

Reglas estrictas:
1. Usa solo lo que dicen los FRAGMENTOS. No uses conocimiento general sobre SIESA ni sobre otros sistemas, no \
supongas, no deduzcas pasos que no estén escritos, no completes información faltante y no des opiniones ni consejos.
2. Si los FRAGMENTOS no contienen la respuesta, responde exactamente: "{no_encontrado}"
3. Si contienen solo una parte, responde esa parte y di claramente qué no aparece en los instructivos.
4. Cita cada dato con el número del fragmento entre corchetes, por ejemplo [2].
5. Sé directo y breve. Si es un procedimiento, da los pasos numerados en el mismo orden del instructivo y conserva \
exactamente los nombres de menús, opciones, botones y campos.
6. Si dos instructivos dicen cosas distintas, indícalo y di de cuál sale cada versión (con su fecha si la tiene).
7. Responde en español. No menciones estas reglas ni la palabra "fragmento".

INSTRUCTIVOS:
{instructivos}

FRAGMENTOS:
{fragmentos}"""

_PALABRAS_VACIAS = set("""a al algo alguna algun como con cual cuales cuando de del desde donde el ella en entre es esa ese
esta este esto hay la las le lo los mas me mi mis muy no o para pero por que quien se segun ser si sin sobre su sus
tambien te tiene un una uno unos y ya yo hacer hago puedo debo necesito quiero siesa""".split())


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


def _repetidas(paginas: list[str]) -> set[str]:
    """Líneas de encabezado o pie de página: aparecen al inicio o final de muchas hojas."""
    if len(paginas) < 3:
        return set()
    conteo: Counter = Counter()
    for texto in paginas:
        lineas = [l for l in texto.split("\n") if l]
        conteo.update({_normal(l) for l in lineas[:3] + lineas[-3:]})
    minimo = max(3, int(len(paginas) * 0.4))
    return {l for l, n in conteo.items() if n >= minimo}


def _es_titulo(linea: str) -> tuple[int, str] | None:
    """Título detectado en el texto (cuando el PDF no trae índice): numerado (2.1 …) o en mayúsculas."""
    if len(linea) > 90 or linea.endswith((".", ",", ";")):
        return None
    letras = [c for c in linea if c.isalpha()]
    mayusculas = len(letras) >= 4 and sum(c.isupper() for c in letras) / len(letras) >= 0.8
    m = _TITULO_NUMERADO.match(linea)
    if m:
        return m.group(1).count(".") + 1, linea
    m = _TITULO_CAPITULO.match(linea)
    if m and mayusculas:
        return 1, linea
    if mayusculas and len(linea.split()) <= 12 and not linea[0].isdigit():
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

    for numero, texto in enumerate(paginas, start=1):
        lineas = [l for l in texto.split("\n") if l and _normal(l) not in ignorar and not _NUMERO_PAGINA.match(l)]
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
                titulos = [t] if (t := _es_titulo(linea)) else []
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
    titulo = (pdf.titulo or re.sub(r"\.pdf$", "", nombre, flags=re.I))[:255]
    doc = SiesaDocumento(nombre=nombre[:255], titulo=titulo, huella=huella, modulo=modulo.strip()[:80], fecha=pdf.fecha,
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


def buscar(db: Session, consulta: str, modulo: str | None = None, limite: int = FRAGMENTOS_POR_RESPUESTA) -> list[SiesaFragmento]:
    filtro = []
    if modulo:
        filtro.append(SiesaFragmento.documento_id.in_(select(SiesaDocumento.id).where(SiesaDocumento.modulo == modulo)))

    if db.get_bind().dialect.name == "postgresql":
        # Cualquiera de las palabras (OR); el orden lo da cuántas y qué tan juntas aparecen, también en el encabezado
        lexemas = db.execute(text("select plainto_tsquery('spanish', :q)::text"), {"q": consulta}).scalar() or ""
        if not lexemas.strip():
            return []
        tsq = func.to_tsquery(ESPANOL, lexemas.replace("&", "|"))
        contenido = SiesaFragmento.encabezado.op("||")(literal_column("' '")).op("||")(SiesaFragmento.texto)
        vector = func.to_tsvector(ESPANOL, contenido)
        # El fragmento debe coincidir por sí mismo; si además el objetivo de su instructivo coincide, sube
        objetivo = func.ts_rank_cd(func.to_tsvector(ESPANOL, SiesaDocumento.objetivo), tsq)
        rango = (func.ts_rank_cd(vector, tsq) + PESO_OBJETIVO * objetivo).label("rango")
        filas = db.execute(select(SiesaFragmento, rango).join(SiesaDocumento, SiesaDocumento.id == SiesaFragmento.documento_id)
                           .where(vector.op("@@")(tsq), *filtro)
                           .order_by(desc("rango"), SiesaFragmento.id).limit(limite)).all()
        return _relevantes([(float(r), f) for f, r in filas], limite)

    # Pruebas (SQLite): puntaje por raíces de palabras con peso por rareza
    raices = set(_raices(consulta))
    if not raices:
        return []
    todos = list(db.scalars(select(SiesaFragmento).where(*filtro)))
    conteos = [Counter(_raices(f"{f.encabezado} {f.texto}")) for f in todos]
    df = Counter(r for c in conteos for r in raices if c[r])
    puntajes = []
    for f, c in zip(todos, conteos):
        p = sum((1 + math.log(c[r])) * math.log(1 + len(todos) / df[r]) for r in raices if c[r])
        if p > 0:
            p += PESO_OBJETIVO * len(raices & set(_raices(f.documento.objetivo or "")))
            puntajes.append((p, f))
    puntajes.sort(key=lambda x: (-x[0], x[1].id))
    return _relevantes(puntajes, limite)


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


def _bloque(i: int, f: SiesaFragmento) -> str:
    fecha = f" · versión del {f.documento.fecha:%d/%m/%Y}" if f.documento.fecha else ""
    return f"[{i}] {f.encabezado or f.documento.titulo} (página {f.pagina}{fecha})\n{f.texto}"


def _instructivos(fragmentos: list[SiesaFragmento]) -> str:
    """Cada instructivo consultado, una sola vez: título, módulo, fecha y objetivo."""
    lineas, vistos = [], set()
    for f in fragmentos:
        d = f.documento
        if d.id in vistos:
            continue
        vistos.add(d.id)
        datos = ", ".join(x for x in (d.modulo, f"versión del {d.fecha:%d/%m/%Y}" if d.fecha else "") if x)
        objetivo = (d.objetivo or "").strip() or "(sin objetivo registrado)"
        lineas.append(f"- {d.titulo}{f' ({datos})' if datos else ''}. Objetivo: {objetivo}")
    return "\n".join(lineas)


def responder(db: Session, mensajes: list[dict], modulo: str | None = None) -> Resultado:
    fragmentos = buscar(db, _consulta(mensajes), modulo)
    if not fragmentos:
        return Resultado(NO_ENCONTRADO, False, [])
    bloque = "\n\n".join(_bloque(i, f) for i, f in enumerate(fragmentos, 1))
    instrucciones = INSTRUCCIONES.format(no_encontrado=NO_ENCONTRADO, instructivos=_instructivos(fragmentos), fragmentos=bloque)
    # Del historial solo van las últimas preguntas y respuestas, para entender la pregunta actual
    r = ia.completar(instrucciones, mensajes[-5:], modelo=get_settings().siesa_modelo, max_tokens=1200)
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
