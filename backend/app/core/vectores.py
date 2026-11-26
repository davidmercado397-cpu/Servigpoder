"""Memoria vectorial (RAG) de los agentes de IA, reutilizable por cualquier desarrollo.

Para no mandarle al modelo todo el catálogo, todas las reglas y todo el historial en cada consulta, cada texto se
convierte una sola vez en un vector (embedding, por OpenRouter con la misma clave) y se guarda aquí; en cada consulta
solo viaja lo más parecido. Los vectores se recalculan únicamente cuando cambia el texto (huella SHA-1).

Sin pgvector: los vectores van comprimidos (float32) en la base y la similitud (coseno, con vectores normalizados) se
calcula en el servidor. Para catálogos de cientos o pocos miles de textos es inmediato y no exige cambiar la base.
También registra el consumo de cada agente (tokens) para vigilar el costo.
"""

import hashlib
import logging
from array import array
from datetime import date, datetime, time, timezone

from sqlalchemy import DateTime, Integer, LargeBinary, String, UniqueConstraint, delete, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core import ia
from app.core.db import BaseEmpresa

log = logging.getLogger("app.ia")
LOTE = 96  # textos por llamada de embeddings
MAX_TEXTO = 1000


class IAVector(BaseEmpresa):
    __tablename__ = "ia_vector"
    __table_args__ = (UniqueConstraint("coleccion", "ref", name="uq_ia_vector"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    coleccion: Mapped[str] = mapped_column(String(40), index=True)  # p. ej. ctb_regla, ctb_cuenta, ctb_ejemplo
    ref: Mapped[str] = mapped_column(String(200))  # identificador del texto dentro de la colección
    huella: Mapped[str] = mapped_column(String(40))  # SHA-1 del texto: si cambia, se recalcula
    modelo: Mapped[str] = mapped_column(String(150))
    vector: Mapped[bytes] = mapped_column(LargeBinary)  # float32 normalizado


class IAUso(BaseEmpresa):
    """Consumo de cada agente: cuántas consultas, cuántas se resolvieron sin IA y cuántos tokens."""

    __tablename__ = "ia_uso"

    id: Mapped[int] = mapped_column(primary_key=True)
    agente: Mapped[str] = mapped_column(String(40), index=True)
    tipo: Mapped[str] = mapped_column(String(20))  # propuesta | memoria | vectores | regla
    tokens_entrada: Mapped[int] = mapped_column(Integer, default=0)
    tokens_salida: Mapped[int] = mapped_column(Integer, default=0)
    modelo: Mapped[str] = mapped_column(String(150), default="")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


def huella(texto: str) -> str:
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()


def _empacar(v: list[float]) -> bytes:
    return array("f", v).tobytes()


def _desempacar(b: bytes) -> array:
    a = array("f")
    a.frombytes(b)
    return a


def sincronizar(db: Session, coleccion: str, items: dict[str, str]) -> int:
    """Deja la colección igual a `items` ({ref: texto}): vectoriza solo lo nuevo o cambiado y borra lo que ya no está.
    Devuelve los tokens usados."""
    modelo = ia.ajustes().modelo_vectores
    actuales = {r: (h, m) for r, h, m in db.execute(select(IAVector.ref, IAVector.huella, IAVector.modelo).where(IAVector.coleccion == coleccion))}
    sobran = set(actuales) - set(items)
    if sobran:
        db.execute(delete(IAVector).where(IAVector.coleccion == coleccion, IAVector.ref.in_(sobran)))
    pendientes = [(r, t[:MAX_TEXTO]) for r, t in items.items() if actuales.get(r) != (huella(t[:MAX_TEXTO]), modelo)]
    tokens = 0
    for i in range(0, len(pendientes), LOTE):
        lote = pendientes[i:i + LOTE]
        vectores, usados = ia.embeber([t for _, t in lote])
        tokens += usados
        existentes = {v.ref: v for v in db.scalars(select(IAVector).where(IAVector.coleccion == coleccion, IAVector.ref.in_([r for r, _ in lote])))}
        for (ref, texto), vec in zip(lote, vectores):
            v = existentes.get(ref) or IAVector(coleccion=coleccion, ref=ref)
            v.huella, v.modelo, v.vector = huella(texto), modelo, _empacar(vec)
            db.add(v)
    db.flush()
    return tokens


def buscar(db: Session, coleccion: str, consultas: list[list[float]], k: int, minimo: float = 0.0) -> list[tuple[str, float]]:
    """Los `k` textos de la colección más parecidos a cualquiera de las consultas (similitud coseno 0 a 1)."""
    if not consultas:
        return []
    modelo = ia.ajustes().modelo_vectores
    qs = [array("f", q) for q in consultas]
    puntajes = []
    for ref, b in db.execute(select(IAVector.ref, IAVector.vector).where(IAVector.coleccion == coleccion, IAVector.modelo == modelo)):
        v = _desempacar(b)
        if len(v) != len(qs[0]):
            continue
        s = max(sum(a * c for a, c in zip(v, q)) for q in qs)
        if s >= minimo:
            puntajes.append((ref, s))
    puntajes.sort(key=lambda x: -x[1])
    return puntajes[:k]


def registrar_uso(db: Session, agente: str, tipo: str, tokens_entrada: int = 0, tokens_salida: int = 0, modelo: str = "") -> None:
    db.add(IAUso(agente=agente, tipo=tipo, tokens_entrada=tokens_entrada or 0, tokens_salida=tokens_salida or 0, modelo=modelo[:150]))


def resumen_uso(db: Session, agente: str, desde: date) -> dict:
    inicio = datetime.combine(desde, time.min, tzinfo=timezone.utc)
    filas = db.execute(select(IAUso.tipo, func.count(), func.coalesce(func.sum(IAUso.tokens_entrada), 0), func.coalesce(func.sum(IAUso.tokens_salida), 0))
                       .where(IAUso.agente == agente, IAUso.creado_en >= inicio).group_by(IAUso.tipo)).all()
    por_tipo = {t: {"veces": int(n), "tokens_entrada": int(te), "tokens_salida": int(ts)} for t, n, te, ts in filas}
    return {"desde": desde.isoformat(), "por_tipo": por_tipo,
            "tokens_entrada": sum(x["tokens_entrada"] for x in por_tipo.values()),
            "tokens_salida": sum(x["tokens_salida"] for x in por_tipo.values())}
