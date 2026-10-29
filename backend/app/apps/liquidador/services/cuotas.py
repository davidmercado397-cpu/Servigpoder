"""Importación de cuotas (descuentos periódicos autorizados: mutual, plan exequial…) desde la lista que manda cada entidad.

Se busca la fila de encabezados con la cédula (IDENTIFICACION, CEDULA o DOCUMENTO) y el valor se lee de la columna que se
indique (letra). Cada persona queda con una cuota con la descripción dada (p. ej. «Cuota mutual»), valor mensual y la
quincena elegida. Volver a importar la misma cuota actualiza el valor; a quien ya no está en la lista se le desactiva (si
se pide). Filas sin cédula numérica (totales, títulos) se omiten. El archivo se procesa y se descarta.
"""

import re
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation

from openpyxl.utils import column_index_from_string
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.apps.liquidador.models import CUOTA, LiqDescuento, LiqEmpleado
from app.apps.liquidador.services.personal import ErrorArchivo, Indice, _abrir, _norm, _texto, documento

CLAVES_CEDULA = ("IDENTIFICACION", "CEDULA", "DOCUMENTO", "NUMERO DE IDENTIFICACION", "CC")


def _valor(v) -> Decimal | None:
    if isinstance(v, (int, float)):
        return Decimal(str(v))
    texto = re.sub(r"[^\d.,-]", "", str(v or ""))
    if not texto:
        return None
    if "," in texto and "." in texto:  # 1.234,56 o 1,234.56: el último separador es el decimal
        texto = texto.replace(".", "").replace(",", ".") if texto.rfind(",") > texto.rfind(".") else texto.replace(",", "")
    elif texto.count(".") > 1 or (texto.count(".") == 1 and len(texto.split(".")[1]) == 3):
        texto = texto.replace(".", "")  # 20.900 = veinte mil novecientos
    texto = texto.replace(",", ".")
    try:
        return Decimal(texto)
    except InvalidOperation:
        return None


def importar(db: Session, contenido: bytes, descripcion: str, columna_valor: str, quincena: str, desde: date,
             desactivar_ausentes: bool = True) -> dict:
    try:
        i_valor = column_index_from_string(columna_valor.strip().upper()) - 1
    except ValueError as e:
        raise ErrorArchivo(f"La columna del valor «{columna_valor}» no es válida: escriba la letra (p. ej. I)") from e
    libro = _abrir(contenido)
    hoja = libro.worksheets[0]
    filas = list(hoja.iter_rows(values_only=True))
    i_doc, inicio = None, 0
    for n, fila in enumerate(filas[:30]):
        for i, celda in enumerate(fila):
            if _norm(celda) in CLAVES_CEDULA:
                i_doc, inicio = i, n + 1
                break
        if i_doc is not None:
            break
    if i_doc is None:
        raise ErrorArchivo("No se encontró la columna de la cédula (IDENTIFICACION, CEDULA o DOCUMENTO) en las primeras filas")

    hallazgos, valores, nombres, filas_de = [], defaultdict(Decimal), {}, defaultdict(list)
    for num, fila in enumerate(filas[inicio:], start=inicio + 1):
        celda = fila[i_doc] if i_doc < len(fila) else None
        doc, solo_numeros = documento(celda)
        if not doc or not solo_numeros:
            continue  # títulos, totales o filas vacías
        valor = _valor(fila[i_valor] if i_valor < len(fila) else None)
        if not valor or valor <= 0:
            hallazgos.append({"hoja": hoja.title, "fila": num, "documento": doc, "detalle": f"Sin valor en la columna {columna_valor.upper()}: no se cargó"})
            continue
        valores[doc] += valor
        filas_de[doc].append(num)
        nombres[doc] = next((_texto(c, 200) for c in fila if isinstance(c, str) and len(c.split()) >= 2 and not _valor(c)), doc)
    if not valores:
        raise ErrorArchivo(f"No se encontraron filas con cédula y valor en la columna {columna_valor.upper()}")

    indice = Indice(db.scalars(select(LiqEmpleado)))
    existentes = {x.empleado_id: x for x in db.scalars(select(LiqDescuento).where(LiqDescuento.tipo == CUOTA, LiqDescuento.activo.is_(True)))
                  if _norm(x.descripcion) == _norm(descripcion)}
    creadas = actualizadas = 0
    vistos: set[int] = set()
    for doc, valor in valores.items():
        if len(filas_de[doc]) > 1:
            hallazgos.append({"hoja": hoja.title, "fila": filas_de[doc][0], "documento": doc,
                              "detalle": f"Aparece en {len(filas_de[doc])} filas ({', '.join(map(str, filas_de[doc]))}): se sumaron ({valor:,.0f})"})
        e = indice.buscar(doc)
        if e is None:
            hallazgos.append({"hoja": hoja.title, "fila": filas_de[doc][0], "documento": doc,
                              "detalle": f"{nombres[doc]} no está en la base de empleados: no se cargó"})
            continue
        if e.estado == "retirado":
            hallazgos.append({"hoja": hoja.title, "fila": filas_de[doc][0], "documento": doc,
                              "detalle": f"{e.nombre} está retirado: se cargó la cuota, pero no se descontará si no está en una nómina"})
        vistos.add(e.id)
        x = existentes.get(e.id)
        if x is None:
            db.add(LiqDescuento(empleado_id=e.id, tipo=CUOTA, descripcion=descripcion, valor_mensual=valor, desde=desde,
                                quincena=quincena, activo=True))
            creadas += 1
        else:
            x.valor_mensual, x.porcentaje, x.quincena = valor, None, quincena
            actualizadas += 1
    desactivadas = 0
    if desactivar_ausentes:
        for eid, x in existentes.items():
            if eid not in vistos:
                x.activo = False
                desactivadas += 1
    db.flush()
    return {"filas": sum(len(v) for v in filas_de.values()), "personas": len(valores), "creadas": creadas, "actualizadas": actualizadas,
            "desactivadas": desactivadas, "total": float(sum(valores.values())), "hallazgos": hallazgos}
