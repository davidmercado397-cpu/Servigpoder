"""Carga del Excel 'ReporteAsignacionResumido' de SIESA.

Formato: filas 1-3 con Compañía / Desde / Hasta, fila 4 con encabezados, una fila
por empleado y puesto, columnas 1..31 con el código de cada día del mes.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.apps.capacidad.models import Novedad, ProgramacionCarga, ProgramacionDia, ProgramacionFila, Puesto, PuestoEquivalencia, Turno
from app.apps.capacidad.models.programacion import DESCONOCIDO, NOVEDAD
from app.apps.capacidad.services.codigos import canonico, compacto, limpiar
from app.apps.capacidad.services.excel import a_fecha, leer_filas, texto


class ErrorProgramacion(ValueError):
    pass


_CORCHETES = re.compile(r"^\[(.+)\]$")


def normalizar_codigo(celda: str) -> str:
    """'[VAC]' → 'VAC'; espacios repetidos colapsados."""
    c = re.sub(r"\s+", " ", celda.strip())
    m = _CORCHETES.match(c)
    return m.group(1).strip() if m else c


@dataclass
class Clasificador:
    novedades: set[str]
    turnos: dict[str, str]  # código → clase

    def clase(self, codigo: str) -> str:
        # La novedad manda: IND y PSA existen como turno en SIESA pero la persona no está en el puesto
        if codigo in self.novedades:
            return NOVEDAD
        return self.turnos.get(codigo, DESCONOCIDO)


@dataclass
class ResolutorPuestos:
    """Resuelve el código de puesto de SIESA al maestro y recuerda la equivalencia."""

    db: Session
    equivalencias: dict[str, PuestoEquivalencia] = field(default_factory=dict)
    por_canonico: dict[str, Puesto] = field(default_factory=dict)
    por_compacto: dict[str, list[Puesto]] = field(default_factory=dict)

    @classmethod
    def crear(cls, db: Session) -> "ResolutorPuestos":
        r = cls(db)
        r.equivalencias = {e.codigo_siesa: e for e in db.scalars(select(PuestoEquivalencia))}
        for p in db.scalars(select(Puesto)):
            r.por_canonico[canonico(p.codigo)] = p
            r.por_compacto.setdefault(compacto(p.codigo), []).append(p)
        return r

    def resolver(self, codigo_siesa: str, ubicacion_siesa: str) -> int | None:
        cod = limpiar(codigo_siesa)
        if cod in self.equivalencias:
            return self.equivalencias[cod].puesto_id
        puesto = self.por_canonico.get(canonico(cod))
        origen = "exacta"
        if puesto is None:
            # Aproximada (283-15-1 → 283-151) solo si además coincide la ubicación (PODER);
            # evita cruces falsos como 01-2 → 12
            ubi = canonico(ubicacion_siesa)
            candidatos = [p for p in self.por_compacto.get(compacto(cod), []) if canonico(p.ubicacion.codigo) == ubi]
            if len(candidatos) != 1:
                return None
            puesto, origen = candidatos[0], "aproximada"
        eq = PuestoEquivalencia(codigo_siesa=cod, puesto_id=puesto.id, origen=origen)
        self.db.add(eq)
        self.equivalencias[cod] = eq
        return puesto.id


def _buscar_valor(filas: list[list[object]], etiqueta: str) -> object:
    for f in filas[:5]:
        if f and texto(f[0]).lower().startswith(etiqueta):
            return f[1] if len(f) > 1 else None
    raise ErrorProgramacion(f"No se encontró '{etiqueta}' en el encabezado del archivo")


def cargar(db: Session, contenido: bytes, archivo: str, usuario_id: int | None) -> ProgramacionCarga:
    filas = leer_filas(contenido)
    if len(filas) < 5:
        raise ErrorProgramacion("El archivo no tiene el formato del reporte de asignación de SIESA")
    compania = texto(_buscar_valor(filas, "compa"))
    try:
        desde, hasta = a_fecha(_buscar_valor(filas, "desde")), a_fecha(_buscar_valor(filas, "hasta"))
    except ValueError as e:
        raise ErrorProgramacion("Las fechas Desde/Hasta no son válidas") from e
    if (desde.year, desde.month) != (hasta.year, hasta.month) or desde > hasta:
        raise ErrorProgramacion("El rango Desde/Hasta debe estar dentro de un mismo mes")

    i_enc = next((i for i, f in enumerate(filas[:10]) if f and "empleado" in texto(f[0]).lower()), None)
    if i_enc is None:
        raise ErrorProgramacion("No se encontró la fila de encabezados (C.C. Empleado)")
    enc = [texto(c).upper() for c in filas[i_enc]]
    col = {nombre: i for i, nombre in enumerate(enc)}
    try:
        i_dia1 = enc.index("1")
        i_puesto, i_desc_puesto = col["PUESTO"], col["DESCRIPCION PUESTO"]
        i_ubi, i_desc_ubi = col["UBICACION"], col["DESCRIPCION UBICACION"]
    except (KeyError, ValueError) as e:
        raise ErrorProgramacion(f"Falta la columna {e} en el archivo") from e
    i_co = col.get("DESCRIPCION CENTRO DE OPERACION")
    i_cliente = col.get("RAZON SOCIAL CLIENTE")

    clasif = Clasificador(
        novedades=set(db.scalars(select(Novedad.codigo))),
        turnos={t.codigo: t.clase for t in db.scalars(select(Turno))},
    )
    if not clasif.turnos:
        raise ErrorProgramacion("Primero cargue el catálogo de horarios de SIESA (Maestros → Turnos)")
    resolutor = ResolutorPuestos.crear(db)

    carga = ProgramacionCarga(
        archivo=archivo[:255], compania=compania, desde=desde, hasta=hasta,
        anio=desde.year, mes=desde.month, usuario_id=usuario_id,
    )
    db.add(carga)

    desconocidos: Counter[str] = Counter()
    sin_puesto: dict[str, str] = {}
    empleados: set[str] = set()
    clases: Counter[str] = Counter()

    for f in filas[i_enc + 1 :]:
        cedula = texto(f[0]) if f else ""
        if not cedula:
            continue
        f = list(f) + [None] * (len(enc) - len(f))
        puesto_siesa = limpiar(f[i_puesto])
        ubicacion_siesa = texto(f[i_ubi])
        fila = ProgramacionFila(
            carga=carga,
            cedula=cedula,
            nombre=texto(f[1]),
            ubicacion_siesa=ubicacion_siesa,
            ubicacion_nombre=texto(f[i_desc_ubi]),
            puesto_siesa=puesto_siesa,
            puesto_descripcion=texto(f[i_desc_puesto])[:300],
            puesto_id=resolutor.resolver(puesto_siesa, ubicacion_siesa),
            centro_operacion=texto(f[i_co]) if i_co is not None else "",
            cliente=texto(f[i_cliente])[:200] if i_cliente is not None else "",
        )
        if fila.puesto_id is None:
            sin_puesto[puesto_siesa] = fila.puesto_descripcion
        empleados.add(cedula)
        for dia in range(desde.day, hasta.day + 1):
            valor = texto(f[i_dia1 + dia - 1])
            if not valor:
                continue
            codigo = normalizar_codigo(valor)
            clase = clasif.clase(codigo)
            clases[clase] += 1
            if clase == DESCONOCIDO:
                desconocidos[codigo] += 1
            fila.dias.append(ProgramacionDia(fecha=date(desde.year, desde.month, dia), codigo=codigo, clase=clase))
        db.add(fila)

    db.flush()
    carga.resumen = {
        "filas": len(carga.filas),
        "empleados": len(empleados),
        "puestos": len({f.puesto_siesa for f in carga.filas}),
        "dias_por_clase": dict(clases),
        "puestos_sin_equivalencia": [{"codigo": c, "descripcion": d} for c, d in sorted(sin_puesto.items())],
        "codigos_desconocidos": [{"codigo": c, "veces": n} for c, n in desconocidos.most_common()],
    }
    db.commit()
    return carga
