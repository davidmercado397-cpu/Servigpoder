from datetime import date, datetime, time
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Orm(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ParametrosIn(BaseModel):
    hora_inicio_nocturna: int = Field(ge=0, le=23)


class ParametrosOut(Orm):
    hora_inicio_nocturna: int
    actualizado_en: datetime | None = None


class TurnoIn(BaseModel):
    codigo: str = Field(min_length=1, max_length=8)
    nombre: str = Field(min_length=1, max_length=80)
    hora_inicio: time
    hora_fin: time  # informativa: las horas las definen ordinarias y extras
    horas_ordinarias: Decimal = Field(ge=0, le=24, decimal_places=2)
    horas_extras: Decimal = Field(ge=0, le=24, decimal_places=2)
    remunerado: bool = True
    incapacidad: bool = False

    @field_validator("codigo")
    @classmethod
    def _codigo(cls, v: str) -> str:
        v = v.strip().upper()
        if not v or any(c.isspace() for c in v):
            raise ValueError("El código no puede tener espacios")
        return v

    @field_validator("horas_extras")
    @classmethod
    def _total(cls, v: Decimal, info) -> Decimal:
        if (info.data.get("horas_ordinarias") or 0) + v > 24:
            raise ValueError("Las horas ordinarias más las extras no pueden pasar de 24")
        return v


class TurnoOut(Orm):
    id: int
    codigo: str
    nombre: str
    hora_inicio: time
    hora_fin: time
    horas_ordinarias: float
    horas_extras: float
    remunerado: bool
    incapacidad: bool
    activo: bool
    clase: str = ""


class TurnoDetalle(TurnoOut):
    matriz: dict[str, dict[str, float]]


class VistaPreviaIn(BaseModel):
    hora_inicio: time
    horas_ordinarias: Decimal = Field(ge=0, le=24)
    horas_extras: Decimal = Field(ge=0, le=24)
    incapacidad: bool = False


class FestivoIn(BaseModel):
    fecha: date
    descripcion: str = Field(default="", max_length=120)


class FestivoOut(BaseModel):
    fecha: date
    descripcion: str
    origen: str  # nacional, quitado, manual
    ajuste_id: int | None
    vigente: bool


class PeriodoIn(BaseModel):
    anio: int = Field(ge=2020, le=2100)
    mes: int = Field(ge=1, le=12)
    quincena: int = Field(ge=1, le=2)


class PeriodoOut(Orm):
    id: int
    anio: int
    mes: int
    quincena: int
    desde: date
    hasta: date
    estado: str
    archivo: str | None
    advertencias: list[str] = []
    cargado_en: datetime | None
    calculado_en: datetime | None
    cerrado_en: datetime | None
    creado_en: datetime | None
    empleados: int = 0


class ResultadoOut(BaseModel):
    empleado_id: int
    documento: str
    nombre: str
    cargo: str
    horas: dict[str, float]
    dias: dict[str, int]
    total_horas: float


class DiaOut(BaseModel):
    fecha: date
    codigo: str
    turno: str
    tipo_dia: str
    clase: str
    horas: dict[str, float]


class DetalleEmpleado(BaseModel):
    empleado: ResultadoOut
    dias: list[DiaOut]


class CargaOut(BaseModel):
    periodo: PeriodoOut
    empleados: int
    dias: int
    fechas: int
    advertencias: list[str]


class EmpleadoOut(BaseModel):
    id: int
    documento: str
    nombre: str
    cargo: str
    quincenas: int
    ultima: str | None
