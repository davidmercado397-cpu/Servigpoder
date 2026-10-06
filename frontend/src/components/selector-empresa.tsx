"use client";

import { Building2 } from "lucide-react";
import { useState } from "react";
import { api, mensajeError } from "@/lib/api";
import { useSesion } from "@/lib/sesion";

/**
 * Empresa con la que se trabaja. Cada empresa tiene sus propios datos: al cambiarla, la pantalla se recarga
 * con los de la nueva empresa (o vuelve al portal si allí no tiene este desarrollo).
 */
export function SelectorEmpresa({ app, oscuro = false }: { app?: string; oscuro?: boolean }) {
  const { empresas, empresa_actual } = useSesion();
  const [ocupado, setOcupado] = useState(false);
  if (!empresas?.length) return null;
  const actual = empresas.find((e) => e.codigo === empresa_actual) ?? empresas[0];
  const estilo = oscuro
    ? "border-white/20 bg-white/10 text-white hover:bg-white/15"
    : "border-slate-200 bg-white text-slate-700 hover:border-slate-300";

  async function cambiar(codigo: string) {
    setOcupado(true);
    try {
      await api("/plataforma/empresa", { method: "POST", json: { codigo } });
      const destino = empresas.find((e) => e.codigo === codigo);
      if (app && destino?.apps.includes(app)) window.location.reload();
      else window.location.href = "/";
    } catch (e) {
      alert(mensajeError(e));
      setOcupado(false);
    }
  }

  if (empresas.length === 1) {
    return (
      <span className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-sm font-medium ${estilo}`} title="Empresa">
        <Building2 className="h-4 w-4 opacity-70" /> {actual.nombre}
      </span>
    );
  }
  return (
    <label className={`relative inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-sm font-medium transition ${estilo}`} title="Empresa con la que trabaja">
      <Building2 className="h-4 w-4 opacity-70" />
      <span className="sr-only">Empresa</span>
      <select value={actual.codigo} disabled={ocupado} onChange={(e) => cambiar(e.target.value)}
        className={`cursor-pointer appearance-none bg-transparent pr-4 font-medium focus:outline-none ${oscuro ? "[&>option]:text-slate-900" : ""}`}>
        {empresas.map((e) => <option key={e.codigo} value={e.codigo}>{e.nombre}</option>)}
      </select>
      <span className="pointer-events-none absolute right-2 text-xs opacity-60">▾</span>
    </label>
  );
}
