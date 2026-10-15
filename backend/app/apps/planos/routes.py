"""Planos SIESA: procesar planos de empleados y contratos y mantener su configuración.

Los planos subidos no se guardan: se leen en memoria, se procesan y el resultado se devuelve en la respuesta.
"""

import base64
import json
import re
from pathlib import PurePath

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DbSession, require
from app.apps.planos.models import PlanoAlias, PlanoCorreccion, PlanoEntidad, PlanoSalarioMinimo
from app.apps.planos.services import configuracion, contratos, empleados
from app.apps.planos.services.comun import PlanoInvalido, Resultado, normalizar
from app.apps.planos.services.dane import catalogo as catalogo_dane
from app.apps.planos.services.entidades import CATALOGOS
from app.core.archivos import leer_xlsx
from app.core.auditoria import auditar
from app.core.rate_limit import limitar
from app.core.respuestas import ApiError, ApiResponse, ok
from app.models import Usuario

router = APIRouter(prefix="/planos", tags=["planos SIESA"])
PROCESAR = "planos.procesar"
CONFIGURAR = "planos.configurar"
COLUMNA = r"^[A-Z]{1,2}$"
MAX_CRUCE = 20000


def _salida(nombre: str, libro: bytes, res: Resultado, **extra) -> dict:
    base = PurePath(nombre).stem.removesuffix("_CARGUE")
    return {"nombre": f"{base}_CARGUE.xlsx", "archivo": base64.b64encode(libro).decode(), "resumen": res.resumen,
            "cambios": res.cambios, "hallazgos": [h.__dict__ for h in res.hallazgos], **extra}


def _auditar(db, request, actual, plano: str, nombre: str, res: Resultado) -> None:
    auditar(db, request, "plano_procesado", actual.id, plano=plano, archivo=nombre[:120], filas=res.resumen.get("filas", 0),
            errores=res.resumen.get("Error", 0))
    db.commit()


@router.post("/empleados", response_model=ApiResponse[dict], dependencies=[Depends(limitar("planos", 30, 60))])
async def procesar_empleados(request: Request, db: DbSession, archivo: UploadFile = File(...), modo: str = Form("completo"),
                             fila_ejemplo: int | None = Form(None), conservar_enie: bool = Form(False),
                             actual: Usuario = Depends(require(PROCESAR))):
    nombre = archivo.filename or "plano_empleados.xlsx"
    contenido = await leer_xlsx(archivo)
    try:
        libro, res, cruce = empleados.procesar(contenido, configuracion.resolver_dane(db), modo, configuracion.correcciones(db, "empleados"),
                                              fila_ejemplo, conservar_enie)
    except PlanoInvalido as e:
        raise ApiError(422, str(e), "PLANO_INVALIDO") from e
    _auditar(db, request, actual, "empleados", nombre, res)
    return ok(_salida(nombre, libro, res, cruce=cruce))


@router.post("/contratos", response_model=ApiResponse[dict], dependencies=[Depends(limitar("planos", 30, 60))])
async def procesar_contratos(request: Request, db: DbSession, archivo: UploadFile = File(...), fila_ejemplo: int | None = Form(None),
                             empleados_cruce: str = Form(""), actual: Usuario = Depends(require(PROCESAR))):
    """empleados_cruce: {cédula: fecha de ingreso} del plano de empleados procesado antes (lo guarda el navegador)."""
    nombre = archivo.filename or "plano_contratos.xlsx"
    contenido = await leer_xlsx(archivo)
    smlv = configuracion.salario_minimo(db)
    if smlv is None:
        raise ApiError(422, "Falta el salario mínimo del año en curso: regístrelo en Planos SIESA → Catálogos", "SIN_SALARIO_MINIMO")
    cruce = None
    if empleados_cruce:
        try:
            cruce = {str(k): str(v) for k, v in json.loads(empleados_cruce).items()}
        except (ValueError, AttributeError) as e:
            raise ApiError(422, "El cruce con el plano de empleados no es válido") from e
        if len(cruce) > MAX_CRUCE:
            raise ApiError(413, "El cruce con el plano de empleados es demasiado grande")
    try:
        libro, res = contratos.procesar(contenido, configuracion.codificador(db), smlv, configuracion.correcciones(db, "contratos"),
                                        cruce, fila_ejemplo)
    except PlanoInvalido as e:
        raise ApiError(422, str(e), "PLANO_INVALIDO") from e
    _auditar(db, request, actual, "contratos", nombre, res)
    return ok(_salida(nombre, libro, res, cruzado=cruce is not None))


