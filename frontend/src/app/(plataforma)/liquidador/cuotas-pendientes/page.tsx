"use client";

import { Search } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Paginador, metaDe, usePaginacion, type MetaPagina } from "@/components/paginacion";
import { Alerta, Insignia, Titulo } from "@/components/ui";
import { apiEnvelope, mensajeError } from "@/lib/api";
import { pesos } from "@/lib/formato";
import { fechaCorta, qInicial, type CuotaPendiente } from "@/lib/gestion";
import { QUINCENAS, TIPOS_DESCUENTO } from "@/lib/liquidador";

export default function CuotasPendientes() {
  const [lista, setLista] = useState<CuotaPendiente[]>([]);
  const [meta, setMeta] = useState<MetaPagina | null>(null);
  const [q, setQ] = useState("");
  useEffect(() => setQ(qInicial()), []);  // desde la ficha llega ?q=documento
  const [tipo, setTipo] = useState("");
  const [error, setError] = useState("");
  const pag = usePaginacion([q, tipo]);

  const cargar = useCallback(async () => {
    const r = await apiEnvelope<CuotaPendiente[]>(`/liquidador/personal/cuotas-pendientes?q=${encodeURIComponent(q)}&tipo=${tipo}&${pag.query}`);
    setLista(r.data ?? []);
    setMeta(metaDe(r));
  }, [q, tipo, pag.query]);

  useEffect(() => {
    const t = setTimeout(() => cargar().catch((e) => setError(mensajeError(e))), 250);
    return () => clearTimeout(t);
  }, [cargar]);

  return (
    <div className="space-y-5">
      <Titulo>Cuotas pendientes</Titulo>
      <p className="-mt-4 text-sm text-slate-500">
        Préstamos, embargos y cuotas (plan exequial, pólizas…) activos de cada persona: lo descontado en las nóminas y lo que falta. Solo
        consulta: se registran y se modifican en Nómina → Préstamos, embargos y cuotas.
      </p>
      {error && <Alerta>{error}</Alerta>}
      <div className="tarjeta overflow-hidden">
        <div className="flex flex-wrap items-center gap-3 px-4 py-3">
          <div className="relative w-72">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input className="input pl-8" placeholder="Cédula, nombre o descripción…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <select className="input w-44" value={tipo} onChange={(e) => setTipo(e.target.value)} aria-label="Tipo">
            <option value="">Todos los tipos</option>
            {Object.entries(TIPOS_DESCUENTO).map(([v, [t]]) => <option key={v} value={v}>{t}</option>)}
          </select>
        </div>
        <div className="overflow-auto">
          <table className="tabla text-sm">
            <thead>
              <tr><th>Empleado</th><th>Tipo</th><th>Descripción</th><th className="text-right">Cuota mensual</th><th className="text-right">Monto total</th>
                <th className="text-right">Descontado</th><th className="text-right">Saldo</th><th>Vigencia</th></tr>
            </thead>
            <tbody>
              {lista.map((x) => (
                <tr key={x.id}>
                  <td><span className="font-medium">{x.nombre}</span><span className="block font-mono text-xs text-slate-500">{x.documento}</span></td>
                  <td><Insignia color={TIPOS_DESCUENTO[x.tipo][1]}>{TIPOS_DESCUENTO[x.tipo][0]}</Insignia></td>
                  <td>{x.descripcion}<span className="block text-xs text-slate-500">{QUINCENAS.find(([v]) => v === x.quincena)?.[1]}</span></td>
                  <td className="text-right tabular-nums">{x.valor_mensual !== null ? pesos(x.valor_mensual) : `${x.porcentaje} %`}</td>
                  <td className="text-right tabular-nums">{x.monto_total !== null ? pesos(x.monto_total) : "—"}</td>
                  <td className="text-right tabular-nums">{pesos(x.descontado)}</td>
                  <td className="text-right tabular-nums font-medium">{x.saldo !== null ? pesos(x.saldo) : <span className="text-xs font-normal text-slate-500">Hasta desactivarla</span>}</td>
                  <td className="whitespace-nowrap text-xs">{fechaCorta(x.desde)}{x.hasta ? ` → ${fechaCorta(x.hasta)}` : " en adelante"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {lista.length === 0 && <p className="p-6 text-center text-sm text-slate-500">No hay descuentos activos con esos filtros.</p>}
        </div>
        <Paginador meta={meta} onPagina={pag.setPagina} onTamano={pag.setTamano} />
      </div>
    </div>
  );
}
