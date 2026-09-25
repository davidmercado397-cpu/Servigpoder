"""Normalización de códigos de puesto entre la matriz y SIESA.

En la matriz y en SIESA el mismo puesto se escribe distinto: `47A` / `47-A`,
`3 - 1` / `03-1`, `283-151` / `283-15-1`. Se usan dos llaves:

- canónica: segmentos separados por guion, sin ceros a la izquierda y
  separando números de letras (`47A` → `47-A`, `03-1` → `3-1`). Coincidir por
  esta llave es una equivalencia **exacta**.
- compacta: la canónica sin separadores (`283-15-1` → `283151`). Coincidir solo
  por esta llave es una equivalencia **aproximada** que el usuario debe verificar.
"""

import re

_SEGMENTOS = re.compile(r"\d+|[A-Z]+")


def limpiar(codigo: object) -> str:
    """Texto del código sin espacios sobrantes, en mayúsculas."""
    return re.sub(r"\s+", "", str(codigo or "")).upper()


def canonico(codigo: object) -> str:
    partes = _SEGMENTOS.findall(limpiar(codigo))
    return "-".join(p.lstrip("0") or "0" if p.isdigit() else p for p in partes)


def compacto(codigo: object) -> str:
    return canonico(codigo).replace("-", "")
