from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy import select

from app.api.deps import DbSession, require
from app.core.archivos import leer_xlsx
from app.core.auditoria import auditar
from app.core.rate_limit import limitar
from app.core.respuestas import ApiError, ApiResponse, ok
from app.apps.capacidad.models import Novedad, Turno, Usuario
from app.apps.capacidad.schemas.f1 import NovedadIn, NovedadOut, TurnoOut
from app.apps.capacidad.services.catalogos import importar_turnos

router = APIRouter(prefix="/catalogos", tags=["catálogos"])


@router.get("/turnos", response_model=ApiResponse[list[TurnoOut]])
def listar_turnos(db: DbSession, _=Depends(require("capacidad.maestros.ver"))):
    turnos = list(db.scalars(select(Turno).order_by(Turno.codigo)))
    return ok(turnos, total=len(turnos))


@router.post("/turnos/importar", response_model=ApiResponse[dict],
             dependencies=[Depends(limitar("importar", 10, 60))])
async def importar(request: Request, db: DbSession, archivo: UploadFile = File(...),
                   actual: Usuario = Depends(require("capacidad.maestros.gestionar"))):
    contenido = await leer_xlsx(archivo)
    try:
        total = importar_turnos(db, contenido)
    except ValueError as e:
        raise ApiError(400, str(e)) from e
    auditar(db, request, "turnos_importados", actual.id, archivo=archivo.filename, turnos=total)
    db.commit()
    return ok({"turnos": total})


@router.get("/novedades", response_model=ApiResponse[list[NovedadOut]])
def listar_novedades(db: DbSession, _=Depends(require("capacidad.maestros.ver"))):
    return ok(list(db.scalars(select(Novedad).order_by(Novedad.codigo))))


@router.put("/novedades", response_model=ApiResponse[NovedadOut])
def guardar_novedad(data: NovedadIn, request: Request, db: DbSession,
                    actual: Usuario = Depends(require("capacidad.maestros.gestionar"))):
    codigo = data.codigo.strip().upper()
    nov = db.get(Novedad, codigo) or Novedad(codigo=codigo)
    nov.descripcion = data.descripcion.strip()
    nov.requiere_cubrimiento = data.requiere_cubrimiento
    db.add(nov)
    auditar(db, request, "novedad_guardada", actual.id, codigo=codigo)
    db.commit()
    return ok(nov)
