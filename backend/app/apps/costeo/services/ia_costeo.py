"""Llenar un costeo con IA a partir de los archivos del cliente (solicitud, pliego, Excel de costeo, correos…).

Se suben de 1 a 6 archivos; aquí se leen en memoria (nunca se guardan), se le pasan al modelo junto con los
catálogos vigentes (servicios, dotación adicional, otros costos) y el modelo devuelve una propuesta en JSON.
La propuesta se normaliza contra los catálogos: solo entran servicios y dotación que existen; las tarifas, los
hombres y los precios salen del catálogo, nunca del modelo. Lo que no se pudo ubicar queda en «faltantes».
El costeo no se guarda aquí: el usuario revisa la propuesta en pantalla y guarda (con las reglas de siempre).
"""

import base64
import copy
import io
import json
import re
import unicodedata
import zipfile

from defusedxml import ElementTree
from openpyxl import load_workbook
from PIL import Image
from pypdf import PdfReader

from app.apps.costeo.services.puestos import ARMAS, DOTACIONES
from app.core import ia

MAX_ARCHIVOS = 6
MAX_CARACTERES_ARCHIVO = 120_000  # texto de cada archivo que se le pasa al modelo
MAX_PAGINAS_PDF = 150
MAX_FILAS_HOJA = 2000
MAX_TOKENS_RESPUESTA = 8000
EXTENSIONES = {".pdf", ".xlsx", ".xlsm", ".docx", ".csv", ".txt", ".png", ".jpg", ".jpeg", ".webp", ".eml"}
TIPOS_OTROS = {"OTROS": "Otros", "ACCES_TOO": "Acces Too y mantenimiento", "EQUIPOS": "Equipos (computador, celular, cámaras…)",
               "CAPACITACION": "Capacitación", "REINVERSION": "Reinversión / bono de libre inversión",
               "NOTA_CREDITO": "Nota crédito / bono tarifa"}


class ArchivoInvalido(ValueError):
    pass


