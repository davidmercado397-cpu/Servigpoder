"""Rate limit en memoria con ventana deslizante.

Suficiente para un solo contenedor de backend (el despliegue actual en Coolify).
Si se escala a varias réplicas, reemplazar el almacenamiento por Redis.
"""

import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.respuestas import ApiError


class LimitadorVentana:
    def __init__(self) -> None:
        self._eventos: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def registrar(self, clave: str, limite: int, ventana: int) -> int | None:
        """Registra un evento. Devuelve segundos de espera si se superó el límite, si no None."""
        ahora = time.monotonic()
        with self._lock:
            eventos = self._eventos[clave]
            while eventos and eventos[0] <= ahora - ventana:
                eventos.popleft()
            if len(eventos) >= limite:
                return int(eventos[0] + ventana - ahora) + 1
            eventos.append(ahora)
            return None

    def contar(self, clave: str, ventana: int) -> int:
        ahora = time.monotonic()
        with self._lock:
            eventos = self._eventos.get(clave)
            if not eventos:
                return 0
            while eventos and eventos[0] <= ahora - ventana:
                eventos.popleft()
            return len(eventos)

    def limpiar(self, clave: str) -> None:
        with self._lock:
            self._eventos.pop(clave, None)

    def reiniciar(self) -> None:
        with self._lock:
            self._eventos.clear()


limitador = LimitadorVentana()


def ip_cliente(request: Request) -> str:
    # uvicorn con --proxy-headers ya resuelve X-Forwarded-For en request.client
    return request.client.host if request.client else "desconocida"


def limitar(nombre: str, limite: int, ventana: int = 60):
    """Dependencia de FastAPI: máximo `limite` peticiones por IP cada `ventana` segundos."""

    def dependencia(request: Request) -> None:
        espera = limitador.registrar(f"{nombre}:{ip_cliente(request)}", limite, ventana)
        if espera is not None:
            raise ApiError(429, f"Demasiadas solicitudes. Intente de nuevo en {espera} segundos.",
                           headers={"Retry-After": str(espera)})

    return dependencia
