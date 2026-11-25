"""Contabilidad: registrar las facturas leídas, proponer cómo contabilizarlas, armar el plano y marcar lo contabilizado."""

import io
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from openpyxl import load_workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.apps.contabilidad.models import (
    APARTE, CONTABILIZADA, LISTA, PENDIENTE, CtbCentroCostos, CtbConfig, CtbFactura, CtbLinea, CtbPlano, CtbProducto, CtbTercero,
)
from app.apps.contabilidad.services import dian, ia_contable, plano
from app.core import ia

log = logging.getLogger("app.contabilidad")
CENTROS_INICIALES = ["Administracion"]


def sembrar(db: Session) -> None:
    if db.get(CtbConfig, 1) is None:
        db.add(CtbConfig(id=1))
    if db.scalar(select(CtbCentroCostos.id).limit(1)) is None:
        for nombre in CENTROS_INICIALES:
            db.add(CtbCentroCostos(nombre=nombre))
    db.flush()


def config(db: Session) -> CtbConfig:
    c = db.get(CtbConfig, 1)
    if c is None:
        sembrar(db)
        c = db.get(CtbConfig, 1)
    return c


# --- Registrar facturas -----------------------------------------------------------------------------

@dataclass
class Resultado:
    nuevas: list[CtbFactura] = field(default_factory=list)
    duplicadas: list[str] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)

    def texto(self) -> str:
        partes = []
        if self.nuevas:
            partes.append(f"{len(self.nuevas)} factura(s) nueva(s): " + ", ".join(f"{f.prefijo}{f.numero}" for f in self.nuevas))
        if self.duplicadas:
            partes.append(f"ya registrada(s): {', '.join(self.duplicadas)}")
        partes += self.errores
        return "; ".join(partes) or "Sin factura adjunta"


def registrar(db: Session, f: dian.Factura, *, leida_con: str = "xml", origen: str = "correo", correo_de: str = "",
              correo_asunto: str = "", correo_fecha: datetime | None = None, proponer: bool = True) -> CtbFactura | None:
    """Guarda los datos de la factura (nunca el documento). None si ya estaba (mismo CUFE)."""
    if db.scalar(select(CtbFactura.id).where(CtbFactura.cufe == f.cufe)):
        return None
    c = config(db)
    avisos = []
    estado, motivo = PENDIENTE, ""
    if f.tipo != "factura":
        estado, motivo = APARTE, "Es una nota " + ("crédito" if f.tipo == "nota_credito" else "débito") + ", no una factura de compra"
    elif c.empresa_nit and f.comprador_nit != dian.solo_nit(c.empresa_nit):
        estado, motivo = APARTE, f"La factura es a nombre de {f.comprador_nombre or 'otro comprador'} (NIT {f.comprador_nit or 'sin NIT'})"
    if leida_con == "ia":
        avisos.append("Leída por la IA desde el PDF (no vino el XML): verifique los valores con la factura")
    hay_terceros = db.scalar(select(CtbTercero.id).limit(1)) is not None
    if hay_terceros and not db.scalar(select(CtbTercero.id).where(CtbTercero.nit == f.emisor_nit)):
        avisos.append(f"El proveedor NIT {f.emisor_nit} no está en el listado de terceros de World Office: créelo antes de cargar el plano")
    fac = CtbFactura(
        cufe=f.cufe[:120], tipo=f.tipo, cuenta_cobro=f.cuenta_cobro, estado=estado, motivo_aparte=motivo[:300], leida_con=leida_con, origen=origen,
        correo_de=correo_de[:200], correo_asunto=correo_asunto[:300], correo_fecha=correo_fecha,
        prefijo=f.prefijo, numero=f.numero, fecha_emision=f.fecha_emision, fecha_vencimiento=f.fecha_vencimiento,
        forma_pago=f.forma_pago, moneda=f.moneda, emisor_nit=f.emisor_nit, emisor_dv=f.emisor_dv, emisor_nombre=f.emisor_nombre,
        comprador_nit=f.comprador_nit, comprador_nombre=f.comprador_nombre, subtotal=f.subtotal, iva=f.iva, total=f.total,
        retenciones=f.retenciones, avisos=avisos,
        lineas=[CtbLinea(orden=x.orden, codigo_proveedor=x.codigo_proveedor, descripcion=x.descripcion, cantidad=x.cantidad,
                         valor_unitario=x.valor_unitario, subtotal=x.subtotal, iva_pct=x.iva_pct, iva_valor=x.iva_valor)
                for x in f.lineas],
    )
    db.add(fac)
    db.flush()
    if proponer:
        proponer_contabilizacion(db, fac)
    return fac


