"""País, departamento y ciudad → códigos DANE de SIESA (plano de empleados, columnas K–M y O–Q).

Solo la coincidencia exacta o un alias se acepta en silencio. Si el nombre se parece pero no es igual, el código
se escribe y se reporta como "aproximada (revisar)": una similitud no es una confirmación (Tuchín no está en el
catálogo y se parece a Chinú; El Bordo se parece a El Tambo).
"""

import csv
import re
from collections import defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher, get_close_matches
from functools import lru_cache
from pathlib import Path

from app.apps.planos.services.comun import normalizar, texto

DATOS = Path(__file__).resolve().parent.parent / "datos"
COLOMBIA = "169"
BOGOTA = {"BOGOTA", "BOGOTA DC", "BOGOTA D C", "SANTAFE DE BOGOTA", "SANTA FE DE BOGOTA"}
CORTE_SIMILITUD = 0.6
MIN_CONFIANZA = 0.5

# Alias de fábrica (se siembran en la base, donde el usuario agrega los suyos)
ALIAS_DEPARTAMENTO = {("169", "VALLE"): "76", ("169", "CUACA"): "19", ("169", "N DE SANTANDER"): "54",
                      ("169", "NORTE SANTANDER"): "54", ("169", "GUAJIRA"): "44", ("169", "SAN ANDRES"): "88",
                      ("850", "DISTRITO CAPITAL"): "01", ("239", "PICHINCHA"): "01"}
ALIAS_CIUDAD = {("169", "76", "BUGA"): "111"}


@dataclass(frozen=True)
class CatalogoDane:
    paises: dict[str, str]
    deptos: dict[str, dict[str, str]]  # país → código → nombre normalizado
    ciudades: dict[tuple[str, str], dict[str, str]]  # (país, depto) → código → nombre normalizado (solo las de búsqueda)
    nombres_ciudad: dict[tuple[str, str, str], str]  # (país, depto, ciudad) → nombre para mostrar
    nombres_depto: dict[tuple[str, str], str]


@lru_cache
def catalogo() -> CatalogoDane:
    def leer(nombre):
        with open(DATOS / nombre, encoding="utf-8") as f:
            return list(csv.DictReader(f))

    deptos: dict[str, dict[str, str]] = defaultdict(dict)
    nombres_depto = {}
    for r in leer("departamentos.csv"):
        deptos[r["codigo_pais"]][r["codigo_depto"]] = r["nombre_normalizado"]
        nombres_depto[(r["codigo_pais"], r["codigo_depto"])] = r["nombre"]
    ciudades: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)
    nombres = {}
    for r in leer("ciudades.csv"):
        nombres[(r["codigo_pais"], r["codigo_depto"], r["codigo_ciudad"])] = r["nombre"]
        if r["usar_en_busqueda"] == "1":
            ciudades[(r["codigo_pais"], r["codigo_depto"])][r["codigo_ciudad"]] = r["nombre_normalizado"]
    return CatalogoDane({r["codigo_pais"]: r["nombre_normalizado"] for r in leer("paises.csv")}, dict(deptos), dict(ciudades),
                        nombres, nombres_depto)


def buscar(n: str, candidatos: dict[str, str]) -> tuple[str, float] | None:
    """Exacta (1.0); luego un nombre que contenga al otro (el de longitud más parecida); luego similitud con corte."""
    if not n:
        return None
    for c, nombre in candidatos.items():
        if nombre == n:
            return c, 1.0
    contiene = [(c, nombre) for c, nombre in candidatos.items() if n in nombre or nombre in n]
    if contiene:
        c, nombre = min(contiene, key=lambda x: abs(len(x[1]) - len(n)))
        return c, min(SequenceMatcher(None, n, nombre).ratio(), 0.99)
    cerca = get_close_matches(n, list(candidatos.values()), n=1, cutoff=CORTE_SIMILITUD)
    if cerca:
        c = next(c for c, nombre in candidatos.items() if nombre == cerca[0])
        return c, min(SequenceMatcher(None, n, cerca[0]).ratio(), 0.99)
    return None


@dataclass
class Lugar:
    pais: str | None = None
    depto: str | None = None
    ciudad: str | None = None
    problemas: list[tuple[str, str, dict | None]] = field(default_factory=list)  # (tipo, mensaje, sugerencia de alias)

    @property
    def completo(self) -> bool:
        return bool(self.pais and self.depto and self.ciudad)


