"""Rutas del asistente de IA, comunes a todas las apps.

Cada app entrega su permiso, su función `responder` (instrucciones y herramientas propias) y,
opcionalmente, cómo describir la pantalla desde donde se pregunta. Límites, validaciones,
auditoría y manejo de errores del proveedor son los mismos para todas.
"""

from collections.abc import Callable
from datetime import datetime, time, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import DbSession, require
from app.core import ia
from app.core.auditoria import auditar
from app.core.config import get_settings
from app.core.rate_limit import limitar
from app.core.respuestas import ApiError, ApiResponse, ok
from app.models import Auditoria, Usuario

ZONA = ZoneInfo("America/Bogota")


class Mensaje(BaseModel):
    rol: Literal["usuario", "asistente"]
    texto: str = Field(min_length=1, max_length=4000)


class PreguntaIn(BaseModel):
    # El historial lo guarda el navegador; el servidor no persiste conversaciones
    mensajes: list[Mensaje] = Field(min_length=1, max_length=20)
    # Pantalla desde donde pregunta (ruta de la app), para dar contexto al asistente
    pantalla: str | None = Field(default=None, max_length=200, pattern=r"^/[A-Za-z0-9/_\-?=&]*$")

    @model_validator(mode="after")
    def _ultimo_es_usuario(self) -> "PreguntaIn":
        if self.mensajes[-1].rol != "usuario":
            raise ValueError("El último mensaje debe ser del usuario")
        if sum(len(m.texto) for m in self.mensajes) > 30_000:
            raise ValueError("La conversación es demasiado larga: inicie una nueva")
        return self


class RespuestaOut(BaseModel):
    texto: str
    herramientas: list[str]
    usadas_hoy: int
    limite_diario: int


class EstadoOut(BaseModel):
    configurado: bool
    modelo: str
    datos_personales: bool
    usadas_hoy: int
    limite_diario: int


def usadas_hoy(db: Session, usuario_id: int) -> int:
    """Preguntas del usuario hoy (hora de Colombia), sumando todas las apps."""
    inicio = datetime.combine(datetime.now(ZONA).date(), time.min, tzinfo=ZONA).astimezone(timezone.utc)
    return db.scalar(select(func.count()).select_from(Auditoria).where(
        Auditoria.usuario_id == usuario_id, Auditoria.accion == "asistente_pregunta", Auditoria.fecha >= inicio)) or 0


def router_asistente(
    app: str,
    permiso: str,
    responder: Callable[[Session, Usuario, list[dict]], ia.Respuesta],
    contexto_pantalla: Callable[[Session, str | None], str | None] = lambda db, pantalla: None,
) -> APIRouter:
    router = APIRouter(prefix="/asistente", tags=["asistente IA"])

    @router.get("/estado", response_model=ApiResponse[EstadoOut])
    def estado(db: DbSession, actual: Usuario = Depends(require(permiso))):
        s = get_settings()
        return ok(EstadoOut(configurado=ia.configurada(), modelo=s.ia_modelo, datos_personales=s.asistente_datos_personales,
                            usadas_hoy=usadas_hoy(db, actual.id), limite_diario=s.asistente_max_diario))

    @router.post("", response_model=ApiResponse[RespuestaOut], dependencies=[Depends(limitar("asistente", 10, 60))])
    def preguntar(data: PreguntaIn, request: Request, db: DbSession, actual: Usuario = Depends(require(permiso))):
        s = get_settings()
        usadas = usadas_hoy(db, actual.id)
        if usadas >= s.asistente_max_diario:
            raise ApiError(429, f"Alcanzó el límite de {s.asistente_max_diario} preguntas diarias al asistente.")

        mensajes = [{"role": "user" if m.rol == "usuario" else "assistant", "content": m.texto} for m in data.mensajes]
        pregunta = data.mensajes[-1].texto
        contexto = contexto_pantalla(db, data.pantalla)
        if contexto:
            mensajes[-1]["content"] = f"[{contexto}]\n\n{pregunta}"
        try:
            r = responder(db, actual, mensajes)
        except ia.IANoConfigurada as e:
            raise ApiError(503, "El asistente no está configurado: falta la clave IA_API_KEY en el servidor.", "ASISTENTE_NO_CONFIGURADO") from e
        except ia.IAError as e:
            raise ApiError(e.status, e.mensaje, e.codigo) from e

        # Auditoría (OWASP A09): la pregunta recortada, herramientas usadas y consumo; nunca la respuesta completa
        auditar(db, request, "asistente_pregunta", actual.id, app=app, pregunta=pregunta[:300], herramientas=r.herramientas,
                tokens_entrada=r.tokens_entrada, tokens_salida=r.tokens_salida, modelo=r.modelo)
        db.commit()
        return ok(RespuestaOut(texto=r.texto, herramientas=r.herramientas, usadas_hoy=usadas + 1, limite_diario=s.asistente_max_diario))

    return router
