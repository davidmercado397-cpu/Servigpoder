"use client";

import { Check, Pencil, Search, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Paginador, metaDe, usePaginacion, type MetaPagina } from "@/components/paginacion";
import { Alerta, Titulo } from "@/components/ui";
import { api, apiEnvelope, mensajeError } from "@/lib/api";
import { pesos } from "@/lib/formato";
import type { Empleado } from "@/lib/liquidador";
import { usePermiso } from "@/lib/sesion";

export default function Empleados() {
  const verNomina = usePermiso("liquidador.nomina.ver");
  const gestionarNomina = usePermiso("liquidador.nomina.gestionar");
  const [editando, setEditando] = useState<{ id: number; valor: string } | null>(null);
  const [aviso, setAviso] = useState("");
  const [lista, setLista] = useState<Empleado[]>([]);
  const [meta, setMeta] = useState<MetaPagina | null>(null);
  const [q, setQ] = useState("");
  const [error, setError] = useState("");
  const pag = usePaginacion([q]);

  const cargar = useCallback(async () => {
    const r = await apiEnvelope<Empleado[]>(`/liquidador/empleados?q=${encodeURIComponent(q)}&${pag.query}`);
    setLista(r.data ?? []);
    setMeta(metaDe(r));
  }, [q, pag.query]);

  useEffect(() => {
    const t = setTimeout(() => cargar().catch((e) => setError(mensajeError(e))), 250);
    return () => clearTimeout(t);
  }, [cargar]);

  async function guardarSalario(e: Empleado, valor: string) {
    setError("");
    try {
      await api(`/liquidador/empleados/${e.id}/salario`, { method: "PUT", json: { salario: valor.trim() ? Number(valor) : null } });
      setEditando(null);
      setAviso(`Salario de ${e.nombre} actualizado. Se aplica al calcular o recalcular cada periodo.`);
      await cargar();
    } catch (err) {
      setError(mensajeError(err));
    }
  }

  return (
    <div className="space-y-5">
      <Titulo>Empleados</Titulo>
      <p className="-mt-4 text-sm text-slate-500">Consulta histórica: se crean y actualizan solos al cargar el Excel de cada periodo.</p>
      {error && <Alerta>{error}</Alerta>}
      {aviso && <Alerta tipo="ok">{aviso}</Alerta>}
      <div className="tarjeta overflow-hidden">
        <div className="px-4 py-3">
          <div className="relative w-72">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input className="input pl-8" placeholder="Buscar por cédula o nombre…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
        </div>
        <div className="overflow-auto">
          <table className="tabla">
            <thead><tr><th>Documento</th><th>Nombre</th><th>Cargo</th><th>Último periodo</th><th className="text-right">Periodos</th>{verNomina && <th>Salario mensual</th>}</tr></thead>
            <tbody>
              {lista.map((e) => (
                <tr key={e.id}>
                  <td className="font-mono">{e.documento}</td>
                  <td>{e.nombre}</td>
                  <td>{e.cargo}</td>
                  <td>{e.ultima ?? "—"}</td>
                  <td className="text-right tabular-nums">{e.quincenas}</td>
                  {verNomina && (
                    <td className="whitespace-nowrap">
                      {editando?.id === e.id ? (
                        <span className="flex items-center gap-1">
                          <input className="input w-36" type="number" min={1} placeholder="Vacío = mínimo" autoFocus value={editando.valor}
                            onChange={(ev) => setEditando({ id: e.id, valor: ev.target.value })}
                            onKeyDown={(ev) => { if (ev.key === "Enter") guardarSalario(e, editando.valor); if (ev.key === "Escape") setEditando(null); }} />
                          <button className="rounded-md p-1 text-green-700 hover:bg-green-50" onClick={() => guardarSalario(e, editando.valor)} aria-label="Guardar"><Check className="h-4 w-4" /></button>
                          <button className="rounded-md p-1 text-slate-500 hover:bg-slate-100" onClick={() => setEditando(null)} aria-label="Cancelar"><X className="h-4 w-4" /></button>
                        </span>
                      ) : (
                        <span className="flex items-center gap-1">
                          {e.salario ? <span className="tabular-nums">{pesos(e.salario)}</span> : <span className="text-slate-500">Salario mínimo</span>}
                          {gestionarNomina && (
                            <button className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700" aria-label="Editar salario"
                              onClick={() => setEditando({ id: e.id, valor: e.salario?.toString() ?? "" })}><Pencil className="h-3.5 w-3.5" /></button>
                          )}
                        </span>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Paginador meta={meta} onPagina={pag.setPagina} onTamano={pag.setTamano} />
      </div>
    </div>
  );
}