def _normal(t: str) -> str:
    t = "".join(c for c in unicodedata.normalize("NFD", str(t or "").lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t).strip()


def _n(v, defecto=None):
    if v in (None, ""):
        return defecto
    if isinstance(v, str):
        v = v.replace("$", "").replace(" ", "")
        if re.fullmatch(r"-?\d{1,3}(\.\d{3})+(,\d+)?", v):  # 1.234.567,5
            v = v.replace(".", "").replace(",", ".")
        else:
            v = v.replace(",", ".") if v.count(",") == 1 and "." not in v else v.replace(",", "")
    try:
        return float(v)
    except (TypeError, ValueError):
        return defecto


# --- Lectura de archivos (en memoria) -------------------------------------------------------------------

def _recortar(texto: str) -> tuple[str, str | None]:
    if len(texto) <= MAX_CARACTERES_ARCHIVO:
        return texto, None
    return texto[:MAX_CARACTERES_ARCHIVO], "El archivo es muy largo: se leyó solo la primera parte"


def _valor(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.6f}".rstrip("0").rstrip(".")
    if hasattr(v, "isoformat"):
        return v.isoformat()[:10]
    return str(v).strip()


def _excel(contenido: bytes) -> str:
    try:
        libro = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    except Exception as e:
        raise ArchivoInvalido("No se pudo abrir el Excel (¿está dañado o protegido?)") from e
    partes = []
    try:
        for hoja in libro.worksheets:
            if getattr(hoja, "sheet_state", "visible") != "visible":
                continue
            filas = []
            for i, fila in enumerate(hoja.iter_rows(values_only=True), start=1):
                celdas = [_valor(v) for v in fila]
                while celdas and not celdas[-1]:
                    celdas.pop()
                if any(celdas):
                    filas.append(f"F{i}: " + " | ".join(celdas))
                if len(filas) >= MAX_FILAS_HOJA:
                    filas.append("(hoja recortada)")
                    break
            if filas:
                partes.append(f"--- Hoja «{hoja.title}» ---\n" + "\n".join(filas))
    finally:
        libro.close()
    return "\n\n".join(partes)


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _docx(contenido: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(contenido)) as z:
            xml = z.read("word/document.xml")
        raiz = ElementTree.fromstring(xml)
    except Exception as e:
        raise ArchivoInvalido("No se pudo abrir el documento de Word") from e
    lineas = []
    for p in raiz.iter(f"{W}p"):
        texto = "".join(t.text or "" for t in p.iter(f"{W}t")).strip()
        if texto:
            lineas.append(texto)
    return "\n".join(lineas)


def _pdf(contenido: bytes) -> tuple[str, bool]:
    """Texto del PDF y si parece escaneado (sin texto: se le pasa el PDF al modelo para que lo lea)."""
    try:
        lector = PdfReader(io.BytesIO(contenido))
        if lector.is_encrypted and not lector.decrypt(""):
            raise ArchivoInvalido("El PDF está protegido con contraseña")
        paginas = lector.pages[:MAX_PAGINAS_PDF]
        textos = [(p.extract_text() or "").strip() for p in paginas]
    except ArchivoInvalido:
        raise
    except Exception as e:
        raise ArchivoInvalido("No se pudo abrir el PDF") from e
    texto = "\n\n".join(f"--- Página {i} ---\n{t}" for i, t in enumerate(textos, start=1) if t)
    escaneado = sum(len(t) for t in textos) < 40 * max(1, len(textos))
    return texto, escaneado


def _texto_plano(contenido: bytes) -> str:
    for codificacion in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return contenido.decode(codificacion)
        except UnicodeDecodeError:
            continue
    return contenido.decode("utf-8", errors="ignore")


def _correo(contenido: bytes) -> str:
    from email import policy
    from email.parser import BytesParser

    m = BytesParser(policy=policy.default).parsebytes(contenido)
    cuerpo = m.get_body(preferencelist=("plain", "html"))
    texto = cuerpo.get_content() if cuerpo else ""
    if cuerpo is not None and cuerpo.get_content_type() == "text/html":
        texto = re.sub(r"<[^>]+>", " ", texto)
    return f"Asunto: {m.get('subject', '')}\nDe: {m.get('from', '')}\nFecha: {m.get('date', '')}\n\n{texto}"


def leer(nombre: str, contenido: bytes) -> dict:
    """Prepara un archivo para el modelo: {"nombre", "texto"} o, si es imagen o PDF escaneado, {"nombre", "parte"}."""
    ext = ("." + nombre.rsplit(".", 1)[-1].lower()) if "." in nombre else ""
    if ext not in EXTENSIONES:
        if ext == ".xls":
            raise ArchivoInvalido(f"«{nombre}»: el Excel antiguo (.xls) no se puede leer; ábralo y guárdelo como .xlsx")
        if ext == ".doc":
            raise ArchivoInvalido(f"«{nombre}»: el Word antiguo (.doc) no se puede leer; guárdelo como .docx o PDF")
        raise ArchivoInvalido(f"«{nombre}»: tipo de archivo no admitido (PDF, Excel .xlsx, Word .docx, imagen, CSV, TXT o correo .eml)")
    if not contenido:
        raise ArchivoInvalido(f"«{nombre}» está vacío")
    out: dict = {"nombre": nombre, "advertencias": []}
    try:
        if ext in (".xlsx", ".xlsm"):
            texto = _excel(contenido)
        elif ext == ".docx":
            texto = _docx(contenido)
        elif ext == ".pdf":
            texto, escaneado = _pdf(contenido)
            if escaneado:
                datos = base64.b64encode(contenido).decode()
                out["parte"] = {"type": "file", "file": {"filename": nombre, "file_data": f"data:application/pdf;base64,{datos}"}}
                out["advertencias"].append("PDF escaneado (sin texto): lo lee el modelo directamente")
                return out
        elif ext in (".png", ".jpg", ".jpeg", ".webp"):
            try:
                with Image.open(io.BytesIO(contenido)) as img:
                    img.verify()
                    formato = (img.format or "png").lower()
            except Exception as e:
                raise ArchivoInvalido(f"«{nombre}» no es una imagen válida") from e
            mime = {"jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(formato, "image/png")
            out["parte"] = {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64.b64encode(contenido).decode()}"}}
            return out
        elif ext == ".eml":
            texto = _correo(contenido)
        else:
            texto = _texto_plano(contenido)
    except ArchivoInvalido as e:
        raise ArchivoInvalido(str(e) if nombre in str(e) else f"«{nombre}»: {e}") from e
    texto = texto.strip()
    if not texto:
        raise ArchivoInvalido(f"«{nombre}» no tiene texto que se pueda leer")
    out["texto"], aviso = _recortar(texto)
    if aviso:
        out["advertencias"].append(aviso)
    return out


# --- Instrucciones y llamada al modelo ------------------------------------------------------------------

INSTRUCCIONES = """Eres el analista de costeos de Servigpoder, empresa colombiana de vigilancia y seguridad privada.
Te entregan los documentos de una oportunidad comercial y debes llenar el costeo de la plataforma con lo que digan.
Documentos habituales (pueden venir todos o solo algunos):
- COSTEO <cliente>.xlsx: el Excel de costeo interno de Servigpoder. ES LA FUENTE PRINCIPAL.
- MFP <cliente>.xlsx: matriz de fortalecimiento del puesto (nota crédito, bono de reinversión, Acces Too…).
- APOYO COMERCIAL / COTIZACIÓN (PDF): la oferta enviada al cliente (servicios, tarifa, descuento).
- BENEFICIOS (PDF): beneficios ofrecidos (capacitaciones, poligrafías, horas de refuerzo, Visitrack…).
- FT-CM-01 (PDF, a veces escaneado): formato de vinculación del cliente (razón social, NIT, contacto, fechas).

Reglas generales:
- Usa SOLO lo que dicen los documentos y las indicaciones del usuario (las indicaciones mandan sobre los documentos).
  Si un dato no aparece, déjalo en null y agrégalo a "faltantes". No inventes valores. Lo que deduzcas va en "supuestos".
- CONFLICTOS: si dos documentos dicen cosas distintas sobre el mismo dato (nota crédito, duración, cantidad de puestos,
  servicio…), MANDA EL EXCEL DE COSTEO. Usa su valor y anota en "conflictos" el dato y lo que dice cada documento,
  p. ej. "Nota crédito: costeo 12 %, apoyo comercial 12,5 %, MFP 7 % (se tomó 12 %)". Sin Excel de costeo, manda la oferta
  al cliente (apoyo comercial / cotización) y luego la MFP.
- OTRO CLIENTE: si un documento nombra a un cliente distinto al de la mayoría de documentos (una plantilla que no se
  actualizó), NO tomes de él cantidades, porcentajes, plazos ni fechas; solo los conceptos (p. ej. que hay Acces Too o bono
  de reinversión, con sus valores en pesos si son fijos) y avísalo en "conflictos" con el nombre del documento y del cliente.
- Porcentajes de salida en por ciento (12 = 12 %). En los Excel suelen venir como fracción (0.12 = 12 %; 0.005 = 0,5 %):
  conviértelos. Valores en pesos colombianos como números, sin puntos de miles ni signo $.

Cómo leer el Excel de COSTEO interno:
- Tabla SERVICIOS | CANTIDAD | PUESTO | TARIFA…: cada fila con cantidad es una línea de "servicios". Ubica el servicio en el
  CATÁLOGO DE SERVICIOS por horas y días: "SERV VIG 24 HRS L-D con F" = 24 horas de lunes a domingo; "12 HRS L-D" = 12 horas
  de lunes a domingo (diurno si no dice nocturno); "L-V" = lunes a viernes; "L-S" = lunes a sábado. La tabla de la derecha
  (SERVICIO | TARIFAS | # DE HOMBRES) es solo la lista de precios: no son puestos.
- "Nota a credito (bono cliente)" → pct_nota_credito. "cupo de inversion" → pct_cupo_inversion. "Duración del contrato" →
  duracion_meses. "Comisión del vendedor" → pct_comision_vendedor; "COMISION DIRECTOR x" → pct_comision_director.
  "ICA 4,5/1000" → ica_por_mil 4.5.
- Costos laborales: columna por tipo de personal (p. ej. "GUARDAS 4x2" = Guarda). "HORAS EXTRAS Y RECARGOS" → horas_extras;
  "AUXILIO DE MOVILIDAD NO CONSTITUTIVO DE SALARIO" → auxilios_no_salariales; "AUXILIO DE RODAMIENTO" → rodamiento.
  El salario, el auxilio de transporte y la Ley 2101 NO se toman (los pone la plataforma).
- "OTROS COSTOS DIRECTOS": filas con descripción y valor → "otros".
- "COSTOS DOTACIÓN DEL PUESTO ADICIONALES…": SOLO las filas con CANTIDAD mayor que 0 → "dotacion_puesto" (con el nombre del
  catálogo más parecido: "CHAL. REFLECTIVO" = "CHALECO REFLECTIVO"). Excepción: "HORAS ADICIONALES N AL AÑO" no es
  dotación: son horas de obsequio → horas_bolsa_total = N × duracion_meses / 12.
- "COSTOS DIRECTOS QUE HACEN PARTE DE LA TARIFA" (uniformes y equipos): no se copian (la plataforma los calcula), pero
  dicen cómo es el puesto: OVEROL o BOTAS PUNTERA con cantidad → dotación "overol"; CAMISA/PANTALÓN → "gala". La fila de
  arma con cantidad dice el arma: ARMA DE FUEGO → "fuego", ARMA DE FOGEO → "fogeo", ARMA TRAUMATICA → "traumatica",
  ARMA NO LETAL → "noletal". Si ninguna arma tiene cantidad → "sin".

Cómo leer la MFP: "NOTA CREDITO" % → pct_nota_credito; "BONO REINVERSION" % → pct_cupo_inversion; "ACCES TOO" y
"MANTENIMIENTO ACCES TOO" → "otros" con tipo_item ACCES_TOO y el valor TOTAL del contrato (tabla MFP TOTAL) como
valor_unitario, cantidad 1. "FECHA INICIACION DEL CONTRATO" → fecha_inicio (si el documento es del mismo cliente).

Servicios y puestos:
- Cada puesto es una línea; "cantidad" = cuántos puestos iguales; "puesto" = nombre o ubicación (Portería, Parqueadero…).
  Si ningún servicio del catálogo corresponde, no lo inventes: ponlo en "faltantes" con la descripción.
- Dotación: "gala" (porterías, recepción, oficinas, conjuntos) u "overol" (campo, industria, obra).
  Arma: "sin", "fuego", "fogeo", "traumatica" o "noletal". "Armado" o "con arma" sin decir cuál: usa el arma del Excel de
  costeo; sin Excel, "fuego" y anótalo en "supuestos".
- No digites tarifas, hombres, salarios ni precios de dotación: los pone la plataforma desde sus catálogos.

APOYO COMERCIAL y BENEFICIOS van a la MFP (lo que se le promete al cliente y se le controla en el contrato):
- Del APOYO COMERCIAL: el beneficio económico ofrecido (nota crédito / descuento % → pct_nota_credito; bono de reinversión
  o cupo de inversión % → pct_cupo_inversion; equipos o bonos en pesos → "otros"). Si choca con el Excel de costeo, manda
  el Excel y se anota en "conflictos".
- De BENEFICIOS: lo que tiene costo va a "otros" (pestaña Otros costos (MFP)), y las horas de refuerzo a la bolsa de horas
  (horas_bolsa_total). Al crear la MFP del contrato, cada uno queda como un ítem a controlar.

Beneficios ofrecidos al cliente:
- Los que le cuestan a Servigpoder (poligrafías, capacitaciones con costo, equipos, celulares, Visitrack, Acces Too,
  pólizas, vuelos de dron…) van a "otros" con su cantidad por año de contrato (o "entregas_anio"). Si un documento o el
  CATÁLOGO DE OTROS COSTOS trae el valor, úsalo; si no, valor_unitario 0 y agrega a "faltantes":
  "Confirmar que <beneficio> vale $0 (no se encontró su valor)".
- Las horas de refuerzo / horas adicionales anuales son horas de obsequio (horas_bolsa_total por todo el contrato), no "otros".
- Los que no tienen costo directo (estudio de seguridad, informes y reuniones, plataforma de riesgos, bienestar del
  personal, relación con la policía…) NO van a "otros": lístalos en "beneficios_sin_costo".

Responde SOLO con un objeto JSON (sin texto antes ni después) con esta forma:
{
  "nombre_sugerido": "nombre corto del costeo o null",
  "cliente": {"nombre": "razón social o null", "nit": "NIT o null"},
  "municipio": "ciudad del servicio o null",
  "fecha_inicio": "AAAA-MM-DD o null",
  "duracion_meses": número o null,
  "pct_nota_credito": número o null,
  "pct_cupo_inversion": número o null,
  "pct_comision_vendedor": número o null,
  "pct_comision_director": número o null,
  "horas_bolsa_total": número o null,
  "donaciones": número o null,
  "ica_por_mil": número o null,
  "servicios": [{"servicio_id": número, "cantidad": número, "puesto": "texto", "dotacion": "gala|overol",
                 "arma": "sin|fuego|fogeo|traumatica|noletal", "personal": "tipo de personal"}],
  "personal": [{"nombre": "Guarda", "horas_extras": número o null, "auxilios_no_salariales": número o null, "rodamiento": número o null}],
  "otros": [{"nombre": "texto", "tipo_item": "código", "valor_unitario": número, "cantidad": número,
             "vida_util_meses": número o null, "entregas_anio": número o null}],
  "dotacion_puesto": [{"nombre": "nombre exacto del catálogo", "cantidad": número}],
  "resumen": "2 a 5 frases: qué pide el cliente y cómo quedó el costeo",
  "conflictos": ["…"],
  "supuestos": ["…"],
  "faltantes": ["…"],
  "beneficios_sin_costo": ["…"]
}
Si una lista no aplica, déjala vacía []."""


def _contexto(servicios_cat: list[dict], catalogo: list[dict], datos: dict) -> str:
    servicios = [{"servicio_id": s["id"], "descripcion": s["descripcion"], "hombres": s["hombres"]} for s in servicios_cat]
    adicional = [c["nombre"] for c in catalogo if c["grupo"] == "dotacion_puesto"]
    otros = [{"nombre": c["nombre"], "valor_unitario": c["valor_unitario"]} for c in catalogo if c["grupo"] == "otros"]
    personal = [p.get("nombre") for p in datos.get("personal") or [] if p.get("nombre")]
    return ("CATÁLOGO DE SERVICIOS:\n" + json.dumps(servicios, ensure_ascii=False)
            + "\n\nTIPOS DE OTROS COSTOS (tipo_item): " + json.dumps(TIPOS_OTROS, ensure_ascii=False)
            + "\n\nCATÁLOGO DE OTROS COSTOS:\n" + json.dumps(otros, ensure_ascii=False)
            + "\n\nCATÁLOGO DE DOTACIÓN ADICIONAL:\n" + json.dumps(adicional, ensure_ascii=False)
            + "\n\nTIPOS DE PERSONAL QUE YA TIENE EL COSTEO: " + json.dumps(personal or ["Guarda"], ensure_ascii=False))


def _json(texto: str) -> dict:
    inicio, fin = texto.find("{"), texto.rfind("}")
    if inicio < 0 or fin <= inicio:
        raise ia.IAError(502, "La IA no devolvió un costeo legible. Intente de nuevo o use otro modelo.")
    try:
        datos = json.loads(texto[inicio:fin + 1])
    except ValueError as e:
        raise ia.IAError(502, "La IA no devolvió un costeo legible. Intente de nuevo o use otro modelo.") from e
    if not isinstance(datos, dict):
        raise ia.IAError(502, "La IA no devolvió un costeo legible. Intente de nuevo o use otro modelo.")
    return datos


def consultar(archivos: list[dict], indicaciones: str, servicios_cat: list[dict], catalogo: list[dict], datos: dict) -> tuple[dict, ia.Respuesta]:
    partes: list[dict] = [{"type": "text", "text": "Indicaciones del usuario: " + (indicaciones.strip() or "(ninguna)")}]
    for i, a in enumerate(archivos, start=1):
        if "texto" in a:
            partes.append({"type": "text", "text": f"=== Archivo {i}: {a['nombre']} ===\n{a['texto']}"})
        else:
            partes.append({"type": "text", "text": f"=== Archivo {i}: {a['nombre']} (adjunto) ==="})
            partes.append(a["parte"])
    instrucciones = INSTRUCCIONES + "\n\n" + _contexto(servicios_cat, catalogo, datos)
    r = ia.completar(instrucciones, [{"role": "user", "content": partes}], modelo=ia.ajustes().modelo_costeo,
                     max_tokens=MAX_TOKENS_RESPUESTA)
    return _json(r.texto), r


# --- Propuesta normalizada contra los catálogos -------------------------------------------------------

def _texto(v, largo: int) -> str:
    return str(v or "").strip()[:largo]


def _lista_textos(v) -> list[str]:
    if not isinstance(v, list):
        return []
    return [_texto(x, 400) for x in v if _texto(x, 400)][:30]


def aplicar(actual: dict, p: dict, servicios_cat: list[dict], catalogo: list[dict]) -> tuple[dict, dict]:
    """Mezcla la propuesta del modelo con el costeo actual. Devuelve (datos, informe)."""
    d = copy.deepcopy(actual or {})
    faltantes = _lista_textos(p.get("faltantes"))
    conflictos = _lista_textos(p.get("conflictos"))
    supuestos = _lista_textos(p.get("supuestos"))
    llenado: list[str] = []

    meses = _n(p.get("duracion_meses"))
    if meses and 1 <= meses <= 120:
        d["duracion_meses"] = int(round(meses))
        llenado.append("duración")
    for clave, nombre in (("pct_nota_credito", "nota crédito"), ("pct_cupo_inversion", "cupo de inversión"),
                          ("pct_comision_vendedor", "comisión del vendedor"), ("pct_comision_director", "comisión del director")):
        v = _n(p.get(clave))
        if v is not None and 0 <= v <= 100:
            d[clave] = round(v / 100, 6)
            llenado.append(nombre)
    horas = _n(p.get("horas_bolsa_total"))
    if horas is not None and horas >= 0:
        d["horas_bolsa_total"] = horas
        d.pop("horas_bolsa_anual", None)
        llenado.append("horas de obsequio")
    donaciones = _n(p.get("donaciones"))
    if donaciones is not None and donaciones >= 0:
        d["donaciones"] = donaciones
        llenado.append("donaciones")
    ica = _n(p.get("ica_por_mil"))
    if ica is not None and 0 <= ica <= 30:
        d["ica_por_mil"] = ica

    # Personal: solo horas extras y auxilios; salario, auxilio de transporte y Ley 2101 los pone la plataforma
    personal = [dict(x) for x in d.get("personal") or []]
    por_nombre = {_normal(x.get("nombre")): x for x in personal}

    def tipo_personal(nombre: str) -> str:
        nombre = _texto(nombre, 60) or (personal[0]["nombre"] if personal else "Guarda")
        x = por_nombre.get(_normal(nombre))
        if x is None:
            x = {"nombre": nombre, "hombres": 0, "horas_extras": 0, "auxilio_transporte": True, "auxilios_no_salariales": 0, "rodamiento": 0}
            personal.append(x)
            por_nombre[_normal(nombre)] = x
        return x["nombre"]

    for linea in p.get("personal") or []:
        if not isinstance(linea, dict) or not _texto(linea.get("nombre"), 60):
            continue
        x = por_nombre.get(_normal(tipo_personal(linea["nombre"])))
        for clave in ("horas_extras", "auxilios_no_salariales", "rodamiento"):
            v = _n(linea.get(clave))
            if v is not None and v >= 0:
                x[clave] = v

    # Servicios: solo del catálogo; tarifa y hombres salen de ahí
    por_id = {s["id"]: s for s in servicios_cat}
    servicios = []
    for s in p.get("servicios") or []:
        if not isinstance(s, dict):
            continue
        cat = por_id.get(int(_n(s.get("servicio_id"), 0) or 0))
        if cat is None:
            faltantes.append(f"Servicio sin equivalente en el catálogo: {_texto(s.get('puesto') or s.get('descripcion'), 120) or 'sin descripción'}")
            continue
        cantidad = _n(s.get("cantidad"), 1) or 1
        servicios.append({"servicio_id": cat["id"], "descripcion": cat["descripcion"], "puesto": _texto(s.get("puesto"), 120),
                          "cantidad": max(1, int(round(cantidad))), "tarifa": cat["tarifa"], "hombres": cat["hombres"],
                          "dotacion": s.get("dotacion") if s.get("dotacion") in DOTACIONES else "gala",
                          "arma": s.get("arma") if s.get("arma") in ARMAS else "sin",
                          "personal": tipo_personal(s.get("personal") or "")})
    if servicios:
        d["servicios"] = servicios
        d["automatico"] = True  # costeo por puestos: hombres y dotación de la tarifa automáticos
        llenado.append(f"{sum(x['cantidad'] for x in servicios):g} puesto(s)")
    if not personal:
        tipo_personal("Guarda")
    d["personal"] = personal

    # Otros costos (MFP)
    cat_otros = {_normal(c["nombre"]): c for c in catalogo if c["grupo"] == "otros"}
    otros = []
    for o in p.get("otros") or []:
        if not isinstance(o, dict) or not _texto(o.get("nombre"), 200):
            continue
        cat = cat_otros.get(_normal(o["nombre"]))
        valor = _n(o.get("valor_unitario"))
        if valor is None and cat:
            valor = cat["valor_unitario"]
        if valor is None or valor < 0:
            faltantes.append(f"Valor de «{_texto(o['nombre'], 80)}»")
            valor = 0
        fila = {"nombre": cat["nombre"] if cat else _texto(o["nombre"], 200), "valor_unitario": valor,
                "cantidad": _n(o.get("cantidad"), 1) or 1,
                "tipo_item": o.get("tipo_item") if o.get("tipo_item") in TIPOS_OTROS else "OTROS"}
        vida, entregas = _n(o.get("vida_util_meses")), _n(o.get("entregas_anio"))
        if entregas and entregas > 0:
            fila["entregas_anio"] = entregas
        elif vida and vida > 0:
            fila["vida_util_meses"] = vida
        elif cat:
            fila["vida_util_meses"], fila["entregas_anio"] = cat.get("vida_util_meses"), cat.get("entregas_anio")
        otros.append(fila)
    if otros:
        d["otros"] = otros
        llenado.append(f"{len(otros)} otro(s) costo(s)")

    # Dotación adicional: solo del catálogo de compras (con sus precios)
    cat_adic = {_normal(c["nombre"]): c for c in catalogo if c["grupo"] == "dotacion_puesto"}
    adicional = []
    for x in p.get("dotacion_puesto") or []:
        if not isinstance(x, dict) or not _texto(x.get("nombre"), 200):
            continue
        cat = cat_adic.get(_normal(x["nombre"]))
        if cat is None:
            faltantes.append(f"Dotación adicional que no está en el catálogo de compras: {_texto(x['nombre'], 120)}")
            continue
        adicional.append({"nombre": cat["nombre"], "valor_unitario": cat["valor_unitario"], "cantidad": _n(x.get("cantidad"), 1) or 1,
                          "vida_util_meses": cat.get("vida_util_meses"), "entregas_anio": cat.get("entregas_anio")})
    if adicional:
        d["dotacion_puesto"] = adicional
        llenado.append(f"{len(adicional)} elemento(s) de dotación adicional")

    cliente = p.get("cliente") if isinstance(p.get("cliente"), dict) else {}
    informe = {
        "resumen": _texto(p.get("resumen"), 1500),
        "nombre_sugerido": _texto(p.get("nombre_sugerido"), 200) or None,
        "cliente": {"nombre": _texto(cliente.get("nombre"), 200) or None, "nit": _texto(cliente.get("nit"), 30) or None},
        "municipio": _texto(p.get("municipio"), 80) or None,
        "fecha_inicio": _texto(p.get("fecha_inicio"), 10) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", _texto(p.get("fecha_inicio"), 10)) else None,
        "ica_por_mil": ica,
        "llenado": llenado,
        "supuestos": supuestos,
        "conflictos": conflictos,
        "beneficios_sin_costo": _lista_textos(p.get("beneficios_sin_costo")),
        "faltantes": faltantes[:40],
    }
    return d, informe
