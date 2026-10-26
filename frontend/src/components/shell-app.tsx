"use client";

import { Bell, ChevronsLeft, ChevronsRight, KeyRound, LayoutGrid, LogOut, Menu, Users, X, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Asistente, type ConfigAsistente } from "@/components/asistente";
import { api } from "@/lib/api";
import { SelectorEmpresa } from "@/components/selector-empresa";
import { useSesion } from "@/lib/sesion";

/** Panel lateral con el color de la marca en diseño sobrio (plano), contenido sobre gris suave, barra superior y asistente
    comunes a los desarrollos. */

export type ItemMenu = { href: string; texto: string; icono: LucideIcon; permiso?: string; contador?: string; critico?: boolean };
export type GrupoMenu = { grupo: string; items: ItemMenu[] };

type PropsShell = {
  nombre: string;
  subtitulo: string;
  icono: LucideIcon;
  /** Ruta de inicio de la app (p. ej. "/capacidad") */
  inicio: string;
  menu: GrupoMenu[];
  /** Contadores de los ítems del menú (y de la campana) */
  contadores?: { url: string; permiso: string };
  campana?: { total: string; criticas: string };
  asistente?: ConfigAsistente & { permiso: string };
  children: React.ReactNode;
};

const CLAVE_COLAPSADO = "menu-colapsado";

function activo(pathname: string, href: string, inicio: string) {
  return href === inicio ? pathname === inicio : pathname === href || pathname.startsWith(`${href}/`);
}

function iniciales(nombre: string) {
  return nombre.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]).join("").toUpperCase();
}

