"""Costeo: parámetros, comisiones, servicios, catálogos de costos y costeos por cliente con versiones.
Un costeo aprobado guarda los parámetros con que se aprobó y puede crear la MFP del contrato."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, require
from app.apps.costeo.models import (
    APROBADO, BORRADOR, ENVIADO, RECHAZADO, CstCatalogoCosto, CstCliente, CstComisionRango, CstCosteo, CstMfp, CstMfpItem,
    CstParametro, CstServicio, CstTipoItem,
)
from app.apps.costeo.services import calculo, configuracion, ia_costeo, notificaciones, puestos
from app.apps.costeo.services.calculo import Rango
from app.core import ia
from app.core.auditoria import auditar
from app.core.config import get_settings
from app.core.rate_limit import limitar
from app.core.respuestas import ApiError, ApiResponse, ok
from app.models import Usuario

router = APIRouter()
VER, COSTEAR, CONFIGURAR, GESTIONAR, PRECIOS = "costeo.ver", "costeo.costear", "costeo.configurar", "costeo.mfp", "costeo.precios"
CONTABLE = "costeo.contable"


def require_alguno(*permisos: str):
    """Basta con uno de los permisos (los precios los actualiza compras/contabilidad o quien configura)."""

    def checker(user: CurrentUser) -> Usuario:
        if not any(p in user.permisos for p in permisos):
            raise ApiError(403, "No tiene permiso para realizar esta acción", details=[{"permiso": " o ".join(permisos)}])
        return user

    return checker
GRUPOS = ("dotacion_tarifa", "dotacion_puesto", "otros")
ESTADOS = (BORRADOR, ENVIADO, APROBADO, RECHAZADO)


# --- Parámetros y comisiones --------------------------------------------------------------------------

@router.get("/parametros", response_model=ApiResponse[list[dict]])
def parametros(db: DbSession, _=Depends(require(VER))):
    return ok([{"clave": p.clave, "valor": float(p.valor), "nombre": p.nombre, "grupo": p.grupo, "ayuda": p.ayuda,
                "actualizado_en": p.actualizado_en.isoformat() if p.actualizado_en else ""}
               for p in db.scalars(select(CstParametro).order_by(CstParametro.orden))])


@router.put("/parametros", response_model=ApiResponse[dict])
def guardar_parametros(data: dict[str, float], request: Request, db: DbSession, actual: Usuario = Depends(require(CONFIGURAR))):
    cambios = {}
    for clave, valor in data.items():
        p = db.get(CstParametro, clave)
        if p is None:
            raise ApiError(422, f"Parámetro desconocido: {clave}")
        if valor < 0 or valor > 1e14:
            raise ApiError(422, f"Valor fuera de rango para {p.nombre}")
        if float(p.valor) != valor:
            cambios[clave] = [float(p.valor), valor]
            p.valor = valor
    auditar(db, request, "cst_parametros", actual.id, cambios=cambios)
    db.commit()
    return ok({"actualizados": len(cambios)})


class RangoIn(BaseModel):
    hasta_pct: float | None = Field(default=None, ge=0, le=1)
    pct_comision: float = Field(ge=0, le=1)
    carga_prestacional: float = Field(gt=0, le=10)


@router.get("/comisiones", response_model=ApiResponse[list[dict]])
def comisiones(db: DbSession, _=Depends(require(VER))):
    filas = sorted(db.scalars(select(CstComisionRango)), key=lambda r: (r.hasta_pct is None, float(r.hasta_pct or 0)))
    return ok([{"id": r.id, "hasta_pct": float(r.hasta_pct) if r.hasta_pct is not None else None, "pct_comision": float(r.pct_comision),
                "carga_prestacional": float(r.carga_prestacional)} for r in filas])


@router.put("/comisiones", response_model=ApiResponse[dict])
def guardar_comisiones(data: list[RangoIn], request: Request, db: DbSession, actual: Usuario = Depends(require(CONFIGURAR))):
    if not data or sum(1 for r in data if r.hasta_pct is None) != 1:
        raise ApiError(422, "La tabla necesita exactamente un último rango sin tope («en adelante»)")
    db.query(CstComisionRango).delete()
    for r in data:
        db.add(CstComisionRango(**r.model_dump()))
    auditar(db, request, "cst_comisiones", actual.id, rangos=[r.model_dump() for r in data])
    db.commit()
    return ok({"rangos": len(data)})


# --- Servicios y catálogos ----------------------------------------------------------------------------

class ServicioIn(BaseModel):
    id: int | None = None
    descripcion: str = Field(min_length=3, max_length=400)
    tarifa: float = Field(ge=0, le=1e12)
    hombres: float = Field(ge=0, le=100)
    activo: bool = True


@router.get("/servicios", response_model=ApiResponse[list[dict]])
def servicios(db: DbSession, _=Depends(require(VER))):
    return ok([{"id": s.id, "descripcion": s.descripcion, "tarifa": float(s.tarifa), "hombres": float(s.hombres), "activo": s.activo}
               for s in db.scalars(select(CstServicio).order_by(CstServicio.id))])


@router.put("/servicios", response_model=ApiResponse[dict])
def guardar_servicio(data: ServicioIn, request: Request, db: DbSession, actual: Usuario = Depends(require_alguno(CONFIGURAR, CONTABLE))):
    s = db.get(CstServicio, data.id) if data.id else CstServicio()
    if s is None:
        raise ApiError(404, "Servicio no encontrado")
    for k, v in data.model_dump(exclude={"id"}).items():
        setattr(s, k, v)
    db.add(s)
    auditar(db, request, "cst_servicio", actual.id, descripcion=s.descripcion[:100], tarifa=data.tarifa, hombres=data.hombres)
    db.commit()
    return ok({"id": s.id})


class CatalogoIn(BaseModel):
    id: int | None = None
    grupo: str = Field(pattern=r"^(dotacion_tarifa|dotacion_puesto|otros)$")
    nombre: str = Field(min_length=2, max_length=200)
    valor_unitario: float = Field(ge=0, le=1e12)
    vida_util_meses: int | None = Field(default=None, ge=1, le=600)
    entregas_anio: float | None = Field(default=None, ge=0, le=365)
    por_hombre: bool = False
    aplica: str = Field(default="", pattern=r"^(|todos|gala|overol|arma|fuego|fogeo|traumatica|noletal)$")
    cantidad: float = Field(default=1, ge=0, le=1000)
    activo: bool = True
    fuente: str = Field(default="", max_length=120)


def _cat_out(c: CstCatalogoCosto) -> dict:
    return {"id": c.id, "grupo": c.grupo, "nombre": c.nombre, "valor_unitario": float(c.valor_unitario),
            "vida_util_meses": c.vida_util_meses, "entregas_anio": float(c.entregas_anio) if c.entregas_anio is not None else None,
            "por_hombre": c.por_hombre, "aplica": c.aplica or "", "cantidad": float(c.cantidad if c.cantidad is not None else 1),
            "activo": c.activo, "fuente": c.fuente,
            "actualizado_en": c.actualizado_en.isoformat() if c.actualizado_en else ""}


@router.get("/catalogo", response_model=ApiResponse[list[dict]])
def catalogo(db: DbSession, grupo: str | None = None, _=Depends(require(VER))):
    q = select(CstCatalogoCosto).order_by(CstCatalogoCosto.grupo, CstCatalogoCosto.id)
    if grupo:
        q = q.where(CstCatalogoCosto.grupo == grupo)
    return ok([_cat_out(c) for c in db.scalars(q)])


@router.put("/catalogo", response_model=ApiResponse[dict])
def guardar_catalogo(data: CatalogoIn, request: Request, db: DbSession, actual: Usuario = Depends(require_alguno(PRECIOS, CONFIGURAR))):
    c = db.get(CstCatalogoCosto, data.id) if data.id else CstCatalogoCosto()
    if c is None:
        raise ApiError(404, "Elemento no encontrado")
    otro = db.scalar(select(CstCatalogoCosto).where(CstCatalogoCosto.grupo == data.grupo, CstCatalogoCosto.nombre == data.nombre.strip()))
    if otro is not None and otro.id != c.id:
        raise ApiError(409, "Ya existe un elemento con ese nombre en el grupo")
    antes = float(c.valor_unitario) if c.id else None
    for k, v in data.model_dump(exclude={"id"}).items():
        setattr(c, k, v.strip() if isinstance(v, str) else v)
    db.add(c)
    auditar(db, request, "cst_catalogo", actual.id, grupo=c.grupo, nombre=c.nombre, antes=antes, valor=data.valor_unitario)
    db.commit()
    return ok(_cat_out(c))


# --- Costeos ------------------------------------------------------------------------------------------

class CosteoIn(BaseModel):
    cliente_id: int
    nombre: str = Field(min_length=2, max_length=200)
    datos: dict = Field(default_factory=dict)


def _catalogo(db: DbSession) -> list[dict]:
    return [_cat_out(c) for c in db.scalars(select(CstCatalogoCosto).where(CstCatalogoCosto.activo.is_(True)).order_by(CstCatalogoCosto.id))]


def _servicios_cat(db: DbSession) -> list[dict]:
    return [{"id": s.id, "descripcion": s.descripcion, "tarifa": float(s.tarifa), "hombres": float(s.hombres)}
            for s in db.scalars(select(CstServicio).where(CstServicio.activo.is_(True)))]


def _preparar(db: DbSession, datos: dict) -> dict:
    """Costeo automático: hombres del personal y dotación de la tarifa con las tablas de compras vigentes."""
    return puestos.preparar(datos, [x for x in _catalogo(db) if x["grupo"] == "dotacion_tarifa"])


def _proteger(db: DbSession, actual: Usuario, nuevo: dict, previo: dict | None) -> dict:
    """Lo que el comercial no cambia queda como estaba o como viene del catálogo (contable y compras sí lo cambian)."""
    admin = CONFIGURAR in actual.permisos
    try:
        return puestos.proteger(nuevo, previo, _servicios_cat(db), _catalogo(db), contable=admin or CONTABLE in actual.permisos,
                                precios=admin or PRECIOS in actual.permisos or CONTABLE in actual.permisos)
    except puestos.CosteoInvalido as e:
        raise ApiError(422, str(e)) from e


def _calcular(db: DbSession, c: CstCosteo | None, datos: dict) -> dict:
    if c is not None and c.estado == APROBADO and c.parametros_aprobados:
        # Aprobado: se calcula con lo guardado (dotación incluida) y los parámetros con que se aprobó
        p = c.parametros_aprobados["parametros"]
        rangos = [Rango(**r) for r in c.parametros_aprobados["rangos"]]
        return calculo.calcular(datos, p, rangos)
    p, rangos = configuracion.parametros(db), configuracion.rangos(db)
    return calculo.calcular(_preparar(db, datos), p, rangos)


def _costeo_out(c: CstCosteo, completo: bool = False) -> dict:
    r = c.resultado or {}
    out = {"id": c.id, "cliente": {"id": c.cliente.id, "nombre": c.cliente.nombre, "nit": c.cliente.nit}, "nombre": c.nombre,
           "version": c.version, "estado": c.estado, "meses": r.get("meses"), "tarifa_decreto": r.get("tarifa_decreto"),
           "pct_mfp": (r.get("mfp") or {}).get("pct_total"), "margen_mensual": r.get("margen_mensual"), "pct_margen": r.get("pct_margen"),
           "actualizado_en": c.actualizado_en.isoformat() if c.actualizado_en else "",
           "mfp_id": None}
    if completo:
        out["datos"] = c.datos
        out["resultado"] = r
        out["parametros_aprobados"] = bool(c.parametros_aprobados)
    return out


def _costeo(db: DbSession, costeo_id: int) -> CstCosteo:
    c = db.get(CstCosteo, costeo_id)
    if c is None:
        raise ApiError(404, "Costeo no encontrado")
    return c


@router.get("/costeos", response_model=ApiResponse[list[dict]])
def costeos(db: DbSession, cliente_id: int | None = None, _=Depends(require(VER))):
    q = select(CstCosteo).order_by(CstCosteo.actualizado_en.desc())
    if cliente_id:
        q = q.where(CstCosteo.cliente_id == cliente_id)
    mfps = dict(db.execute(select(CstMfp.costeo_id, CstMfp.id).where(CstMfp.costeo_id.is_not(None))).all())
    out = []
    for c in db.scalars(q):
        x = _costeo_out(c)
        x["mfp_id"] = mfps.get(c.id)
        out.append(x)
    return ok(out)


@router.post("/costeos/calcular", response_model=ApiResponse[dict])
def previsualizar(datos: dict, db: DbSession, _=Depends(require(VER))):
    """Calcula sin guardar (para ver el resultado mientras se edita)."""
    return ok(_calcular(db, None, datos))


@router.post("/costeos", response_model=ApiResponse[dict], status_code=201)
def crear_costeo(data: CosteoIn, request: Request, db: DbSession, actual: Usuario = Depends(require(COSTEAR))):
    if db.get(CstCliente, data.cliente_id) is None:
        raise ApiError(422, "Cliente no encontrado")
    datos = data.datos or {"duracion_meses": 12, "pct_nota_credito": 0, "pct_cupo_inversion": 0, "servicios": [],
                           "personal": [{"nombre": "Guarda", "hombres": 0, "horas_extras": 0, "auxilio_transporte": True,
                                         "auxilios_no_salariales": 0, "rodamiento": 0}],
                           "otros": [], "dotacion_tarifa": [], "dotacion_puesto": [], "horas_bolsa_total": 0, "donaciones": 0,
                           "automatico": True}
    datos = _preparar(db, _proteger(db, actual, datos, {"automatico": True}))
    c = CstCosteo(cliente_id=data.cliente_id, nombre=data.nombre.strip(), datos=datos, creado_por=actual.id)
    c.resultado = _calcular(db, None, datos)
    db.add(c)
    db.flush()
    auditar(db, request, "cst_costeo_creado", actual.id, costeo=c.nombre, cliente_id=c.cliente_id)
    db.commit()
    return ok(_costeo_out(c, True))


@router.get("/costeos/{costeo_id}", response_model=ApiResponse[dict])
def ver_costeo(costeo_id: int, db: DbSession, _=Depends(require(VER))):
    c = _costeo(db, costeo_id)
    out = _costeo_out(c, True)
    out["mfp_id"] = db.scalar(select(CstMfp.id).where(CstMfp.costeo_id == c.id))
    return ok(out)


@router.put("/costeos/{costeo_id}", response_model=ApiResponse[dict])
def guardar_costeo(costeo_id: int, data: CosteoIn, request: Request, db: DbSession,
                   actual: Usuario = Depends(require_alguno(COSTEAR, CONTABLE))):
    c = _costeo(db, costeo_id)
    if c.estado == APROBADO:
        raise ApiError(409, "El costeo está aprobado: cree una nueva versión para modificarlo")
    datos = _preparar(db, _proteger(db, actual, data.datos, c.datos))
    c.cliente_id, c.nombre, c.datos = data.cliente_id, data.nombre.strip(), datos
    c.resultado = _calcular(db, c, datos)
    auditar(db, request, "cst_costeo_guardado", actual.id, costeo=c.nombre, version=c.version,
            margen=round(c.resultado.get("margen_mensual", 0)))
    db.commit()
    return ok(_costeo_out(c, True))


class EstadoIn(BaseModel):
    estado: str


@router.post("/costeos/{costeo_id}/estado", response_model=ApiResponse[dict])
def cambiar_estado(costeo_id: int, data: EstadoIn, request: Request, db: DbSession, actual: Usuario = Depends(require(COSTEAR))):
    c = _costeo(db, costeo_id)
    if data.estado not in ESTADOS:
        raise ApiError(422, "Estado no válido")
    if data.estado == APROBADO:
        if CONFIGURAR not in actual.permisos and GESTIONAR not in actual.permisos:
            raise ApiError(403, "Aprobar un costeo requiere permiso para gestionar MFP o configurar el costeo")
        # Congela los parámetros con que se aprueba: un cambio posterior de parámetros no lo altera
        c.parametros_aprobados = {"parametros": configuracion.parametros(db),
                                  "rangos": [r.__dict__ for r in configuracion.rangos(db)], "fecha": date.today().isoformat()}
        c.resultado = _calcular(db, c, c.datos)
    elif c.estado == APROBADO:
        if db.scalar(select(CstMfp.id).where(CstMfp.costeo_id == c.id)):
            raise ApiError(409, "El costeo ya creó una MFP: no se puede desaprobar")
        c.parametros_aprobados = None
    c.estado = data.estado
    auditar(db, request, "cst_costeo_estado", actual.id, costeo=c.nombre, version=c.version, estado=data.estado)
    db.commit()
    return ok(_costeo_out(c, True))


@router.post("/costeos/{costeo_id}/version", response_model=ApiResponse[dict], status_code=201)
def nueva_version(costeo_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(COSTEAR))):
    c = _costeo(db, costeo_id)
    ultima = db.scalar(select(func.max(CstCosteo.version)).where(CstCosteo.cliente_id == c.cliente_id, CstCosteo.nombre == c.nombre)) or 1
    n = CstCosteo(cliente_id=c.cliente_id, nombre=c.nombre, version=ultima + 1, datos=c.datos, creado_por=actual.id)
    n.resultado = _calcular(db, None, c.datos)
    db.add(n)
    db.flush()
    auditar(db, request, "cst_costeo_version", actual.id, costeo=c.nombre, version=n.version)
    db.commit()
    return ok(_costeo_out(n, True))


@router.delete("/costeos/{costeo_id}", response_model=ApiResponse[dict])
def eliminar_costeo(costeo_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(COSTEAR))):
    c = _costeo(db, costeo_id)
    if c.estado == APROBADO:
        raise ApiError(409, "Un costeo aprobado no se elimina")
    auditar(db, request, "cst_costeo_eliminado", actual.id, costeo=c.nombre, version=c.version)
    db.delete(c)
    db.commit()
    return ok({"eliminado": costeo_id})


class CrearMfpIn(BaseModel):
    numero: str = Field(min_length=1, max_length=30)
    contrato: str = Field(default="", max_length=80)
    fecha_inicio: date


@router.post("/costeos/{costeo_id}/crear-mfp", response_model=ApiResponse[dict], status_code=201)
def crear_mfp(costeo_id: int, data: CrearMfpIn, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    """Con el contrato firmado, el costeo aprobado crea la MFP con sus ítems pactados y sus bolsas."""
    c = _costeo(db, costeo_id)
    if c.estado != APROBADO:
        raise ApiError(409, "Solo un costeo aprobado puede crear la MFP")
    if db.scalar(select(CstMfp.id).where(CstMfp.costeo_id == c.id)):
        raise ApiError(409, "Este costeo ya creó su MFP")
    r = c.resultado
    tipos = {t.codigo: t.id for t in db.scalars(select(CstTipoItem))}
    m = CstMfp(numero=data.numero.strip(), cliente_id=c.cliente_id, contrato=data.contrato.strip(), fecha_inicio=data.fecha_inicio,
               duracion_meses=r["meses"], valor_mensual=r["tarifa_decreto"], pct_comercial=round(r["mfp"]["pct_total"], 5),
               costeo_id=c.id, creado_por=actual.id, notas=f"Creada desde el costeo «{c.nombre}» v{c.version}")
    db.add(m)
    db.flush()

    def item(codigo: str, pactado: float, descripcion: str) -> None:
        if pactado > 0 and codigo in tipos:
            db.add(CstMfpItem(mfp_id=m.id, tipo_id=tipos[codigo], pactado=round(pactado, 2), descripcion=descripcion[:300],
                              nombre=descripcion[:120] if codigo == "OTROS" else ""))

    item("NOTA_CREDITO", r["mfp"]["nota_credito_total"], f"Nota crédito {r['mfp']['pct_nota_credito']:.2%} de la tarifa")
    item("REINVERSION", r["mfp"]["cupo_inversion_vp"], f"Cupo de inversión {r['mfp']['pct_cupo_inversion']:.2%} (valor presente)")
    for o in r.get("otros") or []:
        total = o["mensual"] * r["meses"]
        item(o.get("tipo_item") or "OTROS", total, o.get("nombre", ""))
    # Beneficios: cada uno queda en la MFP con su cantidad (por año o por todo el contrato) y su valor, y se controla por consumo
    for b in c.datos.get("beneficios") or []:
        cantidad = float(b.get("cantidad") or 0)
        if cantidad > 0 and (b.get("nombre") or "").strip() and "BENEFICIO" in tipos:
            db.add(CstMfpItem(mfp_id=m.id, tipo_id=tipos["BENEFICIO"], pactado=round(cantidad, 2), nombre=b["nombre"].strip()[:120],
                              descripcion=(b.get("detalle") or "").strip()[:300],
                              periodo="contrato" if b.get("periodo") == "contrato" else "anio",
                              valor_unitario=round(float(b.get("valor_unitario") or 0), 2)))
    # La bolsa de la MFP es por año de contrato: el total del costeo repartido en los años (el último puede ser parcial).
    # Los costeos de antes traen las horas por año.
    if c.datos.get("horas_bolsa_total") not in (None, ""):
        horas_total = float(c.datos["horas_bolsa_total"])
        item("BOLSA_HORAS", horas_total / max(1, -(-r["meses"] // 12)), f"Horas de obsequio: {horas_total:g} h en todo el contrato")
    else:
        item("BOLSA_HORAS", r["bolsas"]["horas_anuales"], "Horas adicionales de vigilancia por año de contrato")
    item("PUBLICIDAD", r["bolsas"]["publicidad"], "Bolsa de publicidad del contrato")
    item("REPRESENTACION", r["bolsas"]["representacion"], "Reserva de gastos de representación del contrato")
    auditar(db, request, "cst_mfp_desde_costeo", actual.id, costeo=c.nombre, version=c.version, numero=m.numero)
    db.commit()
    # Costeo aprobado + fecha de inicio: arranca el puesto y se avisa a las áreas (un fallo del correo no deshace la MFP)
    db.expire_all()
    avisos = notificaciones.notificar(db, db.get(CstMfp, m.id), actual.id, getattr(request.state, "empresa", None))
    db.commit()
    return ok({"mfp_id": m.id, "avisos": {n.area: n.estado for n in avisos}})


# --- Llenar el costeo con IA a partir de archivos -------------------------------------------------------

def _proponer(db: DbSession, c: CstCosteo, archivos: list[dict], indicaciones: str) -> tuple[dict, dict, ia.Respuesta]:
    ia.cargar(db)
    servicios_cat, catalogo = _servicios_cat(db), _catalogo(db)
    try:
        propuesta, r = ia_costeo.consultar(archivos, indicaciones, servicios_cat, catalogo, c.datos or {})
    except ia.IANoConfigurada as e:
        raise ApiError(503, "La IA no está configurada: el administrador debe poner la clave en Administración → Inteligencia artificial.",
                       "ASISTENTE_NO_CONFIGURADO") from e
    except ia.IAError as e:
        raise ApiError(e.status, e.mensaje, e.codigo) from e
    datos, informe = ia_costeo.aplicar(c.datos or {}, propuesta, servicios_cat, catalogo)
    return datos, informe, r


@router.post("/costeos/{costeo_id}/ia", response_model=ApiResponse[dict], dependencies=[Depends(limitar("costeo_ia", 5, 60))])
async def llenar_con_ia(costeo_id: int, request: Request, db: DbSession, archivos: list[UploadFile] = File(...),
                        indicaciones: str = Form("", max_length=2000), actual: Usuario = Depends(require(COSTEAR))):
    """Propuesta del costeo leída de 1 a 6 archivos. No guarda nada: ni el costeo ni los archivos (se leen en memoria)."""
    c = _costeo(db, costeo_id)
    if c.estado == APROBADO:
        raise ApiError(409, "El costeo está aprobado: cree una nueva versión para llenarla con IA")
    if not 1 <= len(archivos) <= ia_costeo.MAX_ARCHIVOS:
        raise ApiError(422, f"Suba entre 1 y {ia_costeo.MAX_ARCHIVOS} archivos")
    limite = get_settings().max_upload_mb * 1024 * 1024
    leidos, advertencias = [], []
    for archivo in archivos:
        nombre = (archivo.filename or "archivo")[:200]
        try:
            contenido = await archivo.read(limite + 1)
        finally:
            await archivo.close()  # el temporal de la subida se borra aquí: no se guarda ningún archivo
        if len(contenido) > limite:
            raise ApiError(413, f"«{nombre}» supera el tamaño máximo de {get_settings().max_upload_mb} MB")
        try:
            a = await run_in_threadpool(ia_costeo.leer, nombre, contenido)
        except ia_costeo.ArchivoInvalido as e:
            raise ApiError(422, str(e)) from e
        del contenido
        advertencias += [f"{nombre}: {x}" for x in a.pop("advertencias", [])]
        leidos.append(a)

    datos, informe, r = await run_in_threadpool(_proponer, db, c, leidos, indicaciones)
    # El texto leído de los documentos vuelve al navegador (no se guarda aquí): con él la IA sigue la conversación
    documentos = [{"nombre": a["nombre"], "texto": a["texto"]} for a in leidos if "texto" in a]
    if informe.get("lectura_adjuntos"):
        documentos.append({"nombre": "Lo que la IA leyó de los adjuntos escaneados", "texto": informe["lectura_adjuntos"]})
    del leidos
    informe["advertencias"] = advertencias
    informe["modelo"] = r.modelo
    # Auditoría: nombres de los archivos, modelo y consumo; nunca su contenido
    auditar(db, request, "cst_costeo_ia", actual.id, costeo=c.nombre, archivos=[(a.filename or "")[:120] for a in archivos],
            modelo=r.modelo, tokens_entrada=r.tokens_entrada, tokens_salida=r.tokens_salida)
    db.commit()
    return ok({"datos": datos, "informe": informe, "documentos": documentos})


class MensajeIA(BaseModel):
    rol: Literal["usuario", "asistente"]
    texto: str = Field(min_length=1, max_length=4000)


class DocumentoIA(BaseModel):
    nombre: str = Field(max_length=200)
    texto: str = Field(max_length=ia_costeo.MAX_CARACTERES_ARCHIVO + 1000)


class ChatIA(BaseModel):
    """Conversación sobre la propuesta: la propuesta actual (datos e informe), el texto de los documentos y los mensajes."""
    mensajes: list[MensajeIA] = Field(min_length=1, max_length=40)
    datos: dict
    informe: dict = Field(default_factory=dict)
    documentos: list[DocumentoIA] = Field(default_factory=list, max_length=ia_costeo.MAX_ARCHIVOS + 1)

    @model_validator(mode="after")
    def _ultimo_es_usuario(self) -> "ChatIA":
        if self.mensajes[-1].rol != "usuario":
            raise ValueError("El último mensaje debe ser del usuario")
        if sum(len(m.texto) for m in self.mensajes) > 40_000:
            raise ValueError("La conversación es demasiado larga: vuelva a analizar los archivos")
        return self


@router.post("/costeos/{costeo_id}/ia/chat", response_model=ApiResponse[dict], dependencies=[Depends(limitar("costeo_ia", 10, 60))])
def chat_con_ia(costeo_id: int, data: ChatIA, request: Request, db: DbSession, actual: Usuario = Depends(require(COSTEAR))):
    """El comercial le contesta a la IA (faltantes, conflictos, cambios) y la IA devuelve la propuesta actualizada. No guarda nada."""
    c = _costeo(db, costeo_id)
    if c.estado == APROBADO:
        raise ApiError(409, "El costeo está aprobado: cree una nueva versión para llenarla con IA")
    ia.cargar(db)
    servicios_cat, catalogo = _servicios_cat(db), _catalogo(db)
    mensajes = [{"role": "user" if m.rol == "usuario" else "assistant", "content": m.texto} for m in data.mensajes]
    try:
        propuesta, r = ia_costeo.conversar([d.model_dump() for d in data.documentos], ia_costeo.para_modelo(data.datos, data.informe),
                                           mensajes, servicios_cat, catalogo, c.datos or {})
    except ia.IANoConfigurada as e:
        raise ApiError(503, "La IA no está configurada: el administrador debe poner la clave en Administración → Inteligencia artificial.",
                       "ASISTENTE_NO_CONFIGURADO") from e
    except ia.IAError as e:
        raise ApiError(e.status, e.mensaje, e.codigo) from e
    datos, informe = ia_costeo.aplicar(c.datos or {}, propuesta, servicios_cat, catalogo, completo=True)
    informe["advertencias"] = data.informe.get("advertencias") or []
    informe["modelo"] = r.modelo
    # Auditoría: el mensaje recortado, el modelo y el consumo
    auditar(db, request, "cst_costeo_ia_chat", actual.id, costeo=c.nombre, mensaje=data.mensajes[-1].texto[:200], modelo=r.modelo,
            tokens_entrada=r.tokens_entrada, tokens_salida=r.tokens_salida)
    db.commit()
    return ok({"datos": datos, "informe": informe})
