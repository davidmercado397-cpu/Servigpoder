from collections import Counter
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select

from app.api.deps import DbSession, require
from app.core.auditoria import auditar
from app.core.paginacion import Paginacion, paginar_consulta, paginar_lista
from app.core.respuestas import ApiError, ApiResponse, ok
from app.apps.capacidad.models import (
    MatrizPeriodo, ProgramacionCarga, ProgramacionFila, Puesto, PuestoEquivalencia, Ubicacion, Usuario,
)
from app.apps.capacidad.models.matriz import CERRADO
from app.apps.capacidad.schemas.f1 import (
    EquivalenciaIn, EquivalenciaOut, PorAclarar, PuestoCrear, PuestoCreado, PuestoEditar, PuestoOut, UbicacionOut,
)
from app.apps.capacidad.services import matriz as svc_matriz
from app.apps.capacidad.services.codigos import limpiar

router = APIRouter(prefix="/maestros", tags=["maestros"])


@router.get("/puestos", response_model=ApiResponse[list[PuestoOut]])
def listar_puestos(db: DbSession, p: Paginacion, q: str = Query("", max_length=100),
                   _=Depends(require("capacidad.maestros.ver"))):
    puestos, meta = paginar_consulta(db, _consulta_puestos(q), p)
    return ok(puestos, **meta)


@router.get("/puestos/opciones", response_model=ApiResponse[list[PuestoOut]])
def opciones_puestos(db: DbSession, q: str = Query("", max_length=100), _=Depends(require("capacidad.maestros.ver"))):
    """Hasta 20 puestos que coinciden con el texto, para selectores con búsqueda."""
    return ok(list(db.scalars(_consulta_puestos(q).limit(20)).unique()))


def _consulta_puestos(q: str):
    consulta = select(Puesto).join(Puesto.ubicacion).order_by(Ubicacion.codigo, Puesto.codigo)
    if q.strip():
        patron = f"%{q.strip()}%"
        consulta = consulta.where(or_(Puesto.codigo.ilike(patron), Puesto.descripcion.ilike(patron), Ubicacion.nombre.ilike(patron)))
    return consulta


@router.get("/ubicaciones/opciones", response_model=ApiResponse[list[UbicacionOut]])
def opciones_ubicaciones(db: DbSession, q: str = Query("", max_length=100), _=Depends(require("capacidad.maestros.ver"))):
    """Hasta 20 ubicaciones que coinciden con el texto (código, nombre o ciudad)."""
    consulta = select(Ubicacion).order_by(Ubicacion.codigo)
    if q.strip():
        patron = f"%{q.strip()}%"
        consulta = consulta.where(or_(Ubicacion.codigo.ilike(patron), Ubicacion.nombre.ilike(patron), Ubicacion.ciudad.ilike(patron)))
    return ok(list(db.scalars(consulta.limit(20))))


def _asignar_equivalencia(db: DbSession, codigo_siesa: str, puesto_id: int) -> str:
    """El código de SIESA queda apuntando al puesto, también en la programación ya cargada."""
    codigo = limpiar(codigo_siesa)
    eq = db.get(PuestoEquivalencia, codigo) or PuestoEquivalencia(codigo_siesa=codigo)
    eq.puesto_id = puesto_id
    eq.origen = "manual"
    db.add(eq)
    db.query(ProgramacionFila).filter(ProgramacionFila.puesto_siesa == codigo).update({"puesto_id": puesto_id})
    return codigo


@router.post("/puestos", response_model=ApiResponse[PuestoCreado], status_code=201)
def crear_puesto(data: PuestoCrear, request: Request, db: DbSession, actual: Usuario = Depends(require("capacidad.maestros.gestionar"))):
    """Crea un puesto (y su ubicación si no existe). Opcionalmente le asigna el código de SIESA y lo agrega a la
    matriz comercial de un mes, para luego configurar allí su cobertura."""
    codigo = limpiar(data.codigo)
    if db.scalar(select(Puesto).where(func.upper(Puesto.codigo) == codigo)):
        raise ApiError(409, f"Ya existe el puesto {codigo}")
    cod_ubicacion = limpiar(data.ubicacion_codigo)
    ubicacion = db.scalar(select(Ubicacion).where(func.upper(Ubicacion.codigo) == cod_ubicacion))
    ubicacion_creada = ubicacion is None
    if ubicacion is None:
        if not (data.ubicacion_nombre or "").strip():
            raise ApiError(422, f"La ubicación {cod_ubicacion} no existe: escriba su nombre para crearla", "UBICACION_NUEVA")
        ubicacion = Ubicacion(codigo=cod_ubicacion, nombre=data.ubicacion_nombre.strip(), ciudad=(data.ubicacion_ciudad or "").strip() or None)
        db.add(ubicacion)
        db.flush()

    periodo = None
    if data.periodo_id is not None:
        periodo = db.get(MatrizPeriodo, data.periodo_id)
        if periodo is None:
            raise ApiError(404, "Matriz del mes no encontrada")
        if periodo.estado == CERRADO:
            raise ApiError(409, f"La matriz de {periodo.mes:02d}/{periodo.anio} está cerrada")

    puesto = Puesto(codigo=codigo, ubicacion_id=ubicacion.id, descripcion=data.descripcion.strip(), excluido=data.excluido)
    db.add(puesto)
    db.flush()
    equivalencia = _asignar_equivalencia(db, data.codigo_siesa, puesto.id) if (data.codigo_siesa or "").strip() else None
    mp = None
    if periodo is not None:
        mp = svc_matriz.agregar_puesto(periodo, puesto, data.hombres, data.secuencia)
        periodo.actualizado_en = datetime.now(timezone.utc)
        db.flush()
    auditar(db, request, "puesto_creado", actual.id, puesto=codigo, ubicacion=ubicacion.codigo, ubicacion_creada=ubicacion_creada,
            codigo_siesa=equivalencia, matriz=f"{periodo.mes:02d}/{periodo.anio}" if periodo else None)
    db.commit()
    db.refresh(puesto)
    return ok(PuestoCreado(puesto=PuestoOut.model_validate(puesto), ubicacion_creada=ubicacion_creada, equivalencia=equivalencia,
                           matriz_puesto_id=mp.id if mp else None))


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
def listar_equivalencias(db: DbSession, p: Paginacion, _=Depends(require("capacidad.maestros.ver"))):
    lista, meta = paginar_consulta(db, select(PuestoEquivalencia).order_by(PuestoEquivalencia.codigo_siesa), p)
    return ok(lista, **meta)


