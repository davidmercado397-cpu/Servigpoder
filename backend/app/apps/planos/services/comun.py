"""Reglas compartidas por los planos de empleados y contratos: limpieza de texto, cédula y fechas,
el libro de Excel (una sola hoja con datos) y la hoja de errores."""

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from io import BytesIO

import openpyxl
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import column_index_from_string

FECHA_MINIMA = "19200101"  # antes es un dato vacío o dañado (18991229 es la fecha cero de Excel)
ENCABEZADO_ERRORES = ["Fila", "Cédula", "Columna", "Tipo", "Problema"]
# Orden de gravedad de los hallazgos: Error (no se puede cargar así), Revisar (se convirtió por aproximación o alias),
# Advertencia (el dato es válido pero no cuadra) e Informativo
TIPOS = ("Error", "Revisar", "Advertencia", "Informativo")


class PlanoInvalido(Exception):
    pass


@dataclass
class Hallazgo:
    fila: int
    cedula: str
    columna: str
    tipo: str
    problema: str
    alias: dict | None = None  # sugerencia para crear un alias desde la pantalla (texto que llegó → código)

    def fila_excel(self) -> list:
        return [self.fila, self.cedula, self.columna, self.tipo, self.problema]


@dataclass
class Resultado:
    hallazgos: list[Hallazgo] = field(default_factory=list)
    resumen: dict[str, int] = field(default_factory=dict)
    cambios: dict[str, int] = field(default_factory=dict)  # "AZ: 1 → 0 (salario > 2 SMLV)": filas

    def sumar(self, clave: str, n: int = 1) -> None:
        self.resumen[clave] = self.resumen.get(clave, 0) + n

    def cambio(self, texto: str) -> None:
        self.cambios[texto] = self.cambios.get(texto, 0) + 1

    def agregar(self, fila: int, cedula: str, columna: str, problema: str, tipo: str = "Error", alias: dict | None = None) -> None:
        self.hallazgos.append(Hallazgo(fila, cedula, columna, tipo, problema, alias))
        self.sumar(tipo)


def col(letra: str) -> int:
    return column_index_from_string(letra)


def texto(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def normalizar(v, enie: bool = True) -> str:
    """Mayúsculas, sin tildes ni signos y con espacios simples. Con enie=False conserva la Ñ."""
    s = texto(v).upper()
    if not enie:
        s = s.replace("Ñ", "\0")
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    s = re.sub(r"[^A-Z0-9\0 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip().replace("\0", "Ñ")


def limpiar_id(v) -> tuple[str, str | None]:
    """Cédula como texto de solo dígitos (1.007.897,943 → 1007897943; 1143831842.0 → 1143831842)."""
    s = texto(v)
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    s = re.sub(r"[\s.,]", "", s)
    if not s or not s.isdigit():
        return texto(v), "Cédula vacía o con caracteres que no son dígitos"
    return s, None


def normalizar_fecha(v) -> tuple[str, bool]:
    """(texto YYYYMMDD, válida). Una fecha que no existe o anterior a 1920 no se adivina: se devuelve como vino."""
    if isinstance(v, (datetime, date)):
        s = v.strftime("%Y%m%d")
        return s, s >= FECHA_MINIMA
    s = texto(v)
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})(?:[ T]00:00:00)?", s) or re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", s)
    if m:
        a, b, c = m.groups()
        s = a + b + c if len(a) == 4 else c + b + a  # aaaa-mm-dd o dd/mm/aaaa
    if re.fullmatch(r"\d{8}", s):
        try:
            datetime.strptime(s, "%Y%m%d")
            return s, s >= FECHA_MINIMA
        except ValueError:
            pass
    return s, False


def a_fecha(s: str) -> datetime:
    return datetime.strptime(s, "%Y%m%d")


def meses_entre(desde: str, hasta: str) -> int:
    a, b = a_fecha(desde), a_fecha(hasta)
    return (b.year - a.year) * 12 + b.month - a.month - (b.day < a.day)


def fila_vacia(ws, fila: int) -> bool:
    return all(texto(c.value) == "" for c in ws[fila])


# ---------------- Libro ----------------

def es_hoja_errores(ws) -> bool:
    primeras = [texto(c.value) for c in ws[1][:3]]
    return ws.title.lower().startswith("errores") or primeras == ENCABEZADO_ERRORES[:3]


def abrir(contenido: bytes):
    """Lee los valores (no las fórmulas) y quita vínculos a otros libros."""
    wb = openpyxl.load_workbook(BytesIO(contenido), data_only=True)
    wb._external_links = []
    return wb


def hoja_de_datos(wb):
    """El plano trae una sola hoja con información. Las hojas de errores de una corrida anterior y las hojas
    vacías se quitan, para que el resultado se pueda volver a procesar sin acumular hojas."""
    for ws in [w for w in wb.worksheets if es_hoja_errores(w)]:
        del wb[ws.title]
    datos = [w for w in wb.worksheets if any(texto(c.value) for fila in w.iter_rows(max_row=3) for c in fila)]
    if len(datos) != 1:
        nombres = ", ".join(w.title for w in datos) or "ninguna"
        raise PlanoInvalido(f"El plano debe traer una sola hoja con información; trae {len(datos)} ({nombres})")
    for w in [w for w in wb.worksheets if w is not datos[0]]:
        del wb[w.title]
    return datos[0]


def ultima_fila(ws) -> int:
    return max((f for f in range(ws.max_row, 1, -1) if not fila_vacia(ws, f)), default=1)


def quitar_filas(ws, ultima: int, borrar: list[int]) -> None:
    if ws.max_row > ultima:
        ws.delete_rows(ultima + 1, ws.max_row - ultima)
    for f in sorted((x for x in borrar if x <= ultima), reverse=True):
        ws.delete_rows(f)


def formato_texto(ws, columnas: list[str], hasta: int) -> None:
    for c in columnas:
        i = col(c)
        for f in range(2, hasta + 1):
            ws.cell(f, i).number_format = "@"


def guardar(wb, hallazgos: list[Hallazgo]) -> bytes:
    """Agrega la hoja Errores (encabezado blanco sobre rojo, primera fila inmovilizada) y devuelve el libro."""
    ws = wb.create_sheet("Errores")
    ws.append(ENCABEZADO_ERRORES)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="C00000")
    for h in hallazgos:
        ws.append(h.fila_excel())
    for letra, ancho in zip("ABCDE", (8, 14, 9, 13, 100)):
        ws.column_dimensions[letra].width = ancho
    ws.freeze_panes = "A2"
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def ordenar(hallazgos: list[Hallazgo]) -> list[Hallazgo]:
    return sorted(hallazgos, key=lambda h: (h.fila, TIPOS.index(h.tipo) if h.tipo in TIPOS else 9))
