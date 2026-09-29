"""Reporte de programación: del Excel de SIESA a un PDF ordenado por ubicación y puesto.

Nada se guarda: el Excel se procesa en memoria y el PDF se devuelve en la misma respuesta.
"""

from io import BytesIO

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.deps import DbSession, require
from app.core.archivos import leer_xlsx
from app.core.auditoria import auditar
from app.core.rate_limit import limitar
from app.core.respuestas import ApiError, ApiResponse, ok
from app.models import Usuario
from app.apps.reporte.services import lector, pdf

router = APIRouter(prefix="/reporte", tags=["reporte de programación"])
PERMISO = "reporte.generar"


class UbicacionOut(BaseModel):
    codigo: str
    nombre: str
    ciudad: str
    puestos: int
    empleados: int


class ResumenOut(BaseModel):
    compania: str
    desde: str
    hasta: str
    dias: int
    ubicaciones: list[UbicacionOut]
    ciudades: list[str]
    puestos: int
    filas: int


def _leer(contenido: bytes) -> lector.Programacion:
    try:
        return lector.leer(contenido)
    except lector.ErrorReporte as e:
        raise ApiError(422, str(e), "EXCEL_INVALIDO") from e


@router.post("/analizar", response_model=ApiResponse[ResumenOut], dependencies=[Depends(limitar("reporte", 20, 60))])
async def analizar(archivo: UploadFile = File(...), _: Usuario = Depends(require(PERMISO))):
    """Lee el Excel y devuelve el rango, las ciudades y las ubicaciones (para elegir filtros)."""
    prog = _leer(await leer_xlsx(archivo))
    return ok(ResumenOut(
        compania=prog.compania, desde=prog.desde.isoformat(), hasta=prog.hasta.isoformat(), dias=len(prog.fechas),
        ciudades=prog.ciudades(), puestos=prog.puestos, filas=prog.filas,
        ubicaciones=[UbicacionOut(codigo=u.codigo, nombre=u.nombre, ciudad=u.ciudad, puestos=len(u.puestos), empleados=u.empleados)
                     for u in lector.ordenada(prog)],
    ))


@router.post("/pdf", dependencies=[Depends(limitar("reporte", 20, 60))])
async def generar_pdf(request: Request, db: DbSession, archivo: UploadFile = File(...),
                      ciudades: str = Form(""), ubicaciones: str = Form(""),
                      actual: Usuario = Depends(require(PERMISO))):
    """PDF en hoja Carta horizontal. `ciudades` y `ubicaciones`: listas separadas por '|' (vacío = todas)."""
    nombre_archivo = (archivo.filename or "")[:200]
    prog = _leer(await leer_xlsx(archivo))
    lista_ciudades = [c for c in ciudades.split("|") if c.strip()][:50]
    lista_ubicaciones = [u for u in ubicaciones.split("|") if u.strip()][:1000]
    filtros = []
    if lista_ciudades:
        filtros.append("ciudad " + ", ".join(lista_ciudades))
    if lista_ubicaciones:
        filtros.append(f"{len(lista_ubicaciones)} ubicaciones seleccionadas")
    try:
        prog = lector.filtrar(prog, lista_ciudades, lista_ubicaciones)
    except lector.ErrorReporte as e:
        raise ApiError(422, str(e)) from e
    contenido = pdf.generar(prog, filtros="; ".join(filtros))

    auditar(db, request, "reporte_pdf_generado", actual.id, archivo=nombre_archivo, desde=prog.desde.isoformat(),
            hasta=prog.hasta.isoformat(), ubicaciones=len(prog.ubicaciones), filas=prog.filas, filtros=filtros)
    db.commit()
    nombre = f"programacion_{prog.desde:%Y-%m-%d}_a_{prog.hasta:%Y-%m-%d}.pdf"
    return StreamingResponse(BytesIO(contenido), media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{nombre}"'})
