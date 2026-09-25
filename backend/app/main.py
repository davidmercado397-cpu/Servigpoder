import logging

from fastapi import APIRouter, FastAPI

from app.api.routes import auth, catalogos, maestros, matriz, programacion, roles, usuarios
from app.core.config import API_VERSION, get_settings
from app.core.middleware import registrar_middlewares
from app.core.respuestas import ApiResponse, ok, registrar_manejadores

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

settings = get_settings()
# OWASP A05: la documentación interactiva solo en desarrollo
docs = not settings.produccion

app = FastAPI(
    title="Capacidad Operativa Servigpoder",
    version="0.2.0",
    docs_url="/api/docs" if docs else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if docs else None,
)
registrar_manejadores(app)
registrar_middlewares(app)

api = APIRouter(prefix="/api")
for modulo in (auth, usuarios, roles, catalogos, maestros, matriz, programacion):
    api.include_router(modulo.router)


@api.get("/health", response_model=ApiResponse[dict], tags=["sistema"])
def health():
    return ok({"status": "ok", "api_version": API_VERSION})


app.include_router(api)
