/** Gestión humana de SERA: incapacidades, restricciones médicas y casos jurídicos (routes/gestion.py). No afecta la nómina. */

export type DocumentoAdjunto = { id: number; nombre: string; mime: string; bytes: number };

export type Incapacidad = {
  id: number; documento: string; nombre: string; empleado_id: number | null; puesto: string | null;
  novedad: string; origen: string | null; prorroga: boolean; desde: string; hasta: string; dias: number;
  entidad: string | null; cie: string | null; diagnostico: string | null; soporte: string | null; observacion: string | null;
  origen_registro: string; vigente: boolean;
  /** Días de la incapacidad inicial más sus prórrogas hasta esta (null en licencias) */
  acumulado: number | null; inicio_caso: string | null; alerta: string | null;
  cie_desconocidos: string[]; documentos: DocumentoAdjunto[];
};
export type ResumenIncapacidades = { registros: number; dias: number; personas: number; vigentes: number; prolongadas: number };

export type Restriccion = {
  id: number; documento: string; nombre: string; empleado_id: number | null; puesto: string | null; tipo: string;
  desde: string | null; hasta: string | null; cie: string | null; diagnostico: string | null; detalle: string | null;
  observacion: string | null; estado: "vigente" | "vencida" | "seguimiento" | "programada"; documentos: DocumentoAdjunto[];
};

export type Actuacion = { id: number; fecha: string | null; descripcion: string; medio: string | null };
export type Caso = {
  id: number; documento: string; nombre: string; empleado_id: number | null; tipo: string; asunto: string; recibido: string;
  vence: string | null; estado: string; vencido: boolean; dias_abierto: number | null; contacto: string | null; observacion: string | null;
  origen_registro: string; actuaciones: Actuacion[]; documentos: DocumentoAdjunto[];
};

export type CuotaPendiente = {
  id: number; empleado_id: number; documento: string; nombre: string; tipo: "prestamo" | "embargo" | "cuota"; descripcion: string;
  valor_mensual: number | null; porcentaje: number | null; monto_total: number | null; descontado: number; saldo: number | null;
  desde: string; hasta: string | null; quincena: string;
};

export type SalidaHistorico = {
  id: number; empleado_id: number; documento: string; nombre: string; puesto: string | null; tipo: string; desde: string | null;
  hasta: string | null; retorno: string | null; dias_habiles: number | null; estado: string; observacion: string | null; origen: string;
};

export const NOVEDADES: [string, string][] = [["incapacidad", "Incapacidad"], ["licencia_maternidad", "Licencia de maternidad"],
  ["licencia_paternidad", "Licencia de paternidad"], ["calamidad", "Calamidad"], ["otra", "Otra"]];
export const ORIGENES: [string, string][] = [["enfermedad_general", "Enfermedad general"], ["accidente_trabajo", "Accidente de trabajo"],
  ["enfermedad_laboral", "Enfermedad laboral"], ["accidente_transito", "Accidente de tránsito"]];
export const ORIGEN_CORTO: Record<string, string> = { enfermedad_general: "EG", accidente_trabajo: "AT", enfermedad_laboral: "EL", accidente_transito: "Tránsito" };
export const SOPORTES: [string, string][] = [["fisico", "Física"], ["escaneado", "Escaneada"], ["virtual", "Virtual"]];
export const TIPOS_RESTRICCION: [string, string][] = [["restriccion", "Restricción"], ["recomendacion", "Recomendación"], ["oncologico", "Caso oncológico"]];
export const TIPOS_CASO: [string, string][] = [["derecho_peticion", "Derecho de petición"], ["tutela", "Tutela"], ["desacato", "Incidente de desacato"],
  ["demanda", "Demanda"], ["orden_judicial", "Orden judicial"], ["acoso_laboral", "Acoso laboral"], ["otro", "Otro"]];
export const ESTADOS_CASO: [string, string][] = [["abierto", "Abierto"], ["contestado", "Contestado"], ["cerrado", "Cerrado"]];

export const etiqueta = (lista: [string, string][], v: string | null | undefined) => lista.find(([k]) => k === v)?.[1] ?? v ?? "—";

/** 2026-01-31 → 31/01/2026 */
export const fechaCorta = (iso: string | null | undefined) => (iso ? iso.slice(0, 10).split("-").reverse().join("/") : "—");

/** Búsqueda inicial desde la URL (?q=…), p. ej. al llegar desde la ficha del empleado */
export const qInicial = () => (typeof window === "undefined" ? "" : new URLSearchParams(window.location.search).get("q") ?? "");