class ResolverDane:
    def __init__(self, alias_depto: dict[tuple[str, str], str] | None = None,
                 alias_ciudad: dict[tuple[str, str, str], str] | None = None):
        self.cat = catalogo()
        self.alias_depto = {**ALIAS_DEPARTAMENTO, **(alias_depto or {})}
        self.alias_ciudad = {**ALIAS_CIUDAD, **(alias_ciudad or {})}
        self._cache: dict[tuple[str, str, str], Lugar] = {}

    def pais(self, v) -> str | None:
        s = texto(v)
        if s.isdigit() and s in self.cat.paises:
            return s
        n = normalizar(s)
        return next((c for c, nombre in self.cat.paises.items() if nombre == n), None)

    def resolver(self, pais_v, depto_v, ciudad_v) -> Lugar:
        clave = (texto(pais_v), texto(depto_v), texto(ciudad_v))
        if clave not in self._cache:
            self._cache[clave] = self._resolver(*clave)
        r = self._cache[clave]
        return Lugar(r.pais, r.depto, r.ciudad, list(r.problemas))

    def _resolver(self, p_txt: str, d_txt: str, c_txt: str) -> Lugar:
        pais = self.pais(p_txt)
        if pais is None:
            return Lugar(problemas=[("Error", f"País no reconocido: '{p_txt}'" if p_txt else "País vacío", None)])
        dn, cn = normalizar(d_txt), normalizar(c_txt)
        lugar = Lugar(pais)
        # Bogotá es su propio departamento: nunca queda bajo Cundinamarca
        if pais == COLOMBIA and (cn in BOGOTA or (dn in BOGOTA and cn in ("", *BOGOTA))):
            lugar.depto, lugar.ciudad = "11", "001"
            return lugar
        deptos = self.cat.deptos.get(pais, {})
        # Departamento vacío: se toma la ciudad si su nombre es único en el país
        if not d_txt and cn:
            unicas = [(d, c) for (p, d), m in self.cat.ciudades.items() if p == pais for c, nombre in m.items() if nombre == cn]
            if len(unicas) == 1:
                lugar.depto, lugar.ciudad = unicas[0]
                lugar.problemas.append(("Revisar", f"Departamento vacío: se tomó el único municipio del país llamado '{c_txt}' "
                                                   f"({lugar.depto}-{lugar.ciudad})", None))
                return lugar
        # Departamento
        if re.fullmatch(r"\d{1,2}", d_txt):
            lugar.depto = d_txt.zfill(2)
            if lugar.depto not in deptos:
                lugar.depto = None
                lugar.problemas.append(("Error", f"El departamento {d_txt.zfill(2)} no existe para el país {pais}", None))
                return lugar
        elif (pais, dn) in self.alias_depto:
            lugar.depto = self.alias_depto[(pais, dn)]
        else:
            r = buscar(dn, deptos)
            if r is None:
                lugar.problemas.append(("Error", f"Departamento sin coincidencia: '{d_txt}'" if d_txt else "Departamento vacío",
                                        _sugerir("DEPARTAMENTO", pais, "", dn, "")))
                return lugar
            lugar.depto, puntaje = r
            if puntaje < 1:
                lugar.problemas.append(("Revisar", f"Departamento aproximado: '{d_txt}' → {lugar.depto} "
                                                   f"{self.cat.nombres_depto[(pais, lugar.depto)]}" + _baja(puntaje),
                                        _sugerir("DEPARTAMENTO", pais, "", dn, lugar.depto)))
        # Ciudad: solo entre las del departamento (hay nombres repetidos: Colón, La Unión, Florida, Nariño…)
        if re.fullmatch(r"\d{1,3}", c_txt):
            lugar.ciudad = c_txt.zfill(3)
            if (pais, lugar.depto, lugar.ciudad) not in self.cat.nombres_ciudad:
                lugar.problemas.append(("Error", f"La ciudad {lugar.depto}-{lugar.ciudad} no existe en el catálogo", None))
            return lugar
        if (pais, lugar.depto, cn) in self.alias_ciudad:
            lugar.ciudad = self.alias_ciudad[(pais, lugar.depto, cn)]
            return lugar
        r = buscar(cn, self.cat.ciudades.get((pais, lugar.depto), {}))
        if r is None:
            lugar.problemas.append(("Error", f"Ciudad no encontrada en el departamento {lugar.depto}: '{c_txt}'" if c_txt else "Ciudad vacía",
                                    _sugerir("CIUDAD", pais, lugar.depto, cn, "")))
            return lugar
        lugar.ciudad, puntaje = r
        if puntaje < 1:
            lugar.problemas.append(("Revisar", f"Ciudad aproximada: '{c_txt}' → {lugar.depto}-{lugar.ciudad} "
                                               f"{self.cat.nombres_ciudad[(pais, lugar.depto, lugar.ciudad)]}" + _baja(puntaje),
                                    _sugerir("CIUDAD", pais, lugar.depto, cn, lugar.ciudad)))
        return lugar


def _sugerir(catalogo: str, pais: str, depto: str, texto_normalizado: str, codigo: str) -> dict | None:
    if not texto_normalizado:
        return None
    return {"catalogo": catalogo, "pais": pais, "departamento": depto, "texto": texto_normalizado, "codigo": codigo}


def _baja(puntaje: float) -> str:
    return " (baja confianza)" if puntaje < MIN_CONFIANZA else ""
