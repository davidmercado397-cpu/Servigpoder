import zipfile
from io import BytesIO

from fastapi import UploadFile

from app.core.config import get_settings
from app.core.respuestas import ApiError

XLSX_MIME = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/octet-stream",  # algunos navegadores en Windows
}
MAX_DESCOMPRIMIDO = 200 * 1024 * 1024  # defensa contra "zip bombs"


async def leer_xlsx(archivo: UploadFile) -> bytes:
    """Valida y devuelve el contenido de un .xlsx subido (OWASP File Upload Cheat Sheet).

    - extensión y tipo declarado
    - firma real del archivo (ZIP) y estructura de libro de Excel
    - tamaño subido y tamaño descomprimido
    El XML interno se procesa con defusedxml (instalado: openpyxl lo usa automáticamente).

    Los archivos NO se guardan en el servidor: el contenido se procesa en memoria y el archivo
    temporal que crea el servidor web al recibir la subida se cierra (y se borra) aquí mismo,
    se acepte o se rechace. En la base solo quedan los datos extraídos y el nombre del archivo.
    """
    try:
        nombre = (archivo.filename or "").lower()
        if not nombre.endswith(".xlsx"):
            raise ApiError(415, "Solo se aceptan archivos de Excel .xlsx")
        if archivo.content_type and archivo.content_type not in XLSX_MIME:
            raise ApiError(415, "El tipo de archivo no corresponde a un Excel .xlsx")

        limite = get_settings().max_upload_mb * 1024 * 1024
        contenido = await archivo.read(limite + 1)
    finally:
        await archivo.close()

    if len(contenido) > limite:
        raise ApiError(413, f"El archivo supera el tamaño máximo de {get_settings().max_upload_mb} MB")
    if not contenido.startswith(b"PK\x03\x04"):
        raise ApiError(415, "El archivo no es un Excel válido")
    try:
        with zipfile.ZipFile(BytesIO(contenido)) as z:
            nombres = set(z.namelist())
            if "xl/workbook.xml" not in nombres:
                raise ApiError(415, "El archivo no es un libro de Excel válido")
            if sum(i.file_size for i in z.infolist()) > MAX_DESCOMPRIMIDO:
                raise ApiError(413, "El contenido del archivo es demasiado grande")
    except zipfile.BadZipFile as e:
        raise ApiError(415, "El archivo está dañado o no es un Excel válido") from e
    return contenido
