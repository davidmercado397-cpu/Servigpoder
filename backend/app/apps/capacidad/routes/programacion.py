from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy import select

from app.api.deps import DbSession, require
from app.core.archivos import leer_xlsx
from app.core.auditoria import auditar
from app.core.rate_limit import limitar
from app.core.paginacion import Paginacion, paginar_consulta, paginar_lista
from app.core.respuestas import ApiError, ApiResponse, ok
from app.apps.capacidad.models import ProgramacionCarga, Usuario
from app.apps.capacidad.schemas.f1 import CargaOut
from app.apps.capacidad.services import cobertura
from app.apps.capacidad.services.programacion import ErrorProgramacion, cargar

router = APIRouter(prefix="/programacion", tags=["programación"])


@router.post("/cargas", response_model=ApiResponse[CargaOut], status_code=201,
             dependencies=[Depends(limitar("importar", 10, 60))])
async def subir(request: Request, db: DbSession, archivo: UploadFile = File(...),
                actual: Usuario = Depends(require("capacidad.programacion.cargar"))):
    contenido = await leer_xlsx(archivo)
    try:
        carga = cargar(db, contenido, archivo.filename or "programacion.xlsx", actual.id)
    except ErrorProgramacion as e:
        db.rollback()
        raise ApiError(400, str(e)) from e
    auditar(db, request, "programacion_cargada", actual.id, carga_id=carga.id, archivo=carga.archivo,
            desde=str(carga.desde), hasta=str(carga.hasta), filas=carga.resumen.get("filas"))
    db.commit()
    # Si ya existe la matriz del mes, el análisis de cobertura se calcula de inmediato
    analisis_id = None
    try:
        analisis_id = cobertura.analizar(db, carga, actual.id).id
    except cobertura.ErrorAnalisis:
        db.rollback()
    return ok(carga, analisis_id=analisis_id)


@router.get("/cargas", response_model=ApiResponse[list[CargaOut]])
def listar(db: DbSession, p: Paginacion, _=Depends(require("capacidad.analisis.ver"))):
    cargas, meta = paginar_consulta(db, select(ProgramacionCarga).order_by(ProgramacionCarga.id.desc()), p)
    return ok(cargas, **meta)


@router.get("/cargas/{carga_id}", response_model=ApiResponse[CargaOut])
def detalle(carga_id: int, db: DbSession, _=Depends(require("capacidad.analisis.ver"))):
    carga = db.get(ProgramacionCarga, carga_id)
    if carga is None:
        raise ApiError(404, "Carga no encontrada")
    return ok(carga)
