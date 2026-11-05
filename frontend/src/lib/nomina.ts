/** Tipos y etiquetas de Validación de nómina. */

export type ArchivoCargado = { nombre: string; registros: number; cargado_en: string };

export type TipoAlerta = { titulo: string; severidad: "alta" | "media" | "baja" | "info"; grupo: string };

export type Revision = {
  n: number; fecha: string; motivo: string; archivo_nomina: string; personas: number; alertas: number;
  corregidas: number; persisten: number; nuevas: number; errores_corregidos: number;
};

export type Periodo = {
  id: number; anio: number; mes: number; nomina: "quincenal" | "mensual"; nombre: string; calculado_en: string | null;
  revisiones: number; requeridos: string[]; historial?: Revision[];
  archivos: Record<string, ArchivoCargado>; alertas: number; pendientes: number; personas: Record<string, number>;
  resumen?: {
    personas: Record<string, number>; personas_con_alertas: number; alertas: number; puestos_sin_modalidad: number;
    puestos_sin_modalidad_pendientes: number; excluidas: Record<string, number>; por_tipo: Record<string, Record<string, number>>;
    vacaciones?: number;
  };
  faltan?: string[];
  tipos?: Record<string, TipoAlerta>;
  nombres_archivo?: Record<string, string>;
};

export type Alerta = {
  id: number; nomina: string; cedula: string; nombre: string; tipo: string; titulo: string; grupo: string; referencia: string;
  severidad: string; mensaje: string; esperado: number | null; pagado: number | null; nueva: boolean; estado: string; comentario: string;
  decidido_en: string | null;
};

export type PersonaLista = {
  nomina: string; cedula: string; nombre: string; grupo: string; alertas: number; dias_pagables: number; dias_salario: number;
  novedad: number; neto: number;
};

export type Dia = { codigo: string; clase: string; puesto?: string; ubicacion?: string; modalidad?: string | null };

export type PuestoPersona = {
  ubicacion: string; ubicacion_nombre: string; puesto: string; puesto_nombre: string; modalidad: string | null;
  origen: "puesto" | "ubicacion" | "aprobado_sin_modalidad" | "sin_modalidad" | "no_esta_en_maestro"; modalidad_texto: string;
  conceptos: Record<string, number>; dias_pagables: number; dias_periodo: number; dias_mes: number;
};

export type PersonaDetalle = {
  puestos?: PuestoPersona[];
  cedula: string; nombre: string; nomina: string; grupo: string; tratamiento: string; cargo: string; salario: number;
  contrato: { activo: boolean; tipo_nomina: string; grupo: string; ingreso: string | null; cargo: string } | null;
  desde: string; hasta: string; dias: Record<string, Dia>;
  conteo: { pagables: number; novedad: number; vacaciones: number; vacios: number; sin_modalidad: number; antes_vacaciones?: number };
  vacaciones: { desde: string; hasta: string; dias: number; antes: number } | null;
  modalidades: Record<string, number>; dias_salario: number;
  auxilio: { pagado: number; dias_pagados: number; dias_esperados: number; esperado: number };
  conceptos: { concepto: string; descripcion: string; esperado: number; pagado: number }[];
  cuotas?: { concepto: string; descripcion: string; devengo: boolean; esperado: number; pagado: number; cuotas: number; pendiente: boolean }[];
  extras: Record<string, number>; devengado: number; deducido: number; neto: number;
  alertas_lista: Alerta[];
};

export type PuestoSinModalidad = {
  ubicacion: string; puesto: string; ubicacion_nombre: string; puesto_nombre: string; motivo: string; modalidad_texto: string;
  personas: number; dias: number; aprobado: boolean; estado: string; comentario: string;
};

export const ARCHIVOS: { tipo: string; titulo: string; ayuda: string; requerido: boolean }[] = [
  { tipo: "modalidades", titulo: "Maestro de modalidades", ayuda: "GenConsultaMaestroGrid: código, conceptos y valor por día", requerido: true },
  { tipo: "ubicaciones", titulo: "Ubicaciones y puestos con modalidad", ayuda: "GenConsultaMaestroGrid: modalidad de la ubicación y del puesto", requerido: true },
  { tipo: "contratos", titulo: "Contratos", ayuda: "GenConsultaMaestroGrid: estado, tipo de nómina y grupo de empleados", requerido: true },
  { tipo: "cuotas", titulo: "Maestro de cuotas", ayuda: "NomRptConCuotasGrid: préstamos, embargos y devengos por cuota", requerido: true },
  { tipo: "programacion", titulo: "Programación del mes", ayuda: "ReporteAsignacionResumido del mes completo", requerido: true },
  { tipo: "quincenal", titulo: "Nómina quincenal", ayuda: "NomLiqConTransColumGrid de la 2.ª quincena (se valida del 16 al 30). Puede recargarla las veces que necesite", requerido: true },
  { tipo: "mensual", titulo: "Nómina mensual", ayuda: "Nómina liquidada del mes (se valida del 1 al 30). Puede recargarla las veces que necesite", requerido: true },
];

export const ESTADOS: [string, string, string][] = [
  ["pendiente", "Pendiente", "bg-amber-100 text-amber-800"],
  ["revisada", "Revisada (correcta)", "bg-green-100 text-green-800"],
  ["justificada", "Justificada", "bg-sky-100 text-sky-800"],
  ["error", "Error a corregir", "bg-red-100 text-red-800"],
];

export const SEVERIDAD: Record<string, string> = {
  alta: "bg-red-50 text-red-700 ring-1 ring-red-200",
  media: "bg-amber-50 text-amber-800 ring-1 ring-amber-200",
  baja: "bg-slate-100 text-slate-600",
  info: "bg-sky-50 text-sky-800 ring-1 ring-sky-200",
};

/** Tipo informativo: personas con vacaciones para verificar en la liquidación (no son alertas pendientes). */
export const VACACIONES = "VACACIONES_VERIFICAR";

export const CLASE_DIA: Record<string, [string, string]> = {
  pagable: ["Pagable", "bg-marca-50 text-marca-800"],
  antes_vacaciones: ["Trabajado antes de vacaciones (va en la liquidación)", "bg-sky-50 text-sky-800"],
  novedad: ["Novedad", "bg-violet-50 text-violet-700"],
  vacaciones: ["Vacaciones", "bg-violet-100 text-violet-800"],
  vacio: ["Sin programación", "bg-slate-50 text-slate-400"],
};

export { pesos } from "@/lib/formato";
