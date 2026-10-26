"use client";

import { ShieldCheck } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useState } from "react";

export type ImagenMarca = { url: string; ancho: number; alto: number; bytes: number; heredada?: boolean } | null;
export type Marca = {
  nombre: string; subtitulo: string; color_primario: string; color_acento: string; color_barra: string; color_barra_fin: string;
  login_fondo: "degradado" | "color" | "imagen"; login_color: string; login_oscurecer: number; version: number;
  logo: ImagenMarca; favicon: ImagenMarca; fondo: ImagenMarca;
  /** Empresa dueña de la marca (null = general) y si la empresa tiene marca propia o usa la general */
  empresa?: string | null; propia?: boolean;
};

export const MARCA_INICIAL: Marca = {
  nombre: "Plataforma Servigpoder", subtitulo: "Desarrollos internos", color_primario: "#1d5fbf", color_acento: "#38bdf8",
  color_barra: "#0f2d5c", color_barra_fin: "#081a38", login_fondo: "degradado", login_color: "#0f2d5c", login_oscurecer: 45,
  version: 0, logo: null, favicon: null, fondo: null,
};

const CLAVE = "marca-plataforma"; // la última marca, para pintarla sin parpadeo al abrir

// --- Colores ---

function rgb(hex: string): [number, number, number] {
  const n = parseInt(hex.replace("#", ""), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/** Mezcla `hex` con blanco (peso > 0) o negro (peso < 0): 0.9 = casi blanco, -0.5 = mitad negro. */
export function mezclar(hex: string, peso: number): string {
  const destino = peso >= 0 ? 255 : 0;
  const p = Math.abs(peso);
  return "#" + rgb(hex).map((c) => Math.round(c + (destino - c) * p).toString(16).padStart(2, "0")).join("");
}

/** Variables CSS de la marca: tonos del color principal y del acento, y el degradado de la barra. */
export function variables(m: Marca): Record<string, string> {
  const p = m.color_primario;
  const a = m.color_acento;
  return {
    "--color-marca-50": mezclar(p, 0.93), "--color-marca-100": mezclar(p, 0.85), "--color-marca-200": mezclar(p, 0.7),
    "--color-marca-600": p, "--color-marca-700": mezclar(p, -0.18), "--color-marca-800": mezclar(p, -0.32),
    "--color-marca-900": mezclar(p, -0.5),
    "--color-acento-200": mezclar(a, 0.55), "--color-acento-300": mezclar(a, 0.3), "--color-acento-400": a,
    "--barra-desde": m.color_barra, "--barra-hasta": m.color_barra_fin,
    "--barra-medio": "#" + rgb(m.color_barra).map((c, i) => Math.round((c + rgb(m.color_barra_fin)[i]) / 2).toString(16).padStart(2, "0")).join(""),
  };
}

function aplicar(m: Marca) {
  const raiz = document.documentElement;
  Object.entries(variables(m)).forEach(([k, v]) => raiz.style.setProperty(k, v));
  // Un solo ícono, el de la marca: se quita cualquier otro y se deja de último en <head> (el navegador usa el último)
  let icono = document.querySelector<HTMLLinkElement>("link[rel='icon'][data-marca]");
  document.querySelectorAll<HTMLLinkElement>("link[rel~='icon']").forEach((l) => l !== icono && l.remove());
  if (!icono) {
    icono = document.createElement("link");
    icono.rel = "icon";
    icono.dataset.marca = "1";
  }
  icono.type = m.favicon ? "image/png" : "image/x-icon";
  const href = m.favicon ? m.favicon.url : "/favicon.ico";
  if (icono.getAttribute("href") !== href) icono.setAttribute("href", href);
  document.head.appendChild(icono);
  if (document.title === MARCA_INICIAL.nombre || !document.title) document.title = m.nombre;
}

// --- Contexto ---

type Ctx = { marca: Marca; recargar: () => Promise<void>; vistaPrevia: (m: Marca | null) => void };
const MarcaCtx = createContext<Ctx>({ marca: MARCA_INICIAL, recargar: async () => {}, vistaPrevia: () => {} });

export function MarcaProvider({ children }: { children: React.ReactNode }) {
  const [marca, setMarca] = useState<Marca>(MARCA_INICIAL);

  const recargar = useCallback(async () => {
    try {
      const r = await fetch("/api/marca", { credentials: "same-origin" });
      if (!r.ok) return;
      const m = (await r.json()).data as Marca;
      setMarca(m);
      aplicar(m);
      try {
        localStorage.setItem(CLAVE, JSON.stringify(m));
      } catch {}
    } catch {}
  }, []);

  useEffect(() => {
    try {
      const guardada = localStorage.getItem(CLAVE);
      if (guardada) {
        const m = JSON.parse(guardada) as Marca;
        setMarca(m);
        aplicar(m);
      }
    } catch {}
    recargar();
  }, [recargar]);

  // Vista previa mientras se edita en Administración → Marca (null = volver a la guardada)
  const vistaPrevia = useCallback((m: Marca | null) => aplicar(m ?? marca), [marca]);

  return <MarcaCtx.Provider value={{ marca, recargar, vistaPrevia }}>{children}</MarcaCtx.Provider>;
}

export function useMarca() {
  return useContext(MarcaCtx);
}

/** Logo de la marca; sin logo, el escudo sobre el color de la marca. */
export function LogoMarca({ alto = 36, marca: propia }: { alto?: number; marca?: Marca }) {
  const { marca: vigente } = useMarca();
  const m = propia ?? vigente;
  if (m.logo) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={m.logo.url} alt={m.nombre} style={{ height: alto, width: "auto", maxWidth: alto * 4 }} className="object-contain" />;
  }
  return (
    <div className="flex items-center justify-center rounded-xl bg-gradient-to-br from-acento-400 to-marca-600 ring-1 ring-white/20"
      style={{ height: alto, width: alto }}>
      <ShieldCheck className="text-white" style={{ height: alto * 0.55, width: alto * 0.55 }} strokeWidth={2.2} />
    </div>
  );
}

/** Fondo de la pantalla de ingreso según la marca: degradado, color sólido o imagen (oscurecida para leer el texto). */
export function estiloFondo(m: Marca): React.CSSProperties {
  if (m.login_fondo === "imagen" && m.fondo) {
    const capa = `rgba(0,0,0,${m.login_oscurecer / 100})`;
    return { backgroundImage: `linear-gradient(${capa}, ${capa}), url(${m.fondo.url})`, backgroundSize: "cover", backgroundPosition: "center" };
  }
  if (m.login_fondo === "color") return { background: m.login_color };
  return { background: `linear-gradient(135deg, ${m.color_barra}, ${m.color_barra_fin})` };
}
