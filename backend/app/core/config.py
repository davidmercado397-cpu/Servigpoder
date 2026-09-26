from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

API_VERSION = "v1"
CLAVES_INSEGURAS = {"", "dev-secret-key-change-me", "cambiar-por-una-clave-larga-y-aleatoria"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # development | production
    environment: str = "development"

    database_url: str = "postgresql+psycopg://capacidad:capacidad@localhost:5432/capacidad"
    secret_key: str = "dev-secret-key-change-me"
    cookie_secure: bool = False
    cookie_name: str = "sesion"

    # Autenticación (OWASP ASVS V2/V3)
    mfa_obligatorio: bool = True  # verificación en dos pasos con app Authenticator para todos
    mfa_emisor: str = "Servigpoder"  # nombre que aparece en la app Authenticator
    sesion_inactividad_min: int = 30  # la sesión se cierra tras este tiempo sin actividad
    sesion_max_horas: int = 12  # duración máxima de una sesión aunque haya actividad
    preauth_minutos: int = 5  # tiempo para completar el segundo paso tras la contraseña

    # Hosts aceptados en la cabecera Host (coma separada). "*" = cualquiera.
    allowed_hosts: str = "*"
    max_upload_mb: int = 15

    # Rate limit (peticiones por ventana en segundos)
    rate_limit_global: int = 300  # por IP y minuto, toda la API
    login_max_intentos: int = 5  # fallidos por usuario antes de bloquear
    login_bloqueo_minutos: int = 15

    # Asistente de IA: cualquier proveedor compatible con OpenAI (por defecto OpenRouter)
    ia_api_key: str = ""
    ia_base_url: str = "https://openrouter.ai/api/v1"
    ia_modelo: str = "anthropic/claude-opus-5"  # cualquier modelo de openrouter.ai/models
    # En OpenRouter: solo proveedores con retención cero de datos (además de no entrenar con ellos)
    ia_zdr: bool = True
    # Aprobado por protección de datos: nombres y cédulas pueden enviarse al proveedor de IA
    asistente_datos_personales: bool = True
    asistente_max_diario: int = 100  # preguntas por usuario y día

    admin_username: str = "admin"
    admin_password: str = "admin"
    admin_nombre: str = "Administrador"

    @property
    def produccion(self) -> bool:
        return self.environment.lower() == "production"

    @model_validator(mode="after")
    def _validar_produccion(self) -> "Settings":
        # OWASP A02/A05: en producción no se aceptan claves por defecto ni débiles
        if self.produccion:
            if self.secret_key in CLAVES_INSEGURAS or len(self.secret_key) < 32:
                raise ValueError("SECRET_KEY debe tener al menos 32 caracteres aleatorios en producción")
            if len(self.admin_password) < 12 or self.admin_password in {"admin", "cambiar-esta-clave"}:
                raise ValueError("ADMIN_PASSWORD debe tener al menos 12 caracteres en producción")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
