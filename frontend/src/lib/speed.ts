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
  "salario" | "incapacidad" | "auxilio_transporte" | "horas_extras" | "comisiones" | "ley_2466" | "bonificaciones" | "rodamiento"
  | "pago_adicional" | "salud" | "pension" | "embargos" | "prestamos" | "cuotas", number>;

export type LiquidacionSpeed = {
  empleado_id: number; cedula: string; nombre: string; cargo: string; puesto: string; devengado: number; deducciones: number; neto: number;
  ibc: number; aplica_programacion: boolean; salario_mensual: number; alertas: string[];
  dias: { contrato: number; trabajados: number; no_laborados: number; incapacidad: number; incapacidad_100: number; incapacidad_pct: number;
    programados: number | null; variables: number };
  conceptos: Conceptos; descuentos: { id: number; tipo: string; descripcion: string; valor: number }[];
};

export type NovedadSpeed = {
  empleado_id: number; cedula: string; nombre: string; cargo: string; aplica_programacion: boolean; fecha_ingreso: string | null;
  dias_programados: number | null; ausencias: number; licencias: number; suspensiones: number; incapacidad: number; incapacidad_previos: number;
  observacion: string; origen: string | null;
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
