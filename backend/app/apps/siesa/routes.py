"""Chat de instructivos SIESA y administración de su base de conocimiento (PDF)."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, func, select

from app.api.deps import DbSession, require
from app.core import ia
from app.core.asistente import usadas_hoy
from app.core.auditoria import auditar
from app.core.config import get_settings
from app.core.rate_limit import limitar
from app.core.respuestas import ApiError, ApiResponse, ok
from app.models import Usuario
from app.apps.siesa import services
from app.apps.siesa.models import SiesaDocumento, SiesaFragmento

router = APIRouter(prefix="/siesa", tags=["instructivos SIESA"])
CONSULTAR = "siesa.consultar"
GESTIONAR = "siesa.gestionar"
MAX_ARCHIVOS = 20


class DocumentoOut(BaseModel):
    id: int
    nombre: str
    titulo: str
    modulo: str
    fecha: date | None
    objetivo: str
    secciones: int
    paginas: int
    paginas_sin_texto: int
    fragmentos: int
    cargado_en: str


def _doc_out(d: SiesaDocumento, secciones: int = 0) -> DocumentoOut:
    return DocumentoOut(id=d.id, nombre=d.nombre, titulo=d.titulo, modulo=d.modulo, fecha=d.fecha, objetivo=d.objetivo or "",
                        secciones=secciones,
                        paginas=d.paginas, paginas_sin_texto=d.paginas_sin_texto, fragmentos=d.fragmentos,
                        cargado_en=d.cargado_en.isoformat() if d.cargado_en else "")


def _secciones(db: DbSession) -> dict[int, int]:
    return dict(db.execute(select(SiesaFragmento.documento_id, func.count(func.distinct(SiesaFragmento.seccion)))
                           .where(SiesaFragmento.seccion != "").group_by(SiesaFragmento.documento_id)).all())


@router.get("/documentos", response_model=ApiResponse[list[DocumentoOut]])
def documentos(db: DbSession, _=Depends(require(CONSULTAR))):
    secciones = _secciones(db)
    lista = db.scalars(select(SiesaDocumento).order_by(SiesaDocumento.modulo, SiesaDocumento.titulo))
    return ok([_doc_out(d, secciones.get(d.id, 0)) for d in lista], modulos=services.modulos(db))


@router.get("/modulos", response_model=ApiResponse[list[str]])
def modulos(db: DbSession, _=Depends(require(CONSULTAR))):
    """Módulos de SIESA con instructivos cargados (para filtrar el chat)."""
    return ok(services.modulos(db))


class DocumentoEditar(BaseModel):
    titulo: str | None = Field(default=None, min_length=1, max_length=255)
    modulo: str | None = Field(default=None, max_length=80)
    fecha: date | None = None
    objetivo: str | None = Field(default=None, max_length=1000)


@router.patch("/documentos/{documento_id}", response_model=ApiResponse[DocumentoOut])
def editar_documento(documento_id: int, data: DocumentoEditar, request: Request, db: DbSession,
                     actual: Usuario = Depends(require(GESTIONAR))):
    """Título, módulo, fecha y objetivo del instructivo; el encabezado de sus fragmentos se actualiza con ellos."""
    d = db.get(SiesaDocumento, documento_id)
    if d is None:
        raise ApiError(404, "Documento no encontrado")
    cambios = data.model_dump(exclude_unset=True)
    if "titulo" in cambios and data.titulo:
        d.titulo = data.titulo.strip()
    if "modulo" in cambios:
        d.modulo = (data.modulo or "").strip()
    if "fecha" in cambios:
        d.fecha = data.fecha
    if "objetivo" in cambios:
        d.objetivo = (data.objetivo or "").strip()
    services.actualizar_encabezados(d)
    auditar(db, request, "siesa_documento_editado", actual.id, archivo=d.nombre, campos=sorted(cambios))
    db.commit()
    return ok(_doc_out(d, _secciones(db).get(d.id, 0)))


@router.get("/estado", response_model=ApiResponse[dict])
def estado(db: DbSession, actual: Usuario = Depends(require(CONSULTAR))):
    s = get_settings()
    return ok({"configurado": ia.configurada(),
               "documentos": db.scalar(select(func.count()).select_from(SiesaDocumento)) or 0,
               "paginas": db.scalar(select(func.coalesce(func.sum(SiesaDocumento.paginas), 0))) or 0,
               "usadas_hoy": usadas_hoy(db, actual.id), "limite_diario": s.asistente_max_diario})


async def _leer_pdf(archivo: UploadFile) -> bytes:
    """Valida y lee el PDF en memoria; el archivo temporal de la subida se cierra (y se borra) aquí mismo."""
    try:
        if not (archivo.filename or "").lower().endswith(".pdf"):
            raise ApiError(415, "Solo se aceptan archivos PDF")
        limite = get_settings().siesa_max_pdf_mb * 1024 * 1024
        contenido = await archivo.read(limite + 1)
    finally:
        await archivo.close()
    if len(contenido) > limite:
        raise ApiError(413, f"El archivo supera el tamaño máximo de {get_settings().siesa_max_pdf_mb} MB")
    if not contenido.startswith(b"%PDF-"):
        raise ApiError(415, "El archivo no es un PDF válido")
    return contenido


@router.post("/documentos", response_model=ApiResponse[list[dict]], dependencies=[Depends(limitar("siesa_cargar", 10, 60))])
async def cargar(request: Request, db: DbSession, archivos: list[UploadFile] = File(...), modulo: str = Form("", max_length=80),
                 actual: Usuario = Depends(require(GESTIONAR))):
    """Carga uno o varios PDF. De cada uno queda solo su texto; el archivo no se guarda."""
    if len(archivos) > MAX_ARCHIVOS:
        raise ApiError(400, f"Cargue máximo {MAX_ARCHIVOS} PDF a la vez")
    resultados = []
    for archivo in archivos:
        nombre = (archivo.filename or "documento.pdf")[:255]
        try:
            contenido = await _leer_pdf(archivo)
            c = services.cargar(db, nombre, contenido, actual.id, modulo)
            del contenido
            if not c.duplicado:
                auditar(db, request, "siesa_documento_cargado", actual.id, archivo=nombre, modulo=c.documento.modulo,
                        paginas=c.documento.paginas, fragmentos=c.documento.fragmentos)
            db.commit()
            resultados.append({"archivo": nombre, "ok": True, "duplicado": c.duplicado, "advertencias": c.advertencias,
                               "documento": _doc_out(c.documento, len({f.seccion for f in c.documento.partes if f.seccion})).model_dump(mode="json")})
        except (ApiError, services.ErrorPDF) as e:
            db.rollback()
            resultados.append({"archivo": nombre, "ok": False, "error": e.detail if isinstance(e, ApiError) else str(e)})
    return ok(resultados)


@router.delete("/documentos/{documento_id}", response_model=ApiResponse[dict])
def eliminar(documento_id: int, request: Request, db: DbSession, actual: Usuario = Depends(require(GESTIONAR))):
    d = db.get(SiesaDocumento, documento_id)
    if d is None:
        raise ApiError(404, "Documento no encontrado")
    auditar(db, request, "siesa_documento_eliminado", actual.id, archivo=d.nombre)
    db.execute(delete(SiesaFragmento).where(SiesaFragmento.documento_id == d.id))
    db.delete(d)
    db.commit()
    return ok({"eliminado": documento_id})


class Mensaje(BaseModel):
    rol: Literal["usuario", "asistente"]
    texto: str = Field(min_length=1, max_length=4000)


class PreguntaIn(BaseModel):
    mensajes: list[Mensaje] = Field(min_length=1, max_length=20)  # el historial vive en el navegador
    modulo: str | None = Field(default=None, max_length=80)  # buscar solo en los instructivos de este módulo

    @model_validator(mode="after")
    def _ultimo_es_usuario(self):
        if self.mensajes[-1].rol != "usuario":
            raise ValueError("El último mensaje debe ser del usuario")
        return self


@router.post("/chat", response_model=ApiResponse[dict], dependencies=[Depends(limitar("asistente", 10, 60))])
def chat(data: PreguntaIn, request: Request, db: DbSession, actual: Usuario = Depends(require(CONSULTAR))):
    s = get_settings()
    usadas = usadas_hoy(db, actual.id)
    if usadas >= s.asistente_max_diario:
        raise ApiError(429, f"Alcanzó el límite de {s.asistente_max_diario} preguntas diarias.")
    mensajes = [{"role": "user" if m.rol == "usuario" else "assistant", "content": m.texto} for m in data.mensajes]
    try:
        r = services.responder(db, mensajes, data.modulo or None)
    except ia.IANoConfigurada as e:
        raise ApiError(503, "El chat no está configurado: falta la clave IA_API_KEY en el servidor.", "ASISTENTE_NO_CONFIGURADO") from e
    except ia.IAError as e:
        raise ApiError(e.status, e.mensaje, e.codigo) from e
    uso = r.respuesta_ia
    # Auditoría: la pregunta recortada, si se encontró y de dónde; nunca la respuesta completa
    auditar(db, request, "asistente_pregunta", actual.id, app="siesa", pregunta=data.mensajes[-1].texto[:300], modulo=data.modulo,
            encontrado=r.encontrado, fuentes=[f"{f['archivo']} p.{f['pagina']}" for f in r.fuentes],
            tokens_entrada=uso.tokens_entrada if uso else 0, tokens_salida=uso.tokens_salida if uso else 0,
            modelo=uso.modelo if uso else "")
    db.commit()
    return ok({"texto": r.texto, "encontrado": r.encontrado, "fuentes": r.fuentes,
               "usadas_hoy": usadas + 1, "limite_diario": s.asistente_max_diario})
