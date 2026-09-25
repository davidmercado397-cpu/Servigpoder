from datetime import date, datetime, time
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Orm(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Catálogos ---------------------------------------------------------------

class FranjaHorario(Orm):
    inicio: time
    fin: time


class TurnoOut(Orm):
    codigo: str
    descripcion: str
    clase: str
    franjas: list[FranjaHorario]


class NovedadOut(Orm):
    codigo: str
    descripcion: str
    requiere_cubrimiento: bool


class NovedadIn(BaseModel):
    codigo: str = Field(min_length=1, max_length=40)
    descripcion: str = Field(min_length=1, max_length=200)
    requiere_cubrimiento: bool = True


# --- Maestros ----------------------------------------------------------------

class UbicacionOut(Orm):
    id: int
    codigo: str
    nombre: str
    nit: str | None
    ciudad: str | None


class PuestoOut(Orm):
    id: int
    codigo: str
    descripcion: str
    tipo: str
    excluido: bool
    activo: bool
    ubicacion: UbicacionOut


class PuestoEditar(BaseModel):
    descripcion: str | None = Field(default=None, max_length=200)
    excluido: bool | None = None
    activo: bool | None = None


class EquivalenciaOut(Orm):
    codigo_siesa: str
    origen: str
    puesto: PuestoOut


class EquivalenciaIn(BaseModel):
    codigo_siesa: str = Field(min_length=1, max_length=40)
    puesto_id: int


class PorAclarar(BaseModel):
    codigo_siesa: str
    descripcion: str
    filas: int
    motivo: str  # sin_equivalencia | aproximada
    puesto_sugerido: PuestoOut | None = None


# --- Matriz comercial --------------------------------------------------------

class PeriodoOut(Orm):
    id: int
    anio: int
    mes: int
    estado: str
    proyectado_desde_id: int | None
    creado_en: datetime


class ResumenPeriodo(PeriodoOut):
    puestos: int
    hombres: Decimal
    requieren_revision: int
    excluidos: int


class FranjaIn(BaseModel):
    dias: int = Field(ge=1, le=127)  # máscara: lunes = 1 ... domingo = 64
    inicio: time
    fin: time
    cantidad: int = Field(default=1, ge=1, le=50)


class FranjaOut(FranjaIn, Orm):
    id: int


class ExcepcionIn(BaseModel):
    fecha: date
    sin_servicio: bool = False
    inicio: time | None = None
    fin: time | None = None
    cantidad: int = Field(default=1, ge=1, le=50)
    observacion: str = Field(default="", max_length=300)

    @model_validator(mode="after")
    def _franja(self) -> "ExcepcionIn":
        if not self.sin_servicio and (self.inicio is None or self.fin is None):
            raise ValueError("Indique inicio y fin, o marque 'sin servicio'")
        return self


class ExcepcionOut(ExcepcionIn, Orm):
    id: int


class MatrizPuestoOut(Orm):
    id: int
    puesto: PuestoOut
    hombres: Decimal
    secuencia: str
    jornada: str
    incluye_festivos: bool
    requiere_revision: bool
    nota: str
    franjas: list[FranjaOut]
    excepciones: list[ExcepcionOut]


class MatrizPuestoEditar(BaseModel):
    hombres: Decimal | None = Field(default=None, ge=0, le=500)
    secuencia: str | None = Field(default=None, max_length=80)
    incluye_festivos: bool | None = None
    requiere_revision: bool | None = None
    nota: str | None = Field(default=None, max_length=2000)
    franjas: list[FranjaIn] | None = Field(default=None, max_length=20)


class ProyectarIn(BaseModel):
    copiar_excepciones: bool = False


class EstadoIn(BaseModel):
    estado: str = Field(pattern="^(borrador|aprobado|cerrado)$")


class ImportacionOut(BaseModel):
    periodo_id: int
    ubicaciones: int
    puestos: int
    requieren_revision: int
    excluidos: int
    avisos: list[str]


class DiaRequerido(BaseModel):
    fecha: date
    festivo: str | None
    franjas: list[FranjaHorario]
    horas: float


# --- Programación ------------------------------------------------------------

class CargaOut(Orm):
    id: int
    archivo: str
    compania: str
    desde: date
    hasta: date
    anio: int
    mes: int
    cargado_en: datetime
    resumen: dict
