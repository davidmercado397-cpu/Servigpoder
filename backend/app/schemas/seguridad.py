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
    mfa_activo: bool = False
    debe_cambiar_password: bool = False
    # Desarrollos marcados en cada empresa: {"sera": ["liquidador"], …}
    accesos: dict[str, list[str]] = {}

    @field_validator("accesos", mode="before")
    @classmethod
    def _accesos(cls, v):
        if isinstance(v, dict):
            return v
        out: dict[str, list[str]] = {}
        for x in v or []:
            out.setdefault(x.empresa.codigo, []).append(x.app)
        return {k: sorted(apps) for k, apps in out.items()}


class EmpresaSesion(BaseModel):
    codigo: str
    nombre: str
    apps: list[str]  # desarrollos a los que entra en esta empresa


class SesionOut(UsuarioOut):
    permisos: list[str]
    empresas: list[EmpresaSesion] = []
    empresa_actual: str | None = None


class UsuarioCrear(BaseModel):
    username: str = Field(min_length=3, max_length=60, pattern=r"^[A-Za-z0-9._-]+$")
    nombre: str = Field(min_length=2, max_length=120)
    email: EmailStr | None = None
    password: str
    roles: list[int] = Field(default=[], max_length=20)
    accesos: dict[str, list[str]] = {}

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
    accesos: dict[str, list[str]] | None = None

    @field_validator("password")
    @classmethod
    def _pwd(cls, v: str | None) -> str | None:
        return validar_password(v) if v else None


class EmpresaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    codigo: str
    nombre: str
    esquema: str
    activa: bool
    apps: list[str]
    usuarios: int = 0

    @field_validator("apps", mode="before")
    @classmethod
    def _apps(cls, v):
        return sorted(x if isinstance(x, str) else x.app for x in v or [])


class EmpresaCrear(BaseModel):
    codigo: str = Field(min_length=2, max_length=20, pattern=r"^[a-z][a-z0-9]{1,19}$",
                        description="Minúsculas y números, sin espacios (p. ej. sera). Define el esquema emp_<codigo>; no se puede cambiar.")
    nombre: str = Field(min_length=2, max_length=120)
    apps: list[str] = Field(default=[], max_length=20)


class EmpresaEditar(BaseModel):
    nombre: str | None = Field(default=None, min_length=2, max_length=120)
    activa: bool | None = None
    apps: list[str] | None = Field(default=None, max_length=20)


class ElegirEmpresa(BaseModel):
    codigo: str = Field(min_length=2, max_length=20)
