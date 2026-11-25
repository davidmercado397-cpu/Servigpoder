"""Contabilidad (Speed): factura electrónica de la DIAN (zip con XML y PDF) → bandeja → plano .xls de World Office."""

import io
import json
import zipfile
from datetime import date
from email.message import EmailMessage

import httpx
import pytest
import xlrd

from app.apps.contabilidad.services import buzon, dian, plano
from app.core import ia
from app.core.config import get_settings
from tests.conftest import xlsx

API = "/api/contabilidad"
SPEED_NIT = "900259118"


def factura_xml(numero="1841310", cufe="5caa7e85955c1c6660e801ea26044b80", comprador_nit=SPEED_NIT, tipo="Invoice",
                lineas=((1, "Pasajes aéreos BOG-CLO a nombre de LAN COLOMBIA", 267800.00, 19, 46380.00),
                        (1, "Ingreso propio PRICE RES SAS", 16845.38, 19, 3200.62))) -> str:
    """Factura UBL 2.1 como la de la DIAN (PTC6-1841310 de PRICE RES S.A.S)."""
    filas = "".join(f"""
  <cac:{tipo}Line><cbc:ID>{i}</cbc:ID><cbc:{'Invoiced' if tipo == 'Invoice' else 'Credited'}Quantity unitCode="94">{c}</cbc:{'Invoiced' if tipo == 'Invoice' else 'Credited'}Quantity>
    <cbc:LineExtensionAmount currencyID="COP">{v:.2f}</cbc:LineExtensionAmount>
    <cac:TaxTotal><cbc:TaxAmount currencyID="COP">{iv:.2f}</cbc:TaxAmount><cac:TaxSubtotal><cbc:TaxAmount currencyID="COP">{iv:.2f}</cbc:TaxAmount>
      <cac:TaxCategory><cbc:Percent>{p:.2f}</cbc:Percent><cac:TaxScheme><cbc:ID>01</cbc:ID><cbc:Name>IVA</cbc:Name></cac:TaxScheme></cac:TaxCategory></cac:TaxSubtotal></cac:TaxTotal>
    <cac:Item><cbc:Description>{d}</cbc:Description><cac:SellersItemIdentification><cbc:ID>{i}</cbc:ID></cac:SellersItemIdentification></cac:Item>
    <cac:Price><cbc:PriceAmount currencyID="COP">{v / c:.2f}</cbc:PriceAmount></cac:Price>
  </cac:{tipo}Line>""" for i, (c, d, v, p, iv) in enumerate(lineas, start=1))
    sub = sum(x[2] for x in lineas)
    iva = sum(x[4] for x in lineas)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<{tipo} xmlns="urn:oasis:names:specification:ubl:schema:xsd:{tipo}-2"
 xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
 xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
 xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"
 xmlns:sts="dian:gov:co:facturaelectronica:Structures-2-1">
  <ext:UBLExtensions><ext:UBLExtension><ext:ExtensionContent><sts:DianExtensions><sts:InvoiceControl>
    <sts:AuthorizedInvoices><sts:Prefix>PTC6</sts:Prefix></sts:AuthorizedInvoices></sts:InvoiceControl></sts:DianExtensions>
  </ext:ExtensionContent></ext:UBLExtension></ext:UBLExtensions>
  <cbc:ID>PTC6{numero}</cbc:ID><cbc:UUID schemeName="CUFE-SHA384">{cufe}</cbc:UUID>
  <cbc:IssueDate>2026-08-22</cbc:IssueDate><cbc:DueDate>2026-08-22</cbc:DueDate><cbc:DocumentCurrencyCode>COP</cbc:DocumentCurrencyCode>
  <cac:AccountingSupplierParty><cac:Party><cac:PartyTaxScheme><cbc:RegistrationName>PRICE RES S.A.S</cbc:RegistrationName>
    <cbc:CompanyID schemeAgencyID="195" schemeID="1" schemeName="31">900474794</cbc:CompanyID></cac:PartyTaxScheme></cac:Party></cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty><cac:Party><cac:PartyTaxScheme><cbc:RegistrationName>SPEED SECURITY LTDA</cbc:RegistrationName>
    <cbc:CompanyID schemeID="8" schemeName="31">{comprador_nit}</cbc:CompanyID></cac:PartyTaxScheme></cac:Party></cac:AccountingCustomerParty>
  <cac:PaymentMeans><cbc:ID>1</cbc:ID><cbc:PaymentMeansCode>31</cbc:PaymentMeansCode></cac:PaymentMeans>
  <cac:TaxTotal><cbc:TaxAmount currencyID="COP">{iva:.2f}</cbc:TaxAmount><cac:TaxSubtotal><cbc:TaxAmount currencyID="COP">{iva:.2f}</cbc:TaxAmount>
    <cac:TaxCategory><cbc:Percent>19.00</cbc:Percent><cac:TaxScheme><cbc:ID>01</cbc:ID></cac:TaxScheme></cac:TaxCategory></cac:TaxSubtotal></cac:TaxTotal>
  <cac:LegalMonetaryTotal><cbc:LineExtensionAmount currencyID="COP">{sub:.2f}</cbc:LineExtensionAmount>
    <cbc:PayableAmount currencyID="COP">{sub + iva:.2f}</cbc:PayableAmount></cac:LegalMonetaryTotal>{filas}