# ---------------- Catálogos DANE (para crear alias) ----------------

@router.get("/dane", response_model=ApiResponse[dict])
def dane(_=Depends(require(PROCESAR))):
    cat = catalogo_dane()
    return ok({
        "paises": [{"codigo": c, "nombre": n} for c, n in cat.paises.items()],
        "departamentos": [{"pais": p, "codigo": d, "nombre": n} for (p, d), n in sorted(cat.nombres_depto.items(), key=lambda x: x[1])],
    })


@router.get("/dane/ciudades", response_model=ApiResponse[list[dict]])
def ciudades(pais: str, departamento: str, _=Depends(require(PROCESAR))):
    cat = catalogo_dane()
    filas = [{"codigo": c, "nombre": cat.nombres_ciudad[(pais, departamento, c)]} for c in cat.ciudades.get((pais, departamento), {})]
    return ok(sorted(filas, key=lambda x: x["nombre"]))


# ---------------- Entidades ----------------

class EntidadIn(BaseModel):
    catalogo: str
    codigo: str = Field(min_length=1, max_length=20)
    descripcion: str = Field(min_length=2, max_length=200)
    observacion: str = Field(default="", max_length=200)


@router.get("/entidades", response_model=ApiResponse[list[dict]])
def entidades(db: DbSession, catalogo: str | None = None, _=Depends(require(PROCESAR))):
    q = select(PlanoEntidad).order_by(PlanoEntidad.catalogo, PlanoEntidad.codigo)
    if catalogo:
        q = q.where(PlanoEntidad.catalogo == catalogo)
    return ok([{"catalogo": e.catalogo, "codigo": e.codigo, "descripcion": e.descripcion, "observacion": e.observacion}
               for e in db.scalars(q)], catalogos=list(CATALOGOS))


@router.put("/entidades", response_model=ApiResponse[dict])
def guardar_entidad(data: EntidadIn, request: Request, db: DbSession, actual: Usuario = Depends(require(CONFIGURAR))):
    if data.catalogo not in CATALOGOS:
        raise ApiError(422, "Catálogo desconocido")
    codigo = data.codigo.strip()
    e = db.get(PlanoEntidad, (data.catalogo, codigo)) or PlanoEntidad(catalogo=data.catalogo, codigo=codigo)
    e.descripcion, e.observacion = data.descripcion.strip(), data.observacion.strip()
    db.add(e)
    auditar(db, request, "plano_entidad_guardada", actual.id, catalogo=data.catalogo, codigo=codigo, descripcion=e.descripcion)
    db.commit()
    return ok({"catalogo": e.catalogo, "codigo": e.codigo, "descripcion": e.descripcion, "observacion": e.observacion})


@router.delete("/entidades/{catalogo}/{codigo}", response_model=ApiResponse[dict])
def eliminar_entidad(catalogo: str, codigo: str, request: Request, db: DbSession, actual: Usuario = Depends(require(CONFIGURAR))):
    e = db.get(PlanoEntidad, (catalogo, codigo))
    if e is None:
        raise ApiError(404, "Entidad no encontrada")
    db.delete(e)
    db.query(PlanoAlias).filter(PlanoAlias.catalogo == catalogo, PlanoAlias.codigo == codigo).delete()
    auditar(db, request, "plano_entidad_eliminada", actual.id, catalogo=catalogo, codigo=codigo)
    db.commit()
    return ok({"eliminado": codigo})


