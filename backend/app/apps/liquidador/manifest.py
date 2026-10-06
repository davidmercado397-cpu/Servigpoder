from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.core.plataforma import App

PERMISOS: dict[str, tuple[str, str]] = {
    "liquidador.periodos.ver": ("Quincenas", "Ver quincenas, empleados y horas contadas; descargar el archivo de liquidación"),
    "liquidador.periodos.gestionar": ("Quincenas", "Crear quincenas, cargar el Excel de turnos, recalcular, cerrar y reabrir"),
    "liquidador.turnos.ver": ("Turnos", "Ver turnos, festivos y la hora de inicio nocturna"),
    "liquidador.turnos.gestionar": ("Turnos", "Crear y editar turnos, ajustar festivos y la hora de inicio nocturna"),
    "liquidador.nomina.ver": ("Nómina", "Ver la nómina calculada (devengado, deducciones y neto), salarios, recargos y descuentos"),
    "liquidador.nomina.gestionar": ("Nómina", "Editar los % de recargos, el salario mínimo, el salario de cada empleado, préstamos y embargos"),
    "liquidador.asistente.usar": ("Asistente IA", "Hacer preguntas al asistente sobre las horas contadas"),
}

ROLES_BASE: dict[str, tuple[str, list[str]]] = {
    # Por ahora la misma persona liquida, consulta y aprueba
    "Liquidador": ("Liquidador de horas: carga los turnos, revisa, cierra los periodos, configura turnos y liquida la nómina", list(PERMISOS)),
}


def _router() -> APIRouter:
    from app.apps.liquidador.routes import asistente, configuracion, nomina, periodos

    router = APIRouter(prefix="/liquidador")
    for modulo in (configuracion, periodos, nomina, asistente):
        router.include_router(modulo.router)
    return router


def _seed(db: Session) -> None:
    from app.apps.liquidador.services.turnos import sembrar

    sembrar(db)


APP = App(
    codigo="liquidador",
    nombre="Liquidador de horas",
    descripcion="Cuenta las horas de cada turno por quincena o mes (diurnas, nocturnas, dominicales, festivas y extras) y liquida la nómina.",
    icono="calculator",
    color="#0f766e",
    permisos=PERMISOS,
    roles_base=ROLES_BASE,
    router=_router,
    seed=_seed,
)
