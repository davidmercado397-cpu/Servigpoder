"""Exportación de la base de personal con el mismo formato de la importación (OPERATIVOS, ADMINISTRATIVOS, RETIROS OP y
RETIROS ADMIN), para descargarla, corregirla en Excel y volver a importarla. Al final de las hojas de activos van datos que
el importador no lee (estado, ingreso, ARL, días hábiles, saldo de vacaciones y, con el permiso de nómina, el salario).
El archivo se genera en memoria y no se guarda."""

from datetime import date

from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.apps.liquidador.models import LiqContrato, LiqEmpleado
from app.apps.liquidador.services import vacaciones as vac
from app.apps.liquidador.services.exportar import XLSX, _CENTRO, _FUENTE, _RELLENO, _autoajustar, _guardar
from app.apps.liquidador.services.personal import ADMINISTRATIVO

# Mismos encabezados que reconoce la importación (services/personal.py, por prefijo)
ACTIVOS = (
    ("CEDULA", "documento"), ("NOMBRE Y APELLIDO", "nombre"), ("CARGO", "cargo"), ("PUESTO", "puesto"), ("CIUDAD", "ciudad"),
    ("SEXO", "sexo"), ("FECHA DE NACIMIENTO", "fecha_nacimiento"), ("EDAD", "_edad"), ("RH", "rh"), ("CELULAR", "celular"),
    ("ID PAIS NACIMIENTO", "pais_nacimiento"), ("ID DEPTO NACIMIENTO", "depto_nacimiento"), ("ID CIUDAD NACIMIENTO", "ciudad_nacimiento"),
    ("FECHA EXPEDICION IDENTIFICACION", "fecha_expedicion"), ("ID PAIS EXPEDICION IDENTIFICACION", "pais_expedicion"),
    ("ID DEPTO EXPEDICION IDENTIFICACION", "depto_expedicion"), ("ID CIUDAD EXPEDICION IDENTIFICACION", "ciudad_expedicion"),
    ("INDICADOR ESTADO CIVIL (0=Ninguno, 1=Soltero, 2=Casado, 3=Unión libre, 4=Viudo, 5=Divorciado)", "estado_civil"),
    ("INDICADOR EXTRANJERO (0=No, 1=Si)", "_extranjero"), ("CORREO", "correo"), ("DIRECCION", "direccion"), ("BARRIO", "barrio"),
    ("CAJA DE COMPENSACION", "caja_compensacion"), ("FONDO DE PENSIONES", "_fondo_pensiones"), ("FONDO DE CESANTIAS", "fondo_cesantias"),
    ("EPS", "eps"), ("PLAN EXEQUIAL", "plan_exequial"), ("NUMERO DE CUENTA", "numero_cuenta"),
    ("FECHA DE INICIO DEL CONTRATO", "_inicio"), ("ANTIGÜEDAD (AÑOS)", "_antiguedad"), ("CONTRATO", "tipo_contrato"),
    ("NIVEL EDUCATIVO", "nivel_educativo"), ("CURSOS ADICIONALES / CUALES", "cursos"),
)
# Solo informativos: el importador no los lee
ADICIONALES = (("ESTADO", "_estado"), ("TIPO DE PERSONAL", "_tipo"), ("PENSIONADO", "_pensionado"), ("CLASE DE RIESGO ARL", "_arl"),
               ("DIAS HABILES DE VACACIONES", "_habiles"), ("SALDO DE VACACIONES (DIAS HABILES PENDIENTES)", "_saldo"))
RETIROS = (("CEDULA", "documento"), ("NOMBRE Y APELLIDO", "nombre"), ("CARGO", "_cargo_contrato"), ("PUESTO", "_puesto_contrato"),
           ("CIUDAD", "ciudad"), ("CELULAR", "celular"), ("CORREO", "correo"), ("DIRECCION", "direccion"), ("BARRIO", "barrio"),
           ("NUMERO DE CUENTA", "numero_cuenta"), ("FECHA DE INICIO DEL CONTRATO", "_inicio"), ("ANTIGÜEDAD (AÑOS)", "_antiguedad"),
           ("CONTRATO", "_tipo_contrato"), ("FECHA DE RETIRO", "_retiro"), ("OBSERVACION", "_motivo"))
FECHAS = {"fecha_nacimiento", "fecha_expedicion", "_inicio", "_retiro"}
CLASES_ARL = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V"}


def _anios(desde: date | None, hasta: date) -> float | None:
    return round((hasta - desde).days / 365.25, 1) if desde else None