@router.put("/equivalencias", response_model=ApiResponse[EquivalenciaOut])
def guardar_equivalencia(data: EquivalenciaIn, request: Request, db: DbSession,
                         actual: Usuario = Depends(require("capacidad.maestros.gestionar"))):
    """Asigna (o confirma) a qué puesto del maestro corresponde un código de SIESA.

    Actualiza también las filas de programación ya cargadas con ese código.
    """
    if db.get(Puesto, data.puesto_id) is None:
        raise ApiError(404, "Puesto no encontrado")
    codigo = _asignar_equivalencia(db, data.codigo_siesa, data.puesto_id)
    auditar(db, request, "equivalencia_guardada", actual.id, codigo_siesa=codigo, puesto_id=data.puesto_id)
    db.commit()
    return ok(db.get(PuestoEquivalencia, codigo))


@router.get("/por-aclarar", response_model=ApiResponse[list[PorAclarar]])
def por_aclarar(db: DbSession, p: Paginacion, _=Depends(require("capacidad.maestros.ver"))):
    """Puestos de la última carga de programación sin equivalencia o con equivalencia aproximada."""
    carga_id = db.scalar(select(func.max(ProgramacionCarga.id)))
    if carga_id is None:
        return ok([], **p.meta(0), mensaje="Aún no hay programación cargada")
    filas = db.execute(
        select(ProgramacionFila.puesto_siesa, func.max(ProgramacionFila.puesto_descripcion), func.count())
        .where(ProgramacionFila.carga_id == carga_id)
        .group_by(ProgramacionFila.puesto_siesa)
    ).all()
    # Ubicación más frecuente con la que llega cada código (para crear el puesto si no existe)
    ubic_siesa: dict[str, Counter] = {}
    for puesto_siesa, cod_ubic, nombre_ubic in db.execute(
            select(ProgramacionFila.puesto_siesa, ProgramacionFila.ubicacion_siesa, ProgramacionFila.ubicacion_nombre)
            .where(ProgramacionFila.carga_id == carga_id)):
        ubic_siesa.setdefault(puesto_siesa, Counter())[(cod_ubic or "", nombre_ubic or "")] += 1
    ubicaciones = {limpiar(u.codigo): u for u in db.scalars(select(Ubicacion))}
    equivalencias = {e.codigo_siesa: e for e in db.scalars(select(PuestoEquivalencia))}
    resultado = []
    for codigo, descripcion, n in filas:
        eq = equivalencias.get(codigo)
        if eq is not None and eq.origen != "aproximada":
            continue
        (cod_ubic, nombre_ubic), _ = (ubic_siesa.get(codigo) or Counter({("", ""): 1})).most_common(1)[0]
        ubic = ubicaciones.get(limpiar(cod_ubic))
        extra = {"ubicacion_siesa": cod_ubic, "ubicacion_nombre": nombre_ubic,
                 "ubicacion": UbicacionOut.model_validate(ubic) if ubic else None}
        if eq is None:
            resultado.append(PorAclarar(codigo_siesa=codigo, descripcion=descripcion or "", filas=n, motivo="sin_equivalencia", **extra))
        else:
            resultado.append(PorAclarar(codigo_siesa=codigo, descripcion=descripcion or "", filas=n, motivo="aproximada",
                                        puesto_sugerido=PuestoOut.model_validate(eq.puesto), **extra))
    resultado.sort(key=lambda r: (r.motivo, r.codigo_siesa))
    pagina, meta = paginar_lista(resultado, p)
    carga = db.get(ProgramacionCarga, carga_id)
    matriz = db.scalar(select(MatrizPeriodo).where(MatrizPeriodo.anio == carga.anio, MatrizPeriodo.mes == carga.mes))
    return ok(pagina, **meta, carga_id=carga_id, anio=carga.anio, mes=carga.mes,
              matriz={"id": matriz.id, "estado": matriz.estado} if matriz else None)
