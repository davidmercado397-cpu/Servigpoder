from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.f1 import FranjaOut, Orm, PuestoOut


class AnalisisIn(BaseModel):
    carga_id: int | None = None
    anio: int | None = Field(default=None, ge=2020, le=2100)
    mes: int | None = Field(default=None, ge=1, le=12)


class AnalisisOut(Orm):
    id: int
    carga_id: int
    periodo_id: int
    generado_en: datetime
    resumen: dict
    desactualizado: bool = False
    motivo_desactualizado: str | None = None


class MesDisponible(BaseModel):
    anio: int
    mes: int
    carga_id: int
    desde: date
    hasta: date
    analisis_id: int | None
    tiene_matriz: bool


class PuestoAnalisisOut(Orm):
    puesto: PuestoOut
    hombres: Decimal
    fijos: int
    personas: int
    horas_requeridas: Decimal
    horas_programadas: Decimal
    horas_descubiertas: Decimal
    horas_exceso: Decimal
    dias_hueco: int
    dias_exceso: int
    estado: str


class DiaAnalisisOut(Orm):
    fecha: date
    horas_requeridas: Decimal
    horas_programadas: Decimal
    horas_descubiertas: Decimal
    horas_exceso: Decimal
    estado: str
    detalle: list[dict]


class PersonaPuesto(BaseModel):
    cedula: str
    nombre: str
    titular: bool
    puesto_titular: str | None
    dias: dict[str, str]  # fecha ISO → código SIESA
    clases: dict[str, str]  # fecha ISO → trabajo | descanso | novedad


class DetallePuesto(BaseModel):
    resumen: PuestoAnalisisOut
    franjas: list[FranjaOut]
    incluye_festivos: bool | None
    festivos: dict[str, str]
    dias: list[DiaAnalisisOut]
    personas: list[PersonaPuesto]
