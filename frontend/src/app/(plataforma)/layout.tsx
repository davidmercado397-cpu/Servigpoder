"use client";

import { SesionProvider } from "@/lib/sesion";

/** Toda la plataforma (portal, administración y apps) requiere sesión. */
export default function PlataformaLayout({ children }: { children: React.ReactNode }) {
  return <SesionProvider>{children}</SesionProvider>;
}
