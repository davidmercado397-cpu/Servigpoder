"""Correos a las áreas cuando el costeo aprobado crea la MFP con su fecha de inicio (el puesto nuevo arranca).

- Compras: los ítems de la MFP y la dotación adicional, para cotizar.
- Almacén: la dotación de la primera entrega, por puesto, para separarla.
- Financiero: el inicio del contrato y lo que se factura.
- Nómina: el salario, las horas extras y recargos y los auxilios de cada tipo de personal.
- Programación: los servicios vendidos (24 h, 12 h…) por puesto, para crearlos en el sistema.
Los destinatarios de cada área se configuran en el costeo; cada envío queda registrado en la MFP.
"""

from collections import defaultdict
from datetime import date
from html import escape

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.apps.costeo.models import CstAreaCorreo, CstCatalogoCosto, CstCosteo, CstMfp, CstNotificacion
from app.apps.costeo.services import puestos
from app.apps.costeo.services.mfp import resumen
from app.core import correo

AREAS = {"compras": "Compras", "almacen": "Almacén", "financiero": "Financiero", "nomina": "Nómina", "programacion": "Programación"}
ENVIADO, ERROR, SIN_DESTINATARIOS = "enviado", "error", "sin_destinatarios"
# Ítems de la MFP que no se compran (descuentos, bolsas internas, horas)
NO_SE_COTIZAN = {"NOTA_CREDITO", "REINVERSION", "BOLSA_HORAS", "PUBLICIDAD", "REPRESENTACION"}


def destinatarios(db: Session) -> dict[str, list[str]]:
    filas = {a.area: a.correos for a in db.scalars(select(CstAreaCorreo))}
    return {area: _correos(filas.get(area, "")) for area in AREAS}


def _correos(texto: str) -> list[str]:
    return [x.strip() for x in texto.replace(";", ",").replace("\n", ",").split(",") if "@" in x]


# --- Formato -----------------------------------------------------------------------------------------

def _pesos(v) -> str:
    return f"${float(v or 0):,.0f}".replace(",", ".")


def _num(v) -> str:
    v = float(v or 0)
    return f"{v:,.2f}".rstrip("0").rstrip(".").replace(",", "X").replace(".", ",").replace("X", ".") if v % 1 else f"{v:,.0f}".replace(",", ".")


