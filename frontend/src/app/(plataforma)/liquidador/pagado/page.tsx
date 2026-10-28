"use client";

import { Download, Search } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Paginador, metaDe, usePaginacion, type MetaPagina } from "@/components/paginacion";
import { Alerta, Insignia, Titulo } from "@/components/ui";
import { apiEnvelope, mensajeError } from "@/lib/api";
import { MESES, pesos } from "@/lib/formato";
import { CAMPOS_PAGADO, ESTADO_PERIODO, type NominaDelMes, type PersonaPagada } from "@/lib/liquidador";

const RESUMEN = ["devengado", "deducciones", "neto"];

export default function PagadoPorMes() {
  const hoy = new Date();
  const [anio, setAnio] = useState(hoy.getFullYear());
  const [mes, setMes] = useState(hoy.getMonth() + 1);
  const [q, setQ] = useState("");
  const [personas, setPersonas] = useState<PersonaPagada[]>([]);
  const [nominas, setNominas] = useState<NominaDelMes[]>([]);
  const [totales, setTotales] = useState<Record<string, number>>({});
  const [abiertas, setAbiertas] = useState(0);
  const [meta, setMeta] = useState<MetaPagina | null>(null);
  const [error, setError] = useState("");
  const pag = usePaginacion([anio, mes, q]);

  const cargar = useCallback(async () => {
    const r = await apiEnvelope<PersonaPagada[]>(`/liquidador/reportes/pagado?anio=${anio}&mes=${mes}&q=${encodeURIComponent(q)}&${pag.query}`);
    setPersonas(r.data ?? []);
    setMeta(metaDe(r));
    setNominas((r.meta.extra?.nominas as NominaDelMes[]) ?? []);
    setTotales((r.meta.extra?.totales as Record<string, number>) ?? {});
    setAbiertas(Number(r.meta.extra?.abiertas ?? 0));
  }, [anio, mes, q, pag.query]);

  useEffect(() => {
    setError("");
    const t = setTimeout(() => cargar().catch((e) => setError(mensajeError(e))), 250);
    return () => clearTimeout(t);
  }, [cargar]);

  return (
    <div className="space-y-5">
      <Titulo>Pagado por mes</Titulo>
      <p className="-mt-4 text-sm text-slate-500">
        Suma de las nóminas cerradas del mes (1.ª y 2.ª quincena o mensual, de todos los clientes). Una nómina abierta no cuenta como pagada.
      </p>
      {error && <Alerta>{error}</Alerta>}
      <div className="tarjeta flex flex-wrap items-end gap-3 p-4">
        <div>
          <label className="label">Año</label>
          <input className="input w-24" type="number" min={2020} max={2100} value={anio} onChange={(e) => setAnio(Number(e.target.value))} />
        </div>
        <div>
          <label className="label">Mes</label>
          <select className="input w-40" value={mes} onChange={(e) => setMes(Number(e.target.value))}>
            {MESES.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
          </select>
        </div>
        {nominas.length > 0 && (
          <a className="btn-secundario ml-auto inline-flex items-center gap-1.5" href={`/api/liquidador/reportes/pagado/excel?anio=${anio}&mes=${mes}`}>
            <Download className="h-4 w-4" /> Descargar Excel
          </a>
        )}
      </div>

      {abiertas > 0 && (
        <Alerta tipo="info">{abiertas === 1 ? "1 nómina del mes está abierta" : `${abiertas} nóminas del mes están abiertas`} y no suma como pagada hasta que se cierre.</Alerta>
      )}

      <div className="grid gap-3 sm:grid-cols-3">
        {RESUMEN.map((k) => (
          <div key={k} className="tarjeta p-4">
            <p className="text-xs text-slate-500">{CAMPOS_PAGADO.find(([c]) => c === k)?.[1]}</p>
            <p className="text-xl font-bold tabular-nums text-slate-900">{pesos(totales[k] ?? 0)}</p>
          </div>
        ))}
      </div>

      <div className="tarjeta overflow-auto">
        <p className="border-b border-slate-200 px-4 py-3 font-semibold text-slate-800">Nóminas del mes</p>
        <table className="tabla">
          <thead>
            <tr><th>Nómina</th><th>Periodo</th><th>Estado</th><th className="text-right">Personas</th>
              {RESUMEN.map((k) => <th key={k} className="text-right">{CAMPOS_PAGADO.find(([c]) => c === k)?.[1]}</th>)}</tr>
          </thead>
          <tbody>
            {nominas.map((n) => {
              const [texto, color] = ESTADO_PERIODO[n.estado as keyof typeof ESTADO_PERIODO] ?? [n.estado, ""];
              return (
                <tr key={n.id} className={n.incluida ? "" : "text-slate-400"}>
                  <td><Link href={`/liquidador/quincenas/${n.id}`} className="font-medium text-marca-700 hover:underline">{n.nombre}</Link></td>
                  <td>{n.tipo === "Mensual" ? "Mensual" : n.tipo === "Q1" ? "1.ª quincena" : "2.ª quincena"}</td>
                  <td><Insignia color={color}>{texto}</Insignia>{!n.incluida && <span className="ml-2 text-xs">no suma</span>}</td>
                  <td className="text-right tabular-nums">{n.personas}</td>
                  {RESUMEN.map((k) => <td key={k} className="text-right tabular-nums">{pesos(Number(n[k] ?? 0))}</td>)}
                </tr>
              );
            })}
            {nominas.length === 0 && <tr><td colSpan={7} className="py-6 text-center text-sm text-slate-500">No hay nóminas en este mes.</td></tr>}
          </tbody>
        </table>
      </div>

      <div className="tarjeta overflow-hidden">
        <div className="flex flex-wrap items-center gap-3 border-b border-slate-200 px-4 py-3">
          <p className="font-semibold text-slate-800">Por persona (nóminas cerradas)</p>
          <div className="relative ml-auto w-72">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input className="input pl-8" placeholder="Buscar por cédula o nombre…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
        </div>
        <div className="overflow-auto">
          <table className="tabla">
            <thead>
              <tr><th>Documento</th><th>Nombre</th><th>Nóminas</th>{CAMPOS_PAGADO.map(([k, t]) => <th key={k} className="text-right">{t}</th>)}</tr>
            </thead>
            <tbody>
              {personas.map((x) => (
                <tr key={x.empleado_id}>
                  <td className="font-mono">{x.documento}</td>
                  <td className="whitespace-nowrap">{x.nombre}</td>
                  <td className="text-xs text-slate-500">{x.nominas.join(", ")}</td>
                  {CAMPOS_PAGADO.map(([k]) => <td key={k} className="text-right tabular-nums">{pesos(Number(x[k] ?? 0))}</td>)}
                </tr>
              ))}
              {personas.length === 0 && (
                <tr><td colSpan={3 + CAMPOS_PAGADO.length} className="py-6 text-center text-sm text-slate-500">Sin nóminas cerradas en este mes.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        <Paginador meta={meta} onPagina={pag.setPagina} onTamano={pag.setTamano} />
      </div>
    </div>
  );
}