# ---------------- Alias ----------------

class AliasIn(BaseModel):
    catalogo: str
    texto: str = Field(min_length=1, max_length=120)
    codigo: str = Field(min_length=1, max_length=20)
    pais: str = Field(default="", max_length=3)
    departamento: str = Field(default="", max_length=2)
    nota: str = Field(default="", max_length=200)


def _alias_out(a: PlanoAlias) -> dict:
    cat = catalogo_dane()
    if a.catalogo == "DEPARTAMENTO":
        destino = cat.nombres_depto.get((a.pais, a.codigo), "")
    elif a.catalogo == "CIUDAD":
        destino = f"{cat.nombres_ciudad.get((a.pais, a.departamento, a.codigo), '')} ({cat.nombres_depto.get((a.pais, a.departamento), '')})"
    else:
        destino = ""
    return {"id": a.id, "catalogo": a.catalogo, "texto": a.texto, "codigo": a.codigo, "pais": a.pais, "departamento": a.departamento,
            "nota": a.nota, "destino": destino, "creado_en": a.creado_en.isoformat() if a.creado_en else ""}


@router.get("/alias", response_model=ApiResponse[list[dict]])
def alias(db: DbSession, catalogo: str | None = None, _=Depends(require(PROCESAR))):
    q = select(PlanoAlias).order_by(PlanoAlias.catalogo, PlanoAlias.texto)
    if catalogo:
        q = q.where(PlanoAlias.catalogo == catalogo)
    lista = [_alias_out(a) for a in db.scalars(q)]
    nombres = {(e.catalogo, e.codigo): e.descripcion for e in db.scalars(select(PlanoEntidad))}
    for a in lista:
        a["destino"] = a["destino"] or nombres.get((a["catalogo"], a["codigo"]), "")
    return ok(lista)


@router.post("/alias", response_model=ApiResponse[dict])
def crear_alias(data: AliasIn, request: Request, db: DbSession, actual: Usuario = Depends(require(CONFIGURAR))):
    texto = normalizar(data.texto)
    if not texto:
        raise ApiError(422, "El texto del alias está vacío")
    cat = catalogo_dane()
    pais, depto, codigo = data.pais.strip(), data.departamento.strip(), data.codigo.strip()
    if data.catalogo == "DEPARTAMENTO":
        depto = ""
        if (pais, codigo) not in cat.nombres_depto:
            raise ApiError(422, "El departamento no existe para ese país")
    elif data.catalogo == "CIUDAD":
        if (pais, depto, codigo) not in cat.nombres_ciudad:
            raise ApiError(422, "La ciudad no existe en ese departamento")
    elif data.catalogo in CATALOGOS:
        pais = depto = ""
        if db.get(PlanoEntidad, (data.catalogo, codigo)) is None:
            raise ApiError(422, f"El código {codigo} no está en el catálogo {data.catalogo}")
    else:
        raise ApiError(422, "Catálogo desconocido")
    a = db.scalar(select(PlanoAlias).where(PlanoAlias.catalogo == data.catalogo, PlanoAlias.pais == pais,
                                           PlanoAlias.departamento == depto, PlanoAlias.texto == texto))
    if a is None:
        a = PlanoAlias(catalogo=data.catalogo, pais=pais, departamento=depto, texto=texto, creado_por=actual.id)
        db.add(a)
    a.codigo, a.nota = codigo, data.nota.strip()
    auditar(db, request, "plano_alias_guardado", actual.id, catalogo=data.catalogo, texto=texto, codigo=codigo, departamento=depto)
    db.commit()
    db.refresh(a)
    return ok(_alias_out(a))


@router.delete("/alias/{alias_id}", response_model=ApiResponse[dict])
def eliminar_alias(alias_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(CONFIGURAR))):
    a = db.get(PlanoAlias, alias_id)
    if a is None:
        raise ApiError(404, "Alias no encontrado")
    auditar(db, request, "plano_alias_eliminado", actual.id, catalogo=a.catalogo, texto=a.texto, codigo=a.codigo)
    db.delete(a)
    db.commit()
    return ok({"eliminado": alias_id})


