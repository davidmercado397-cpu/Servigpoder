"""Imágenes de la marca: validación y normalización con Pillow (OWASP File Upload).

- Solo PNG, JPEG, WEBP, GIF o ICO, comprobado por el contenido real (no por la extensión). SVG no se acepta:
  puede llevar código.
- Se vuelve a codificar la imagen: se descartan metadatos y cualquier contenido extra del archivo.
- Tamaños: logo hasta 800×400 (PNG, conserva transparencia), favicon 64×64 (PNG cuadrado), fondo hasta
  2560×1600 (JPEG).
"""

import io

from PIL import Image, ImageOps, UnidentifiedImageError

FORMATOS = {"PNG", "JPEG", "WEBP", "GIF", "ICO", "MPO"}
TIPOS = ("logo", "favicon", "fondo")
MAX_BYTES = 8 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 40_000_000  # defensa contra "bombas" de descompresión


class ImagenInvalida(ValueError):
    pass


def procesar(tipo: str, contenido: bytes) -> tuple[bytes, str, int, int]:
    """Devuelve (bytes, mime, ancho, alto) de la imagen lista para servir."""
    if tipo not in TIPOS:
        raise ImagenInvalida("Tipo de imagen desconocido")
    if len(contenido) > MAX_BYTES:
        raise ImagenInvalida("La imagen supera los 8 MB")
    try:
        with Image.open(io.BytesIO(contenido)) as prueba:
            prueba.verify()
        img = Image.open(io.BytesIO(contenido))
        if img.format not in FORMATOS:
            raise ImagenInvalida("Formato no admitido: use PNG, JPG, WEBP o ICO")
        if tipo == "favicon" and img.format == "ICO":
            img.size = max(img.info.get("sizes", {img.size}))  # el tamaño más grande del .ico
        img.load()
        img = ImageOps.exif_transpose(img)
    except ImagenInvalida:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError, ValueError) as e:
        raise ImagenInvalida("El archivo no es una imagen válida") from e

    salida = io.BytesIO()
    if tipo == "fondo":
        img = img.convert("RGB")
        img.thumbnail((2560, 1600))
        img.save(salida, "JPEG", quality=82, optimize=True, progressive=True)
        return salida.getvalue(), "image/jpeg", img.width, img.height
    img = img.convert("RGBA")
    if tipo == "logo":
        img.thumbnail((800, 400))
    else:  # favicon: cuadrado de 64 px, centrado sobre fondo transparente
        img.thumbnail((64, 64))
        lienzo = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        lienzo.paste(img, ((64 - img.width) // 2, (64 - img.height) // 2), img)
        img = lienzo
    img.save(salida, "PNG", optimize=True)
    return salida.getvalue(), "image/png", img.width, img.height
