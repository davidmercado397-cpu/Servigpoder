from datetime import date, datetime, time
from decimal import Decimal

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
    quincena: int = Field(ge=0, le=2, description="1: días 1-15 · 2: del 16 al fin de mes · 0: mensual (mes completo)")


class PeriodoOut(Orm):
    id: int
    anio: int
    mes: int
    quincena: int
    tipo: str  # Q1, Q2 o Mensual
    etiqueta: str
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
    # Solo con el permiso liquidador.nomina.ver
    devengado: float | None = None
    neto: float | None = None
    nomina: dict | None = None


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
    salario: float | None = None  # vacío = salario mínimo (solo con el permiso liquidador.nomina.ver)


class TarifaIn(BaseModel):
    vigente_desde: date
    smlmv: Decimal = Field(gt=0, le=100_000_000)
    auxilio_transporte: Decimal = Field(ge=0, le=10_000_000)
    horas_mes: int = Field(ge=100, le=300)
    salud_pct: Decimal = Field(ge=0, le=100)
    pension_pct: Decimal = Field(ge=0, le=100)
    porcentajes: dict[str, Decimal]
    nota: str = Field("", max_length=300)

    @field_validator("porcentajes")
    @classmethod
    def _porcentajes(cls, v: dict[str, Decimal]) -> dict[str, Decimal]:
        from app.apps.liquidador.services.nomina import CONCEPTOS_PAGO

        faltan = [c for c in CONCEPTOS_PAGO if c not in v]
        if faltan or set(v) - set(CONCEPTOS_PAGO):
            raise ValueError("Debe indicar el % de los 11 conceptos de recargos y horas extras")
        if any(x < 0 or x > 500 for x in v.values()):
            raise ValueError("Cada % debe estar entre 0 y 500")
        return v


class TarifaOut(Orm):
    id: int
    vigente_desde: date
    smlmv: float
    auxilio_transporte: float
    horas_mes: int
    salud_pct: float
    pension_pct: float
    porcentajes: dict[str, float]
    nota: str
    actualizado_en: datetime | None


class DescuentoIn(BaseModel):
    documento: str = Field(min_length=1, max_length=32)
    tipo: Literal["prestamo", "embargo"]
    descripcion: str = Field(min_length=1, max_length=200)
    valor_mensual: Decimal | None = Field(None, gt=0, le=100_000_000)
    porcentaje: Decimal | None = Field(None, gt=0, le=100)
    monto_total: Decimal | None = Field(None, gt=0, le=1_000_000_000)
    desde: date
    hasta: date | None = None
    activo: bool = True

    @model_validator(mode="after")
    def _forma(self):
        if (self.valor_mensual is None) == (self.porcentaje is None):
            raise ValueError("Indique un valor mensual o un porcentaje (solo uno de los dos)")
        if self.hasta and self.hasta < self.desde:
            raise ValueError("La fecha final no puede ser anterior a la inicial")
        return self


class DescuentoOut(BaseModel):
    id: int
    empleado_id: int
    documento: str
    nombre: str
    tipo: str
    descripcion: str
    valor_mensual: float | None
    porcentaje: float | None
    monto_total: float | None
    desde: date
    hasta: date | None
    activo: bool
    descontado: float
    saldo: float | None


class SalarioIn(BaseModel):
    salario: Decimal | None = Field(None, gt=0, le=100_000_000)  # vacío = salario mínimo
