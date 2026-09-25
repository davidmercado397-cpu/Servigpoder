from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://capacidad:capacidad@localhost:5432/capacidad"
    secret_key: str = "dev-secret-key-change-me"
    access_token_minutes: int = 720
    cookie_secure: bool = False
    cookie_name: str = "sesion"

    admin_username: str = "admin"
    admin_password: str = "admin"
    admin_nombre: str = "Administrador"


@lru_cache
def get_settings() -> Settings:
    return Settings()
