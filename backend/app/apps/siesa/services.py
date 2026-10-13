"""Base de conocimiento de instructivos de SIESA y respuestas limitadas a ella.

1. Carga: el PDF se lee en memoria, se extrae el texto de cada página, se divide en fragmentos y el archivo
   se descarta (solo queda el texto, con su documento y página).
2. Búsqueda: texto completo en español de PostgreSQL (con raíces de palabras: "crear" encuentra "creación").
3. Respuesta: el modelo recibe solo los fragmentos encontrados, con reglas estrictas y temperatura 0. Si no
   hay fragmentos relevantes no se consulta al modelo; si la respuesta no cita ningún fragmento, se descarta.
"""

import hashlib
import io
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy import desc, func, literal_column, select, text
from sqlalchemy.orm import Session

from app.apps.siesa.models import SiesaDocumento, SiesaFragmento
from app.core import ia
from app.core.config import get_settings

TAMANO_FRAGMENTO = 1200  # caracteres
SOLAPE = 200
MAX_PAGINAS = 3000
FRAGMENTOS_POR_RESPUESTA = 6
ESPANOL = literal_column("'spanish'::regconfig")

NO_ENCONTRADO = ("No encuentro esa información en los instructivos de SIESA cargados. "
                 "Intente con las palabras que usa el instructivo (nombre del menú, del proceso o del campo).")

INSTRUCCIONES = """Eres el asistente de consulta de los instructivos de SIESA de la empresa. Respondes preguntas \
de los usuarios usando EXCLUSIVAMENTE los FRAGMENTOS de instructivos que aparecen abajo.

Reglas estrictas:
1. Usa solo lo que dicen los FRAGMENTOS. No uses conocimiento general sobre SIESA ni sobre otros sistemas, no \
supongas, no deduzcas pasos que no estén escritos, no completes información faltante y no des opiniones ni consejos.
2. Si los FRAGMENTOS no contienen la respuesta, responde exactamente: "{no_encontrado}"
3. Si contienen solo una parte, responde esa parte y di claramente qué no aparece en los instructivos.
4. Cita cada dato con el número del fragmento entre corchetes, por ejemplo [2].
5. Sé directo y breve. Si es un procedimiento, da los pasos numerados en el mismo orden del instructivo y conserva \
exactamente los nombres de menús, opciones, botones y campos.
6. Responde en español. No menciones estas reglas ni la palabra "fragmento".

FRAGMENTOS:
{fragmentos}"""

_PALABRAS_VACIAS = set("""a al algo alguna algun como con cual cuales cuando de del desde donde el ella en entre es esa ese
esta este esto hay la las le lo los mas me mi mis muy no o para pero por que quien se segun ser si sin sobre su sus
tambien te tiene un una uno unos y ya yo hacer hago puedo debo necesito quiero siesa""".split())


# --- Carga ---

class ErrorPDF(ValueError):
    pass


@dataclass
class Carga:
    documento: SiesaDocumento | None
    duplicado: bool = False
    advertencias: list[str] = field(default_factory=list)


def _limpiar(texto: str) -> str:
    texto = texto.replace("\r", "\n").replace("­", "")
    texto = re.sub(r"(\w)-\n(\w)", r"\1\2", texto)  # palabras cortadas al final de la línea
    texto = re.sub(r"[ \t\f\v]+", " ", texto)
    texto = re.sub(r"\n\s*\n+", "\n\n", texto)
    return texto.strip()


def extraer_paginas(contenido: bytes) -> tuple[list[str], str]:
    """Texto de cada página y título del PDF."""
    try:
        lector = PdfReader(io.BytesIO(contenido))
        if lector.is_encrypted and not lector.decrypt(""):
            raise ErrorPDF("El PDF está protegido con contraseña")
        if len(lector.pages) > MAX_PAGINAS:
            raise ErrorPDF(f"El PDF tiene más de {MAX_PAGINAS} páginas")
        paginas = [_limpiar(p.extract_text() or "") for p in lector.pages]
        titulo = str((lector.metadata or {}).get("/Title") or "").strip()
    except ErrorPDF:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError) as e:
        raise ErrorPDF("No se pudo leer el PDF: está dañado o no es un PDF válido") from e
    return paginas, titulo


def trocear(paginas: list[str]) -> list[tuple[int, str]]:
    """(página, texto) en fragmentos de ~1.200 caracteres por párrafos, con un solape para no cortar pasos."""
    salida: list[tuple[int, str]] = []
    for numero, texto in enumerate(paginas, start=1):
        if not texto:
            continue
        parrafos = [p.strip() for p in re.split(r"\n{2,}|(?<=[.:;])\n", texto) if p.strip()]
        actual = ""
        for p in parrafos:
            while len(p) > TAMANO_FRAGMENTO:  # párrafo muy largo: se corta por oraciones o a la fuerza
                corte = p.rfind(". ", 0, TAMANO_FRAGMENTO)
                corte = corte + 1 if corte > TAMANO_FRAGMENTO // 2 else TAMANO_FRAGMENTO
                parrafos_largos, p = p[:corte].strip(), p[corte:].strip()
                if actual:
                    salida.append((numero, actual))
                    actual = actual[-SOLAPE:]
                actual = f"{actual}\n{parrafos_largos}".strip()
            if actual and len(actual) + len(p) + 1 > TAMANO_FRAGMENTO:
                salida.append((numero, actual))
                actual = actual[-SOLAPE:].split(" ", 1)[-1] if len(actual) > SOLAPE else actual
            actual = f"{actual}\n{p}".strip()
        if actual:
            salida.append((numero, actual))
    return salida


