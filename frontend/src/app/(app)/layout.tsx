"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { api } from "@/lib/api";
import { SesionProvider, useSesion } from "@/lib/sesion";

type Item = { href: string; texto: string; permiso?: string; proximamente?: boolean };

const MENU: { grupo: string; items: Item[] }[] = [
  { grupo: "General", items: [{ href: "/", texto: "Inicio" }] },
  {
    grupo: "Operación",
    items: [
      { href: "/programacion", texto: "Cargar programación", permiso: "programacion.cargar", proximamente: true },
      { href: "/cobertura", texto: "Cobertura", permiso: "analisis.ver", proximamente: true },
      { href: "/cubrimientos", texto: "Cubrimientos (nómina)", permiso: "cubrimientos.aprobar", proximamente: true },
    ],
  },
  {
    grupo: "Configuración",
    items: [
      { href: "/matriz", texto: "Matriz comercial", permiso: "matriz.ver", proximamente: true },
      { href: "/maestros", texto: "Maestros", permiso: "maestros.ver", proximamente: true },
    ],
  },
  {
    grupo: "Administración",
    items: [
      { href: "/admin/usuarios", texto: "Usuarios", permiso: "usuarios.ver" },
      { href: "/admin/roles", texto: "Roles y permisos", permiso: "roles.ver" },
    ],
  },
];

function Shell({ children }: { children: React.ReactNode }) {
  const sesion = useSesion();
  const pathname = usePathname();

  async function salir() {
    await api("/auth/logout", { method: "POST" });
    window.location.href = "/login";
  }

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-60 shrink-0 flex-col bg-marca-900 text-slate-200">
        <div className="px-5 py-5">
          <p className="text-base font-bold text-white">Capacidad Operativa</p>
          <p className="text-xs text-slate-400">Servigpoder</p>
        </div>
        <nav className="flex-1 space-y-5 px-3">
          {MENU.map(({ grupo, items }) => {
            const visibles = items.filter((i) => !i.permiso || sesion.permisos.includes(i.permiso));
            if (!visibles.length) return null;
            return (
              <div key={grupo}>
                <p className="px-2 pb-1 text-xs uppercase tracking-wide text-slate-400">{grupo}</p>
                {visibles.map((i) =>
                  i.proximamente ? (
                    <span key={i.href} className="flex items-center justify-between rounded px-2 py-1.5 text-sm text-slate-500">
                      {i.texto}
                      <span className="rounded bg-white/10 px-1.5 text-[10px]">pronto</span>
                    </span>
                  ) : (
                    <Link
                      key={i.href}
                      href={i.href}
                      className={`block rounded px-2 py-1.5 text-sm hover:bg-white/10 ${pathname === i.href ? "bg-white/15 text-white" : ""}`}
                    >
                      {i.texto}
                    </Link>
                  ),
                )}
              </div>
            );
          })}
        </nav>
        <div className="border-t border-white/10 px-5 py-4 text-sm">
          <p className="font-medium text-white">{sesion.nombre}</p>
          <p className="text-xs text-slate-400">{sesion.roles.map((r) => r.nombre).join(", ")}</p>
          <button onClick={salir} className="mt-2 text-xs text-slate-300 underline hover:text-white">
            Cerrar sesión
          </button>
        </div>
      </aside>
      <main className="flex-1 overflow-x-auto p-8">{children}</main>
    </div>
  );
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <SesionProvider>
      <Shell>{children}</Shell>
    </SesionProvider>
  );
}
