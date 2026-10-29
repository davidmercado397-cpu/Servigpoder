"""Novedades manuales de cada nómina (mayor y menor valor pagado, horas extras y recargos pendientes, otros devengos y
deducciones). Cada cambio recalcula la nómina; con la nómina cerrada no se pueden cambiar."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Request, UploadFile
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select

from app.api.deps import DbSession, require
from app.core.archivos import leer_xlsx
from app.core.auditoria import auditar
from app.core.rate_limit import limitar
from app.core.respuestas import ApiError, ApiResponse, ok
from app.models import Usuario
from app.apps.liquidador.models import AUXILIOS_VARIABLES, CERRADA, NOVEDADES_HORAS, OTRO_DEVENGO, LiqNovedad, LiqPeriodo, LiqResultado
from app.apps.liquidador.services import calculo, novedades
from app.apps.liquidador.services.nomina import CONCEPTOS_PAGO
from app.apps.liquidador.services.personal import ErrorArchivo, Indice

router = APIRouter(tags=["liquidador: novedades de nómina"])
VER = "liquidador.nomina.ver"
GESTIONAR = "liquidador.nomina.gestionar"


class NovedadIn(BaseModel):
    documento: str = Field(min_length=1, max_length=32)
    tipo: str = Field(pattern="^(" + "|".join(novedades.TIPOS) + ")$")
    descripcion: str = Field(min_length=1, max_length=200)
    horas: dict[str, float] = Field(default_factory=dict)
    fecha_causacion: date | None = None
    valor: Decimal | None = Field(None, gt=0, le=100_000_000)
    salarial: bool = True
    nomina_origen: str | None = Field(None, max_length=80)

    @model_validator(mode="after")
    def _coherente(self):
        horas = {c: h for c, h in self.horas.items() if h}
        if any(c not in CONCEPTOS_PAGO for c in horas) or any(h < 0 or h > 400 for h in horas.values()):
            raise ValueError("Horas inválidas")
        if self.tipo in NOVEDADES_HORAS:
            if not horas and self.valor is None:
                raise ValueError("Escriba las horas de cada concepto (o el valor)")
        elif self.valor is None:
            raise ValueError("Escriba el valor")
        self.horas = horas if self.tipo in NOVEDADES_HORAS else {}
        return self


def _periodo_abierto(db, periodo_id: int) -> LiqPeriodo:
    p = db.get(LiqPeriodo, periodo_id)
    if p is None:
        raise ApiError(404, "Nómina no encontrada")
    if p.estado == CERRADA:
        raise ApiError(409, "La nómina está cerrada. Reábrala para registrar novedades.", "PERIODO_CERRADO")
    return p


def _out(x: LiqNovedad, calculadas: dict[int, dict]) -> dict:
    c = calculadas.get(x.id, {})
    return {"id": x.id, "empleado_id": x.empleado_id, "documento": x.empleado.documento, "nombre": x.empleado.nombre, "tipo": x.tipo,
            "descripcion": x.descripcion, "horas": x.horas or {}, "fecha_causacion": x.fecha_causacion.isoformat() if x.fecha_causacion else None,
            "valor_escrito": float(x.valor) if x.valor is not None else None, "salarial": x.salarial, "nomina_origen": x.nomina_origen,
            "origen_registro": x.origen_registro, "valor": c.get("valor"), "calculo": c.get("calculo"), "deduccion": c.get("deduccion"),
            "observacion": c.get("observacion", "")}


def _calculadas(db, periodo_id: int) -> dict[int, dict]:
    out = {}
    for n in db.scalars(select(LiqResultado.nomina).where(LiqResultado.periodo_id == periodo_id)):
        for x in (n or {}).get("novedades", []):
            out[x["id"]] = x
        for x in (n or {}).get("auxilios", []):  # los auxilios variables se aplican con los auxilios no prestacionales
            if str(x["id"]).startswith("nov-"):
                out[int(str(x["id"])[4:])] = {**x, "deduccion": False, "salarial": False}
    return out


@router.get("/periodos/{periodo_id}/novedades", response_model=ApiResponse[list[dict]])
def listar(periodo_id: int, db: DbSession, _=Depends(require(VER))):
    if db.get(LiqPeriodo, periodo_id) is None:
        raise ApiError(404, "Nómina no encontrada")
    lista = db.scalars(select(LiqNovedad).where(LiqNovedad.periodo_id == periodo_id).order_by(LiqNovedad.id)).all()
    calc = _calculadas(db, periodo_id)
    return ok([_out(x, calc) for x in sorted(lista, key=lambda x: (x.empleado.nombre, x.id))])


def _guardar(db, p: LiqPeriodo, x: LiqNovedad, data: NovedadIn) -> None:
    en_nomina = [r.empleado for r in db.scalars(select(LiqResultado).where(LiqResultado.periodo_id == p.id))]
    e = Indice(en_nomina).buscar(data.documento.strip())
    if e is None:
        raise ApiError(409, f"El documento {data.documento.strip()} no está en esta nómina", "NO_ESTA_EN_NOMINA")
    if data.fecha_causacion and data.fecha_causacion > p.hasta:
        raise ApiError(422, "La fecha en que se causaron las horas no puede ser posterior a esta nómina")
    x.empleado_id, x.tipo, x.descripcion = e.id, data.tipo, data.descripcion.strip()
    x.horas, x.valor = data.horas, data.valor
    x.fecha_causacion = data.fecha_causacion if data.tipo in NOVEDADES_HORAS else None
    x.salarial = data.salarial if data.tipo == OTRO_DEVENGO else data.tipo not in AUXILIOS_VARIABLES
    x.nomina_origen = (data.nomina_origen or "").strip() or None


@router.post("/periodos/{periodo_id}/novedades", response_model=ApiResponse[dict], status_code=201)
def crear(periodo_id: int, data: NovedadIn, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    p = _periodo_abierto(db, periodo_id)
    x = LiqNovedad(periodo_id=p.id, origen_registro="manual", creado_por=actual.id)
    _guardar(db, p, x, data)
    db.add(x)
    db.flush()
    calculo.calcular(db, p, con_hermanas=False)
    auditar(db, request, "liq_novedad_creada", actual.id, periodo=p.etiqueta, novedad_id=x.id, tipo=x.tipo)
    db.commit()
    return ok(_out(x, _calculadas(db, p.id)), aviso="Novedad registrada y nómina recalculada.")


@router.put("/novedades/{novedad_id}", response_model=ApiResponse[dict])
def editar(novedad_id: int, data: NovedadIn, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    x = db.get(LiqNovedad, novedad_id)
    if x is None:
        raise ApiError(404, "Novedad no encontrada")
    p = _periodo_abierto(db, x.periodo_id)
    _guardar(db, p, x, data)
    db.flush()
    calculo.calcular(db, p, con_hermanas=False)
    auditar(db, request, "liq_novedad_editada", actual.id, periodo=p.etiqueta, novedad_id=x.id, tipo=x.tipo)
    db.commit()
    return ok(_out(x, _calculadas(db, p.id)))


@router.delete("/novedades/{novedad_id}", response_model=ApiResponse[dict])
def eliminar(novedad_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    x = db.get(LiqNovedad, novedad_id)
    if x is None:
        raise ApiError(404, "Novedad no encontrada")
    p = _periodo_abierto(db, x.periodo_id)
    auditar(db, request, "liq_novedad_eliminada", actual.id, periodo=p.etiqueta, novedad_id=x.id, tipo=x.tipo)
    db.delete(x)
    db.flush()
    calculo.calcular(db, p, con_hermanas=False)
    db.commit()
    return ok({"eliminada": novedad_id})


@router.get("/periodos/{periodo_id}/novedades/plantilla")
def descargar_plantilla(periodo_id: int, db: DbSession, _=Depends(require(VER))):
    from app.apps.liquidador.routes.periodos import _archivo

    p = db.get(LiqPeriodo, periodo_id)
    if p is None:
        raise ApiError(404, "Nómina no encontrada")
    return _archivo(*novedades.plantilla(p))


@router.post("/periodos/{periodo_id}/novedades/importar", response_model=ApiResponse[dict],
             dependencies=[Depends(limitar("liq_novedades", 10, 60))])
async def importar(periodo_id: int, request: Request, db: DbSession, archivo: UploadFile = File(...),
                   actual: Usuario = Depends(require(GESTIONAR))):
    """Carga novedades desde la plantilla. Reemplaza las cargadas antes por Excel; el archivo no se guarda."""
    p = _periodo_abierto(db, periodo_id)
    contenido = await leer_xlsx(archivo)
    try:
        res = novedades.importar(db, p, contenido, actual.id)
    except ErrorArchivo as e:
        db.rollback()
        raise ApiError(422, str(e), "EXCEL_INVALIDO") from e
    calculo.calcular(db, p, con_hermanas=False)
    auditar(db, request, "liq_novedades_importadas", actual.id, periodo=p.etiqueta, archivo=(archivo.filename or "")[:255],
            cargadas=res["cargadas"], reemplazadas=res["reemplazadas"], hallazgos=len(res["hallazgos"]))
    db.commit()
    return ok(res)
