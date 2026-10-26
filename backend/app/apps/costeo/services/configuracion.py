"""Datos iniciales y configuración editable del desarrollo: tipos de ítem de MFP, parámetros del costeo,
rangos de comisión, servicios y catálogos de dotación y otros costos (tomados del costeo de Palmaseca).
La carga inicial es idempotente: no pisa lo que el usuario ya cambió."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.apps.costeo.models import (
    HORAS, PESOS, PESOS_MES, CstCatalogoCosto, CstComisionRango, CstParametro, CstServicio, CstTipoItem,
)
from app.apps.costeo.services.calculo import CARGA_PRESTACIONAL, COMISIONES, PARAMETROS, Rango

# codigo: (nombre, unidad, reembolsable, cuenta en el % de MFP)
TIPOS_ITEM = {
    "REINVERSION": ("Reinversión / bono de libre inversión", PESOS, True, True),
    "NOTA_CREDITO": ("Nota crédito / bono tarifa", PESOS, True, True),
    "ACCES_TOO": ("Acces Too y mantenimiento", PESOS, True, True),
    "CAPACITACION": ("Capacitación", PESOS, True, True),
    "EQUIPOS": ("Equipos (computador, celular, cámaras…)", PESOS, True, True),
    "OTROS": ("Otros", PESOS, True, True),
    "SERVICIO_MENSUAL": ("Servicio mensual (plan celular, mantenimiento…)", PESOS_MES, False, True),
    "BOLSA_HORAS": ("Bolsa de horas de vigilancia", HORAS, False, True),
    "PUBLICIDAD": ("Bolsa de publicidad", PESOS, False, False),
    "REPRESENTACION": ("Reserva de gastos de representación", PESOS, False, False),
}

SERVICIOS = [
    ("Servicio de vigilancia 24 horas de lunes a domingo todo el mes, dotado con medio de comunicación", 18490849, 3),
    ("Servicio de vigilancia 12 horas DIURNO de lunes a domingo todo el mes, dotado con medio de comunicación", 5855463, 1.5),
    ("Servicio de vigilancia 12 horas NOCTURNO de lunes a domingo todo el mes, dotado con medio de comunicación", 7221037, 1.5),
    ("Servicio de vigilancia 10 horas DIURNO de lunes a domingo todo el mes, dotado con medio de comunicación", 4880077, 1.25),
    ("Servicio de vigilancia 10 horas NOCTURNO de lunes a domingo todo el mes, dotado con medio de comunicación", 5757959, 1.25),
    ("Servicio de vigilancia 8 horas DIURNO de lunes a domingo todo el mes, dotado con medio de comunicación", 3904692, 1.1),
    ("Servicio de vigilancia 8 horas NOCTURNO de lunes a domingo todo el mes, dotado con medio de comunicación", 5118536, 1.1),
    ("Servicio de vigilancia y seguridad privada 12 horas de lunes a sábado, apoyo en porterías (sin arma)", 6556331, 1.5),
]

# (nombre, valor, vida útil en meses, entregas al año, por hombre); vida útil vacía = los meses del contrato
DOTACION_TARIFA = [
    ("PANTALÓN", 44030, None, 3, True), ("JEAN", 103503, None, 3, True), ("CAMISA", 49385, None, 3, True),
    ("OVEROL", 73780, None, 1, True), ("GOLEANA", 21301, None, 1, True), ("CORBATA", 14042, None, 1, True),
    ("CORREA", 15470, None, 1, True), ("APELLIDOS (PAR)", 5950, None, 2, True), ("BOTAS PUNTERA", 73780, None, 1, True),
    ("CALZADO HOMBRE", 49861, None, 2, True), ("CALZADO MUJER", 46410, None, 2, True), ("CAPA IMPERMEABLE", 48385, 12, None, False),
    ("ARMA DE FUEGO", 0, 60, None, False), ("ARMA TRAUMÁTICA", 1666666, 60, None, False), ("ARMA NO LETAL", 700000, 60, None, False),
    ("CHAPUZA EXTERNA", 25595, 24, None, False), ("RADIO KENWOOD", 987700, 36, None, False), ("PORTA RADIOS", 33915, 24, None, False),
    ("CARGADOR DE RADIO", 131264, 24, None, False), ("TONFA CON PORTA TONFA", 31535, 24, None, False),
    ("MINUTAS", 13866, None, 3, True), ("EXÁMENES MÉDICOS (OSTEOMUSCULAR, AUDIOMETRÍA Y VISIOMETRÍA)", 68000, None, 1, True),
    ("PRUEBAS DE SPA", 9000, None, 1, True),
]
DOTACION_PUESTO = [
    ("RADIO KENWOOD ADICIONAL", 987700, 36), ("PORTA RADIOS", 33915, 24), ("CARGADOR DE RADIO", 131264, 24), ("LINTERNAS", 57120, 24),
    ("LECTORA DE MARCACIÓN CON ESTUCHE", 566321, 24), ("PUNTO DE MARCACIÓN", 24990, 24), ("BOTAS CAUCHO PUNTERA", 62786, 12),
    ("SOMBRILLA CON LOGO", 42000, 12), ("CHALECO REFLECTIVO", 38080, 21), ("RADIOS PUNTO A PUNTO", 178500, 24),
    ("CHALECO ANTIBALAS", 1474410, 36), ("FORRO CHALECO BLINDADO", 237881, 36), ("DETECTOR DE METALES", 77350, 24),
    ("MASCARILLAS", 227500, None), ("FILTROS", 83300, None), ("CHAQUETAS", 95200, 12), ("GAFAS CLARAS", 5950, 24),
    ("GAFAS OSCURAS", 17900, 24), ("CASCOS", 41650, 24), ("GUANTES DE TELA", 13000, 24), ("CAJA GUANTES LÁTEX", 40000, 12),
    ("PITOS", 3332, 24), ("KIT MOTORIZADO", 279650, 12), ("EQUIPO CELULAR", 600000, None), ("SEGWAY", 8000000, None),
    ("CILINDROS DESCARGUE DE ARMAS", 1547000, None), ("BICICLETAS", 530000, 24), ("CAJA DE SEGURIDAD", 2600000, None),
    ("ESPEJO DETECTOR", 154700, 21), ("CAJILLA DE SEGURIDAD", 1100000, None), ("TRAJE MOTO LLUVIA", 116620, 12),
    ("BOTAS PANTANERAS", 31300, 12), ("LOCKERS", 2284800, 60), ("PÓLIZAS EXCLUSIVAS PARA EL CLIENTE", 0, None),
    ("VUELO DRON", 260000, None),
]
OTROS = [
    ("ACCES TOO", 3600000, None), ("MÓDEM MONITOREO E INSTALACIÓN", 5017297, None), ("CELULAR", 700000, None),
    ("VISITRACK (MENSUAL)", 69020, 1), ("TARJETAS VIP", 2500000, 60), ("BONO TARIFA", 0, None),
    ("DISPENSADOR DE AGUA FRÍA Y CALIENTE", 1106700, None), ("IN HOUSE / AUXILIOS (MENSUAL)", 2500000, 1),
]
POR_HOMBRE_PUESTO = {"CHAQUETAS", "PITOS", "BOTAS PANTANERAS"}


def sembrar(db: Session) -> None:
    existentes = {t.codigo for t in db.scalars(select(CstTipoItem))}
    for orden, (codigo, (nombre, unidad, reemb, cuenta)) in enumerate(TIPOS_ITEM.items()):
        if codigo not in existentes:
            db.add(CstTipoItem(codigo=codigo, nombre=nombre, unidad=unidad, reembolsable=reemb, cuenta_en_mfp=cuenta, orden=orden * 10))
    claves = {p.clave for p in db.scalars(select(CstParametro))}
    for orden, (clave, (valor, nombre, grupo, ayuda)) in enumerate(PARAMETROS.items()):
        if clave not in claves:
            db.add(CstParametro(clave=clave, valor=valor, nombre=nombre, grupo=grupo, ayuda=ayuda, orden=orden))
    if db.scalar(select(CstComisionRango).limit(1)) is None:
        for hasta, pct in COMISIONES:
            db.add(CstComisionRango(hasta_pct=hasta, pct_comision=pct, carga_prestacional=CARGA_PRESTACIONAL))
    if db.scalar(select(CstServicio).limit(1)) is None:
        for desc, tarifa, hombres in SERVICIOS:
            db.add(CstServicio(descripcion=desc, tarifa=tarifa, hombres=hombres))
    if db.scalar(select(CstCatalogoCosto).limit(1)) is None:
        fuente_c, fuente_d = "Compras (16/03/2026)", "Fabian Sabogal (01/03/2026)"
        for nombre, valor, vida, entregas, por_hombre in DOTACION_TARIFA:
            db.add(CstCatalogoCosto(grupo="dotacion_tarifa", nombre=nombre, valor_unitario=valor, vida_util_meses=vida,
                                    entregas_anio=entregas, por_hombre=por_hombre, fuente=fuente_c))
        for nombre, valor, vida in DOTACION_PUESTO:
            db.add(CstCatalogoCosto(grupo="dotacion_puesto", nombre=nombre, valor_unitario=valor, vida_util_meses=vida,
                                    por_hombre=nombre in POR_HOMBRE_PUESTO, fuente=fuente_d))
        for nombre, valor, vida in OTROS:
            db.add(CstCatalogoCosto(grupo="otros", nombre=nombre, valor_unitario=valor, vida_util_meses=vida))
    db.flush()


def parametros(db: Session) -> dict[str, float]:
    valores = {k: v[0] for k, v in PARAMETROS.items()}
    valores.update({p.clave: float(p.valor) for p in db.scalars(select(CstParametro))})
    return valores


def rangos(db: Session) -> list[Rango]:
    filas = db.scalars(select(CstComisionRango)).all()
    if not filas:
        return [Rango(h, p, CARGA_PRESTACIONAL) for h, p in COMISIONES]
    return [Rango(float(r.hasta_pct) if r.hasta_pct is not None else None, float(r.pct_comision), float(r.carga_prestacional))
            for r in filas]
