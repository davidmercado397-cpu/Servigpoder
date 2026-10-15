"""Nombre de banco, AFP, EPS, cesantías, caja o cargo → código del catálogo de SIESA (plano de contratos).

Orden: código válido; código sin ceros a la izquierda; alias; nombre exacto (sin prefijos como AFP, EPS, BANCO
ni sufijos S.A.); un único nombre que lo contenga; similitud solo si hay UN candidato claramente mejor.
Lo que es ambiguo o no tiene candidato no se inventa: se reporta.
"""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.apps.planos.services.comun import normalizar, texto

CATALOGOS = ("BANCOS", "AFP", "EPS", "CESANTIAS", "CAJAS", "CARGOS")
CEROS = {"BANCOS": 2, "CESANTIAS": 3, "CARGOS": 3}
RUIDO = re.compile(r"\b(AFP|CESANTIAS|CCF|EPS|EPSS|EPSI|E P S|BANCO|S A S|S A|SA|SAS|ENTIDAD PROMOTORA DE SALUD|"
                   r"CAJA DE COMPENSACION FAMILIAR|FONDO DE PENSIONES)\b")
SIMILITUD_MINIMA = 0.8
VENTAJA_MINIMA = 0.1  # sobre el segundo candidato


def nucleo(s: str) -> str:
    return re.sub(r"\s+", " ", RUIDO.sub(" ", normalizar(s))).strip()


@dataclass
class Codigo:
    codigo: str | None
    como: str  # codigo | ceros | alias | exacto | contenido | similitud | ambiguo | sin_coincidencia | vacio
    detalle: str = ""

    @property
    def revisar(self) -> bool:
        """Asignado por alias, por ceros o por parecido: el usuario lo verifica en la hoja de errores."""
        return self.como in ("ceros", "alias", "contenido", "similitud")


class Codificador:
    def __init__(self, catalogos: dict[str, dict[str, str]], alias: dict[tuple[str, str], str]):
        """catalogos: {catálogo: {código: descripción}}; alias: {(catálogo, texto normalizado): código}."""
        self.catalogos = catalogos
        self.alias = alias
        self._nucleos = {c: {cod: nucleo(d) for cod, d in cat.items()} for c, cat in catalogos.items()}

    def descripcion(self, catalogo: str, codigo: str) -> str:
        return self.catalogos.get(catalogo, {}).get(codigo, "")

    def codificar(self, catalogo: str, valor) -> Codigo:
        cat = self.catalogos.get(catalogo, {})
        s = texto(valor).strip("* ")
        if not s:
            return Codigo(None, "vacio")
        if s in cat:
            return Codigo(s, "codigo")
        if s.isdigit() and catalogo in CEROS and s.zfill(CEROS[catalogo]) in cat:
            return Codigo(s.zfill(CEROS[catalogo]), "ceros")
        n = normalizar(s)
        if (catalogo, n) in self.alias:
            return Codigo(self.alias[(catalogo, n)], "alias")
        nucleos = self._nucleos.get(catalogo, {})
        ns = nucleo(s)
        exactos = [c for c, d in cat.items() if normalizar(d) == n] or [c for c, d in nucleos.items() if ns and d == ns]
        if len(exactos) == 1:
            return Codigo(exactos[0], "exacto")
        if len(exactos) > 1:
            return Codigo(None, "ambiguo", ", ".join(exactos))
        if ns:
            contiene = [c for c, d in nucleos.items() if re.search(rf"\b{re.escape(ns)}\b", d)]
            if len(contiene) == 1:
                return Codigo(contiene[0], "contenido")
            if len(contiene) > 1:
                return Codigo(None, "ambiguo", ", ".join(contiene))
        puntajes = sorted(((SequenceMatcher(None, ns or n, d).ratio(), c) for c, d in nucleos.items()), reverse=True)
        if not puntajes:
            return Codigo(None, "sin_coincidencia")
        p1, c1 = puntajes[0]
        p2 = puntajes[1][0] if len(puntajes) > 1 else 0
        if p1 >= SIMILITUD_MINIMA and p1 - p2 >= VENTAJA_MINIMA:
            return Codigo(c1, "similitud", f"{p1:.2f}")
        return Codigo(None, "sin_coincidencia", f"la más parecida es {c1} {cat[c1]}" if p1 >= 0.5 else "")
