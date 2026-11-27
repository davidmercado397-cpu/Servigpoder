"""Legalizaciones: el colaborador entrega el formato (Excel o PDF) con los gastos de un anticipo o un reembolso y el PDF de
soportes (fotos de entrega, transferencias, recibos). La IA lee el formato y revisa que cada gasto tenga su soporte; la
cuenta sale de la columna del formato. Se arma la nota contable de World Office (NC / LG). Los archivos no se guardan.

Reglas del usuario (2026-11-27):
- Cuenta de cada gasto por la columna del formato (tabla editable). En la columna transporte/parqueo/peajes, el detalle dice cuál.
- Contrapartida: reembolso → crédito 233595 por el total. Con anticipo → crédito 13301501 por el anticipo; si gastó más, la
  diferencia crédito 233595; si gastó menos, lo que debe devolver débito a la cuenta por cobrar.
- Columna F (tercero interno) = quien hace el documento; columna G (tercero externo) = el colaborador (listado de empleados).
- Soportes: se verifican con IA y se descartan.
"""

import base64
import io
import json
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone

import xlwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.apps.contabilidad.models import (
    CONTABILIZADA, LEG_COLUMNAS, LISTA, PENDIENTE, CtbLegalizacion, CtbLegConfig, CtbLegLinea, CtbLegPlano, CtbPersona,
)
from app.apps.contabilidad.services.dian import solo_nit
from app.apps.contabilidad.services.servicio import _fecha_excel
from app.apps.contabilidad.services.ia_contable import completar_json
from app.core import ia

log = logging.getLogger("app.contabilidad")
EXT_EXCEL = (".xlsx", ".xlsm")

INSTRUCCIONES_LEER = """Lees el FORMATO DE LEGALIZACIÓN de gastos de una empresa colombiana de vigilancia (reembolso de fondo fijo o
legalización de un anticipo). Devuelve los datos EXACTOS. Valores como números (sin $ ni puntos de miles). Fechas AAAA-MM-DD
(el formato usa día/mes/año). Ignora las filas vacías ($ -) y las de totales.
Cada gasto está en UNA de las columnas de valor: "transporte" (TRANSPORTE/PARQUEO/PEAJES: si el detalle habla de peaje usa
"peajes", si habla de parqueadero o parqueo usa "parqueo", si no "transporte"), "aseo_cafeteria" (ELEMENTOS DE ASEO Y
CAFETERÍA), "alojamiento", "alimentacion", "combustible", "correo" (CORREO Y PORTES), "otros" (OTROS GASTOS). Si el detalle de
otros gastos trae un texto, ponlo en el detalle. "documento" es la cédula o NIT del proveedor/beneficiario de esa fila.
Responde SOLO un JSON:
{"numero": "031", "colaborador": {"nombre": "…", "documento": "solo dígitos"}, "sucursal": "…", "motivo": "…",
 "reembolso_a": "…", "fecha_legalizacion": "AAAA-MM-DD",
 "anticipo": {"fecha": null, "valor": 0, "descripcion": "…"}, "total": 0,
 "lineas": [{"fecha": "AAAA-MM-DD", "beneficiario": "…", "documento": "…", "columna": "alimentacion", "valor": 0, "iva": 0,
             "retencion": 0, "detalle": "…"}]}"""

INSTRUCCIONES_SOPORTES = """Revisas los SOPORTES de una legalización de gastos (fotos de entrega de dinero a vigilantes con su
nombre, pantallazos de transferencias, recibos de peaje, facturas). Para cada GASTO de la lista di si hay un soporte que lo
respalde (por el nombre del beneficiario, el valor, el concepto o el peaje) y qué es. No inventes: si no lo ves, false.
Responde SOLO un JSON: {"lineas": [{"n": 1, "soporte": true, "nota": "foto de entrega con el nombre del vigilante"}]}"""


def config(db: Session) -> CtbLegConfig:
    c = db.get(CtbLegConfig, 1)
    if c is None:
        c = CtbLegConfig(id=1)
        db.add(c)
        db.flush()
    return c


def cuentas(c: CtbLegConfig) -> dict[str, str]:
    return {k: (c.cuentas or {}).get(k) or cta for k, (_, cta) in LEG_COLUMNAS.items()}