export function ShellApp({ nombre, subtitulo, icono: IconoApp, inicio, menu, contadores: fuente, campana, asistente, children }: PropsShell) {
  const sesion = useSesion();
  const pathname = usePathname();
  const [colapsado, setColapsado] = useState(false);
  const [movilAbierto, setMovilAbierto] = useState(false);
  const [contadores, setContadores] = useState<Record<string, number> | null>(null);
  const url = fuente?.url;
  const puedeContadores = !!fuente && sesion.permisos.includes(fuente.permiso);
  const puedeAdmin = sesion.permisos.includes("usuarios.ver") || sesion.permisos.includes("roles.ver");

  useEffect(() => {
    try {
      setColapsado(localStorage.getItem(CLAVE_COLAPSADO) === "1");
    } catch {}
  }, []);

  // Los contadores se refrescan al navegar (p. ej. después de aprobar cubrimientos)
  useEffect(() => {
    setMovilAbierto(false);
    if (url && puedeContadores) api<Record<string, number>>(url).then(setContadores).catch(() => {});
  }, [pathname, puedeContadores, url]);

  function alternar() {
    const v = !colapsado;
    setColapsado(v);
    try {
      localStorage.setItem(CLAVE_COLAPSADO, v ? "1" : "0");
    } catch {}
  }

  async function salir() {
    await api("/auth/logout", { method: "POST" });
    window.location.href = "/login";
  }

  const visibles = menu.map((g) => ({ ...g, items: g.items.filter((i) => !i.permiso || sesion.permisos.includes(i.permiso)) })).filter((g) => g.items.length);
  const actual = visibles.flatMap((g) => g.items.map((i) => ({ ...i, grupo: g.grupo }))).find((i) => activo(pathname, i.href, inicio));
  const angosto = colapsado && !movilAbierto;
  const rol = sesion.roles.map((r) => r.nombre).join(", ") || "Sin rol";
  const fecha = new Date().toLocaleDateString("es-CO", { weekday: "long", day: "numeric", month: "long", year: "numeric" });

  const enlace = "flex items-center gap-3 rounded-lg py-2 text-sm text-slate-300 transition hover:bg-white/[0.07] hover:text-white";

  return (
    <div className="app-limpia flex min-h-screen bg-[#eef1f5]">
      {movilAbierto && <div className="fixed inset-0 z-30 bg-slate-900/40 lg:hidden" onClick={() => setMovilAbierto(false)} />}

      <aside
        className={`fixed inset-y-0 left-0 z-40 flex flex-col bg-(--barra-desde) text-slate-300 transition-all duration-300 lg:sticky lg:top-0 lg:h-screen lg:translate-x-0
          ${movilAbierto ? "translate-x-0" : "-translate-x-full"} ${angosto ? "w-[72px]" : "w-64"}`}
      >
        {/* App: el color de la marca solo en el ícono */}
        <div className={`flex items-center gap-3 pb-3 pt-5 ${angosto ? "justify-center px-2" : "px-4"}`}>
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-marca-600" title={angosto ? nombre : undefined}>
            <IconoApp className="h-5 w-5 text-white" strokeWidth={2} />
          </div>
          {!angosto && (
            <div className="min-w-0 flex-1 leading-tight">
              <p className="truncate text-[15px] font-semibold text-white">{nombre}</p>
              <p className="truncate text-xs font-medium text-acento-300">{subtitulo}</p>
            </div>
          )}
          <button className="rounded-md p-1 text-slate-400 hover:bg-white/10 hover:text-white lg:hidden" onClick={() => setMovilAbierto(false)} aria-label="Cerrar menú">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Navegación */}
        <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-4">
          {visibles.map(({ grupo, items }) => (
            <div key={grupo}>
              {angosto ? (
                <div className="mx-auto mb-2 h-px w-8 bg-white/10" />
              ) : (
                <p className="mb-1 px-3 text-xs font-medium text-white/45">{grupo}</p>
              )}
              <ul className="space-y-0.5">
                {items.map((i) => {
                  const on = activo(pathname, i.href, inicio);
                  const n = i.contador && contadores ? contadores[i.contador] ?? 0 : 0;
                  const Icono = i.icono;
                  return (
                    <li key={i.href}>
                      <Link
                        href={i.href}
                        title={angosto ? `${i.texto}${n ? ` (${n})` : ""}` : undefined}
                        className={`relative flex items-center gap-3 rounded-lg border py-2 text-sm transition
                          ${angosto ? "justify-center px-2" : "px-3"}
                          ${on ? "border-white/10 bg-white/[0.10] font-medium text-white" : "border-transparent text-slate-300 hover:bg-white/[0.06] hover:text-white"}`}
                      >
                        <Icono className={`h-[18px] w-[18px] shrink-0 ${on ? "text-acento-300" : "text-slate-400"}`} strokeWidth={1.9} />
                        {!angosto && <span className="flex-1 truncate">{i.texto}</span>}
                        {n > 0 && (
                          <span
                            className={`${angosto ? "absolute right-1 top-1 h-4 min-w-4 px-1 text-[9px]" : "px-1.5 text-[11px]"} rounded-full font-semibold leading-4 tabular-nums
                              ${i.critico ? "bg-[#d03b3b] text-white" : "bg-amber-400/90 text-[#3d2a00]"}`}
                          >
                            {n > 99 ? "99+" : n}
                          </span>
                        )}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>

        <div className="space-y-0.5 border-t border-white/10 px-3 py-2">
          <Link href="/" title={angosto ? "Portal de aplicaciones" : undefined} className={`${enlace} ${angosto ? "justify-center px-2" : "px-3"}`}>
            <LayoutGrid className="h-[18px] w-[18px] text-slate-400" strokeWidth={1.9} />
            {!angosto && "Portal de aplicaciones"}
          </Link>
          {puedeAdmin && (
            <Link href="/admin/usuarios" title={angosto ? "Administración" : undefined} className={`${enlace} ${angosto ? "justify-center px-2" : "px-3"}`}>
              <Users className="h-[18px] w-[18px] text-slate-400" strokeWidth={1.9} />
              {!angosto && "Administración"}
            </Link>
          )}
          <button onClick={alternar} className={`hidden w-full lg:flex ${enlace} text-xs ${angosto ? "justify-center px-2" : "justify-center px-3"}`}
            aria-label={colapsado ? "Expandir menú" : "Colapsar menú"}>
            {colapsado ? <ChevronsRight className="h-4 w-4" /> : <><ChevronsLeft className="h-4 w-4" /> Colapsar menú</>}
          </button>
        </div>

        {/* Usuario */}
        <div className={`border-t border-white/10 ${angosto ? "px-2 py-3" : "px-4 py-3"}`}>
          <div className={`flex items-center gap-2.5 ${angosto ? "flex-col" : ""}`}>
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white/10 text-xs font-semibold text-white" title={angosto ? `${sesion.nombre} · ${rol}` : undefined}>
              {iniciales(sesion.nombre)}
            </div>
            {!angosto && (
              <div className="min-w-0 flex-1 leading-tight">
                <p className="truncate text-sm font-medium text-white">{sesion.nombre}</p>
                <p className="truncate text-[11px] text-slate-400">{rol}</p>
              </div>
            )}
            <Link href="/cuenta" className="rounded-md p-1.5 text-slate-400 transition hover:bg-white/10 hover:text-white" title="Seguridad de mi cuenta" aria-label="Seguridad de mi cuenta">
              <KeyRound className="h-4 w-4" />
            </Link>
            <button onClick={salir} className="rounded-md p-1.5 text-slate-400 transition hover:bg-white/10 hover:text-white" title="Cerrar sesión" aria-label="Cerrar sesión">
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Barra superior: sección actual, empresa, fecha y alertas (sin cambios de contenido) */}
        <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-[#dfe4eb] bg-[#f6f7f9]/95 px-4 backdrop-blur lg:px-10">
          <button className="rounded-md p-1.5 text-slate-600 hover:bg-slate-100 lg:hidden" onClick={() => setMovilAbierto(true)} aria-label="Abrir menú">
            <Menu className="h-5 w-5" />
          </button>
          <div className="min-w-0">
            <p className="text-[11px] text-slate-400">{actual?.grupo ?? nombre}</p>
            <p className="truncate text-sm font-medium text-slate-800">{actual?.texto ?? ""}</p>
          </div>
          <div className="ml-auto flex items-center gap-4">
            <SelectorEmpresa app={inicio.replace(/^\//, "").split("/")[0]} />
            <span className="hidden text-xs text-slate-500 first-letter:uppercase md:inline">{fecha}</span>
            {campana && puedeContadores && (
              <Link href={inicio} className="relative rounded-full p-2 text-slate-500 transition hover:bg-slate-100 hover:text-marca-700" title="Alertas" aria-label="Alertas">
                <Bell className="h-5 w-5" />
                {contadores && (contadores[campana.total] ?? 0) > 0 && (
                  <span className={`absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-[10px] font-semibold text-white ${contadores[campana.criticas] ? "bg-[#d03b3b]" : "bg-amber-500"}`}>
                    {contadores[campana.total]}
                  </span>
                )}
              </Link>
            )}
          </div>
        </header>

        <main className="flex-1 overflow-x-auto p-4 lg:px-10 lg:py-8">{children}</main>
      </div>

      {asistente && sesion.permisos.includes(asistente.permiso) && (
        <Suspense fallback={null}>
          <Asistente base={asistente.base} bienvenida={asistente.bienvenida} sugerencias={asistente.sugerencias} />
        </Suspense>
      )}
    </div>
  );
}
