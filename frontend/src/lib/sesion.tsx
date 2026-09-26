"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { ApiError, api, type Sesion } from "./api";

const SesionContext = createContext<Sesion | null>(null);

export function SesionProvider({ children }: { children: React.ReactNode }) {
  const [sesion, setSesion] = useState<Sesion | null>(null);
  const [fallo, setFallo] = useState(false);

  useEffect(() => {
    api<Sesion>("/auth/me")
      .then((s) => {
        // Con contraseña temporal solo se permite la pantalla de cambio
        if (s.debe_cambiar_password && !window.location.pathname.startsWith("/cuenta")) {
          window.location.href = "/cuenta?forzado=1";
          return;
        }
        setSesion(s);
      })
      .catch((e) => {
        // Sesión vencida o revocada (la cookie sigue en el navegador): volver a ingresar
        if (e instanceof ApiError && e.status === 401) {
          window.location.href = "/login?expirada=1";
          return;
        }
        setFallo(true);
      });
  }, []);

  if (fallo) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-3 text-slate-600">
        No fue posible conectar con el servidor.
        <button className="btn-primario" onClick={() => window.location.reload()}>Reintentar</button>
      </div>
    );
  }
  if (!sesion) {
    return <div className="flex h-screen items-center justify-center text-slate-500">Cargando…</div>;
  }
  return <SesionContext.Provider value={sesion}>{children}</SesionContext.Provider>;
}

export function useSesion(): Sesion {
  const s = useContext(SesionContext);
  if (!s) throw new Error("useSesion fuera de SesionProvider");
  return s;
}

export function usePermiso(codigo: string): boolean {
  return useSesion().permisos.includes(codigo);
}