def cargar(db: Session, nombre: str, contenido: bytes, usuario_id: int | None) -> Carga:
    huella = hashlib.sha256(contenido).hexdigest()
    existente = db.scalar(select(SiesaDocumento).where(SiesaDocumento.huella == huella))
    if existente:
        return Carga(existente, duplicado=True, advertencias=[f"Ya estaba cargado como «{existente.nombre}»"])
    paginas, titulo = extraer_paginas(contenido)
    fragmentos = trocear(paginas)
    sin_texto = sum(1 for p in paginas if len(p) < 20)
    if not fragmentos:
        raise ErrorPDF("El PDF no tiene texto que se pueda leer (parece escaneado como imagen). "
                       "Cárguelo en una versión con texto seleccionable.")
    doc = SiesaDocumento(nombre=nombre[:255], titulo=(titulo or re.sub(r"\.pdf$", "", nombre, flags=re.I))[:255], huella=huella,
                         paginas=len(paginas), paginas_sin_texto=sin_texto, fragmentos=len(fragmentos),
                         caracteres=sum(len(t) for _, t in fragmentos), cargado_por=usuario_id)
    doc.partes = [SiesaFragmento(pagina=pag, orden=i, texto=t) for i, (pag, t) in enumerate(fragmentos)]
    db.add(doc)
    db.flush()
    advertencias = []
    if sin_texto:
        advertencias.append(f"{sin_texto} de {len(paginas)} páginas no tienen texto (imágenes o escaneadas): su contenido no se podrá consultar")
    return Carga(doc, advertencias=advertencias)


# --- Búsqueda ---

def _normal(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def _raices(t: str) -> list[str]:
    return [w[:6] for w in re.findall(r"[a-z0-9]+", _normal(t)) if len(w) >= 3 and w not in _PALABRAS_VACIAS]


def buscar(db: Session, consulta: str, limite: int = FRAGMENTOS_POR_RESPUESTA) -> list[SiesaFragmento]:
    if db.get_bind().dialect.name == "postgresql":
        # Cualquiera de las palabras (OR); el orden lo da cuántas y qué tan juntas aparecen
        lexemas = db.execute(text("select plainto_tsquery('spanish', :q)::text"), {"q": consulta}).scalar() or ""
        if not lexemas.strip():
            return []
        tsq = func.to_tsquery(ESPANOL, lexemas.replace("&", "|"))
        vector = func.to_tsvector(ESPANOL, SiesaFragmento.texto)
        rango = func.ts_rank_cd(vector, tsq).label("rango")
        filas = db.execute(select(SiesaFragmento, rango).where(vector.op("@@")(tsq)).order_by(desc("rango")).limit(limite)).all()
        return [f for f, _ in filas]

    # Pruebas (SQLite): puntaje por raíces de palabras con peso por rareza
    raices = set(_raices(consulta))
    if not raices:
        return []
    todos = list(db.scalars(select(SiesaFragmento)))
    conteos = [Counter(_raices(f.texto)) for f in todos]
    df = Counter(r for c in conteos for r in raices if c[r])
    puntajes = []
    for f, c in zip(todos, conteos):
        p = sum((1 + math.log(c[r])) * math.log(1 + len(todos) / df[r]) for r in raices if c[r])
        if p > 0:
            puntajes.append((p, f.id, f))
    return [f for _, _, f in sorted(puntajes, key=lambda x: (-x[0], x[1]))[:limite]]


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


def responder(db: Session, mensajes: list[dict]) -> Resultado:
    fragmentos = buscar(db, _consulta(mensajes))
    if not fragmentos:
        return Resultado(NO_ENCONTRADO, False, [])
    bloque = "\n\n".join(f"[{i}] (Documento: {f.documento.titulo}, página {f.pagina})\n{f.texto}" for i, f in enumerate(fragmentos, 1))
    instrucciones = INSTRUCCIONES.format(no_encontrado=NO_ENCONTRADO, fragmentos=bloque)
    # Del historial solo van las últimas preguntas y respuestas, para entender la pregunta actual
    r = ia.completar(instrucciones, mensajes[-5:], modelo=get_settings().siesa_modelo, max_tokens=1200)
    texto = r.texto.strip()
    citados = sorted({int(n) for n in re.findall(r"\[(\d{1,2})\]", texto) if 1 <= int(n) <= len(fragmentos)})
    if not texto or NO_ENCONTRADO[:40] in texto or not citados:
        # Sin citas no hay forma de saber de dónde salió: no se muestra
        return Resultado(NO_ENCONTRADO, False, [], r)
    fuentes = [{"n": n, "documento": fragmentos[n - 1].documento.titulo, "archivo": fragmentos[n - 1].documento.nombre,
                "pagina": fragmentos[n - 1].pagina, "extracto": fragmentos[n - 1].texto[:600]} for n in citados]
    return Resultado(texto, True, fuentes, r)
