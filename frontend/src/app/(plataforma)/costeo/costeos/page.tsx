"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Alerta, Titulo } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";
import { ESTADO_COSTEO, pct, pesos, type Cliente } from "@/lib/costeo";
import { usePermiso } from "@/lib/sesion";

type CosteoFila = { id: number; cliente: Cliente; nombre: string; version: number; estado: string; meses: number | null; tarifa_decreto: number | null;
  pct_mfp: number | null; margen_mensual: number | null; pct_margen: number | null; actualizado_en: string; mfp_id: number | null };

export default function Costeos() {
  const costear = usePermiso("costeo.costear");
  const router = useRouter();
  const [lista, setLista] = useState<CosteoFila[] | null>(null);
  const [clientes, setClientes] = useState<Cliente[]>([]);
  const [nuevo, setNuevo] = useState<{ cliente_id: string; nombre: string } | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api<CosteoFila[]>("/costeo/costeos").then(setLista).catch((e) => setError(mensajeError(e)));
    api<Cliente[]>("/costeo/clientes").then(setClientes).catch(() => {});
  }, []);

  async function crear() {
    if (!nuevo) return;
    try {
      const c = await api<{ id: number }>("/costeo/costeos", { method: "POST", json: { cliente_id: Number(nuevo.cliente_id), nombre: nuevo.nombre } });
      router.push(`/costeo/costeos/${c.id}`);
    } catch (e) {
      setError(mensajeError(e));
    }
  }

  return (
    <>
      <Titulo accion={costear && !nuevo && <button className="btn-primario" onClick={() => setNuevo({ cliente_id: "", nombre: "" })}><Plus className="h-4 w-4" /> Nuevo costeo</button>}>
        Costeos
      </Titulo>
      {error && <div className="mb-4"><Alerta>{error}</Alerta></div>}
      {nuevo && (
        <div className="tarjeta mb-5 grid gap-3 p-5 sm:grid-cols-[2fr_2fr_auto] sm:items-end">
          <div><label className="label">Cliente</label>
            <select className="input" value={nuevo.cliente_id} onChange={(e) => setNuevo({ ...nuevo, cliente_id: e.target.value })}>
              <option value="">Seleccione… (créelo en Clientes si no existe)</option>{clientes.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
            </select></div>
          <div><label className="label">Nombre del costeo</label><input className="input" placeholder="Ej. Palmaseca 2026" value={nuevo.nombre} onChange={(e) => setNuevo({ ...nuevo, nombre: e.target.value })} /></div>
          <div className="flex gap-2"><button className="btn-secundario" onClick={() => setNuevo(null)}>Cancelar</button>
            <button className="btn-primario" disabled={!nuevo.cliente_id || nuevo.nombre.trim().length < 2} onClick={crear}>Crear</button></div>
        </div>
      )}
      <div className="tarjeta overflow-x-auto">
        <table className="tabla">
          <thead><tr><th>Costeo</th><th>Cliente</th><th>Estado</th><th className="text-right">Meses</th><th className="text-right">Tarifa mensual</th>
            <th className="text-right">% MFP</th><th className="text-right">Margen mensual</th><th className="text-right">% margen</th><th>MFP</th></tr></thead>
          <tbody>
            {(lista ?? []).map((c) => (
              <tr key={c.id}>
                <td><Link className="font-medium text-marca-700 hover:underline" href={`/costeo/costeos/${c.id}`}>{c.nombre}</Link> <span className="text-xs text-slate-500">v{c.version}</span></td>
                <td>{c.cliente.nombre}</td>
                <td><span className={`rounded-full px-2 py-0.5 text-xs font-medium ${ESTADO_COSTEO[c.estado]}`}>{c.estado}</span></td>
                <td className="text-right tabular-nums">{c.meses ?? "—"}</td>
                <td className="text-right tabular-nums">{pesos(c.tarifa_decreto)}</td>
                <td className="text-right tabular-nums">{pct(c.pct_mfp)}</td>
                <td className={`text-right tabular-nums ${(c.margen_mensual ?? 0) < 0 ? "font-semibold text-red-700" : ""}`}>{pesos(c.margen_mensual)}</td>
                <td className={`text-right tabular-nums ${(c.pct_margen ?? 0) < 0 ? "text-red-700" : ""}`}>{pct(c.pct_margen)}</td>
                <td>{c.mfp_id ? <Link className="text-marca-700 hover:underline" href={`/costeo/mfp/${c.mfp_id}`}>Ver MFP</Link> : ""}</td>
              </tr>
            ))}
            {lista && !lista.length && <tr><td colSpan={9} className="py-8 text-center text-slate-400">Sin costeos.</td></tr>}
          </tbody>
        </table>
      </div>
    </>
  );
}
