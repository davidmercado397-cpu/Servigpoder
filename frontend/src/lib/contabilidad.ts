/** Tipos y utilidades del desarrollo Contabilidad (Speed). */

export type Estado = "pendiente" | "lista" | "aparte" | "descartada" | "contabilizada";
export const ESTADOS: [Estado, string][] = [
  ["pendiente", "Por revisar"], ["lista", "Listas para el plano"], ["aparte", "Aparte (confirmar)"],
  ["contabilizada", "Contabilizadas"], ["descartada", "Descartadas"],
];
export type Linea = {
  id: number; orden: number; codigo_proveedor: string; descripcion: string; cantidad: number; valor_unitario: number; subtotal: number;
  iva_pct: number; iva_valor: number; producto: string; centro_costos: string; nota: string;
};
export type Factura = {
  id: number; estado: Estado; tipo: string; cuenta_cobro: boolean; motivo_aparte: string; leida_con: string; origen: string; prefijo: string; numero: string;
  fecha_emision: string | null; fecha_vencimiento: string | null; emisor_nit: string; emisor_dv: string; emisor_nombre: string;
  comprador_nit: string; comprador_nombre: string; subtotal: number; iva: number; total: number; nota: string; avisos: string[];
  faltantes: string[]; documento_numero: number | null; fecha_contable: string | null; correo_de: string; correo_asunto: string;
  creado_en: string | null;
  /** cuántos productos trae (en el detalle, la lista de líneas) */
  lineas: number;
};
export type FacturaCompleta = Omit<Factura, "lineas"> & { cufe: string; forma_pago: string; moneda: string; retenciones: Record<string, number>; lineas: Linea[] };
export type Producto = { codigo: string; nombre: string; activo: boolean };
export type Centro = { id: number; nombre: string; codigo: string; activo: boolean };

export const fecha = (iso: string | null | undefined) => (iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : "—");
export const fechaHora = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString("es-CO", { dateStyle: "short", timeStyle: "short" }) : "—";
export const plata = (v: number) => "$" + v.toLocaleString("es-CO", { maximumFractionDigits: 2 });