def exportar_base(db: Session, con_salario: bool, hoy: date | None = None) -> tuple[bytes, str, str]:
    hoy = hoy or date.today()
    empleados = list(db.scalars(select(LiqEmpleado).order_by(LiqEmpleado.nombre)))
    contratos: dict[int, list[LiqContrato]] = {}
    for c in db.scalars(select(LiqContrato).order_by(LiqContrato.fecha_inicio)):
        contratos.setdefault(c.empleado_id, []).append(c)
    disfrutados = vac.habiles_disfrutados(db, {e.id: e for e in empleados})

    def valor(e: LiqEmpleado, campo: str, c: LiqContrato | None = None):
        if campo == "_edad":
            n = e.fecha_nacimiento
            return hoy.year - n.year - ((hoy.month, hoy.day) < (n.month, n.day)) if n else None
        if campo == "_extranjero":
            return 1 if e.extranjero else 0
        if campo == "_fondo_pensiones":  # el pensionado vuelve como lo trae la base («PENSIONADO - fondo»)
            return f"PENSIONADO - {e.fondo_pensiones}" if e.pensionado and e.fondo_pensiones else "PENSIONADO" if e.pensionado else e.fondo_pensiones
        if campo == "_inicio":
            return c.fecha_inicio if c else e.fecha_ingreso
        if campo == "_antiguedad":
            inicio = c.fecha_inicio if c else e.fecha_ingreso
            return _anios(inicio, (c.fecha_retiro if c and c.fecha_retiro else hoy))
        if campo == "_retiro":
            return c.fecha_retiro if c else None
        if campo == "_motivo":
            return c.motivo_retiro if c else None
        if campo == "_cargo_contrato":
            return (c.cargo if c else None) or e.cargo
        if campo == "_puesto_contrato":
            return (c.puesto if c else None) or e.puesto
        if campo == "_tipo_contrato":
            return (c.tipo_contrato if c else None) or e.tipo_contrato
        if campo == "_estado":
            return "Retirado" if e.estado == "retirado" else "Activo"
        if campo == "_tipo":
            return "Administrativo" if e.tipo_personal == ADMINISTRATIVO else "Operativo"
        if campo == "_pensionado":
            return "SI" if e.pensionado else "NO"
        if campo == "_arl":
            return CLASES_ARL.get(e.arl_clase or 0)
        if campo == "_habiles":
            return vac.texto_habiles(e.dias_habiles)
        if campo == "_saldo":
            s = vac.saldo(e, disfrutados.get(e.id, 0), hoy)
            return float(s["pendientes"]) if s else None
        if campo == "_salario":
            return float(e.salario) if e.salario is not None else "Salario mínimo"
        return getattr(e, campo)

    libro = Workbook()
    libro.remove(libro.active)
    columnas_activos = (*ACTIVOS, *ADICIONALES, *((("SALARIO MENSUAL", "_salario"),) if con_salario else ()))
    hojas = {}
    for nombre, columnas in (("OPERATIVOS", columnas_activos), ("ADMINISTRATIVOS", columnas_activos),
                             ("RETIROS OP", RETIROS), ("RETIROS ADMIN", RETIROS)):
        h = libro.create_sheet(nombre)
        h.append([t for t, _ in columnas] + ([None] if nombre.startswith("RETIROS") else []))
        hojas[nombre] = (h, columnas)

    def fila(hoja: str, e: LiqEmpleado, c: LiqContrato | None = None) -> None:
        h, columnas = hojas[hoja]
        h.append([valor(e, campo, c) for _, campo in columnas] + ([c.observacion if c else None] if hoja.startswith("RETIROS") else []))

    for e in empleados:
        admin = e.tipo_personal == ADMINISTRATIVO
        cs = contratos.get(e.id, [])
        if e.estado != "retirado":
            abierto = next((c for c in reversed(cs) if c.fecha_retiro is None), None)
            fila("ADMINISTRATIVOS" if admin else "OPERATIVOS", e, abierto)
        for c in cs:  # contratos terminados (también los de quien volvió a ingresar)
            if c.fecha_retiro is not None:
                fila("RETIROS ADMIN" if admin else "RETIROS OP", e, c)

    for h, columnas in hojas.values():
        for celda in h[1]:
            if celda.value is not None:
                celda.fill, celda.font, celda.alignment = _RELLENO, _FUENTE, _CENTRO
        for i, (_, campo) in enumerate(columnas, start=1):
            if campo in FECHAS:
                for (celda,) in h.iter_rows(min_row=2, min_col=i, max_col=i):
                    celda.number_format = "dd/mm/yyyy"
            if campo == "_salario":
                for (celda,) in h.iter_rows(min_row=2, min_col=i, max_col=i):
                    celda.number_format = "$ #,##0"
        _autoajustar(h, minimo=10, maximo=36)
        h.freeze_panes = "C2"
        h.row_dimensions[1].height = 48
    return _guardar(libro), XLSX, f"base_de_personal_{hoy:%Y_%m_%d}.xlsx"
