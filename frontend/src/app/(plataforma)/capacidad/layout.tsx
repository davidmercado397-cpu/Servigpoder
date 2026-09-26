"use client";

import {
  Bell, ChevronsLeft, ChevronsRight, Database, FileSpreadsheet, Gauge, History, Inbox, KeyRound, LayoutDashboard, LayoutGrid,
  LogOut, Menu, ShieldCheck, SlidersHorizontal, Table2, Users, X, type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Asistente } from "@/components/asistente";
import { api } from "@/lib/api";
import { useSesion } from "@/lib/sesion";

type Contadores = { alertas: number; alertas_criticas: number; cubrimientos_pendientes: number; por_aclarar: number };
type Item = { href: string; texto: string; icono: LucideIcon; permiso?: string; contador?: keyof Contadores; critico?: boolean };

const MENU: { grupo: string; items: Item[] }[] = [
  { grupo: "General", items: [{ href: "/capacidad", texto: "Inicio", icono: LayoutDashboard, contador: "alertas_criticas", critico: true }] },
  {
    grupo: "Operación",
    items: [
      { href: "/capacidad/programacion", texto: "Programación SIESA", icono: FileSpreadsheet, permiso: "capacidad.analisis.ver" },
      { href: "/capacidad/cobertura", texto: "Cobertura", icono: Gauge, permiso: "capacidad.analisis.ver" },
      { href: "/capacidad/cubrimientos", texto: "Cubrimientos (nómina)", icono: Inbox, permiso: "capacidad.analisis.ver", contador: "cubrimientos_pendientes" },
      { href: "/capacidad/bolsas", texto: "Personas en bolsa", icono: Users, permiso: "capacidad.analisis.ver" },
      { href: "/capacidad/historico", texto: "Histórico y novedades", icono: History, permiso: "capacidad.analisis.ver" },
    ],
  },
  {
    grupo: "Configuración",
    items: [
      { href: "/capacidad/matriz", texto: "Matriz comercial", icono: Table2, permiso: "capacidad.matriz.ver" },
      { href: "/capacidad/maestros", texto: "Maestros", icono: Database, permiso: "capacidad.maestros.ver", contador: "por_aclarar" },
      { href: "/capacidad/parametros", texto: "Parámetros de alertas", icono: SlidersHorizontal, permiso: "capacidad.parametros.gestionar" },
    ],
  },
];

const CLAVE_COLAPSADO = "menu-colapsado";

function activo(pathname: string, href: string) {
  return href === "/capacidad" ? pathname === "/capacidad" : pathname === href || pathname.startsWith(`${href}/`);
}

function iniciales(nombre: string) {
  return nombre.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]).join("").toUpperCase();
}

