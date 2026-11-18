/** Tipos y utilidades de la Nómina Speed. */
export { pesos } from "@/lib/formato";

export type EmpleadoSpeed = {
  id: number; cedula: string; nombre: string; fecha_ingreso: string | null; tipo_contrato: string; grupo: string; cargo: string; area: string;
  puesto: string; cliente: string; tipo_turno: string; salario: number; auxilio_listado: number; horas_extras: number; comisiones: number;
  ley_2466: number; bonificaciones: number; rodamiento: number; nota: string; aplica_programacion: boolean; activo: boolean;
};

export type PeriodoSpeed = {
  id: number; anio: number; mes: number; quincena: number; estado: "abierto" | "cerrado"; calculado_en: string | null;
  personas: number; devengado: number; deducciones: number; neto: number; novedades: number;
};

export type Conceptos = Record<
  "salario" | "vacaciones" | "incapacidad" | "auxilio_transporte" | "horas_extras" | "comisiones" | "ley_2466" | "bonificaciones" | "rodamiento"
  | "turnos_adicionales" | "pago_adicional" | "salud" | "pension" | "embargos" | "prestamos" | "cuotas", number>;

export type LiquidacionSpeed = {
  empleado_id: number; cedula: string; nombre: string; cargo: string; puesto: string; devengado: number; deducciones: number; neto: number;
  ibc: number; aplica_programacion: boolean; salario_mensual: number; alertas: string[];
  dias: { contrato: number; trabajados: number; no_laborados: number; incapacidad: number; incapacidad_100: number; incapacidad_pct: number;
    programados: number | null; variables: number; vacaciones?: number; remunerados?: number; laborados?: number; turnos_tad?: number;
    turnos_tan?: number };
  conceptos: Conceptos; descuentos: { id: number; tipo: string; descripcion: string; valor: number }[];
};

export type NovedadSpeed = {
  empleado_id: number; cedula: string; nombre: string; cargo: string; aplica_programacion: boolean; fecha_ingreso: string | null;
  dias_programados: number | null; ausencias: number; licencias: number; suspensiones: number; desprogramados: number;
  permisos_remunerados: number; vacaciones: number; incapacidad: number; incapacidad_previos: number; turnos_tad: number; turnos_tan: number;
  sin_programacion: number; programacion: ProgramacionDias | null; observacion: string; origen: string | null;
};

/** Lo que trajo el archivo de programación para una persona en la quincena. */
export type ProgramacionDias = { dias: Record<string, string>; puestos: string[]; conflictos: string[]; tramos_incapacidad: number[] };

export type ResultadoProgramacion = {
  hojas: string[]; personas: number; cargadas: number; quitadas: number; avisos: string[];
  no_encontrados: { cedula: string; nombre: string; puestos: string[] }[];
  por_nombre: { nombre: string; cedula: string; en_archivo: string }[];
  sin_programacion: { cedula: string; nombre: string; cargo: string }[];
  conflictos: { cedula: string; nombre: string; detalle: string[] }[];
  resumen: { vacaciones: number; incapacidad: number; no_laborados: number; remunerados: number; turnos_tad: number; turnos_tan: number;
    sin_programacion: number };
};

/** Códigos de la programación: nombre y color de la casilla. */
export const CODIGOS_PROGRAMACION: Record<string, [string, string]> = {
  D: ["Turno diurno", "bg-sky-100 text-sky-800"], N: ["Turno nocturno", "bg-indigo-100 text-indigo-800"],
  A: ["Turno 06:00 a 14:00", "bg-sky-100 text-sky-800"], B: ["Turno 14:00 a 22:00", "bg-sky-100 text-sky-800"],
  C: ["Turno 22:00 a 06:00", "bg-indigo-100 text-indigo-800"], IND: ["Inducción diurno", "bg-sky-100 text-sky-800"],
  INN: ["Inducción nocturno", "bg-indigo-100 text-indigo-800"], TMA: ["Turno mutuo acuerdo", "bg-sky-100 text-sky-800"],
  DISP: ["Disponible", "bg-sky-100 text-sky-800"], X: ["Descanso", "bg-slate-100 text-slate-500"],
  TAD: ["Turno adicional diurno", "bg-emerald-200 text-emerald-900"], TAN: ["Turno adicional nocturno", "bg-emerald-200 text-emerald-900"],
  AUS: ["Ausencia", "bg-red-100 text-red-800"], PNR: ["Permiso no remunerado", "bg-red-100 text-red-800"],
  SUS: ["Suspensión", "bg-red-100 text-red-800"], RUN: ["Renuncia", "bg-red-100 text-red-800"], DESPR: ["Desprogramado", "bg-red-100 text-red-800"],
  PR: ["Permiso remunerado", "bg-amber-100 text-amber-800"], CD: ["Calamidad doméstica", "bg-amber-100 text-amber-800"],
  LUT: ["Licencia de luto", "bg-amber-100 text-amber-800"], DDF: ["Día de la familia", "bg-amber-100 text-amber-800"],
  LYM: ["Ley María", "bg-amber-100 text-amber-800"], VAC: ["Vacaciones", "bg-violet-100 text-violet-800"],
  INC: ["Incapacidad", "bg-orange-100 text-orange-800"],
};

export type DescuentoSpeed = {
  id: number; empleado_id: number; cedula: string; nombre: string; tipo: "embargo" | "prestamo" | "cuota" | "adicional"; tipo_nombre: string;
  descripcion: string; valor_total: number | null; cuota: number; salarial: boolean; activo: boolean; aplicado: number; saldo: number | null;
};

export const MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
export const nombrePeriodo = (p: { anio: number; mes: number; quincena: number }) =>
  `${p.quincena === 1 ? "1.ª" : "2.ª"} quincena de ${MESES_CORTOS[p.mes - 1]} ${p.anio} (${p.quincena === 1 ? "1 al 15" : "16 al 30"})`;

export const TIPOS_DESCUENTO: [DescuentoSpeed["tipo"], string][] = [
  ["prestamo", "Préstamo"], ["embargo", "Embargo"], ["cuota", "Cuota por mayor valor pagado"], ["adicional", "Pago adicional (menor valor pagado)"],
];
