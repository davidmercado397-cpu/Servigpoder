/** Formato estándar de respuesta del backend. */
export type Envelope<T> = {
  success: boolean;
  data: T | null;
  error: { code: string; message: string; details?: unknown[] | null } | null;
  meta: { api_version: string; request_id: string; timestamp: string; extra?: Record<string, unknown> | null };
};

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public code = "ERROR",
    public requestId = "",
    public details: unknown[] | null = null,
  ) {
    super(message);
  }
}

type Opciones = RequestInit & { json?: unknown };

export async function apiEnvelope<T>(path: string, options: Opciones = {}): Promise<Envelope<T>> {
  const { json, headers, ...rest } = options;
  const res = await fetch(`/api${path}`, {
    ...rest,
    credentials: "same-origin",
    headers: {
      // Defensa CSRF: el backend exige esta cabecera en toda petición que modifica datos
      "X-Requested-With": "fetch",
      ...(json !== undefined ? { "Content-Type": "application/json" } : {}),
      ...headers,
    },
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
  let body: Envelope<T> | null = null;
  try {
    body = (await res.json()) as Envelope<T>;
  } catch {}

  if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/auth/")) {
    window.location.href = "/login";
  }
  if (!res.ok || !body?.success) {
    const e = body?.error;
    throw new ApiError(res.status, e?.message ?? `Error ${res.status}`, e?.code, body?.meta?.request_id, e?.details ?? null);
  }
  return body;
}

export async function api<T>(path: string, options: Opciones = {}): Promise<T> {
  return (await apiEnvelope<T>(path, options)).data as T;
}

export function subirArchivo<T>(path: string, archivo: File, campos: Record<string, string> = {}): Promise<T> {
  const form = new FormData();
  form.append("archivo", archivo);
  Object.entries(campos).forEach(([k, v]) => form.append(k, v));
  return api<T>(path, { method: "POST", body: form });
}

export function mensajeError(err: unknown): string {
  if (err instanceof ApiError) {
    const detalles = (err.details ?? [])
      .map((d) => (typeof d === "object" && d && "mensaje" in d ? `${(d as { campo?: string }).campo ?? ""}: ${(d as { mensaje: string }).mensaje}` : ""))
      .filter(Boolean);
    return [err.message, ...detalles].join(" · ");
  }
  return "No fue posible conectar con el servidor";
}

// ---- Tipos ----------------------------------------------------------------

export type RolResumen = { id: number; nombre: string };
export type Usuario = { id: number; username: string; nombre: string; email: string | null; activo: boolean; roles: RolResumen[] };
export type Sesion = Usuario & { permisos: string[] };
export type Rol = RolResumen & { descripcion: string; permisos: string[] };
export type Permiso = { codigo: string; modulo: string; descripcion: string };

export type Ubicacion = { id: number; codigo: string; nombre: string; nit: string | null; ciudad: string | null };
export type Puesto = { id: number; codigo: string; descripcion: string; tipo: string; excluido: boolean; activo: boolean; ubicacion: Ubicacion };
export type Turno = { codigo: string; descripcion: string; clase: string; franjas: { inicio: string; fin: string }[] };
export type Novedad = { codigo: string; descripcion: string; requiere_cubrimiento: boolean };
export type PorAclarar = { codigo_siesa: string; descripcion: string; filas: number; motivo: string; puesto_sugerido: Puesto | null };

export type Periodo = {
  id: number; anio: number; mes: number; estado: string; proyectado_desde_id: number | null; creado_en: string;
  puestos: number; hombres: string; requieren_revision: number; excluidos: number;
};
export type Franja = { id?: number; dias: number; inicio: string; fin: string; cantidad: number };
export type Excepcion = { id: number; fecha: string; sin_servicio: boolean; inicio: string | null; fin: string | null; cantidad: number; observacion: string };
export type MatrizPuesto = {
  id: number; puesto: Puesto; hombres: string; secuencia: string; jornada: string; incluye_festivos: boolean;
  requiere_revision: boolean; nota: string; franjas: Franja[]; excepciones: Excepcion[];
};
export type DiaRequerido = { fecha: string; festivo: string | null; franjas: { inicio: string; fin: string }[]; horas: number };
export type Carga = {
  id: number; archivo: string; compania: string; desde: string; hasta: string; anio: number; mes: number; cargado_en: string;
  resumen: {
    filas: number; empleados: number; puestos: number; dias_por_clase: Record<string, number>;
    puestos_sin_equivalencia: { codigo: string; descripcion: string }[];
    codigos_desconocidos: { codigo: string; veces: number }[];
  };
};

export type ResumenAnalisis = {
  desde: string; hasta: string; anio: number; mes: number; cobertura_pct: number | null;
  requeridas?: number; programadas?: number; descubiertas?: number; exceso?: number;
  puestos?: number; puestos_ok?: number; puestos_hueco?: number; puestos_exceso?: number; puestos_mixto?: number;
  puestos_sin_matriz?: number; puestos_sin_programacion?: number; hombres?: number; fijos?: number;
  puestos_fijos_de_mas?: number; puestos_fijos_de_menos?: number; filas_sin_puesto?: number;
  por_ciudad: Record<string, { puestos?: number; requeridas?: number; descubiertas?: number; exceso?: number; cobertura_pct: number | null;
    puestos_hueco?: number; puestos_exceso?: number; puestos_mixto?: number }>;
};
export type Analisis = { id: number; carga_id: number; periodo_id: number; generado_en: string; resumen: ResumenAnalisis; desactualizado: boolean; motivo_desactualizado: string | null };
export type MesDisponible = { anio: number; mes: number; carga_id: number; desde: string; hasta: string; analisis_id: number | null; tiene_matriz: boolean };
export type PuestoAnalisis = {
  puesto: Puesto; hombres: string; fijos: number; personas: number; horas_requeridas: string; horas_programadas: string;
  horas_descubiertas: string; horas_exceso: string; dias_hueco: number; dias_exceso: number; estado: string;
};
export type Tramo = { tipo: "hueco" | "exceso"; inicio: string; fin: string; personas: number };
export type DiaAnalisis = { fecha: string; horas_requeridas: string; horas_programadas: string; horas_descubiertas: string; horas_exceso: string; estado: string; detalle: Tramo[] };
export type PersonaPuesto = { cedula: string; nombre: string; titular: boolean; puesto_titular: string | null; dias: Record<string, string>; clases: Record<string, string> };
export type DetallePuesto = { resumen: PuestoAnalisis; franjas: Franja[]; incluye_festivos: boolean | null; festivos: Record<string, string>; dias: DiaAnalisis[]; personas: PersonaPuesto[] };

export type Cubrimiento = {
  id: number; puesto: Puesto; fecha: string; cedula: string; nombre: string; codigo_turno: string; horas: string;
  puesto_titular: string | null; motivo: "novedad" | "descanso" | "sin_motivo"; referencia: { cedula: string; nombre: string; codigo: string }[];
  genera_exceso: boolean; doble_turno: boolean; estado_auto: string; estado: string;
  comentario: string | null; decidido_por: string | null; decidido_en: string | null;
};
export type PersonaBolsa = { cedula: string; nombre: string; bolsas: string[]; dias_sin_puesto: string[]; horas_sin_puesto: number; dias_en_puesto: number };
export type AlertaT = { nivel: "critica" | "advertencia" | "info"; titulo: string; detalle: string; enlace: string | null; items: Record<string, string | number>[] };
export type Historico = {
  carga_id: number; anio: number; mes: number; desde: string; hasta: string; cargado_en: string; archivo: string; analisis_id: number | null;
  cobertura_pct: number | null; requeridas: number | null; descubiertas: number | null; exceso: number | null; puestos: number | null;
  puestos_hueco: number | null; puestos_exceso: number | null; puestos_mixto: number | null; cubrimientos: number | null; cubrimientos_pendiente: number | null;
};
export type Comparacion = {
  anterior: number; actual: number; desde: string; hasta: string; total: number; por_tipo: Record<string, number>; personas: number; puestos: number;
  cambios: { tipo: string; cedula: string; nombre: string; puesto: string; fecha: string; antes: string | null; despues: string | null }[];
  truncado: boolean;
  impacto: { puesto_id: number; puesto: string; descubiertas_antes: number; descubiertas_despues: number; exceso_antes: number; exceso_despues: number }[];
};
export type Parametro = { clave: string; valor: string; descripcion: string };
