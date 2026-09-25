from pydantic import BaseModel, ConfigDict, Field


class LoginIn(BaseModel):
    username: str
    password: str


class PermisoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    codigo: str
    modulo: str
    descripcion: str


class RolResumen(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str


class RolOut(RolResumen):
    descripcion: str
    permisos: list[str]


class RolIn(BaseModel):
    nombre: str = Field(min_length=2, max_length=60)
    descripcion: str = ""
    permisos: list[str] = []


class UsuarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    nombre: str
    email: str | None
    activo: bool
    roles: list[RolResumen]


class SesionOut(UsuarioOut):
    permisos: list[str]


class UsuarioCrear(BaseModel):
    username: str = Field(min_length=3, max_length=60)
    nombre: str = Field(min_length=2, max_length=120)
    email: str | None = None
    password: str = Field(min_length=8)
    roles: list[int] = []


class UsuarioEditar(BaseModel):
    nombre: str | None = Field(default=None, min_length=2, max_length=120)
    email: str | None = None
    password: str | None = Field(default=None, min_length=8)
    activo: bool | None = None
    roles: list[int] | None = None