def _n(v) -> float:
    try:
        return round(float(str(v).replace("$", "").replace(" ", "").replace(",", "")), 2) if v not in (None, "") else 0.0
    except ValueError:
        return 0.0


def _fecha(v) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def _doc(v) -> str:
    return re.sub(r"\D", "", solo_nit(str(v or "")))[:20]


def _columna(columna: str, detalle: str) -> str:
    col = columna if columna in LEG_COLUMNAS else "otros"
    if col in ("transporte", "parqueo", "peajes"):  # una sola columna en el formato: el detalle dice cuál
        d = detalle.lower()
        col = "peajes" if "peaje" in d else "parqueo" if ("parqueadero" in d or "parqueo" in d) else "transporte"
    return col


def _texto_excel(contenido: bytes) -> str:
    from app.apps.costeo.services.ia_costeo import _excel

    return _excel(contenido)


def leer_formato(nombre: str, contenido: bytes, modelo: str = "") -> dict:
    """El formato en Excel va como texto (barato); en PDF, la IA lo ve con su diseño (para saber en qué columna está cada valor)."""
    if nombre.lower().endswith(EXT_EXCEL):
        partes = [{"type": "text", "text": f"FORMATO (Excel {nombre}), una fila por línea con sus celdas separadas por |:\n{_texto_excel(contenido)}"}]
    elif nombre.lower().endswith(".pdf"):
        partes = [{"type": "text", "text": f"FORMATO: {nombre}"},
                  {"type": "file", "file": {"filename": nombre, "file_data": "data:application/pdf;base64," + base64.b64encode(contenido).decode()}}]
    else:
        raise ValueError("El formato debe ser Excel (.xlsx) o PDF")
    d, _ = completar_json(INSTRUCCIONES_LEER, [{"role": "user", "content": partes}], modelo, 8000)
    return d


def revisar_soportes(leg: CtbLegalizacion, nombre: str, contenido: bytes, modelo: str = "") -> None:
    gastos = [{"n": x.orden, "beneficiario": x.beneficiario, "valor": float(x.valor), "detalle": x.detalle[:200]} for x in leg.lineas]
    partes = [{"type": "text", "text": "GASTOS:\n" + json.dumps(gastos, ensure_ascii=False)},
              {"type": "file", "file": {"filename": nombre, "file_data": "data:application/pdf;base64," + base64.b64encode(contenido).decode()}}]
    d, _ = completar_json(INSTRUCCIONES_SOPORTES, [{"role": "user", "content": partes}], modelo, 6000)
    por_n = {int(x.get("n") or 0): x for x in d.get("lineas") or [] if isinstance(x, dict)}
    for x in leg.lineas:
        r = por_n.get(x.orden)
        x.soporte = bool(r.get("soporte")) if r else False
        x.soporte_nota = str((r or {}).get("nota") or "")[:300]
    leg.soportes_revisados = True
    faltan = [x.orden for x in leg.lineas if not x.soporte]
    leg.avisos = [a for a in leg.avisos or [] if not a.startswith("Sin soporte")]
    if faltan:
        leg.avisos = [*leg.avisos, f"Sin soporte: línea(s) {', '.join(map(str, faltan))}"]


