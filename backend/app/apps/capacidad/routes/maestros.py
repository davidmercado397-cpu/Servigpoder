from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select

from app.api.deps import DbSession, require
from app.core.auditoria import auditar
from app.core.respuestas import ApiError, ApiResponse, ok
from app.apps.capacidad.models import ProgramacionCarga, ProgramacionFila, Puesto, PuestoEquivalencia, Ubicacion, Usuario
from app.apps.capacidad.schemas.f1 import EquivalenciaIn, EquivalenciaOut, PorAclarar, PuestoEditar, PuestoOut
from app.apps.capacidad.services.codigos import limpiar

router = APIRouter(prefix="/maestros", tags=["maestros"])


@router.get("/puestos", response_model=ApiResponse[list[PuestoOut]])
def listar_puestos(db: DbSession, q: str = Query("", max_length=100), _=Depends(require("capacidad.maestros.ver"))):
    consulta = select(Puesto).join(Puesto.ubicacion).order_by(Ubicacion.codigo, Puesto.codigo)
    if q.strip():
        patron = f"%{q.strip()}%"
        consulta = consulta.where(or_(Puesto.codigo.ilike(patron), Puesto.descripcion.ilike(patron), Ubicacion.nombre.ilike(patron)))
    puestos = list(db.scalars(consulta))
    return ok(puestos, total=len(puestos))


@router.patch("/puestos/{puesto_id}", response_model=ApiResponse[PuestoOut])
def editar_puesto(puesto_id: int, data: PuestoEditar, request: Request, db: DbSession,
                  actual: Usuario = Depends(require("capacidad.maestros.gestionar"))):
    puesto = db.get(Puesto, puesto_id)
    if puesto is None:
        raise ApiError(404, "Puesto no encontrado")
    for campo, valor in data.model_dump(exclude_none=True).items():
        setattr(puesto, campo, valor)
    auditar(db, request, "puesto_editado", actual.id, puesto=puesto.codigo, **data.model_dump(exclude_none=True))
    db.commit()
    return ok(puesto)


@router.get("/equivalencias", response_model=ApiResponse[list[EquivalenciaOut]])
def listar_equivalencias(db: DbSession, _=Depends(require("capacidad.maestros.ver"))):
    return ok(list(db.scalars(select(PuestoEquivalencia).order_by(PuestoEquivalencia.codigo_siesa))))


@router.put("/equivalencias", response_model=ApiResponse[EquivalenciaOut])
def guardar_equivalencia(data: EquivalenciaIn, request: Request, db: DbSession,
                         actual: Usuario = Depends(require("capacidad.maestros.gestionar"))):
    """Asigna (o confirma) a qué puesto del maestro corresponde un código de SIESA.

    Actualiza también las filas de programación ya cargadas con ese código.
    """
    if db.get(Puesto, data.puesto_id) is None:
        raise ApiError(404, "Puesto no encontrado")
    codigo = limpiar(data.codigo_siesa)
    eq = db.get(PuestoEquivalencia, codigo) or PuestoEquivalencia(codigo_siesa=codigo)
    eq.puesto_id = data.puesto_id
    eq.origen = "manual"
    db.add(eq)
    db.query(ProgramacionFila).filter(ProgramacionFila.puesto_siesa == codigo).update({"puesto_id": data.puesto_id})
    auditar(db, request, "equivalencia_guardada", actual.id, codigo_siesa=codigo, puesto_id=data.puesto_id)
    db.commit()
    db.refresh(eq)
    return ok(eq)


@router.get("/por-aclarar", response_model=ApiResponse[list[PorAclarar]])
def por_aclarar(db: DbSession, _=Depends(require("capacidad.maestros.ver"))):
    """Puestos de la última carga de programación sin equivalencia o con equivalencia aproximada."""
    carga_id = db.scalar(select(func.max(ProgramacionCarga.id)))
    if carga_id is None:
        return ok([], mensaje="Aún no hay programación cargada")
    filas = db.execute(
        select(ProgramacionFila.puesto_siesa, func.max(ProgramacionFila.puesto_descripcion), func.count())
        .where(ProgramacionFila.carga_id == carga_id)
        .group_by(ProgramacionFila.puesto_siesa)
    ).all()
    equivalencias = {e.codigo_siesa: e for e in db.scalars(select(PuestoEquivalencia))}
    resultado = []
    for codigo, descripcion, n in filas:
        eq = equivalencias.get(codigo)
        if eq is None:
            resultado.append(PorAclarar(codigo_siesa=codigo, descripcion=descripcion or "", filas=n, motivo="sin_equivalencia"))
        elif eq.origen == "aproximada":
            resultado.append(PorAclarar(codigo_siesa=codigo, descripcion=descripcion or "", filas=n, motivo="aproximada",
                                        puesto_sugerido=PuestoOut.model_validate(eq.puesto)))
    resultado.sort(key=lambda r: (r.motivo, r.codigo_siesa))
    return ok(resultado, carga_id=carga_id, total=len(resultado))
