from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.security import validar_password


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=200)


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
    descripcion: str = Field(default="", max_length=200)
    permisos: list[str] = Field(default=[], max_length=100)


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
    username: str = Field(min_length=3, max_length=60, pattern=r"^[A-Za-z0-9._-]+$")
    nombre: str = Field(min_length=2, max_length=120)
    email: EmailStr | None = None
    password: str
    roles: list[int] = Field(default=[], max_length=20)

    @field_validator("password")
    @classmethod
    def _pwd(cls, v: str) -> str:
        return validar_password(v)


class UsuarioEditar(BaseModel):
    nombre: str | None = Field(default=None, min_length=2, max_length=120)
    email: EmailStr | None = None
    password: str | None = None
    activo: bool | None = None
    roles: list[int] | None = Field(default=None, max_length=20)

    @field_validator("password")
    @classmethod
    def _pwd(cls, v: str | None) -> str | None:
        return validar_password(v) if v else None
