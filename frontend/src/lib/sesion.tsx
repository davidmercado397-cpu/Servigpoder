"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { api, type Sesion } from "./api";

const SesionContext = createContext<Sesion | null>(null);

export function SesionProvider({ children }: { children: React.ReactNode }) {
  const [sesion, setSesion] = useState<Sesion | null>(null);

  useEffect(() => {
    api<Sesion>("/auth/me").then(setSesion).catch(() => {});
  }, []);

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
