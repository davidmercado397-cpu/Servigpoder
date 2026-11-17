"use client";

import { ArrowRight, Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Alerta, Insignia, Titulo } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";
import { MESES } from "@/lib/formato";
import { usePermiso } from "@/lib/sesion";
import { nombrePeriodo, pesos, type PeriodoSpeed } from "@/lib/speed";

export default function QuincenasSpeed() {
  const liquidar = usePermiso("speed.liquidar");
  const router = useRouter();
  const hoy = new Date();
  const [nuevo, setNuevo] = useState({ anio: hoy.getFullYear(), mes: hoy.getMonth() + 1, quincena: hoy.getDate() <= 15 ? 1 : 2 });
  const [lista, setLista] = useState<PeriodoSpeed[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<PeriodoSpeed[]>("/speed/periodos").then(setLista).catch((e) => setError(mensajeError(e)));
  }, []);

  async function crear(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const p = await api<PeriodoSpeed>("/speed/periodos", { method: "POST", json: nuevo });
      router.push(`/speed/periodos/${p.id}`);
    } catch (err) { setError(mensajeError(err)); }
  }

  return (
    <div>
      <Titulo>Quincenas</Titulo>
      <p className="mb-4 text-sm text-slate-600">Nómina quincenal y comercial (30 días). Cada quincena se liquida con los valores del Listado de
        cada persona y sus novedades: días programados, tiempos no laborados e incapacidades.</p>
      {liquidar && (
        <form onSubmit={crear} className="tarjeta mb-5 flex flex-wrap items-end gap-3 p-4">
          <div><label className="label">Año</label>
            <input className="input w-24" type="number" value={nuevo.anio} onChange={(e) => setNuevo({ ...nuevo, anio: Number(e.target.value) })} /></div>
          <div><label className="label">Mes</label>
            <select className="input w-40" value={nuevo.mes} onChange={(e) => setNuevo({ ...nuevo, mes: Number(e.target.value) })}>
              {MESES.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}</select></div>
          <div><label className="label">Quincena</label>
            <select className="input w-44" value={nuevo.quincena} onChange={(e) => setNuevo({ ...nuevo, quincena: Number(e.target.value) })}>
              <option value={1}>1.ª (1 al 15)</option><option value={2}>2.ª (16 al 30)</option></select></div>
          <button className="btn-primario"><Plus className="h-4 w-4" /> Nueva quincena</button>
        </form>
      )}
      {error && <div className="mb-4"><Alerta>{error}</Alerta></div>}
      <div className="tarjeta overflow-x-auto">
        <table className="tabla">
          <thead><tr><th>Quincena</th><th>Estado</th><th className="text-right">Personas</th><th className="text-right">Devengado</th>
            <th className="text-right">Deducciones</th><th className="text-right">Neto a pagar</th><th /></tr></thead>
          <tbody>
            {lista === null && <tr><td colSpan={7} className="py-6 text-center text-slate-400">Cargando…</td></tr>}
            {lista?.length === 0 && <tr><td colSpan={7} className="py-6 text-center text-slate-400">Aún no hay quincenas.</td></tr>}
            {lista?.map((p) => (
              <tr key={p.id} className="hover:bg-slate-50">
                <td className="font-medium">{nombrePeriodo(p)}</td>
                <td><Insignia color={p.estado === "cerrado" ? "bg-slate-200 text-slate-700" : "bg-green-100 text-green-800"}>{p.estado}</Insignia>
                  {!p.calculado_en && <span className="ml-2 text-xs text-amber-700">sin liquidar</span>}</td>
                <td className="text-right tabular-nums">{p.personas}</td>
                <td className="text-right tabular-nums">{pesos(p.devengado)}</td>
                <td className="text-right tabular-nums">{pesos(p.deducciones)}</td>
                <td className="text-right font-semibold tabular-nums">{pesos(p.neto)}</td>
                <td className="text-right"><Link href={`/speed/periodos/${p.id}`} className="inline-flex items-center gap-1 text-marca-700 hover:underline">Abrir <ArrowRight className="h-4 w-4" /></Link></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
