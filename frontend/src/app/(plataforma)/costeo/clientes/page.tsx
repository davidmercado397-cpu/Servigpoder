"use client";

import { Pencil, Plus, Search } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Alerta, Titulo } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";
import { pct, pesos } from "@/lib/costeo";
import { usePermiso } from "@/lib/sesion";

type ClienteFila = { id: number; nit: string; nombre: string; activo: boolean; mfp: number; vigentes: number; facturacion_total: number;
  pactado: number; ejecutado: number; pendiente: number; reembolso: number; alertas: number };

export default function Clientes() {
  const gestionar = usePermiso("costeo.mfp");
  const [lista, setLista] = useState<ClienteFila[] | null>(null);
  const [q, setQ] = useState("");
  const [edicion, setEdicion] = useState<{ id?: number; nit: string; nombre: string; activo: boolean } | null>(null);
  const [error, setError] = useState("");

  const cargar = useCallback(() => api<ClienteFila[]>("/costeo/clientes").then(setLista).catch((e) => setError(mensajeError(e))), []);
  useEffect(() => {
    cargar();
  }, [cargar]);
  const visibles = useMemo(() => {
    const t = q.trim().toLowerCase();
    return (lista ?? []).filter((c) => !t || `${c.nombre} ${c.nit}`.toLowerCase().includes(t));
  }, [lista, q]);

  async function guardar() {
    if (!edicion) return;
    setError("");
    try {
      const datos = { nit: edicion.nit, nombre: edicion.nombre, activo: edicion.activo };
      if (edicion.id) await api(`/costeo/clientes/${edicion.id}`, { method: "PUT", json: datos });
      else await api("/costeo/clientes", { method: "POST", json: datos });
      setEdicion(null);
      cargar();
    } catch (e) {
      setError(mensajeError(e));
    }
  }

  return (
    <>
      <Titulo accion={gestionar && !edicion && <button className="btn-primario" onClick={() => setEdicion({ nit: "", nombre: "", activo: true })}><Plus className="h-4 w-4" /> Nuevo cliente</button>}>
        Clientes
      </Titulo>
      {error && <div className="mb-4"><Alerta>{error}</Alerta></div>}
      {edicion && (
        <div className="tarjeta mb-5 grid gap-3 p-5 sm:grid-cols-[1fr_2fr_auto_auto] sm:items-end">
          <div><label className="label">NIT</label><input className="input" value={edicion.nit} onChange={(e) => setEdicion({ ...edicion, nit: e.target.value })} /></div>
          <div><label className="label">Nombre</label><input className="input" value={edicion.nombre} onChange={(e) => setEdicion({ ...edicion, nombre: e.target.value })} /></div>
          <label className="flex items-center gap-2 pb-2 text-sm"><input type="checkbox" checked={edicion.activo} onChange={(e) => setEdicion({ ...edicion, activo: e.target.checked })} /> Activo</label>
          <div className="flex gap-2"><button className="btn-secundario" onClick={() => setEdicion(null)}>Cancelar</button>
            <button className="btn-primario" disabled={edicion.nombre.trim().length < 2} onClick={guardar}>Guardar</button></div>
        </div>
      )}
      <div className="tarjeta overflow-hidden">
        <div className="border-b border-slate-100 p-4">
          <div className="relative w-80">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-slate-400" />
            <input className="input pl-8" placeholder="Nombre o NIT" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="tabla">
            <thead><tr><th>Cliente</th><th className="text-right">MFP</th><th className="text-right">Facturación</th><th className="text-right">Pactado</th>
              <th className="text-right">% MFP</th><th className="text-right">Ejecutado</th><th className="text-right">Pendiente</th><th className="text-right">Reembolso</th>
              <th className="text-right">Alertas</th>{gestionar && <th />}</tr></thead>
            <tbody>
              {visibles.map((c) => (
                <tr key={c.id} className={c.activo ? "" : "opacity-60"}>
                  <td><Link className="font-medium text-marca-700 hover:underline" href={`/costeo/mfp?cliente=${c.id}`}>{c.nombre}</Link><p className="text-xs text-slate-500">{c.nit}</p></td>
                  <td className="text-right tabular-nums">{c.mfp} <span className="text-xs text-slate-500">({c.vigentes} vig.)</span></td>
                  <td className="text-right tabular-nums">{pesos(c.facturacion_total)}</td>
                  <td className="text-right tabular-nums">{pesos(c.pactado)}</td>
                  <td className="text-right tabular-nums">{pct(c.facturacion_total ? c.pactado / c.facturacion_total : null)}</td>
                  <td className="text-right tabular-nums">{pesos(c.ejecutado)}</td>
                  <td className="text-right tabular-nums">{pesos(c.pendiente)}</td>
                  <td className="text-right tabular-nums">{pesos(c.reembolso)}</td>
                  <td className={`text-right tabular-nums ${c.alertas ? "text-amber-700" : ""}`}>{c.alertas}</td>
                  {gestionar && <td><button title="Editar" onClick={() => setEdicion({ id: c.id, nit: c.nit, nombre: c.nombre, activo: c.activo })}><Pencil className="h-4 w-4 text-slate-400 hover:text-marca-700" /></button></td>}
                </tr>
              ))}
              {lista && !visibles.length && <tr><td colSpan={10} className="py-8 text-center text-slate-400">Sin clientes.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