def _fecha(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else "—"


def _tabla(encabezados: list[str], filas: list[list], derecha: set[int] = frozenset()) -> str:
    th = "".join(f'<th style="text-align:{"right" if i in derecha else "left"};padding:6px 10px;background:#eef2f7;border-bottom:1px solid #d5dce6">'
                 f"{escape(h)}</th>" for i, h in enumerate(encabezados))
    cuerpo = "".join("<tr>" + "".join(f'<td style="text-align:{"right" if i in derecha else "left"};padding:6px 10px;border-bottom:1px solid #edf0f4">'
                                      f"{escape(str(c))}</td>" for i, c in enumerate(f)) + "</tr>" for f in filas)
    if not filas:
        cuerpo = f'<tr><td colspan="{len(encabezados)}" style="padding:6px 10px;color:#6b7280">Sin elementos</td></tr>'
    return f'<table style="border-collapse:collapse;font-size:13px;margin:8px 0 16px">{"<thead><tr>" + th + "</tr></thead>"}<tbody>{cuerpo}</tbody></table>'


def _pagina(titulo: str, m: CstMfp, cuerpo: str) -> str:
    cab = _tabla(["Dato", "Valor"], [["Cliente", f"{m.cliente.nombre} (NIT {m.cliente.nit or '—'})"], ["MFP", m.numero],
                                    ["Contrato", m.contrato or "—"], ["Inicio del contrato", _fecha(m.fecha_inicio)],
                                    ["Duración", f"{m.duracion_meses or '—'} meses"]])
    return (f'<div style="font-family:Segoe UI,Arial,sans-serif;color:#1f2937;max-width:820px">'
            f'<h2 style="color:#1e3a5f;margin:0 0 4px">{escape(titulo)}</h2>{cab}{cuerpo}'
            f'<p style="font-size:12px;color:#6b7280;margin-top:20px">Correo automático de la plataforma Servigpoder (Costeo y MFP\'s).</p></div>')


def _servicios_filas(datos: dict) -> list[list]:
    filas = []
    for s in datos.get("servicios") or []:
        filas.append([s.get("puesto") or "—", s.get("descripcion", ""), _num(s.get("cantidad") or 1), _num(s.get("hombres")),
                      _num((s.get("hombres") or 0) * (s.get("cantidad") or 1))])
    return filas


# --- Contenido por área ------------------------------------------------------------------------------

def _compras(m: CstMfp, c: CstCosteo | None) -> str:
    items = [[i["tipo"], i["descripcion"] or "—", _pesos(i["pactado"]) + (" al mes" if i["unidad"] == "pesos_mes" else "")]
             for i in resumen(m, date.today())["items"] if i["tipo_codigo"] not in NO_SE_COTIZAN]
    cuerpo = "<h3>Ítems de la MFP para cotizar</h3>" + _tabla(["Ítem", "Descripción", "Pactado"], items, {2})
    if c is not None:
        adicional = [[x.get("nombre", ""), _num(x.get("cantidad")), _pesos(x.get("valor_unitario"))] for x in c.datos.get("dotacion_puesto") or []]
        cuerpo += "<h3>Dotación adicional del puesto</h3>" + _tabla(["Elemento", "Cantidad", "Valor unitario de referencia"], adicional, {1, 2})
    return cuerpo


def _almacen(db: Session, m: CstMfp, c: CstCosteo | None) -> str:
    if c is None:
        return "<p>La MFP no viene de un costeo: no hay dotación calculada.</p>"
    datos = c.datos
    cuerpo = "<p>Dotación de la <b>primera entrega</b> para el inicio del contrato.</p>"
    if datos.get("automatico"):
        catalogo = [{"nombre": x.nombre, "valor_unitario": float(x.valor_unitario), "vida_util_meses": x.vida_util_meses,
                     "entregas_anio": x.entregas_anio, "por_hombre": x.por_hombre, "aplica": x.aplica or "", "cantidad": float(x.cantidad or 1)}
                    for x in db.scalars(select(CstCatalogoCosto).where(CstCatalogoCosto.grupo == "dotacion_tarifa",
                                                                       CstCatalogoCosto.activo.is_(True)).order_by(CstCatalogoCosto.id))]
        total: dict[str, float] = defaultdict(float)
        for s in datos.get("servicios") or []:
            filas = puestos.dotacion_automatica([s], catalogo)
            dot = puestos.DOTACIONES.get(s.get("dotacion") or "gala", "")
            arma = puestos.ARMAS.get(s.get("arma") or "sin", "")
            hombres = (s.get("hombres") or 0) * (s.get("cantidad") or 1)
            cuerpo += (f"<h3>{escape(s.get('puesto') or 'Puesto')} · {escape(s.get('descripcion', ''))}</h3>"
                       f"<p>{_num(s.get('cantidad') or 1)} puesto(s), {_num(hombres)} hombres · dotación {escape(dot)} · {escape(arma)}</p>")
            cuerpo += _tabla(["Elemento", "Cantidad"], [[f["nombre"], _num(f["cantidad"])] for f in filas], {1})
            for f in filas:
                total[f["nombre"]] += f["cantidad"]
        cuerpo += "<h3>Total a separar</h3>" + _tabla(["Elemento", "Cantidad"], [[k, _num(v)] for k, v in total.items()], {1})
    else:
        cuerpo += "<h3>Dotación de la tarifa</h3>" + _tabla(
            ["Elemento", "Cantidad"], [[x.get("nombre", ""), _num(x.get("cantidad"))] for x in datos.get("dotacion_tarifa") or []], {1})
    adicional = [[x.get("nombre", ""), _num(x.get("cantidad"))] for x in datos.get("dotacion_puesto") or []]
    if adicional:
        cuerpo += "<h3>Dotación adicional del puesto</h3>" + _tabla(["Elemento", "Cantidad"], adicional, {1})
    return cuerpo


def _financiero(m: CstMfp, c: CstCosteo | None) -> str:
    r = c.resultado if c is not None else {}
    filas = [["Facturación mensual (tarifa decreto)", _pesos(m.valor_mensual)]]
    if r:
        filas += [["Nota crédito al mes", _pesos(r.get("descuento_nota_credito"))], ["Tarifa neta al mes", _pesos(r.get("tarifa_neta"))],
                  ["MFP pactada", f"{(r.get('mfp') or {}).get('pct_total', 0) * 100:.2f} %"]]
    filas.append(["Facturación del contrato", _pesos(float(m.valor_mensual or 0) * (m.duracion_meses or 0))])
    cuerpo = "<p>Inicia el contrato: los puestos arrancan el " + _fecha(m.fecha_inicio) + ".</p>" + _tabla(["Concepto", "Valor"], filas, {1})
    if c is not None:
        servicios = [[s.get("puesto") or "—", s.get("descripcion", ""), _num(s.get("cantidad") or 1), _pesos(s.get("tarifa")),
                      _pesos((s.get("tarifa") or 0) * (s.get("cantidad") or 1))] for s in c.datos.get("servicios") or []]
        cuerpo += "<h3>Servicios facturados</h3>" + _tabla(["Puesto", "Servicio", "Cantidad", "Tarifa", "Total al mes"], servicios, {2, 3, 4})
    return cuerpo


def _nomina(c: CstCosteo | None) -> str:
    if c is None:
        return "<p>La MFP no viene de un costeo: no hay valores de nómina.</p>"
    personal = c.resultado.get("personal") or []
    filas = []
    for i, p in enumerate(c.datos.get("personal") or []):
        res = personal[i] if i < len(personal) else {}
        partes = res.get("partes") or {}
        filas.append([p.get("nombre", ""), _num(res.get("hombres", p.get("hombres"))), _pesos(partes.get("salario")),
                      _pesos(p.get("horas_extras")), _pesos(p.get("auxilios_no_salariales")), _pesos(p.get("rodamiento")),
                      "Sí" if p.get("auxilio_transporte", True) else "No"])
    cuerpo = ("<p>Valores por hombre al mes que recibirá el personal del puesto nuevo.</p>"
              + _tabla(["Tipo de personal", "Hombres", "Salario", "Horas extras y recargos", "Aux. no salariales", "Rodamiento", "Aux. transporte"],
                       filas, {1, 2, 3, 4, 5}))
    por_tipo = [[s.get("puesto") or "—", s.get("descripcion", ""), s.get("personal") or (c.datos.get("personal") or [{}])[0].get("nombre", "")]
                for s in c.datos.get("servicios") or []]
    return cuerpo + "<h3>Puestos</h3>" + _tabla(["Puesto", "Servicio", "Tipo de personal"], por_tipo)


def _programacion(m: CstMfp, c: CstCosteo | None) -> str:
    if c is None:
        return "<p>La MFP no viene de un costeo: no hay servicios detallados.</p>"
    filas = _servicios_filas(c.datos)
    total = sum((s.get("hombres") or 0) * (s.get("cantidad") or 1) for s in c.datos.get("servicios") or [])
    return (f"<p>Servicios vendidos para crear en el sistema a partir del {_fecha(m.fecha_inicio)}.</p>"
            + _tabla(["Puesto", "Servicio", "Cantidad", "Hombres por servicio", "Hombres"], filas, {2, 3, 4})
            + f"<p><b>Total: {_num(total)} hombres.</b></p>")


def mensajes(db: Session, m: CstMfp) -> dict[str, tuple[str, str]]:
    """{área: (asunto, html)} de una MFP."""
    c = db.get(CstCosteo, m.costeo_id) if m.costeo_id else None
    base = f"MFP {m.numero} · {m.cliente.nombre} · inicia {_fecha(m.fecha_inicio)}"
    contenido = {
        "compras": ("Ítems para cotizar", _compras(m, c)),
        "almacen": ("Dotación para separar", _almacen(db, m, c)),
        "financiero": ("Inicio del contrato", _financiero(m, c)),
        "nomina": ("Valores de nómina del puesto nuevo", _nomina(c)),
        "programacion": ("Servicios vendidos", _programacion(m, c)),
    }
    return {area: (f"{titulo} · {base}", _pagina(f"{titulo} — {AREAS[area]}", m, cuerpo)) for area, (titulo, cuerpo) in contenido.items()}


def notificar(db: Session, m: CstMfp, usuario_id: int | None) -> list[CstNotificacion]:
    """Envía a cada área su correo y lo registra en la MFP (también si no hay destinatarios o falla)."""
    para = destinatarios(db)
    contenido = mensajes(db, m)
    con_destino = [a for a in AREAS if para[a]]
    errores = dict(zip(con_destino, correo.enviar([correo.Mensaje(para[a], *contenido[a]) for a in con_destino]), strict=True)) if con_destino else {}
    registros = []
    for area in AREAS:
        if not para[area]:
            estado, error = SIN_DESTINATARIOS, "No hay correos configurados para el área"
        else:
            error = errores.get(area)
            estado = ERROR if error else ENVIADO
        n = CstNotificacion(mfp_id=m.id, area=area, destinatarios=", ".join(para[area]), asunto=contenido[area][0][:300],
                            estado=estado, error=error or "", usuario_id=usuario_id)
        db.add(n)
        registros.append(n)
    db.flush()
    return registros
