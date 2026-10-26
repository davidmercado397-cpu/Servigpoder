/** Tipos y utilidades de Costeo y MFP's. */
export { pesos } from "@/lib/formato";

export type Cliente = { id: number; nit: string; nombre: string };
export type TipoItem = { id: number; codigo: string; nombre: string; unidad: "pesos" | "pesos_mes" | "horas"; reembolsable: boolean; cuenta_en_mfp: boolean; activo: boolean };
export type AlertaMfp = { tipo: string; severidad: "alta" | "media" | "baja"; mensaje: string };
export type Movimiento = { id: number; fecha: string; valor: number; descripcion: string; soporte: string; excede: boolean; autorizacion: string; creado_en: string };
export type AnioBolsa = { anio: number; desde: string | null; hasta: string | null; pactado: number; usado: number; saldo: number; vencido: boolean; actual: boolean };
export type ItemMfp = {
  id: number; tipo: string; tipo_codigo: string; unidad: TipoItem["unidad"]; descripcion: string; reembolsable: boolean; cuenta_en_mfp: boolean;
  pactado: number; pactado_total: number; ejecutado: number; pendiente: number; causado: number | null; reembolso: number; excede: boolean;
  anios: AnioBolsa[]; movimientos?: Movimiento[];
};
export type Mfp = {
  id: number; numero: string; contrato: string; cliente: Cliente; fecha_inicio: string | null; fecha_fin: string | null; duracion_meses: number | null;
  valor_mensual: number; facturacion_total: number; pct_comercial: number | null; pct_mfp: number | null; diferencia_pct: number | null;
  pactado: number; ejecutado: number; pendiente: number; pct_ejecucion: number | null; reembolso: number; meses_pendientes: number | null;
  estado: "vigente" | "vencida" | "terminada"; terminada: boolean; fecha_terminacion: string | null; notas: string; costeo_id: number | null;
  alertas: AlertaMfp[]; items: ItemMfp[];
};

export const ESTADO_MFP: Record<string, string> = {
  vigente: "bg-green-100 text-green-800", vencida: "bg-slate-200 text-slate-700", terminada: "bg-red-100 text-red-700",
};
export const SEVERIDAD: Record<string, string> = { alta: "text-red-700", media: "text-amber-700", baja: "text-slate-500" };
export const UNIDAD: Record<string, string> = { pesos: "Pesos", pesos_mes: "Pesos por mes", horas: "Horas por año" };
export const ESTADO_COSTEO: Record<string, string> = {
  borrador: "bg-amber-100 text-amber-800", enviado: "bg-sky-100 text-sky-800", aprobado: "bg-green-100 text-green-800", rechazado: "bg-red-100 text-red-700",
};

export function pct(v: number | null | undefined, decimales = 2): string {
  if (v === null || v === undefined) return "—";
  return `${(v * 100).toFixed(decimales).replace(".", ",")} %`;
}

export function fecha(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [a, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${a}`;
}

export function valorItem(v: number, unidad: string): string {
  if (unidad === "horas") return `${v.toLocaleString("es-CO")} h`;
  return "$" + Math.round(v).toLocaleString("es-CO");
}

export function hoyISO(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