def procesar_archivos(db: Session, archivos: list[tuple[str, bytes]], **meta) -> Resultado:
    """Adjuntos de un correo o archivos cargados: zip, XML y PDF. Los XML mandan; un PDF solo se lee (con IA) si no vino XML."""
    res = Resultado()
    try:
        adj = dian.abrir_adjuntos(archivos)
    except dian.FacturaInvalida as e:
        res.errores.append(str(e))
        return res
    leidas = 0
    for nombre, datos in adj.xmls:
        try:
            f = dian.leer_xml(datos)
        except dian.FacturaInvalida as e:
            if "no es una factura" not in str(e):  # los XML que no son facturas (p. ej. respuestas de la DIAN) se ignoran
                res.errores.append(f"{nombre}: {e}")
            continue
        leidas += 1
        fac = registrar(db, f, leida_con="xml", **meta)
        (res.nuevas.append(fac) if fac else res.duplicadas.append(f"{f.prefijo}{f.numero}"))
    if not leidas:
        for nombre, datos in adj.pdfs:
            if not ia.configurada():
                res.errores.append(f"{nombre}: vino solo el PDF y la IA no está configurada para leerlo")
                continue
            try:
                f = ia_contable.leer_pdf(nombre, datos, config(db).modelo)
            except (dian.FacturaInvalida, ia.IAError) as e:
                res.errores.append(f"{nombre}: {getattr(e, 'mensaje', str(e))}")
                continue
            fac = registrar(db, f, leida_con="ia", **meta)
            (res.nuevas.append(fac) if fac else res.duplicadas.append(f"{f.prefijo}{f.numero}"))
    return res


# --- Cómo contabilizar: la IA propone, con lo que se ha hecho antes con el proveedor -------------------

def historial(db: Session, nit: str, sin: int | None = None) -> list[dict]:
    q = (select(CtbLinea.descripcion, CtbLinea.producto, CtbLinea.centro_costos, CtbLinea.nota)
         .join(CtbFactura).where(CtbFactura.emisor_nit == nit, CtbFactura.estado.in_((LISTA, CONTABILIZADA)), CtbLinea.producto != "")
         .order_by(CtbFactura.id.desc()).limit(30))
    if sin:
        q = q.where(CtbFactura.id != sin)
    return [{"descripcion": d[:120], "producto": p, "centro_costos": c, "nota": n} for d, p, c, n in db.execute(q)]


def proponer_contabilizacion(db: Session, fac: CtbFactura) -> None:
    """Llena producto, centro de costos y notas de lo que esté vacío. Sin IA (o si falla), repite lo más usado con el proveedor."""
    productos = [(c, n) for c, n in db.execute(select(CtbProducto.codigo, CtbProducto.nombre).where(CtbProducto.activo.is_(True)))]
    centros = list(db.scalars(select(CtbCentroCostos.nombre).where(CtbCentroCostos.activo.is_(True)).order_by(CtbCentroCostos.nombre)))
    hist = historial(db, fac.emisor_nit, sin=fac.id)
    validos = {c for c, _ in productos}
    propuesta: dict = {}
    if ia.configurada() and (productos or hist):
        try:
            propuesta = ia_contable.proponer(
                {"proveedor": fac.emisor_nombre, "nit": fac.emisor_nit,
                 "lineas": [{"n": x.orden, "descripcion": x.descripcion, "cantidad": float(x.cantidad), "valor": float(x.subtotal),
                             "iva_pct": float(x.iva_pct)} for x in fac.lineas]},
                productos, centros, hist, config(db).modelo)
        except ia.IAError as e:
            log.warning("La IA no propuso la factura %s: %s", fac.id, e.mensaje)
            fac.avisos = [*fac.avisos, f"La IA no pudo proponer la cuenta: {e.mensaje}"]
    por_n = {int(x.get("n") or 0): x for x in propuesta.get("lineas") or [] if isinstance(x, dict)}
    # Sin IA: lo más usado con el proveedor
    comun_p = Counter(h["producto"] for h in hist).most_common(1)
    comun_c = Counter(h["centro_costos"] for h in hist if h["centro_costos"]).most_common(1)
    for x in fac.lineas:
        p = por_n.get(x.orden, {})
        producto = str(p.get("producto") or "").strip()
        if not x.producto:
            x.producto = producto if producto and (not validos or producto in validos) else (comun_p[0][0] if comun_p else "")
        centro = str(p.get("centro_costos") or "").strip()
        if not x.centro_costos:
            x.centro_costos = centro if centro and (not centros or centro in centros) else (comun_c[0][0] if comun_c else "")
        if not x.nota:
            x.nota = str(p.get("nota") or "").strip()[:200] or (hist[0]["nota"] if hist else "")
    if not fac.nota:
        fac.nota = str(propuesta.get("nota") or "").strip()[:300] or (fac.lineas[0].nota.upper() if fac.lineas and fac.lineas[0].nota else "")
    dudas = [str(d)[:300] for d in propuesta.get("dudas") or [] if d]
    if dudas:
        fac.avisos = [*fac.avisos, *[f"IA: {d}" for d in dudas[:5]]]


