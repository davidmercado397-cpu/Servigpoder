/** Tipos y utilidades del desarrollo Contabilidad (Speed). */

/** Filas por página de los listados de Contabilidad */
export const TAMANOS = [20, 50, 100] as const;

export type Estado = "pendiente" | "lista" | "aparte" | "descartada" | "contabilizada";
export const ESTADOS: [Estado, string][] = [
  ["pendiente", "Por revisar"], ["lista", "Listas para el plano"], ["aparte", "Aparte (confirmar)"],
  ["contabilizada", "Contabilizadas"], ["descartada", "Descartadas"],
];
export type Linea = {
  id: number; orden: number; codigo_proveedor: string; descripcion: string; cantidad: number; valor_unitario: number; subtotal: number;
  iva_pct: number; iva_valor: number; producto: string; centro_costos: string; nota: string;
  /** No va en el plano (la quitó contabilidad o es un negativo mínimo) */
  excluida?: boolean;
  /** Valor unitario con que va en el plano si se le restó un valor negativo de la factura */
  valor_plano?: number | null;
  /** La cuenta que propuso el agente (si contabilidad la cambia, el agente ofrece aprender) */
  producto_ia?: string;
};
/** Regla contable de la empresa que el agente aplica por encima de la norma general */
export type Regla = {
  id: number; texto: string; cuentas: string; activa: boolean; origen: "manual" | "correccion"; ejemplo: string; usos: number;
  /** Veces que se corrigió una factura donde el agente la aplicó (si sube, hay que revisarla) */
  corregida: number;
  creado_en: string | null; actualizado_en: string | null;
};
/** Consumo del agente contable en el mes */
export type UsoAgente = {
  desde: string; modelo: string; modelo_vectores: string; tokens_entrada: number; tokens_salida: number;
  por_tipo: Record<string, { veces: number; tokens_entrada: number; tokens_salida: number }>;
};
/** Una cuenta que contabilidad corrigió al guardar: el agente ofrece aprenderla como regla */
export type Correccion = { linea_id: number; orden: number; descripcion: string; cuenta_agente: string; cuenta_correcta: string };
export type Factura = {
  id: number; estado: Estado; tipo: string; cuenta_cobro: boolean; motivo_aparte: string; leida_con: string; origen: string; prefijo: string; numero: string;
  fecha_emision: string | null; fecha_vencimiento: string | null; emisor_nit: string; emisor_dv: string; emisor_nombre: string;
  comprador_nit: string; comprador_nombre: string; subtotal: number; iva: number; total: number; nota: string; avisos: string[];
  faltantes: string[]; documento_numero: number | null; fecha_contable: string | null; correo_de: string; correo_asunto: string;
  creado_en: string | null;
  /** cuántos productos trae (en el detalle, la lista de líneas) */
  lineas: number;
};
/** Con qué producto se ha registrado el proveedor en World Office (informe «Compras por Producto y Proveedor») */
export type OpcionProveedor = { producto: string; nombre: string; compras: number; ultima_fecha: string | null; ultimo_precio: number };
export type FacturaCompleta = Omit<Factura, "lineas"> & { cufe: string; forma_pago: string; moneda: string; retenciones: Record<string, number>; lineas: Linea[];
  opciones_proveedor?: OpcionProveedor[];
  /** Cómo se restaron los valores negativos de los otros productos */
  ajuste_negativos?: string[] };
export type Producto = { codigo: string; nombre: string; activo: boolean };
export type Centro = { id: number; nombre: string; codigo: string; activo: boolean };

export const fecha = (iso: string | null | undefined) => (iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : "—");
export const fechaHora = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString("es-CO", { dateStyle: "short", timeStyle: "short" }) : "—";
export const plata = (v: number) => "$" + v.toLocaleString("es-CO", { maximumFractionDigits: 2 });

// --- Legalizaciones ---
export type EstadoLeg = "pendiente" | "lista" | "contabilizada" | "descartada";
export const ESTADOS_LEG: [EstadoLeg, string][] = [["pendiente", "Por revisar"], ["lista", "Listas para el plano"], ["contabilizada", "Contabilizadas"], ["descartada", "Descartadas"]];
export type Legalizacion = {
  id: number; estado: EstadoLeg; numero_formato: string; archivo: string; leida_con: string; colaborador_nombre: string; colaborador_documento: string;
  elabora_documento: string; sucursal: string; motivo: string; fecha_legalizacion: string | null; anticipo_fecha: string | null; anticipo_valor: number;
  anticipo_descripcion: string; total_formato: number; total: number; gastos: number; nota: string; avisos: string[]; faltantes: string[];
  soportes_revisados: boolean; sin_soporte: number; documento_numero: number | null; fecha_contable: string | null; creado_en: string | null;
};
export type LineaLeg = {
  id: number; orden: number; fecha: string | null; beneficiario: string; documento: string; columna: string; valor: number; iva: number; retencion: number;
  detalle: string; cuenta: string; soporte: boolean | null; soporte_nota: string; excluida: boolean;
};
export type Movimiento = { cuenta: string; nota: string; tercero: string; debito: number; credito: number };
export type LegalizacionCompleta = Legalizacion & { elabora_nombre: string; colaborador_en_listado: boolean; lineas: LineaLeg[]; movimientos: Movimiento[] };
export type Persona = { id: number; documento: string; nombre: string; activo: boolean };
export const COLUMNAS_LEG: Record<string, string> = {
  transporte: "Transporte", parqueo: "Parqueo", peajes: "Peajes", aseo_cafeteria: "Aseo y cafetería", alojamiento: "Alojamiento",
  alimentacion: "Alimentación", combustible: "Combustible", correo: "Correo y portes", otros: "Otros gastos",
};
