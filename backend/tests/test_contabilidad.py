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
    # Facturas FC siguen en 2608009 y 2608010; la cuenta de cobro va como FC / DSS con el 346
    assert docs == {("FC", "FC", 2608009), ("FC", "FC", 2608010), ("FC", "DSS", 346)}
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


def test_agente_aprende_las_reglas_de_la_empresa(speed, monkeypatch):
    """Las reglas de la empresa mandan sobre la norma general; al corregir una cuenta, el agente redacta la regla a aprender."""
    monkeypatch.setattr(get_settings(), "ia_api_key", "sk-or-prueba")
    pedidos, respuestas = [], []

    def falso(request: httpx.Request) -> httpx.Response:
        pedidos.append(json.loads(request.content))
        return httpx.Response(200, json={"model": "m", "usage": {}, "choices": [{"message": {"content": json.dumps(respuestas.pop(0))}}]})

    monkeypatch.setattr(ia, "cliente_http", lambda: httpx.Client(transport=httpx.MockTransport(falso)))
    speed.post(f"{API}/productos/importar", files={"archivo": ("c.xlsx", xlsx([["530520 INTERESES DE MORA"], ["519595 OTROS GASTOS"], ["735095 OTROS COSTOS"]]),
                                                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    # Regla escrita a mano por contabilidad
    r = speed.post(f"{API}/reglas", json={"texto": "En Speed los intereses de mora no van a la cuenta de intereses de mora: van al costo (7) o al gasto (5) del concepto principal.",
                                          "cuentas": "5, 7"})
    assert r.status_code == 201, r.text
    regla = r.json()["data"]

    respuestas.append({"nota": "INTERESES", "lineas": [{"n": 1, "producto": "519595", "centro_costos": "Administracion", "nota": "intereses de mora"},
                                                       {"n": 2, "producto": "519595", "centro_costos": "Administracion", "nota": "cargo"}],
                       "reglas_aplicadas": [regla["id"], 99], "dudas": []})
    f = _cargar(speed, zip_factura(cufe="con-regla")).json()["data"]["nuevas"][0]
    d = speed.get(f"{API}/facturas/{f['id']}").json()["data"]
    sistema = pedidos[-1]["messages"][0]["content"]
    assert "LAS REGLAS DE LA EMPRESA MANDAN" in sistema and f"[{regla['id']}] En Speed los intereses de mora" in sistema
    assert d["lineas"][0]["producto"] == "519595" and d["lineas"][0]["producto_ia"] == "519595"
    assert any("Regla de la empresa aplicada" in a for a in d["avisos"])
    assert speed.get(f"{API}/reglas").json()["data"][0]["usos"] == 1  # la 99 no existe: no cuenta

    # Contabilidad corrige la cuenta de la línea 1: el agente ofrece aprenderlo
    lineas = [{"id": x["id"], "producto": "735095" if x["orden"] == 1 else x["producto"], "centro_costos": x["centro_costos"], "nota": x["nota"]}
              for x in d["lineas"]]
    g = speed.put(f"{API}/facturas/{f['id']}", json={"nota": d["nota"], "lineas": lineas}).json()["data"]
    assert [(c["orden"], c["cuenta_agente"], c["cuenta_correcta"]) for c in g["correcciones"]] == [(1, "519595", "735095")]
    # Guardar otra vez sin cambios no vuelve a ofrecerlo
    assert speed.put(f"{API}/facturas/{f['id']}", json={"nota": d["nota"], "lineas": lineas}).json()["data"]["correcciones"] == []

    respuestas.append({"texto": "Los intereses de mora de los proveedores de servicio para los puestos van al costo 735095.", "cuentas": "735095"})
    c = g["correcciones"][0]
    red = speed.post(f"{API}/reglas/redactar", json={"factura_id": f["id"], "linea_id": c["linea_id"], "cuenta_agente": c["cuenta_agente"],
                                                    "cuenta_correcta": c["cuenta_correcta"], "motivo": "es del puesto del cliente"})
    assert red.status_code == 200, red.text
    caso = json.loads(pedidos[-1]["messages"][1]["content"].split("\n", 1)[1])
    assert caso["nombre_cuenta_correcta"] == "OTROS COSTOS" and caso["motivo"] == "es del puesto del cliente"
    assert "En Speed los intereses de mora" in pedidos[-1]["messages"][0]["content"]  # conoce las reglas parecidas que ya existen
    nueva = speed.post(f"{API}/reglas", json={**{k: red.json()["data"][k] for k in ("texto", "cuentas", "ejemplo")}, "origen": "correccion"})
    assert nueva.status_code == 201 and nueva.json()["data"]["origen"] == "correccion"

    # Editar y desactivar: la desactivada ya no se le pasa al agente
    speed.put(f"{API}/reglas/{regla['id']}", json={"texto": regla["texto"], "cuentas": "5, 7", "activa": False})
    respuestas.append({"nota": "X", "lineas": [], "dudas": []})
    speed.post(f"{API}/facturas/{f['id']}/proponer")
    sistema = pedidos[-1]["messages"][0]["content"]
    assert "intereses de mora no van" not in sistema and "] Los intereses de mora de los proveedores" in sistema
    assert speed.delete(f"{API}/reglas/{regla['id']}").status_code == 200
    assert len(speed.get(f"{API}/reglas").json()["data"]) == 1


def _vector(texto: str) -> list[float]:
    """Embedding de prueba: bolsa de palabras en 64 posiciones (textos con palabras en común se parecen)."""
    import hashlib
    v = [0.0] * 64
    for palabra in texto.lower().split():
        v[int(hashlib.md5(palabra.encode()).hexdigest(), 16) % 64] += 1.0
    return v


def test_rag_y_memoria_bajan_el_costo(speed, monkeypatch):
    """Catálogo y reglas grandes: al agente solo le llega lo parecido (RAG). Lo ya contabilizado se repite sin IA."""
    monkeypatch.setattr(get_settings(), "ia_api_key", "sk-or-prueba")
    chats, embeddings, respuestas = [], [], []

    def falso(request: httpx.Request) -> httpx.Response:
        cuerpo = json.loads(request.content)
        if request.url.path.endswith("/embeddings"):
            embeddings.append(cuerpo)
            return httpx.Response(200, json={"data": [{"index": i, "embedding": _vector(t)} for i, t in enumerate(cuerpo["input"])],
                                             "usage": {"prompt_tokens": 7 * len(cuerpo["input"])}})
        chats.append(cuerpo)
        return httpx.Response(200, json={"model": "m", "usage": {"prompt_tokens": 900, "completion_tokens": 80},
                                         "choices": [{"message": {"content": json.dumps(respuestas.pop(0))}}]})

    monkeypatch.setattr(ia, "cliente_http", lambda: httpx.Client(transport=httpx.MockTransport(falso)))
    cuentas = [["515515 PASAJES AEREOS"], ["519595 OTROS"]] + [[f"51{10 + i:02d}95 HONORARIOS DE ASESORIA NUMERO {i}"] for i in range(68)]
    speed.post(f"{API}/productos/importar", files={"archivo": ("c.xlsx", xlsx(cuentas), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    for i in range(10):
        speed.post(f"{API}/reglas", json={"texto": f"Los arrendamientos de bodega número {i} van a la cuenta de arrendamientos"})
    clave = speed.post(f"{API}/reglas", json={"texto": "Los pasajes aereos de viajes de la gerencia van a 515515"}).json()["data"]

    respuestas.append({"nota": "COMPRA DE VUELO", "lineas": [{"n": 1, "producto": "515515", "centro_costos": "Administracion", "nota": "vuelo"},
                                                             {"n": 2, "producto": "519595", "centro_costos": "Administracion", "nota": "cargo"}],
                       "reglas_aplicadas": [clave["id"]]})
    f = _cargar(speed, zip_factura(cufe="rag-1")).json()["data"]["nuevas"][0]
    sistema = chats[-1]["messages"][0]["content"]
    assert "515515 PASAJES AEREOS" in sistema
    assert sistema.count("HONORARIOS DE ASESORIA") < 68  # no viaja el catálogo completo
    assert sistema.count("Los arrendamientos de bodega") < 10 and "pasajes aereos de viajes" in sistema  # solo las reglas al caso
    assert embeddings and embeddings[0]["model"] == "openai/text-embedding-3-small" and embeddings[0]["dimensions"] == 512

    # Se contabiliza y llega otra factura igual del mismo proveedor: se repite sin llamar al modelo
    d = speed.get(f"{API}/facturas/{f['id']}").json()["data"]
    speed.put(f"{API}/facturas/{f['id']}", json={"nota": d["nota"], "lista": True, "lineas": [
        {"id": x["id"], "producto": x["producto"], "centro_costos": x["centro_costos"], "nota": x["nota"]} for x in d["lineas"]]})
    r = speed.post(f"{API}/plano", json={"fecha": "2026-08-25"})
    speed.post(f"{API}/planos/{int(r.headers['x-plano-id'])}/contabilizar", json={"ids": [f["id"]]})
    antes = len(chats)
    g = _cargar(speed, zip_factura(numero="1841400", cufe="rag-2")).json()["data"]["nuevas"][0]
    otra = speed.get(f"{API}/facturas/{g['id']}").json()["data"]
    assert len(chats) == antes  # sin llamada al modelo
    assert [x["producto"] for x in otra["lineas"]] == ["515515", "519595"] and any("sin costo de IA" in a for a in otra["avisos"])
    uso = speed.get(f"{API}/agente/uso").json()["data"]
    assert uso["por_tipo"]["propuesta"]["veces"] == 1 and uso["por_tipo"]["memoria"]["veces"] == 1
    assert uso["por_tipo"]["vectores"]["tokens_entrada"] > 0 and uso["tokens_salida"] == 80

    # Si cambia una regla, lo contabilizado antes ya no se repite a ciegas: el agente vuelve a decidir
    speed.put(f"{API}/reglas/{clave['id']}", json={"texto": clave["texto"] + " (revisada)", "cuentas": ""})
    respuestas.append({"nota": "X", "lineas": [], "reglas_aplicadas": []})
    _cargar(speed, zip_factura(numero="1841401", cufe="rag-3"))
    assert len(chats) == antes + 1


def _compras_por_proveedor(filas):
    return xlsx([["SPEED SECURITY LTDA"], ["Compras por Producto y Proveedor Basado en Movimientos"], ["Entre 01/01/2020 Y 31/12/2026"],
                 ["Inventario", "Tercero", "U Medida", "Ultimo Precio Unitario", "Fecha"], *filas])


def test_productos_por_proveedor_de_world_office(speed, monkeypatch):
    from datetime import datetime as dt

    tipo = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    informe = _compras_por_proveedor([
        ["515515 PASAJES AEREOS", "PRICE RES S.A.S  900474794", "Und.", 250000, dt(2026, 3, 1)],
        ["515515 PASAJES AEREOS", "PRICE RES S.A.S  900474794", "Und.", 300000, dt(2026, 7, 1)],
        ["15281001 EQUIPOS TELECOMUNICACIONES", "CRC COMUNICACIONES S.A.S  830095304", "Und.", 470000, dt(2025, 6, 4)],
        ["734525 Mantenimiento Equipo de Computacion", "CRC COMUNICACIONES S.A.S  830095304", "Und.", 365000, dt(2025, 8, 20)],
    ])
    r = speed.post(f"{API}/productos-proveedor/importar", files={"archivo": ("compras.xlsx", informe, tipo)})
    assert r.status_code == 200, r.text
    assert r.json()["data"] == {"relaciones": 3, "productos": 3}
    codigos = {p["codigo"] for p in speed.get(f"{API}/productos").json()["data"]}
    assert {"515515", "15281001", "734525"} <= codigos  # los productos de World Office entran al catálogo

    # PRICE RES siempre con 515515 (2 compras): se usa sin IA
    f = _cargar(speed, zip_factura(cufe="pp-1")).json()["data"]["nuevas"][0]
    d = speed.get(f"{API}/facturas/{f['id']}").json()["data"]
    assert {x["producto"] for x in d["lineas"]} == {"515515"} and d["lineas"][0]["centro_costos"] == "Administracion"
    assert any("Producto tomado de World Office" in a for a in d["avisos"])
    assert d["opciones_proveedor"][0] == {"producto": "515515", "nombre": "PASAJES AEREOS", "compras": 2, "ultima_fecha": "2026-07-01",
                                          "ultimo_precio": 300000.0}

    # CRC tiene dos opciones: la IA las recibe y escoge
    monkeypatch.setattr(get_settings(), "ia_api_key", "sk-or-prueba")
    pedidos = []

    def falso(request: httpx.Request) -> httpx.Response:
        pedidos.append(json.loads(request.content))
        return httpx.Response(200, json={"model": "m", "usage": {}, "choices": [{"message": {"content": json.dumps(
            {"nota": "COMPRA EQUIPO", "lineas": [{"n": 1, "producto": "15281001", "centro_costos": "Administracion", "nota": "radio"}]})}}]})

    monkeypatch.setattr(ia, "cliente_http", lambda: httpx.Client(transport=httpx.MockTransport(falso)))
    xml = factura_xml(cufe="pp-2", lineas=((1, "Radio portátil", 470000.0, 19, 89300.0),)).replace("900474794", "830095304")
    f = _cargar(speed, attached(xml), "crc.xml").json()["data"]["nuevas"][0]
    d = speed.get(f"{API}/facturas/{f['id']}").json()["data"]
    assert d["lineas"][0]["producto"] == "15281001"
    sistema = next(p for p in pedidos if "OPCIONES DE ESTE PROVEEDOR" in p["messages"][0]["content"])["messages"][0]["content"]
    assert '["15281001", "EQUIPOS TELECOMUNICACIONES", 1, "2025-06-04"]' in sistema and '"734525"' in sistema


def test_respuesta_cortada_de_la_ia_se_reintenta(speed, monkeypatch):
    """Un modelo que razona puede gastarse los tokens pensando y dejar el JSON cortado: se reintenta una vez."""
    monkeypatch.setattr(get_settings(), "ia_api_key", "sk-or-prueba")
    pedidos = []

    def falso(request: httpx.Request) -> httpx.Response:
        cuerpo = json.loads(request.content)
        pedidos.append(cuerpo)
        if len(pedidos) == 1:
            return httpx.Response(200, json={"model": "m", "usage": {"completion_tokens": 6000},
                                             "choices": [{"message": {"content": '{"nota": "COMPRA DE INSUMOS", "lineas": [{"n'}, "finish_reason": "length"}]})
        respuesta = {"nota": "INSUMOS IMPRESORA", "lineas": [{"n": 1, "producto": "519530", "centro_costos": "Administracion", "nota": "toner ricoh"}]}
        return httpx.Response(200, json={"model": "m", "usage": {}, "choices": [{"message": {"content": json.dumps(respuesta)}, "finish_reason": "stop"}]})

    monkeypatch.setattr(ia, "cliente_http", lambda: httpx.Client(transport=httpx.MockTransport(falso)))
    tipo = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    speed.post(f"{API}/productos/importar", files={"archivo": ("c.xlsx", xlsx([["519530 UTILES, PAPELERIA Y FOTOCOPIAS"], ["514520 EQUIPO DE OFICINA"]]), tipo)})
    xml = factura_xml(cufe="ricoh", lineas=((2, "TONER RICOH 4503", 250000.0, 19, 47500.0),))
    f = _cargar(speed, attached(xml), "ricoh.xml").json()["data"]["nuevas"][0]
    d = speed.get(f"{API}/facturas/{f['id']}").json()["data"]
    assert d["lineas"][0]["producto"] == "519530" and not any("no pudo proponer" in a for a in d["avisos"])
    assert len(pedidos) == 2 and pedidos[1]["max_tokens"] == 2 * pedidos[0]["max_tokens"]
    assert "solo el objeto JSON" in pedidos[1]["messages"][-1]["content"] or "únicamente con el objeto JSON" in pedidos[1]["messages"][-1]["content"]
    assert "RICOH MPC 4503" in pedidos[0]["messages"][0]["content"]  # el agente sabe identificar el producto por la marca


def test_negativos_y_numero_de_factura_para_world_office(speed):
    assert dian.limpiar_numero("FE45", "FE45 - 4548") == ("FE45", "4548")
    assert dian.limpiar_numero("FE45-", "4548-4") == ("FE45", "4548")
    assert dian.limpiar_numero("PTC6", "1841310") == ("PTC6", "1841310")
    # Factura con número «FE45-4548-6» y un ajuste al peso de −6 pesos
    xml = factura_xml(cufe="neg-1", lineas=((1, "Servicio de monitoreo", 100000.0, 19, 19000.0), (1, "Ajuste al peso", -6.0, 0, 0.0)))
    xml = xml.replace("<cbc:ID>PTC6", "<cbc:ID>FE45-").replace("<sts:Prefix>PTC6", "<sts:Prefix>FE45").replace("1841310</cbc:ID>", "1841310-6</cbc:ID>")
    f = _cargar(speed, attached(xml), "neg.xml").json()["data"]["nuevas"][0]
    assert (f["prefijo"], f["numero"]) == ("FE45", "1841310")
    assert any("viene en −$6: no va en el plano y se resta" in a for a in f["avisos"])
    d = speed.get(f"{API}/facturas/{f['id']}").json()["data"]
    assert d["lineas"][1]["excluida"] and d["lineas"][1]["valor_unitario"] == -6  # se ve, pero no va
    assert d["lineas"][0]["valor_plano"] == 99994 and "−$6 de la línea 1" in d["ajuste_negativos"][0]
    r = speed.put(f"{API}/facturas/{f['id']}", json={"nota": "MONITOREO", "lista": True, "lineas": [
        {"id": d["lineas"][0]["id"], "producto": "513505", "centro_costos": "Administracion", "nota": "monitoreo"},
        {"id": d["lineas"][1]["id"], "excluida": True}]})
    assert r.status_code == 200, r.text
    hoja = xlrd.open_workbook(file_contents=speed.post(f"{API}/plano", json={"fecha": "2026-11-26"}).content).sheet_by_index(0)
    assert hoja.nrows == 2  # la línea negativa no va
    fila = dict(zip(plano.COLUMNAS, hoja.row_values(1)))
    assert (fila["Encab: Pref Dto Ext"], fila["Encab: No. Dto Ext"]) == ("FE45", 1841310)
    assert fila["Detalle: Valor Unitario"] == 99994  # 100.000 − 6

    # Como la factura de energía: los ajustes (−3 y −1) se restan de un producto de cantidad 1 que alcance
    xml = factura_xml(cufe="neg-2", lineas=((222, "ENERGIA ACTIVA FP", 194261.10, 0, 0.0), (1, "Ajustes a la decena", -3.0, 0, 0.0),
                                            (1, "CONSUMO EXCEDENTE", 13533.0, 0, 0.0), (1, "ASEO SERVICIO RESIDENCIAL", 43224.0, 0, 0.0),
                                            (1, "ASEO AJUSTE A LA DECENA", -1.0, 0, 0.0)))
    g = speed.get(f"{API}/facturas/{_cargar(speed, attached(xml), 'energia.xml').json()['data']['nuevas'][0]['id']}").json()["data"]
    assert [x["excluida"] for x in g["lineas"]] == [False, True, False, False, True]
    assert [x["valor_plano"] for x in g["lineas"]] == [None, None, None, 43220, None]  # energía (222 unidades) queda igual
    assert not any("negativo" in x for x in g["faltantes"])

    # Si los negativos superan a los productos no se puede restar: la factura no pasa al plano
    xml = factura_xml(cufe="neg-3", lineas=((1, "Servicio", 1000.0, 0, 0.0), (1, "Descuento", -5000.0, 0, 0.0)))
    h = _cargar(speed, attached(xml), "neg3.xml").json()["data"]["nuevas"][0]
    assert any("superan a los productos por $4.000" in x for x in h["faltantes"])