def registrar(db: Session, datos: dict, archivo: str, leida_con: str, usuario_id: int | None) -> CtbLegalizacion:
    c = config(db)
    cta = cuentas(c)
    col = datos.get("colaborador") if isinstance(datos.get("colaborador"), dict) else {}
    ant = datos.get("anticipo") if isinstance(datos.get("anticipo"), dict) else {}
    leg = CtbLegalizacion(
        numero_formato=str(datos.get("numero") or "")[:40], archivo=archivo[:200], leida_con=leida_con,
        colaborador_nombre=str(col.get("nombre") or "")[:200], colaborador_documento=_doc(col.get("documento")),
        sucursal=str(datos.get("sucursal") or "")[:80], motivo=str(datos.get("motivo") or "")[:400],
        fecha_legalizacion=_fecha(datos.get("fecha_legalizacion")), anticipo_fecha=_fecha(ant.get("fecha")),
        anticipo_valor=_n(ant.get("valor")), anticipo_descripcion=str(ant.get("descripcion") or "")[:400], total=_n(datos.get("total")),
        nota=c.nota, creado_por=usuario_id, avisos=[],
    )
    for i, x in enumerate([x for x in datos.get("lineas") or [] if isinstance(x, dict) and _n(x.get("valor"))], start=1):
        detalle = re.sub(r"\s+", " ", str(x.get("detalle") or "")).strip()[:600]
        columna = _columna(str(x.get("columna") or ""), detalle)
        leg.lineas.append(CtbLegLinea(orden=i, fecha=_fecha(x.get("fecha")), beneficiario=str(x.get("beneficiario") or "")[:200],
                                      documento=_doc(x.get("documento")), columna=columna, valor=_n(x.get("valor")), iva=_n(x.get("iva")),
                                      retencion=_n(x.get("retencion")), detalle=detalle, cuenta=cta[columna]))
    if not leg.lineas:
        raise ValueError("No se encontraron gastos en el formato")
    avisos = []
    if leida_con == "ia":
        avisos.append("Formato leído por la IA desde el PDF: verifique valores y cédulas con el formato")
    suma = round(sum(float(x.valor) for x in leg.lineas), 2)
    if leg.total and abs(suma - float(leg.total)) > 1:
        avisos.append(f"Los gastos suman ${suma:,.0f} y el total del formato dice ${float(leg.total):,.0f}: revise".replace(",", "."))
    if any(float(x.iva) or float(x.retencion) for x in leg.lineas):
        avisos.append("Algún gasto trae IVA o retención: la nota contable no los separa; revise si hay que registrarlos aparte")
    empleados = db.scalar(select(CtbPersona.id).where(CtbPersona.tipo == "empleado").limit(1)) is not None
    if empleados and leg.colaborador_documento and not db.scalar(select(CtbPersona.id).where(
            CtbPersona.tipo == "empleado", CtbPersona.documento == leg.colaborador_documento)):
        avisos.append(f"El colaborador {leg.colaborador_documento} no está en el listado de empleados")
    leg.avisos = avisos
    db.add(leg)
    db.flush()
    return leg


def faltantes(leg: CtbLegalizacion) -> list[str]:
    out = []
    if not leg.colaborador_documento:
        out.append("Falta la cédula del colaborador (tercero externo)")
    if not leg.elabora_documento:
        out.append("Falta quién elabora el documento (tercero interno)")
    for x in leg.lineas:
        if x.excluida:
            continue
        if not x.cuenta:
            out.append(f"Línea {x.orden}: falta la cuenta")
        if float(x.valor) <= 0:
            out.append(f"Línea {x.orden}: el valor debe ser mayor que 0")
    if not any(not x.excluida for x in leg.lineas):
        out.append("No hay gastos para llevar al plano")
    return out


@dataclass
class Movimiento:
    cuenta: str
    nota: str
    tercero: str
    debito: float
    credito: float


def movimientos(leg: CtbLegalizacion, c: CtbLegConfig) -> list[Movimiento]:
    """Débito por gasto y la contrapartida: reembolso → reintegro; con anticipo → anticipo ± diferencia."""
    gastos = [x for x in leg.lineas if not x.excluida]
    movs = [Movimiento(x.cuenta, x.detalle, x.documento or leg.colaborador_documento, float(x.valor), 0.0) for x in gastos]
    total = round(sum(float(x.valor) for x in gastos), 2)
    quien = leg.colaborador_documento
    anticipo = round(float(leg.anticipo_valor or 0), 2)
    if anticipo > 0:
        movs.append(Movimiento(c.cuenta_anticipo, f"legalizacion anticipo {leg.anticipo_descripcion}".strip()[:200], quien, 0.0, anticipo))
        if total > anticipo:
            movs.append(Movimiento(c.cuenta_reintegro, "reintegro de dinero", quien, 0.0, round(total - anticipo, 2)))
        elif total < anticipo:
            movs.append(Movimiento(c.cuenta_por_cobrar, "saldo del anticipo por devolver", quien, round(anticipo - total, 2), 0.0))
    else:
        movs.append(Movimiento(c.cuenta_reintegro, "reintegro de dinero", quien, 0.0, total))
    return movs