def faltantes(fac: CtbFactura) -> list[str]:
    """Lo que impide que la factura salga en el plano."""
    out = []
    for x in fac.lineas:
        if not x.producto:
            out.append(f"Línea {x.orden}: falta el producto (cuenta)")
        if not x.centro_costos:
            out.append(f"Línea {x.orden}: falta el centro de costos")
    if not fac.nota.strip():
        out.append("Falta la nota de la factura")
    return out


# --- Plano y contabilización ------------------------------------------------------------------------

def _base_consecutivo(db: Session, fecha: date, cuenta_cobro: bool, ultimo_wo: int | None) -> int:
    """El último número usado en esa serie: por las ya contabilizadas aquí o el último que se registró en World Office
    (Configuración). Facturas (FC): consecutivo del mes de `fecha` (AAMM + 001). Cuentas de cobro (DSS): número seguido
    que no reinicia con el mes (345, 346…)."""
    nums = list(db.scalars(select(CtbFactura.documento_numero).where(
        CtbFactura.estado == CONTABILIZADA, CtbFactura.documento_numero.is_not(None), CtbFactura.cuenta_cobro.is_(cuenta_cobro))))
    if cuenta_cobro:
        return max(nums + [ultimo_wo or 0])
    return max([plano.consecutivo(n, fecha) for n in nums] + [plano.consecutivo(ultimo_wo, fecha)])


def armar_plano(db: Session, fecha: date, ids: list[int] | None, usuario_id: int | None) -> tuple[bytes, CtbPlano, list[CtbFactura]]:
    q = select(CtbFactura).where(CtbFactura.estado == LISTA).order_by(CtbFactura.fecha_emision, CtbFactura.id)
    if ids:
        q = q.where(CtbFactura.id.in_(ids))
    facturas = list(db.scalars(q))
    if not facturas:
        raise ValueError("No hay facturas listas para el plano")
    c = config(db)
    # Cada serie lleva su consecutivo: facturas (FC) y cuentas de cobro (DSS)
    siguiente = {False: _base_consecutivo(db, fecha, False, c.ultimo_fc), True: _base_consecutivo(db, fecha, True, c.ultimo_ds)}
    filas, items = [], []
    for fac in facturas:
        siguiente[fac.cuenta_cobro] += 1
        numero = siguiente[True] if fac.cuenta_cobro else plano.documento(fecha, siguiente[False])
        tipo, prefijo = (c.tipo_documento_ds, c.prefijo_ds) if fac.cuenta_cobro else (c.tipo_documento, c.prefijo)
        items.append({"factura_id": fac.id, "documento": numero, "serie": tipo})
        for x in fac.lineas:
            filas.append(plano.Fila(
                documento=numero, nit=fac.emisor_nit, prefijo_ext=fac.prefijo, numero_ext=fac.numero, nota=fac.nota,
                forma_pago=fac.forma_pago, fecha_emision=fac.fecha_emision, producto=x.producto, cantidad=float(x.cantidad),
                iva=round(float(x.iva_pct) / 100, 4), valor_unitario=float(x.valor_unitario), vencimiento=fac.fecha_vencimiento,
                nota_detalle=x.nota, centro_costos=x.centro_costos,
                codigo_centro=db.scalar(select(CtbCentroCostos.codigo).where(CtbCentroCostos.nombre == x.centro_costos)) or "",
                tipo=tipo, prefijo=prefijo))
    contenido = plano.excel(filas, fecha, c.empresa_nombre, c.bodega, c.unidad)
    p = CtbPlano(fecha=fecha, items=items, usuario_id=usuario_id)
    db.add(p)
    db.flush()
    return contenido, p, facturas


def eliminar_plano(db: Session, p: CtbPlano) -> list[CtbFactura]:
    """Borra un plano (por si algo salió mal). Las facturas que se marcaron contabilizadas con él vuelven a «lista»,
    sin número de documento, para salir en el próximo plano."""
    devueltas = []
    for x in p.items:
        fac = db.get(CtbFactura, x["factura_id"])
        if fac is not None and fac.estado == CONTABILIZADA and fac.documento_numero == x["documento"] and fac.fecha_contable == p.fecha:
            fac.estado, fac.documento_numero, fac.fecha_contable = LISTA, None, None
            fac.contabilizada_en = fac.contabilizada_por = None
            devueltas.append(fac)
    db.delete(p)
    return devueltas


