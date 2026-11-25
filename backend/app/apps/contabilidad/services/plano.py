"""Plano de World Office «Encabezados + Movimiento de inventario» (compras, tipo FC), en .xls.

Una fila por producto de la factura; el encabezado se repite en cada fila (así lo pide la plantilla de World Office).
Modelo: DocumentosComprasEncabezadosMovimientoInventarioWO.xls (Speed, 2026-11-25). Reglas del usuario:
- Documento Número = AAMM + consecutivo de 3 cifras de las facturas que se van contabilizando en ese mes (2608001).
  Las cuentas de cobro van como Tipo DSS y Prefijo DSS, con su propio número seguido que no reinicia con el mes
  (345, 346…; 2026-11-25).
- Fecha = la fecha de cargue en World Office (la digita contabilidad antes de descargar).
- Tercero interno y externo = NIT del proveedor sin dígito de verificación.
- Una línea por producto.
"""

import io
import re
from dataclasses import dataclass
from datetime import date

import xlwt

COLUMNAS = [
    "Encab: Empresa", "Encab: Tipo Documento", "Encab: Prefijo", "Encab: Documento Número", "Encab: Fecha",
    "Encab: Tercero Interno", "Encab: Tercero Externo", "Encab: Pref Dto Ext", "Encab: No. Dto Ext", "Encab: Nota",
    "Encab: FormaPago", "Encab: Verificado", "Encab: Anulado", "Encab: Fecha Emision",
    *[f"Encab: Personalizado {i}" for i in range(1, 16)],
    "Encab: Importacion", "Encab: Sucursal", "Encab: Clasificación",
    "Detalle: Producto", "Detalle: Bodega", "Detalle: UnidadDeMedida", "Detalle: Cantidad", "Detalle: IVA",
    "Detalle: Valor Unitario", "Detalle: Descuento", "Detalle: Vencimiento", "Detalle: Nota", "Detalle: Centro costos",
    *[f"Detalle: Personalizado{i}" for i in range(1, 16)],
    "Detalle : Código Centro Costos",
]
HOJA = "Encab +Movimi. Inventa"


def documento(fecha: date, consecutivo: int) -> int:
    """2608001: año (26) + mes (08) + consecutivo del mes (001)."""
    return int(f"{fecha:%y%m}{consecutivo:03d}")


def consecutivo(numero: int | None, fecha: date) -> int:
    """El consecutivo de un número de documento si es del mes de `fecha`; 0 si no."""
    t = str(numero or "")
    return int(t[4:]) if t.startswith(f"{fecha:%y%m}") and t[4:].isdigit() else 0


def _numero(valor: str):
    """Los NIT y números de factura van como número (como en la plantilla); si traen letras, como texto."""
    t = re.sub(r"\s", "", valor or "")
    return int(t) if t.isdigit() and len(t) < 16 else t


@dataclass
class Fila:
    documento: int
    nit: str
    prefijo_ext: str
    numero_ext: str
    nota: str
    forma_pago: str
    fecha_emision: date | None
    producto: str
    cantidad: float
    iva: float  # fracción: 0.19
    valor_unitario: float
    vencimiento: date | None
    nota_detalle: str
    centro_costos: str
    codigo_centro: str = ""
    tipo: str = "FC"  # facturas FC / FC; cuentas de cobro DS / DSS
    prefijo: str = "FC"


def excel(filas: list[Fila], fecha: date, empresa: str, bodega: str, unidad: str) -> bytes:
    libro = xlwt.Workbook(encoding="utf-8")
    hoja = libro.add_sheet(HOJA)
    negrita = xlwt.easyxf("font: bold on")
    estilo_fecha = xlwt.easyxf(num_format_str="DD/MM/YYYY")
    for j, c in enumerate(COLUMNAS):
        hoja.write(0, j, c, negrita)
    col = {c: j for j, c in enumerate(COLUMNAS)}
    for i, f in enumerate(filas, start=1):
        valores = {
            "Encab: Empresa": empresa, "Encab: Tipo Documento": f.tipo, "Encab: Prefijo": f.prefijo,
            "Encab: Documento Número": f.documento, "Encab: Tercero Interno": _numero(f.nit), "Encab: Tercero Externo": _numero(f.nit),
            "Encab: Pref Dto Ext": f.prefijo_ext, "Encab: No. Dto Ext": _numero(f.numero_ext), "Encab: Nota": f.nota,
            "Encab: FormaPago": f.forma_pago, "Encab: Verificado": -1, "Encab: Anulado": 0,
            "Detalle: Producto": f.producto, "Detalle: Bodega": bodega, "Detalle: UnidadDeMedida": unidad,
            "Detalle: Cantidad": f.cantidad, "Detalle: IVA": f.iva, "Detalle: Valor Unitario": round(f.valor_unitario, 2),
            "Detalle: Descuento": 0, "Detalle: Nota": f.nota_detalle, "Detalle: Centro costos": f.centro_costos,
            "Detalle : Código Centro Costos": f.codigo_centro,
        }
        for c, v in valores.items():
            if v not in ("", None):
                hoja.write(i, col[c], v)
        for c, v in (("Encab: Fecha", fecha), ("Encab: Fecha Emision", f.fecha_emision), ("Detalle: Vencimiento", f.vencimiento)):
            if v:
                hoja.write(i, col[c], v, estilo_fecha)
    buf = io.BytesIO()
    libro.save(buf)
    return buf.getvalue()
