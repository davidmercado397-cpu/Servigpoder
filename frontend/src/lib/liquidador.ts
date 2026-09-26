/** Tipos y etiquetas del Liquidador de horas. */

export type Periodo = {
  id: number; anio: number; mes: number; quincena: number; desde: string; hasta: string;
  estado: "borrador" | "calculada" | "cerrada"; archivo: string | null; advertencias: string[];
  cargado_en: string | null; calculado_en: string | null; cerrado_en: string | null; creado_en: string | null; empleados: number;
};

export type Resultado = {
  empleado_id: number; documento: string; nombre: string; cargo: string;
  horas: Record<string, number>; dias: Record<string, number>; total_horas: number;
};

export type Dia = { fecha: string; codigo: string; turno: string; tipo_dia: string; clase: string; horas: Record<string, number> };

export type Turno = {
  id: number; codigo: string; nombre: string; hora_inicio: string; hora_fin: string; horas_ordinarias: number;
  horas_extras: number; remunerado: boolean; incapacidad: boolean; activo: boolean; clase: string;
};

export type Matriz = Record<string, Record<string, number>>;

export type Festivo = { fecha: string; descripcion: string; origen: "nacional" | "quitado" | "manual"; ajuste_id: number | null; vigente: boolean };

export type Empleado = { id: number; documento: string; nombre: string; cargo: string; quincenas: number; ultima: string | null };

/** Los 12 conceptos, en el orden de las columnas del archivo de liquidación. */
export const CONCEPTOS: [string, string, string][] = [
  ["ordinary_day", "Diurnas ordinarias", "Diurnas ord."],
  ["ordinary_night", "Recargo nocturno", "Rec. noct."],
  ["holiday_day_surcharge", "Recargo festivo diurno", "Rec. fest. diur."],
  ["holiday_night_surcharge", "Recargo festivo nocturno", "Rec. fest. noct."],
  ["sunday_surcharge", "Recargo dominical diurno", "Rec. dom. diur."],
  ["sunday_night_surcharge", "Recargo dominical nocturno", "Rec. dom. noct."],
  ["overtime_day", "Extras ordinarias diurnas", "Ext. diur."],
  ["overtime_night", "Extras ordinarias nocturnas", "Ext. noct."],
  ["holiday_overtime_day", "Extras festivas diurnas", "Ext. fest. diur."],
  ["holiday_overtime_night", "Extras festivas nocturnas", "Ext. fest. noct."],
  ["sunday_overtime_day", "Extras dominicales diurnas", "Ext. dom. diur."],
  ["sunday_overtime_night", "Extras dominicales nocturnas", "Ext. dom. noct."],
];

/** Las 8 columnas de la matriz de un turno. */
export const TIPOS_DIA: [string, string][] = [
  ["weekday", "Ordinario"], ["saturday", "Sábado"], ["saturday_holiday", "Sáb. festivo"], ["sunday", "Domingo"],
  ["sunday_holiday_eve", "Dom. ant. fest."], ["holiday", "Festivo"], ["holiday_eve", "Ant. festivo"], ["holiday_double", "Fest. ant. fest."],
];

/** Clase de día: [clave, total, color, encabezado corto, un día] */
export const CLASES: [string, string, string, string, string][] = [
  ["trabajado", "Días trabajados", "bg-marca-50 text-marca-700", "Trab.", "Trabajado"],
  ["descanso_pago", "Descansos pagos", "bg-emerald-50 text-emerald-700", "Desc. pago", "Descanso pago"],
  ["libre", "Libres", "bg-slate-100 text-slate-700", "Libres", "Libre"],
  ["ausencia", "Ausencias", "bg-red-50 text-red-700", "Aus.", "Ausencia"],
  ["incapacidad", "Incapacidades", "bg-amber-50 text-amber-800", "Incap.", "Incapacidad"],
  ["novedad", "Días con novedad", "bg-violet-50 text-violet-700", "Novedad", "Novedad"],
];

export const ESTADO_PERIODO: Record<string, [string, string]> = {
  borrador: ["Sin cargar", "bg-amber-100 text-amber-800"],
  calculada: ["Calculada", "bg-green-100 text-green-800"],
  cerrada: ["Cerrada", "bg-slate-200 text-slate-700"],
};

export function horas(v: number | undefined): string {
  if (!v) return "–";
  return v.toLocaleString("es-CO", { maximumFractionDigits: 2 });
}