function Shell({ children }: { children: React.ReactNode }) {
  const sesion = useSesion();
  const pathname = usePathname();
  const [colapsado, setColapsado] = useState(false);
  const [movilAbierto, setMovilAbierto] = useState(false);
  const [contadores, setContadores] = useState<Contadores | null>(null);
  const puedeAnalisis = sesion.permisos.includes("capacidad.analisis.ver");
  const puedeAdmin = sesion.permisos.includes("usuarios.ver") || sesion.permisos.includes("roles.ver");

  useEffect(() => {
    try {
      setColapsado(localStorage.getItem(CLAVE_COLAPSADO) === "1");
    } catch {}
  }, []);

  // Los contadores se refrescan al navegar (p. ej. después de aprobar cubrimientos)
  useEffect(() => {
    setMovilAbierto(false);
    if (puedeAnalisis) api<Contadores>("/capacidad/menu/contadores").then(setContadores).catch(() => {});
  }, [pathname, puedeAnalisis]);

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

  const visibles = MENU.map((g) => ({ ...g, items: g.items.filter((i) => !i.permiso || sesion.permisos.includes(i.permiso)) })).filter((g) => g.items.length);
  const actual = visibles.flatMap((g) => g.items.map((i) => ({ ...i, grupo: g.grupo }))).find((i) => activo(pathname, i.href));
  const angosto = colapsado && !movilAbierto;
  const rol = sesion.roles.map((r) => r.nombre).join(", ") || "Sin rol";
  const fecha = new Date().toLocaleDateString("es-CO", { weekday: "long", day: "numeric", month: "long", year: "numeric" });

  return (
    <div className="flex min-h-screen">
      {movilAbierto && <div className="fixed inset-0 z-30 bg-slate-900/50 lg:hidden" onClick={() => setMovilAbierto(false)} />}

      <aside
        className={`fixed inset-y-0 left-0 z-40 flex flex-col bg-gradient-to-b from-[#0f2d5c] via-[#0c2750] to-[#081a38] text-slate-300 shadow-xl transition-all duration-300 lg:sticky lg:top-0 lg:h-screen lg:translate-x-0
          ${movilAbierto ? "translate-x-0" : "-translate-x-full"} ${angosto ? "w-[72px]" : "w-64"}`}
      >
        {/* Marca */}
        <div className={`flex items-center gap-3 border-b border-white/10 py-5 ${angosto ? "justify-center px-2" : "px-5"}`}>
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-sky-400 to-marca-600 shadow-lg shadow-sky-900/40 ring-1 ring-white/20">
            <ShieldCheck className="h-5 w-5 text-white" strokeWidth={2.2} />
          </div>
          {!angosto && (
            <div className="min-w-0">
              <p className="truncate text-[15px] font-bold leading-tight text-white">Capacidad Operativa</p>
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-sky-300/80">Servigpoder</p>
            </div>
          )}
          <button className="ml-auto rounded-md p-1 text-slate-400 hover:bg-white/10 hover:text-white lg:hidden" onClick={() => setMovilAbierto(false)} aria-label="Cerrar menú">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Navegación */}
        <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-5">
          {visibles.map(({ grupo, items }) => (
            <div key={grupo}>
              {angosto ? (
                <div className="mx-auto mb-2 h-px w-8 bg-white/10" />
              ) : (
                <p className="mb-1.5 px-3 text-[10.5px] font-semibold uppercase tracking-[0.14em] text-slate-500">{grupo}</p>
              )}
              <ul className="space-y-0.5">
                {items.map((i) => {
                  const on = activo(pathname, i.href);
                  const n = i.contador && contadores ? contadores[i.contador] : 0;
                  const Icono = i.icono;
                  return (
                    <li key={i.href}>
                      <Link
                        href={i.href}
                        title={angosto ? `${i.texto}${n ? ` (${n})` : ""}` : undefined}
                        className={`group relative flex items-center gap-3 rounded-lg py-2 text-sm transition-all duration-200
                          ${angosto ? "justify-center px-2" : "px-3"}
                          ${on ? "bg-white/[0.12] font-medium text-white shadow-inner shadow-black/10" : "text-slate-300 hover:bg-white/[0.06] hover:text-white"}`}
                      >
                        <span className={`absolute left-0 top-1/2 h-6 w-1 -translate-y-1/2 rounded-r-full bg-sky-400 transition-opacity ${on ? "opacity-100" : "opacity-0"}`} />
                        <Icono className={`h-[18px] w-[18px] shrink-0 transition-transform duration-200 group-hover:scale-110 ${on ? "text-sky-300" : "text-slate-400 group-hover:text-sky-200"}`} strokeWidth={1.9} />
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

        {/* Volver al portal */}
        <div className="mx-3 mb-1 space-y-0.5 border-t border-white/10 pt-2">
          <Link href="/" title={angosto ? "Portal de aplicaciones" : undefined}
            className={`flex items-center gap-3 rounded-lg py-2 text-sm text-slate-300 transition hover:bg-white/[0.06] hover:text-white ${angosto ? "justify-center px-2" : "px-3"}`}>
            <LayoutGrid className="h-[18px] w-[18px] text-slate-400" strokeWidth={1.9} />
            {!angosto && "Portal de aplicaciones"}
          </Link>
          {puedeAdmin && (
            <Link href="/admin/usuarios" title={angosto ? "Administración" : undefined}
              className={`flex items-center gap-3 rounded-lg py-2 text-sm text-slate-300 transition hover:bg-white/[0.06] hover:text-white ${angosto ? "justify-center px-2" : "px-3"}`}>
              <Users className="h-[18px] w-[18px] text-slate-400" strokeWidth={1.9} />
              {!angosto && "Administración"}
            </Link>
          )}
        </div>

        {/* Colapsar */}
        <button
          onClick={alternar}
          className="mx-3 mb-2 hidden items-center justify-center gap-2 rounded-lg py-1.5 text-xs text-slate-400 transition hover:bg-white/[0.06] hover:text-white lg:flex"
          aria-label={colapsado ? "Expandir menú" : "Colapsar menú"}
        >
          {colapsado ? <ChevronsRight className="h-4 w-4" /> : <><ChevronsLeft className="h-4 w-4" /> Colapsar menú</>}
        </button>

        {/* Usuario */}
        <div className={`border-t border-white/10 bg-black/15 ${angosto ? "px-2 py-3" : "px-4 py-3"}`}>
          <div className={`flex items-center gap-3 ${angosto ? "flex-col" : ""}`}>
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-sky-400 to-indigo-500 text-xs font-bold text-white ring-2 ring-white/15" title={angosto ? `${sesion.nombre} · ${rol}` : undefined}>
              {iniciales(sesion.nombre)}
            </div>
            {!angosto && (
              <div className="min-w-0 flex-1">
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
        {/* Barra superior */}
        <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-slate-200 bg-white/85 px-4 backdrop-blur lg:px-8">
          <button className="rounded-md p-1.5 text-slate-600 hover:bg-slate-100 lg:hidden" onClick={() => setMovilAbierto(true)} aria-label="Abrir menú">
            <Menu className="h-5 w-5" />
          </button>
          <div className="min-w-0">
            <p className="text-[11px] font-medium uppercase tracking-wider text-slate-400">{actual?.grupo ?? "Capacidad Operativa"}</p>
            <p className="truncate text-sm font-semibold text-slate-800">{actual?.texto ?? ""}</p>
          </div>
          <div className="ml-auto flex items-center gap-4">
            <span className="hidden text-xs capitalize text-slate-500 md:inline">{fecha}</span>
            {puedeAnalisis && (
              <Link href="/capacidad" className="relative rounded-full p-2 text-slate-500 transition hover:bg-slate-100 hover:text-marca-700" title="Alertas" aria-label="Alertas">
                <Bell className="h-5 w-5" />
                {contadores && contadores.alertas > 0 && (
                  <span className={`absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-[10px] font-semibold text-white ${contadores.alertas_criticas ? "bg-[#d03b3b]" : "bg-amber-500"}`}>
                    {contadores.alertas}
                  </span>
                )}
              </Link>
            )}
          </div>
        </header>

        <main className="flex-1 overflow-x-auto p-4 lg:p-8">{children}</main>
      </div>

      {sesion.permisos.includes("capacidad.asistente.usar") && (
        <Suspense fallback={null}>
          <Asistente />
        </Suspense>
      )}
    </div>
  );
}

export default function CapacidadLayout({ children }: { children: React.ReactNode }) {
  return <Shell>{children}</Shell>;
}
