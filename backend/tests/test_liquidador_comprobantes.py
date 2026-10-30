"""Comprobantes de nómina (desprendibles de pago) en PDF."""

from io import BytesIO

from tests.test_liquidador import API
from tests.test_liquidador_nomina import _nomina, _periodo_con

DIAS = list(range(1, 16))

def test_comprobantes_de_pago_en_pdf(admin):
    from pypdf import PdfReader

    pid = _periodo_con(admin, 2026, 11, 1, [[1001, "1001", *(["A"] * 15)], [2002, "2002", *(["A"] * 15)]], DIAS)
    admin.post(f"{API}/periodos/{pid}/novedades", json={"documento": "1001", "tipo": "auxilio_intermunicipal", "descripcion": "Auxilio intermunicipal", "valor": 47000})
    assert admin.get(f"{API}/periodos/{pid}/comprobantes").status_code == 409  # abierta
    admin.post(f"{API}/periodos/{pid}/cerrar")
    r = admin.get(f"{API}/periodos/{pid}/comprobantes")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    pdf = PdfReader(BytesIO(r.content))
    assert len(pdf.pages) == 2
    texto = pdf.pages[0].extract_text()
    n = _nomina(admin, pid, "1001")
    assert "Comprobante de Nómina" in texto and "SERA 360" in texto and "Siigo" not in texto
    assert "SERVICIOS EMPRESARIALES RESIDENCIALES Y" in texto and "900889870" in texto
    assert "Auxilio intermunicipal" in texto and "Fondo de salud" in texto
    neto = f"{n['neto']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    assert neto in texto


def test_comprobante_con_el_logo_de_la_marca(admin, db):
    from io import BytesIO as B

    from PIL import Image as PILImage
    from pypdf import PdfReader

    from app.models import Empresa
    from app.models.marca import Marca, MarcaImagen

    buf = B()
    PILImage.new("RGBA", (300, 160), (40, 90, 140, 255)).save(buf, "PNG")
    s = db()
    m = Marca(empresa_id=s.query(Empresa).filter(Empresa.codigo == "sera").one().id, nombre="SERA", subtitulo="SERA 360")
    s.add(m)
    s.flush()
    s.add(MarcaImagen(marca_id=m.id, tipo="logo", contenido=buf.getvalue(), mime="image/png", ancho=300, alto=160, bytes=len(buf.getvalue())))
    s.commit()
    pid = _periodo_con(admin, 2026, 11, 1, [[1001, "1001", *(["A"] * 15)]], DIAS)
    admin.post(f"{API}/periodos/{pid}/cerrar")
    r = admin.get(f"{API}/periodos/{pid}/comprobantes")
    assert r.status_code == 200, r.text
    pagina = PdfReader(BytesIO(r.content)).pages[0]
    assert len(pagina.images) == 1  # el logo de la marca
