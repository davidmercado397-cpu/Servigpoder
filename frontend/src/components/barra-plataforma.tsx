"use client";

import { ChevronDown, KeyRound, LayoutGrid, LogOut } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { SelectorEmpresa } from "@/components/selector-empresa";
import { LogoMarca, useMarca } from "@/lib/marca";
import { useSesion } from "@/lib/sesion";

export function iniciales(nombre: string) {
  return nombre.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]).join("").toUpperCase();
}

export async function cerrarSesion() {
  await api("/auth/logout", { method: "POST" }).catch(() => {});
  window.location.href = "/login";
}

/** Barra superior del portal y de la administración de la plataforma. */
export function BarraPlataforma({ children }: { children?: React.ReactNode }) {
  const sesion = useSesion();
  const { marca } = useMarca();
  const [menu, setMenu] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const cerrar = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setMenu(false); };
    document.addEventListener("mousedown", cerrar);
    return () => document.removeEventListener("mousedown", cerrar);
  }, []);

  return (
    <header className="sticky top-0 z-30 bg-gradient-to-r from-(--barra-desde) via-(--barra-medio) to-(--barra-hasta) text-white shadow-md">
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-4 px-4 lg:px-8">
        <Link href="/" className="flex items-center gap-3">
          <LogoMarca alto={36} />
          <div className="leading-tight">
            <p className="text-[15px] font-bold">{marca.nombre}</p>
            {marca.subtitulo && <p className="text-[10.5px] font-semibold uppercase tracking-[0.18em] text-acento-300/80">{marca.subtitulo}</p>}
          </div>
        </Link>
        <nav className="ml-4 hidden items-center gap-1 text-sm md:flex">{children}</nav>

        <div className="ml-auto"><SelectorEmpresa oscuro /></div>
        <div className="relative" ref={ref}>
          <button onClick={() => setMenu(!menu)} className="flex items-center gap-2 rounded-full py-1 pl-1 pr-2 transition hover:bg-white/10" aria-haspopup="menu" aria-expanded={menu}>
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-acento-400 to-marca-600 text-xs font-bold ring-2 ring-white/15">
              {iniciales(sesion.nombre)}
            </span>
            <span className="hidden text-sm sm:inline">{sesion.nombre}</span>
            <ChevronDown className="h-4 w-4 text-acento-200" />
          </button>
          {menu && (
            <div role="menu" className="absolute right-0 mt-2 w-60 overflow-hidden rounded-xl border border-slate-200 bg-white text-sm text-slate-700 shadow-xl">
              <div className="border-b border-slate-100 px-4 py-3">
                <p className="font-medium text-slate-900">{sesion.nombre}</p>
                <p className="text-xs text-slate-500">{sesion.roles.map((r) => r.nombre).join(", ") || "Sin rol"}</p>
              </div>
              <Link href="/" className="flex items-center gap-2 px-4 py-2 hover:bg-slate-50"><LayoutGrid className="h-4 w-4" /> Aplicaciones</Link>
              <Link href="/cuenta" className="flex items-center gap-2 px-4 py-2 hover:bg-slate-50"><KeyRound className="h-4 w-4" /> Seguridad de mi cuenta</Link>
              <button onClick={cerrarSesion} className="flex w-full items-center gap-2 border-t border-slate-100 px-4 py-2 text-left text-red-700 hover:bg-red-50">
                <LogOut className="h-4 w-4" /> Cerrar sesión
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