def contabilizar(db: Session, p: CtbPlano, ids: list[int], usuario_id: int | None) -> list[CtbFactura]:
    """Marca como contabilizadas las facturas del plano que quedaron en World Office: no vuelven a salir en el plano."""
    por_id = {x["factura_id"]: x["documento"] for x in p.items}
    elegidas = [i for i in ids if i in por_id]
    if not elegidas:
        raise ValueError("Elija las facturas del plano que quedaron contabilizadas")
    usados = set(db.execute(select(CtbFactura.cuenta_cobro, CtbFactura.documento_numero).where(CtbFactura.estado == CONTABILIZADA)).all())
    serie = {f.id: f.cuenta_cobro for f in db.scalars(select(CtbFactura).where(CtbFactura.id.in_(elegidas)))}
    choque = [por_id[i] for i in elegidas if (serie.get(i, False), por_id[i]) in usados]
    if choque:
        raise ValueError(f"El documento {choque[0]} ya está usado por otra factura contabilizada: descargue un plano nuevo")
    ahora = datetime.now(timezone.utc)
    out = []
    for fid in elegidas:
        fac = db.get(CtbFactura, fid)
        if fac is None or fac.estado != LISTA:
            continue
        fac.estado, fac.documento_numero, fac.fecha_contable = CONTABILIZADA, por_id[fid], p.fecha
        fac.contabilizada_en, fac.contabilizada_por = ahora, usuario_id
        out.append(fac)
    return out


# --- Catálogos desde los Excel de World Office (el archivo no se guarda) ----------------------------

def _filas(contenido: bytes) -> list[list]:
    libro = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    try:
        return [list(f) for f in libro.worksheets[0].iter_rows(values_only=True)]
    finally:
        libro.close()


def importar_cuentas(db: Session, contenido: bytes) -> int:
    """Libro auxiliar o listado de cuentas: filas «515515 PASAJES AEREOS» (o código y nombre en dos columnas)."""
    vistos: dict[str, str] = {}
    for f in _filas(contenido):
        a = str(f[0] or "").strip() if f else ""
        if not a or a.lower().startswith("total"):
            continue
        m = re.match(r"^(\d{4,12})\s+(.+)$", a)
        if m:
            vistos[m.group(1)] = m.group(2).strip()[:200]
        elif re.fullmatch(r"\d{4,12}", a) and len(f) > 1 and f[1]:
            vistos[a] = str(f[1]).strip()[:200]
    if not vistos:
        raise ValueError("No se encontraron cuentas (filas con «código nombre»)")
    existentes = {p.codigo: p for p in db.scalars(select(CtbProducto))}
    for codigo, nombre in vistos.items():
        if codigo in existentes:
            existentes[codigo].nombre, existentes[codigo].activo = nombre, True
        else:
            db.add(CtbProducto(codigo=codigo, nombre=nombre))
    return len(vistos)


def importar_terceros(db: Session, contenido: bytes) -> int:
    """Listado de terceros de World Office: Nombre e Identificación («NIT 900731891 7»)."""
    filas = _filas(contenido)
    i_enc = next((i for i, f in enumerate(filas[:10]) if any(str(c or "").strip().lower() == "identificacion" for c in f)), None)
    if i_enc is None:
        raise ValueError("No se encontró la columna «Identificacion» del listado de terceros")
    enc = [str(c or "").strip().lower() for c in filas[i_enc]]
    i_nombre, i_id = enc.index("nombre") if "nombre" in enc else 0, enc.index("identificacion")
    vistos: dict[str, tuple[str, str]] = {}
    for f in filas[i_enc + 1:]:
        ident = str(f[i_id] or "").strip() if len(f) > i_id else ""
        m = re.match(r"^(?:[A-Z]+\s+)?([\d.]+)(?:[\s-]+(\d))?$", ident.upper())
        if m:
            vistos[m.group(1).replace(".", "")] = (m.group(2) or "", str(f[i_nombre] or "").strip()[:200])
    if not vistos:
        raise ValueError("El listado no trae terceros")
    existentes = {t.nit: t for t in db.scalars(select(CtbTercero))}
    for nit, (dv, nombre) in vistos.items():
        if nit in existentes:
            existentes[nit].dv, existentes[nit].nombre = dv, nombre
        else:
            db.add(CtbTercero(nit=nit, dv=dv, nombre=nombre))
    # Las facturas pendientes que avisaban «no está en el listado» se revisan de nuevo
    for fac in db.scalars(select(CtbFactura).where(CtbFactura.estado.in_((PENDIENTE, LISTA, APARTE)))):
        if fac.emisor_nit in vistos:
            fac.avisos = [a for a in fac.avisos if "listado de terceros" not in a]
    return len(vistos)


def conteos(db: Session) -> dict[str, int]:
    return dict(db.execute(select(CtbFactura.estado, func.count()).group_by(CtbFactura.estado)).all())
