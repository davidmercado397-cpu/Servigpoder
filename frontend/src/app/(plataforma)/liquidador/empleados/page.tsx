"use client";

import { Search } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Paginador, metaDe, usePaginacion, type MetaPagina } from "@/components/paginacion";
import { Alerta, Titulo } from "@/components/ui";
import { apiEnvelope, mensajeError } from "@/lib/api";
import type { Empleado } from "@/lib/liquidador";

export default function Empleados() {
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

  return (
    <div className="space-y-5">
      <Titulo>Empleados</Titulo>
      <p className="-mt-4 text-sm text-slate-500">Consulta histórica: se crean y actualizan solos al cargar el Excel de cada quincena.</p>
      {error && <Alerta>{error}</Alerta>}
      <div className="tarjeta overflow-hidden">
        <div className="px-4 py-3">
          <div className="relative w-72">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input className="input pl-8" placeholder="Buscar por cédula o nombre…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
        </div>
        <div className="overflow-auto">
          <table className="tabla">
            <thead><tr><th>Documento</th><th>Nombre</th><th>Cargo</th><th>Última quincena</th><th className="text-right">Quincenas</th></tr></thead>
            <tbody>
              {lista.map((e) => (
                <tr key={e.id}>
                  <td className="font-mono">{e.documento}</td>
                  <td>{e.nombre}</td>
                  <td>{e.cargo}</td>
                  <td>{e.ultima ?? "—"}</td>
                  <td className="text-right tabular-nums">{e.quincenas}</td>
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
