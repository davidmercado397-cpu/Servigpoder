from fastapi import APIRouter, FastAPI

from app.api.routes import auth, roles, usuarios

app = FastAPI(title="Capacidad Operativa Servigpoder", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")

api = APIRouter(prefix="/api")
api.include_router(auth.router)
api.include_router(usuarios.router)
api.include_router(roles.router)


@api.get("/health", tags=["sistema"])
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api)
