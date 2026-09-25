export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function api<T>(path: string, options: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = options;
  const res = await fetch(`/api${path}`, {
    ...rest,
    credentials: "same-origin",
    headers: { ...(json !== undefined ? { "Content-Type": "application/json" } : {}), ...headers },
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
  if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/auth/login")) {
    window.location.href = "/login";
  }
  if (!res.ok) {
    let detalle = res.statusText;
    try {
      const body = await res.json();
      detalle = typeof body.detail === "string" ? body.detail : "Datos inválidos";
    } catch {}
    throw new ApiError(res.status, detalle);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export type RolResumen = { id: number; nombre: string };
export type Usuario = {
  id: number;
  username: string;
  nombre: string;
  email: string | null;
  activo: boolean;
  roles: RolResumen[];
};
export type Sesion = Usuario & { permisos: string[] };
export type Rol = RolResumen & { descripcion: string; permisos: string[] };
export type Permiso = { codigo: string; modulo: string; descripcion: string };
