"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarraPlataforma } from "@/components/barra-plataforma";
import { useSesion } from "@/lib/sesion";

const SECCIONES = [
  { href: "/admin/usuarios", texto: "Usuarios", permiso: "usuarios.ver" },
  { href: "/admin/roles", texto: "Roles y permisos", permiso: "roles.ver" },
  { href: "/admin/auditoria", texto: "Auditoría", permiso: "auditoria.ver" },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const sesion = useSesion();
  const pathname = usePathname();
  const visibles = SECCIONES.filter((s) => sesion.permisos.includes(s.permiso));
  return (
    <div className="min-h-screen bg-slate-50">
      <BarraPlataforma>
        {visibles.map((s) => (
          <Link key={s.href} href={s.href}
            className={`rounded-lg px-3 py-1.5 transition ${pathname.startsWith(s.href) ? "bg-white/15 text-white" : "text-sky-100/80 hover:bg-white/10 hover:text-white"}`}>
            {s.texto}
          </Link>
        ))}
      </BarraPlataforma>
      <main className="mx-auto max-w-7xl px-4 py-8 lg:px-8">{children}</main>
    </div>
  );
}