COLUMNAS_NC = [
    "Encab: Empresa", "Encab: Tipo Documento", "Encab: Prefijo", "Encab: Documento Número", "Encab: Fecha", "Encab: Tercero Interno",
    "Encab: Tercero Externo", "Encab: Nota", "Encab: Verificado", "Encab: Anulado", "Encab: Sucursal", "Encab: Clasificación",
    *[f"Encab: Personalizado {i}" for i in range(1, 16)],
    "Detalle Con: IdCuentaContable", "Detalle Con: Nota", "Detalle Con: Tercero_Externo", "Detalle Con: Cheque", "Detalle Con: Débito",
    "Detalle Con: Crédito", "Detalle Con: Vencimiento", "Detalle Con: Centro costos", "Detalle Con: Activo Fijo", "Detalle Con: Tipo_Base",
    "Detalle Con: Porcentaje_Retención", "Detalle Con: BaseRetención", "Detalle Con: PagoRetención", "Detalle Con: IVAalCosto",
    "Detalle Con: Sucursal", "Detalle Con: Importación", "Detalle Con: Caja Menor", "Detalle Con: Excluir NIIF",
    "Detalle Con: ImpoConsumoCosto", "Detalle Con: No Deducible", "Detalle Con: Código Centro Costos",
]


def _num(v: str):
    t = re.sub(r"\D", "", v or "")
    return int(t) if t and len(t) < 16 else (v or "")


def armar_plano(db: Session, fecha: date, ids: list[int] | None, empresa: str, usuario_id: int | None) -> tuple[bytes, CtbLegPlano, list]:
    q = select(CtbLegalizacion).where(CtbLegalizacion.estado == LISTA).order_by(CtbLegalizacion.id)
    if ids:
        q = q.where(CtbLegalizacion.id.in_(ids))
    legs = list(db.scalars(q))
    if not legs:
        raise ValueError("No hay legalizaciones listas para el plano")
    c = config(db)
    usados = [x for x in db.scalars(select(CtbLegalizacion.documento_numero).where(CtbLegalizacion.estado == CONTABILIZADA)) if x]
    siguiente = max(usados + [c.ultimo_numero or 0])
    libro = xlwt.Workbook(encoding="utf-8")
    hoja = libro.add_sheet("Encabezados+Detalles Contables")
    negrita, f_fecha = xlwt.easyxf("font: bold on"), xlwt.easyxf(num_format_str="DD/MM/YYYY")
    for j, t in enumerate(COLUMNAS_NC):
        hoja.write(0, j, t, negrita)
    col = {t: j for j, t in enumerate(COLUMNAS_NC)}
    fila, items = 1, []
    for leg in legs:
        siguiente += 1
        items.append({"legalizacion_id": leg.id, "documento": siguiente})
        for m in movimientos(leg, c):
            valores = {"Encab: Empresa": empresa, "Encab: Tipo Documento": c.tipo_documento, "Encab: Prefijo": c.prefijo,
                       "Encab: Documento Número": siguiente, "Encab: Tercero Interno": _num(leg.elabora_documento),
                       "Encab: Tercero Externo": _num(leg.colaborador_documento), "Encab: Nota": leg.nota or c.nota,
                       "Detalle Con: IdCuentaContable": _num(m.cuenta), "Detalle Con: Nota": m.nota,
                       "Detalle Con: Tercero_Externo": _num(m.tercero), "Detalle Con: Débito": m.debito, "Detalle Con: Crédito": m.credito}
            for k, v in valores.items():
                if v not in ("", None):
                    hoja.write(fila, col[k], v)
            hoja.write(fila, col["Encab: Fecha"], fecha, f_fecha)
            hoja.write(fila, col["Detalle Con: Vencimiento"], fecha, f_fecha)
            fila += 1
    buf = io.BytesIO()
    libro.save(buf)
    p = CtbLegPlano(fecha=fecha, items=items, usuario_id=usuario_id)
    db.add(p)
    db.flush()
    return buf.getvalue(), p, legs