# ---------------- Correcciones manuales ----------------

class CorreccionIn(BaseModel):
    plano: str = Field(pattern=r"^(empleados|contratos)$")
    cedula: str = Field(min_length=3, max_length=20)
    columna: str = Field(pattern=COLUMNA)
    valor: str = Field(min_length=1, max_length=120)
    nota: str = Field(default="", max_length=200)


def _correccion_out(c: PlanoCorreccion) -> dict:
    return {"id": c.id, "plano": c.plano, "cedula": c.cedula, "columna": c.columna, "valor": c.valor, "nota": c.nota,
            "creado_en": c.creado_en.isoformat() if c.creado_en else ""}


@router.get("/correcciones", response_model=ApiResponse[list[dict]])
def listar_correcciones(db: DbSession, plano: str | None = None, _=Depends(require(PROCESAR))):
    q = select(PlanoCorreccion).order_by(PlanoCorreccion.plano, PlanoCorreccion.cedula, PlanoCorreccion.columna)
    if plano:
        q = q.where(PlanoCorreccion.plano == plano)
    return ok([_correccion_out(c) for c in db.scalars(q)])


@router.post("/correcciones", response_model=ApiResponse[dict])
def guardar_correccion(data: CorreccionIn, request: Request, db: DbSession, actual: Usuario = Depends(require(CONFIGURAR))):
    cedula = re.sub(r"\D", "", data.cedula)
    if not cedula:
        raise ApiError(422, "La cédula debe tener dígitos")
    c = db.scalar(select(PlanoCorreccion).where(PlanoCorreccion.plano == data.plano, PlanoCorreccion.cedula == cedula,
                                                PlanoCorreccion.columna == data.columna))
    if c is None:
        c = PlanoCorreccion(plano=data.plano, cedula=cedula, columna=data.columna, creado_por=actual.id)
        db.add(c)
    c.valor, c.nota = data.valor.strip(), data.nota.strip()
    auditar(db, request, "plano_correccion_guardada", actual.id, plano=data.plano, columna=data.columna)
    db.commit()
    db.refresh(c)
    return ok(_correccion_out(c))


@router.delete("/correcciones/{correccion_id}", response_model=ApiResponse[dict])
def eliminar_correccion(correccion_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(CONFIGURAR))):
    c = db.get(PlanoCorreccion, correccion_id)
    if c is None:
        raise ApiError(404, "Corrección no encontrada")
    auditar(db, request, "plano_correccion_eliminada", actual.id, plano=c.plano, columna=c.columna)
    db.delete(c)
    db.commit()
    return ok({"eliminado": correccion_id})


# ---------------- Salario mínimo ----------------

class SalarioIn(BaseModel):
    valor: int = Field(gt=0, lt=100_000_000)


@router.get("/salarios", response_model=ApiResponse[list[dict]])
def salarios(db: DbSession, _=Depends(require(PROCESAR))):
    return ok([{"anio": s.anio, "valor": s.valor} for s in db.scalars(select(PlanoSalarioMinimo).order_by(PlanoSalarioMinimo.anio.desc()))])


@router.put("/salarios/{anio}", response_model=ApiResponse[dict])
def guardar_salario(anio: int, data: SalarioIn, request: Request, db: DbSession, actual: Usuario = Depends(require(CONFIGURAR))):
    if not 2000 <= anio <= 2100:
        raise ApiError(422, "Año fuera de rango")
    s = db.get(PlanoSalarioMinimo, anio) or PlanoSalarioMinimo(anio=anio)
    antes = s.valor
    s.valor = data.valor
    db.add(s)
    auditar(db, request, "plano_salario_minimo", actual.id, anio=anio, antes=antes, despues=data.valor)
    db.commit()
    return ok({"anio": anio, "valor": s.valor})