</{tipo}>"""


def attached(interno: str) -> bytes:
    """El contenedor AttachedDocument que manda el proveedor, con la factura dentro como texto."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<AttachedDocument xmlns="urn:oasis:names:specification:ubl:schema:xsd:AttachedDocument-2"
 xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
 xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:ID>PTC61841310</cbc:ID>
  <cac:Attachment><cac:ExternalReference><cbc:MimeCode>text/xml</cbc:MimeCode>
    <cbc:Description><![CDATA[{interno}]]></cbc:Description></cac:ExternalReference></cac:Attachment>
</AttachedDocument>""".encode("utf-8")


def zip_factura(**kw) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("ad09004747940002600001.xml", attached(factura_xml(**kw)))
        z.writestr("fv09004747940002600001.pdf", b"%PDF-1.4 representacion grafica")
    return buf.getvalue()


def test_lee_la_factura_del_xml_de_la_dian():
    f = dian.leer_xml(attached(factura_xml()))
    assert (f.tipo, f.prefijo, f.numero, f.cufe) == ("factura", "PTC6", "1841310", "5caa7e85955c1c6660e801ea26044b80")
    assert (f.emisor_nit, f.emisor_dv, f.emisor_nombre) == ("900474794", "1", "PRICE RES S.A.S")
    assert f.comprador_nit == SPEED_NIT and f.fecha_emision == date(2026, 8, 22) and f.forma_pago == "Contado"
    assert f.subtotal == pytest.approx(284645.38) and f.iva == pytest.approx(49580.62) and f.total == pytest.approx(334226.00)
    assert [(x.cantidad, x.valor_unitario, x.iva_pct) for x in f.lineas] == [(1, 267800.0, 19), (1, 16845.38, 19)]
    # El zip trae el XML y el PDF; manda el XML
    adj = dian.abrir_adjuntos([("factura.zip", zip_factura())])
    assert len(adj.xmls) == 1 and len(adj.pdfs) == 1
    assert dian.solo_nit("900.474.794-1") == "900474794"
    with pytest.raises(dian.FacturaInvalida):
        dian.leer_xml(b"<otro/>")


@pytest.fixture
def speed(admin):
    assert admin.post("/api/plataforma/empresa", json={"codigo": "speed"}).status_code == 200
    return admin


def _cargar(cliente, contenido: bytes, nombre="factura.zip"):
    return cliente.post(f"{API}/cargar", files=[("archivos", (nombre, contenido, "application/zip"))])


def test_flujo_bandeja_plano_y_contabilizadas(speed):
    # Catálogos de World Office: cuentas (libro auxiliar) y terceros
    cuentas = xlsx([["SPEED SECURITY LTDA"], ["Libro Auxiliar"], [], ["Cuenta", "Tercero"], ["515515 PASAJES AEREOS", None],
                    ["Total 515515 PASAJES AEREOS"], ["519595 OTROS"]])
    r = speed.post(f"{API}/productos/importar", files={"archivo": ("cuentas.xlsx", cuentas, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["cuentas"] == 2
    terceros = xlsx([["SPEED SECURITY LTDA"], ["Listado de Terceros"], ["Clasificacion1", "Clasificacion2", "Nombre", "Identificacion", "Propiedades"],
                     [None, None, "ALCA LTDA", "NIT 800060530 0", "Proveedor;"]])
    assert speed.post(f"{API}/terceros/importar", files={"archivo": ("t.xlsx", terceros, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}).json()["data"]["terceros"] == 1

    r = _cargar(speed, zip_factura())
    assert r.status_code == 200, r.text
    nueva = r.json()["data"]["nuevas"][0]
    assert nueva["estado"] == "pendiente" and nueva["lineas"] == 2
    assert any("no está en el listado de terceros" in a for a in nueva["avisos"])  # PRICE RES no está creado en World Office
    assert _cargar(speed, zip_factura()).json()["data"]["duplicadas"] == ["PTC61841310"]  # mismo CUFE: no entra dos veces

    f = speed.get(f"{API}/facturas/{nueva['id']}").json()["data"]
    l1, l2 = f["lineas"]
    # Sin producto ni centro no pasa al plano
    r = speed.put(f"{API}/facturas/{f['id']}", json={"nota": "", "lineas": [], "lista": True})
    assert r.status_code == 422 and "falta el producto" in r.json()["error"]["message"]
    r = speed.put(f"{API}/facturas/{f['id']}", json={"nota": "COMPRA DE VUELO", "lista": True, "lineas": [
        {"id": l1["id"], "producto": "515515", "centro_costos": "Administracion", "nota": "compra de vuelos"},
        {"id": l2["id"], "producto": "519595", "centro_costos": "Administracion", "nota": "cargo de la agencia"}]})
    assert r.status_code == 200 and r.json()["data"]["estado"] == "lista"

    # Otra factura del mismo mes: queda pendiente (no sale en el plano)
    _cargar(speed, zip_factura(numero="1841999", cufe="otro-cufe"))

    r = speed.post(f"{API}/plano", json={"fecha": "2026-08-25"})
    assert r.status_code == 200, r.text
    assert r.headers["content-disposition"].endswith('.xls"')
    plano_id = int(r.headers["x-plano-id"])
    hoja = xlrd.open_workbook(file_contents=r.content).sheet_by_index(0)
    enc = hoja.row_values(0)
    assert enc == plano.COLUMNAS and len(enc) == 58 and hoja.nrows == 3  # una fila por producto
    fila = dict(zip(enc, hoja.row_values(1)))
    assert fila["Encab: Empresa"] == "SPEED SECURITY LTDA" and fila["Encab: Documento Número"] == 2608001
    assert fila["Encab: Tercero Interno"] == fila["Encab: Tercero Externo"] == 900474794
    assert (fila["Encab: Pref Dto Ext"], fila["Encab: No. Dto Ext"], fila["Encab: Nota"]) == ("PTC6", 1841310, "COMPRA DE VUELO")
    assert xlrd.xldate_as_datetime(fila["Encab: Fecha"], 0).date() == date(2026, 8, 25)
    assert xlrd.xldate_as_datetime(fila["Encab: Fecha Emision"], 0).date() == date(2026, 8, 22)
    assert (fila["Detalle: Producto"], fila["Detalle: IVA"], fila["Detalle: Valor Unitario"]) == ("515515", 0.19, 267800)
    assert (fila["Detalle: Centro costos"], fila["Detalle: Nota"], fila["Encab: Verificado"]) == ("Administracion", "compra de vuelos", -1)
    assert dict(zip(enc, hoja.row_values(2)))["Detalle: Valor Unitario"] == 16845.38

    # Se marca contabilizada: no vuelve a salir en el plano y el siguiente número del mes sigue
    r = speed.post(f"{API}/planos/{plano_id}/contabilizar", json={"ids": [f["id"]]})
    assert r.status_code == 200 and r.json()["data"]["contabilizadas"] == 1
    hecha = speed.get(f"{API}/facturas/{f['id']}").json()["data"]
    assert (hecha["estado"], hecha["documento_numero"], hecha["fecha_contable"]) == ("contabilizada", 2608001, "2026-08-25")
    assert speed.post(f"{API}/plano", json={"fecha": "2026-08-25"}).status_code == 422  # ya no hay listas

    otra = speed.get(f"{API}/facturas?estado=pendiente").json()["data"][0]
    det = speed.get(f"{API}/facturas/{otra['id']}").json()["data"]
    # Sin IA: repite lo que se usó antes con el proveedor
    assert [x["producto"] for x in det["lineas"]] == ["515515", "515515"] and det["lineas"][0]["centro_costos"] == "Administracion"
    speed.put(f"{API}/facturas/{otra['id']}", json={"nota": "COMPRA", "lista": True, "lineas": [
        {"id": x["id"], "producto": x["producto"], "centro_costos": x["centro_costos"], "nota": "vuelo"} for x in det["lineas"]]})
    r = speed.post(f"{API}/plano", json={"fecha": "2026-08-30"})
    assert dict(zip(plano.COLUMNAS, xlrd.open_workbook(file_contents=r.content).sheet_by_index(0).row_values(1)))["Encab: Documento Número"] == 2608002
    planos = speed.get(f"{API}/planos").json()["data"]
    assert [p["facturas"][0]["documento"] for p in planos] == [2608002, 2608001]


def test_listados_por_paginas(speed):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:  # 23 facturas en un solo zip
        for i in range(23):
            z.writestr(f"f{i}.xml", attached(factura_xml(numero=str(100 + i), cufe=f"p{i}")))
    assert len(_cargar(speed, buf.getvalue()).json()["data"]["nuevas"]) == 23
    r = speed.get(f"{API}/facturas?estado=pendiente").json()
    assert len(r["data"]) == 20 and r["meta"]["extra"] == {"total": 23, "pagina": 1, "tamano": 20, "paginas": 2}
    r = speed.get(f"{API}/facturas?estado=pendiente&pagina=2&tamano=20").json()
    assert len(r["data"]) == 3
    assert len(speed.get(f"{API}/facturas?estado=pendiente&tamano=50").json()["data"]) == 23
    assert speed.get(f"{API}/facturas?estado=pendiente&tamano=30").status_code == 422
    assert len(speed.get(f"{API}/facturas?estado=pendiente&todas=true").json()["data"]) == 23  # el plano las elige todas
    assert speed.get(f"{API}/correos?tamano=100").json()["meta"]["extra"]["tamano"] == 100


def test_otro_comprador_y_notas_van_aparte(speed):
    r = _cargar(speed, zip_factura(comprador_nit="900369097", cufe="c-servig"))
    f = r.json()["data"]["nuevas"][0]
    assert f["estado"] == "aparte" and "900369097" in f["motivo_aparte"]
    r = speed.put(f"{API}/facturas/{f['id']}", json={"nota": "X", "lista": True, "lineas": []})
    assert r.status_code in (409, 422)
    assert speed.post(f"{API}/facturas/{f['id']}/estado", json={"accion": "incluir"}).json()["data"]["estado"] == "pendiente"
    assert speed.post(f"{API}/facturas/{f['id']}/estado", json={"accion": "descartar"}).json()["data"]["estado"] == "descartada"
    nc = _cargar(speed, attached(factura_xml(tipo="CreditNote", cufe="nc-1")), "nota.xml").json()["data"]["nuevas"][0]
    assert nc["estado"] == "aparte" and "nota crédito" in nc["motivo_aparte"]


def test_correo_con_zip_adjunto(speed, db):
    msg = EmailMessage()
    msg["From"], msg["Subject"], msg["Message-ID"] = "facturacion@pricetravel.com", "Factura PTC6-1841310", "<abc@x>"
    msg["Date"] = "Sat, 22 Aug 2026 13:45:56 -0500"
    msg.set_content("Adjuntamos la factura")
    msg.add_attachment(zip_factura(cufe="por-correo"), maintype="application", subtype="zip", filename="ad0900474794.zip")
    from app.core.db import traduccion

    with db() as s:
        s.bind = s.get_bind().execution_options(**traduccion("emp_speed"))
        registro = buzon.procesar_mensaje(s, msg.as_bytes())
        s.commit()
        assert registro.facturas == 1 and "PTC61841310" in registro.resultado
    f = speed.get(f"{API}/facturas?estado=pendiente").json()["data"][0]
    assert f["correo_de"] == "facturacion@pricetravel.com" and f["correo_asunto"] == "Factura PTC6-1841310"
    assert speed.get(f"{API}/correos").json()["data"][0]["facturas"] == 1


def test_la_ia_propone_cuenta_y_centro(speed, monkeypatch):
    monkeypatch.setattr(get_settings(), "ia_api_key", "sk-or-prueba")
    pedidos = []

    def falso(request: httpx.Request) -> httpx.Response:
        pedidos.append(json.loads(request.content))
        respuesta = {"nota": "COMPRA DE VUELO", "lineas": [{"n": 1, "producto": "515515", "centro_costos": "Administracion", "nota": "vuelo"},
                                                           {"n": 2, "producto": "999999", "centro_costos": "Inventado", "nota": "cargo"}],
                     "dudas": ["La línea 2 es un cargo de la agencia"]}
        return httpx.Response(200, json={"model": "m", "usage": {}, "choices": [{"message": {"content": json.dumps(respuesta)}}]})

    monkeypatch.setattr(ia, "cliente_http", lambda: httpx.Client(transport=httpx.MockTransport(falso)))
    # El modelo de Contabilidad es propio del desarrollo
    c = speed.put(f"{API}/config", json={"modelo": "google/gemini-3.8-flash", "empresa_nombre": "SPEED SECURITY LTDA", "empresa_nit": SPEED_NIT})
    assert c.json()["data"]["modelo"] == "google/gemini-3.8-flash"
    assert speed.put(f"{API}/config", json={"modelo": "no es un modelo", "empresa_nombre": "X S", "empresa_nit": SPEED_NIT}).status_code == 422
    speed.post(f"{API}/productos/importar", files={"archivo": ("c.xlsx", xlsx([["515515 PASAJES AEREOS"]]),
                                                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    f = _cargar(speed, zip_factura(cufe="con-ia")).json()["data"]["nuevas"][0]
    d = speed.get(f"{API}/facturas/{f['id']}").json()["data"]
    assert d["nota"] == "COMPRA DE VUELO" and d["lineas"][0]["producto"] == "515515" and d["lineas"][0]["centro_costos"] == "Administracion"
    # Lo que no está en los catálogos no se acepta
    assert d["lineas"][1]["producto"] == "" and d["lineas"][1]["centro_costos"] == ""
    assert any("cargo de la agencia" in a for a in d["avisos"])
    assert "515515 PASAJES AEREOS" in pedidos[0]["messages"][0]["content"] and pedidos[0]["model"] == "google/gemini-3.8-flash"


def test_config_del_buzon(speed, db):
    r = speed.put(f"{API}/config", json={"correo": "facturas.speed@gmail.com", "clave": "abcd efgh ijkl mnop",
                                         "empresa_nombre": "SPEED SECURITY LTDA", "empresa_nit": "900.259.118-4"})
    assert r.status_code == 200, r.text
    c = r.json()["data"]
    assert c["clave_guardada"] and c["empresa_nit"] == "900259118" and "abcd" not in r.text
    from app.apps.contabilidad.models import CtbConfig
    from app.core.db import traduccion
    from app.core.security import descifrar_secreto

    with db() as s:
        s.bind = s.get_bind().execution_options(**traduccion("emp_speed"))
        assert descifrar_secreto(s.get(CtbConfig, 1).clave_cifrada, "imap") == "abcdefghijklmnop"
    # Guardar sin clave conserva la que había
    assert speed.put(f"{API}/config", json={"correo": "facturas.speed@gmail.com", "empresa_nombre": "SPEED SECURITY LTDA",
                                            "empresa_nit": "900259118"}).json()["data"]["clave_guardada"]
    # Sin buzón configurado del todo, «Revisar correo» explica qué falta
    with db() as s:
        s.bind = s.get_bind().execution_options(**traduccion("emp_speed"))
        s.get(CtbConfig, 1).clave_cifrada = None
        s.commit()
    r = speed.post(f"{API}/buzon/leer")
    assert r.status_code == 502 and "contraseña de aplicación" in r.json()["error"]["message"]


def test_cuentas_de_cobro_y_consecutivo_desde_world_office(speed):
    # En World Office las facturas quedaron en 2608008: la siguiente de agosto es la 2608009
    # Las cuentas de cobro van por la 345: número seguido, sin año ni mes
    speed.put(f"{API}/config", json={"empresa_nombre": "SPEED SECURITY LTDA", "empresa_nit": SPEED_NIT, "ultimo_fc": 2608008, "ultimo_ds": 345})
    hechas = []
    for n, cufe in (("1", "a"), ("2", "b"), ("3", "c")):
        f = _cargar(speed, zip_factura(numero=n, cufe=cufe)).json()["data"]["nuevas"][0]
        d = speed.get(f"{API}/facturas/{f['id']}").json()["data"]
        speed.put(f"{API}/facturas/{f['id']}", json={"nota": "COMPRA", "lista": True, "cuenta_cobro": n == "3", "lineas": [
            {"id": x["id"], "producto": "515515", "centro_costos": "Administracion", "nota": "x"} for x in d["lineas"]]})
        hechas.append(f["id"])
    assert speed.get(f"{API}/facturas/{hechas[2]}").json()["data"]["cuenta_cobro"]
    r = speed.post(f"{API}/plano", json={"fecha": "2026-08-31"})
    hoja = xlrd.open_workbook(file_contents=r.content).sheet_by_index(0)
    filas = [dict(zip(plano.COLUMNAS, hoja.row_values(i))) for i in range(1, hoja.nrows)]
    docs = {(f["Encab: Tipo Documento"], f["Encab: Prefijo"], f["Encab: Documento Número"]) for f in filas}
    # Facturas FC siguen en 2608009 y 2608010; la cuenta de cobro va como DSS / DSS con el 346
    assert docs == {("FC", "FC", 2608009), ("FC", "FC", 2608010), ("DSS", "DSS", 346)}
    # En otro mes las facturas empiezan de nuevo; la cuenta de cobro no reinicia
    r = speed.post(f"{API}/plano", json={"fecha": "2026-11-05"})
    hoja = xlrd.open_workbook(file_contents=r.content).sheet_by_index(0)
    assert {hoja.row_values(i)[3] for i in range(1, hoja.nrows)} == {2611001, 2611002, 346}
    p = speed.get(f"{API}/planos").json()["data"][0]
    assert speed.post(f"{API}/planos/{p['id']}/contabilizar", json={"ids": hechas}).json()["data"]["contabilizadas"] == 3
    assert {f["serie"] for f in p["facturas"]} == {"FC", "DSS"}
    # Eliminar un plano: lo que se marcó contabilizado con él vuelve a «lista» (y la siguiente cuenta de cobro vuelve a ser la 346)
    otro = speed.get(f"{API}/planos").json()["data"][1]
    assert speed.delete(f"{API}/planos/{otro['id']}").json()["data"]["devueltas"] == 0  # el de agosto no se marcó
    assert speed.delete(f"{API}/planos/{p['id']}").json()["data"]["devueltas"] == 3
    assert {x["estado"] for x in speed.get(f"{API}/facturas?estado=lista").json()["data"]} == {"lista"}
    assert len(speed.get(f"{API}/facturas?estado=lista").json()["data"]) == 3 and speed.get(f"{API}/planos").json()["data"] == []
    r = speed.post(f"{API}/plano", json={"fecha": "2026-11-05"})
    p = speed.get(f"{API}/planos").json()["data"][0]
    speed.post(f"{API}/planos/{p['id']}/contabilizar", json={"ids": hechas})
    # La siguiente cuenta de cobro es la 347
    f = _cargar(speed, zip_factura(numero="4", cufe="d")).json()["data"]["nuevas"][0]
    d = speed.get(f"{API}/facturas/{f['id']}").json()["data"]
    speed.put(f"{API}/facturas/{f['id']}", json={"nota": "COBRO", "lista": True, "cuenta_cobro": True, "lineas": [
        {"id": x["id"], "producto": "515515", "centro_costos": "Administracion", "nota": "x"} for x in d["lineas"]]})
    r = speed.post(f"{API}/plano", json={"fecha": "2026-12-01"})
    assert xlrd.open_workbook(file_contents=r.content).sheet_by_index(0).row_values(1)[3] == 347


def test_cuenta_de_cobro_reconocida_en_el_xml():
    xml = factura_xml().replace("<cbc:IssueDate>", "<cbc:Note>CUENTA DE COBRO No. 15</cbc:Note><cbc:IssueDate>")
    assert dian.leer_xml(xml.encode()).cuenta_cobro and not dian.leer_xml(factura_xml().encode()).cuenta_cobro