def contabilizar(db: Session, p: CtbLegPlano, ids: list[int], usuario_id: int | None) -> list[CtbLegalizacion]:
    por_id = {x["legalizacion_id"]: x["documento"] for x in p.items}
    elegidas = [i for i in ids if i in por_id]
    if not elegidas:
        raise ValueError("Elija las legalizaciones del plano que quedaron contabilizadas")
    usados = set(db.scalars(select(CtbLegalizacion.documento_numero).where(CtbLegalizacion.estado == CONTABILIZADA)))
    choque = [por_id[i] for i in elegidas if por_id[i] in usados]
    if choque:
        raise ValueError(f"El documento LG {choque[0]} ya está usado: descargue un plano nuevo")
    ahora, out = datetime.now(timezone.utc), []
    for i in elegidas:
        leg = db.get(CtbLegalizacion, i)
        if leg is not None and leg.estado == LISTA:
            leg.estado, leg.documento_numero, leg.fecha_contable = CONTABILIZADA, por_id[i], p.fecha
            leg.contabilizada_en, leg.contabilizada_por = ahora, usuario_id
            out.append(leg)
    return out


def eliminar_plano(db: Session, p: CtbLegPlano) -> list[CtbLegalizacion]:
    devueltas = []
    for x in p.items:
        leg = db.get(CtbLegalizacion, x["legalizacion_id"])
        if leg is not None and leg.estado == CONTABILIZADA and leg.documento_numero == x["documento"] and leg.fecha_contable == p.fecha:
            leg.estado, leg.documento_numero, leg.fecha_contable, leg.contabilizada_en, leg.contabilizada_por = LISTA, None, None, None, None
            devueltas.append(leg)
    db.delete(p)
    return devueltas


def importar_personas(db: Session, tipo: str, filas: list[list]) -> int:
    """Listado de personas (quienes elaboran o empleados): columnas de nombre y de cédula/identificación."""
    i_enc, enc = None, []
    for i, f in enumerate(filas[:15]):
        t = [str(c or "").strip().lower() for c in f]
        if any("nombre" in c for c in t) and any(re.search(r"c[eé]dula|identificaci|documento|nit", c) for c in t):
            i_enc, enc = i, t
            break
    if i_enc is None:
        raise ValueError("No se encontraron las columnas de nombre y cédula/identificación")
    i_nom = next(j for j, c in enumerate(enc) if "nombre" in c)
    i_doc = next(j for j, c in enumerate(enc) if re.search(r"c[eé]dula|identificaci|documento|nit", c))
    # Informe de personal de World Office: quien ya tiene fecha de retiro pasada queda inactivo
    i_ret = next((j for j, c in enumerate(enc) if "retiro" in c), None)
    hoy = date.today()
    vistos: dict[str, tuple[str, bool]] = {}
    for f in filas[i_enc + 1:]:
        doc = _doc(f[i_doc] if len(f) > i_doc else "")
        if re.search(r"\s\d$", str(f[i_doc] or "").strip()) and len(doc) > 6:  # «NIT 900731891 7»: el último dígito es el DV
            doc = doc[:-1]
        if not doc:
            continue
        retiro = f[i_ret] if i_ret is not None and len(f) > i_ret else None
        retiro = _fecha_excel(retiro) or _fecha(retiro) if retiro not in (None, "") else None
        activo = retiro is None or retiro >= hoy
        if doc in vistos and vistos[doc][1] and not activo:
            continue  # la misma persona con un contrato vigente y otro retirado: queda activa
        vistos[doc] = (str(f[i_nom] if len(f) > i_nom else "").strip()[:200], activo)
    if not vistos:
        raise ValueError("El listado no trae personas")
    existentes = {p.documento: p for p in db.scalars(select(CtbPersona).where(CtbPersona.tipo == tipo))}
    for doc, (nombre, activo) in vistos.items():
        if doc in existentes:
            existentes[doc].nombre, existentes[doc].activo = nombre or existentes[doc].nombre, activo
        else:
            db.add(CtbPersona(tipo=tipo, documento=doc, nombre=nombre, activo=activo))
    return len(vistos)


ESTADOS_LEG = (PENDIENTE, LISTA, CONTABILIZADA, "descartada")
