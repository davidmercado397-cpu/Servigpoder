import re
from datetime import datetime, time, timezone
from typing import Literal

import anthropic
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select

from app.api.deps import DbSession, require
from app.core.auditoria import auditar
from app.core.config import get_settings
from app.core.rate_limit import limitar
from app.core.respuestas import ApiError, ApiResponse, ok
from app.models import Auditoria, Puesto, Usuario
from app.services import asistente as svc
from app.services.alertas import ZONA

router = APIRouter(prefix="/asistente", tags=["asistente IA"])


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


def _usadas_hoy(db: DbSession, usuario_id: int) -> int:
    inicio = datetime.combine(datetime.now(ZONA).date(), time.min, tzinfo=ZONA).astimezone(timezone.utc)
    return db.scalar(select(func.count()).select_from(Auditoria).where(
        Auditoria.usuario_id == usuario_id, Auditoria.accion == "asistente_pregunta", Auditoria.fecha >= inicio)) or 0


def _contexto_pantalla(db: DbSession, pantalla: str | None) -> str | None:
    if not pantalla:
        return None
    m = re.match(r"^/cobertura/(\d+)", pantalla)
    if m:
        puesto = db.get(Puesto, int(m.group(1)))
        if puesto:
            return f"El usuario está viendo el calendario de cobertura del puesto {puesto.codigo} ({puesto.ubicacion.nombre})"
    nombres = {"/cobertura": "el tablero de cobertura", "/cubrimientos": "la bandeja de cubrimientos de nómina",
               "/bolsas": "el reporte de personas en bolsa", "/historico": "el histórico y comparación de cargas",
               "/matriz": "la matriz comercial", "/maestros": "los maestros y puestos por aclarar",
               "/programacion": "la carga de programación de SIESA", "/": "el inicio con las alertas"}
    nombre = nombres.get(pantalla.split("?")[0])
    return f"El usuario está en {nombre}" if nombre else None


@router.get("/estado", response_model=ApiResponse[EstadoOut])
def estado(db: DbSession, actual: Usuario = Depends(require("asistente.usar"))):
    s = get_settings()
    return ok(EstadoOut(configurado=bool(s.anthropic_api_key), modelo=s.asistente_modelo, datos_personales=s.asistente_datos_personales,
                        usadas_hoy=_usadas_hoy(db, actual.id), limite_diario=s.asistente_max_diario))


@router.post("", response_model=ApiResponse[RespuestaOut], dependencies=[Depends(limitar("asistente", 10, 60))])
def preguntar(data: PreguntaIn, request: Request, db: DbSession, actual: Usuario = Depends(require("asistente.usar"))):
    s = get_settings()
    usadas = _usadas_hoy(db, actual.id)
    if usadas >= s.asistente_max_diario:
        raise ApiError(429, f"Alcanzó el límite de {s.asistente_max_diario} preguntas diarias al asistente.")

    mensajes = [{"role": "user" if m.rol == "usuario" else "assistant", "content": m.texto} for m in data.mensajes]
    pregunta = data.mensajes[-1].texto
    contexto = _contexto_pantalla(db, data.pantalla)
    if contexto:
        mensajes[-1]["content"] = f"[{contexto}]\n\n{pregunta}"
    try:
        r = svc.responder(db, actual, mensajes)
    except svc.AsistenteNoConfigurado as e:
        raise ApiError(503, "El asistente no está configurado: falta la clave ANTHROPIC_API_KEY en el servidor.", "ASISTENTE_NO_CONFIGURADO") from e
    except anthropic.RateLimitError as e:
        raise ApiError(429, "El servicio de IA está ocupado. Intente de nuevo en un minuto.") from e
    except anthropic.AuthenticationError as e:
        raise ApiError(503, "La clave de la API de Anthropic no es válida. Revise ANTHROPIC_API_KEY.", "ASISTENTE_NO_CONFIGURADO") from e
    except anthropic.APIStatusError as e:
        raise ApiError(502, "El servicio de IA respondió con un error. Intente de nuevo.", "ERROR_IA") from e
    except anthropic.APIConnectionError as e:
        raise ApiError(503, "No fue posible conectar con el servicio de IA.", "ERROR_IA") from e

    # Auditoría (OWASP A09): la pregunta recortada, herramientas usadas y consumo; nunca la respuesta completa
    auditar(db, request, "asistente_pregunta", actual.id, pregunta=pregunta[:300], herramientas=r.herramientas,
            tokens_entrada=r.tokens_entrada, tokens_salida=r.tokens_salida, modelo=r.modelo)
    db.commit()
    return ok(RespuestaOut(texto=r.texto, herramientas=r.herramientas, usadas_hoy=usadas + 1, limite_diario=s.asistente_max_diario))
