"use client";

import { ArrowRight, Boxes, Calculator, KeyRound, ScrollText, ShieldCheck, UserCog, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { BarraPlataforma } from "@/components/barra-plataforma";
import { api } from "@/lib/api";
import { useSesion } from "@/lib/sesion";

type AppPortal = { codigo: string; nombre: string; descripcion: string; icono: string; color: string; ruta: string };

// Íconos disponibles para las apps (el backend indica el nombre en su manifest)
const ICONOS: Record<string, LucideIcon> = { "shield-check": ShieldCheck, calculator: Calculator };

export default function Portal() {
  const sesion = useSesion();
  const [apps, setApps] = useState<AppPortal[] | null>(null);

  useEffect(() => {
    api<AppPortal[]>("/plataforma/apps").then(setApps).catch(() => setApps([]));
  }, []);

  const admin = [
    { href: "/admin/usuarios", texto: "Usuarios", desc: "Crear cuentas, restablecer acceso", icono: UserCog, permiso: "usuarios.ver" },
    { href: "/admin/roles", texto: "Roles y permisos", desc: "Qué puede hacer cada rol en cada app", icono: KeyRound, permiso: "roles.ver" },
    { href: "/admin/auditoria", texto: "Auditoría", desc: "Bitácora de accesos y cambios", icono: ScrollText, permiso: "auditoria.ver" },
  ].filter((a) => sesion.permisos.includes(a.permiso));

  const hora = new Date().getHours();
  const saludo = hora < 12 ? "Buenos días" : hora < 19 ? "Buenas tardes" : "Buenas noches";

  return (
    <div className="min-h-screen bg-slate-50">
      <BarraPlataforma />
      <main className="mx-auto max-w-7xl space-y-10 px-4 py-10 lg:px-8">
        <div>
          <h1 className="text-3xl font-bold text-marca-900">{saludo}, {sesion.nombre.split(" ")[0]}</h1>
          <p className="mt-1 text-slate-500">Estas son las aplicaciones a las que tiene acceso.</p>
        </div>

        <section>
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Aplicaciones</h2>
          {apps === null && <p className="text-slate-500">Cargando…</p>}
          {apps?.length === 0 && (
            <div className="tarjeta flex items-center gap-3 p-6 text-slate-600">
              <Boxes className="h-6 w-6 text-slate-400" />
              Su usuario aún no tiene acceso a ninguna aplicación. Solicítelo al administrador de la plataforma.
            </div>
          )}
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {apps?.map((a) => {
              const Icono = ICONOS[a.icono] ?? Boxes;
              return (
                <Link key={a.codigo} href={a.ruta}
                  className="group relative overflow-hidden rounded-2xl border border-slate-200 bg-white p-6 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg">
                  <div className="absolute inset-x-0 top-0 h-1" style={{ background: a.color }} />
                  <div className="flex h-12 w-12 items-center justify-center rounded-xl text-white shadow-md" style={{ background: `linear-gradient(135deg, ${a.color}, #0f2d5c)` }}>
                    <Icono className="h-6 w-6" strokeWidth={2} />
                  </div>
                  <h3 className="mt-4 text-lg font-semibold text-slate-900">{a.nombre}</h3>
                  <p className="mt-1 text-sm text-slate-500">{a.descripcion}</p>
                  <span className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-marca-600">
                    Abrir <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
                  </span>
                </Link>
              );
            })}
            {apps && apps.length > 0 && (
              <div className="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-slate-200 p-6 text-center text-sm text-slate-400">
                <Boxes className="mb-2 h-6 w-6" />
                Próximos desarrollos
              </div>
            )}
          </div>
        </section>

        {admin.length > 0 && (
          <section>
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Administración de la plataforma</h2>
            <div className="grid gap-4 sm:grid-cols-3">
              {admin.map((a) => (
                <Link key={a.href} href={a.href} className="tarjeta flex items-center gap-3 p-4 transition hover:border-marca-600 hover:shadow-md">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-marca-50 text-marca-700"><a.icono className="h-5 w-5" /></div>
                  <div>
                    <p className="font-medium text-slate-800">{a.texto}</p>
                    <p className="text-xs text-slate-500">{a.desc}</p>
                  </div>
                </Link>
              ))}
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
