"use client";

import { Search } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Paginador, metaDe, usePaginacion, type MetaPagina } from "@/components/paginacion";
import { Alerta, Insignia, Pestanas, Titulo } from "@/components/ui";
import { apiEnvelope, mensajeError } from "@/lib/api";
import { fechaCorta, qInicial, type SalidaHistorico } from "@/lib/gestion";
import type { Empleado } from "@/lib/liquidador";

type Vista = "saldos" | "salidas";
const ESTADO_SALIDA: Record<string, [string, string]> = {
  historico: ["Disfrutada", "bg-slate-100 text-slate-700"], programada: ["Programada", "bg-sky-100 text-sky-800"],
  cancelada: ["Cancelada", "bg-rose-100 text-rose-800"],
};
const anioActual = new Date().getFullYear();

export default function HistoricoVacaciones() {
  const [vista, setVista] = useState<Vista>("saldos");
  const [saldos, setSaldos] = useState<Empleado[]>([]);
  const [salidas, setSalidas] = useState<SalidaHistorico[]>([]);
  const [meta, setMeta] = useState<MetaPagina | null>(null);
  const [q, setQ] = useState("");
  useEffect(() => setQ(qInicial()), []);  // desde la ficha llega ?q=documento
  const [estado, setEstado] = useState("");
  const [anio, setAnio] = useState("");
  const [error, setError] = useState("");
  const pag = usePaginacion([q, estado, anio, vista]);

  const cargar = useCallback(async () => {
    if (vista === "saldos") {
      const r = await apiEnvelope<Empleado[]>(`/liquidador/empleados?q=${encodeURIComponent(q)}&estado=activo&${pag.query}`);
      setSaldos(r.data ?? []);
      setMeta(metaDe(r));
    } else {
      const r = await apiEnvelope<SalidaHistorico[]>(`/liquidador/personal/salidas?q=${encodeURIComponent(q)}&estado=${estado}&anio=${anio}&${pag.query}`);
      setSalidas(r.data ?? []);
      setMeta(metaDe(r));
    }
  }, [vista, q, estado, anio, pag.query]);

  useEffect(() => {
    const t = setTimeout(() => cargar().catch((e) => setError(mensajeError(e))), 250);
    return () => clearTimeout(t);
  }, [cargar]);

  return (
    <div className="space-y-5">
      <Titulo>Histórico de vacaciones</Titulo>
      <p className="-mt-4 text-sm text-slate-500">
        Saldo de cada persona activa (días causados con el año de 360 días, menos los disfrutados hasta el corte del libro y los días V liquidados
        después) y las salidas registradas. Las salidas se registran en la ficha de cada empleado; la liquidación está en Nómina → Liquidar vacaciones.
      </p>
      {error && <Alerta>{error}</Alerta>}
      <div className="tarjeta overflow-hidden">
        <div className="px-4 pt-3">
          <Pestanas<Vista> opciones={[["saldos", "Saldos pendientes"], ["salidas", "Salidas a vacaciones"]]} valor={vista} onChange={setVista} />
        </div>
        <div className="flex flex-wrap items-center gap-3 px-4 pb-3">
          <div className="relative w-72">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input className="input pl-8" placeholder="Buscar por cédula o nombre…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          {vista === "salidas" && (
            <>
              <select className="input w-40" value={estado} onChange={(e) => setEstado(e.target.value)} aria-label="Estado">
                <option value="">Todas</option>
                <option value="historico">Disfrutadas</option>
                <option value="programada">Programadas</option>
                <option value="cancelada">Canceladas</option>
              </select>
              <select className="input w-32" value={anio} onChange={(e) => setAnio(e.target.value)} aria-label="Año">
                <option value="">Todos los años</option>
                {Array.from({ length: 6 }, (_, i) => anioActual + 1 - i).map((a) => <option key={a} value={a}>{a}</option>)}
              </select>
            </>
          )}
          {meta && <span className="text-sm text-slate-500">{meta.total.toLocaleString("es-CO")} {vista === "saldos" ? "personas" : "salidas"}</span>}
        </div>
        <div className="overflow-auto">
          {vista === "saldos" ? (
            <table className="tabla text-sm">
              <thead><tr><th>Empleado</th><th>Ingreso</th><th className="text-right">Causados</th><th className="text-right">Disfrutados</th><th className="text-right">Pendientes</th></tr></thead>
              <tbody>
                {saldos.map((e) => {
                  const s = e.saldo_vacaciones;
                  return (
                    <tr key={e.id}>
                      <td><Link className="font-medium text-marca-700 hover:underline" href={`/liquidador/empleados/${e.id}`}>{e.nombre}</Link>
                        <span className="block text-xs text-slate-500"><span className="font-mono">{e.documento}</span>{e.puesto ? ` · ${e.puesto}` : ""}</span></td>
                      <td className="whitespace-nowrap text-xs">{fechaCorta(e.fecha_ingreso)}</td>
                      <td className="text-right tabular-nums">{s ? s.causados.toLocaleString("es-CO") : "—"}</td>
                      <td className="text-right tabular-nums">{s ? (s.previos + s.liquidador).toLocaleString("es-CO") : "—"}</td>
                      <td className={`text-right tabular-nums font-medium ${s && s.pendientes < 0 ? "text-red-700" : ""}`}>
                        {s ? s.pendientes.toLocaleString("es-CO") : <span className="text-xs font-normal text-slate-500">Sin fecha de ingreso</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <table className="tabla text-sm">
              <thead><tr><th>Empleado</th><th>Tipo</th><th>Desde</th><th>Hasta</th><th>Retoma</th><th className="text-right">Días hábiles</th><th>Estado</th><th>Observación</th></tr></thead>
              <tbody>
                {salidas.map((s) => (
                  <tr key={s.id}>
                    <td><Link className="font-medium text-marca-700 hover:underline" href={`/liquidador/empleados/${s.empleado_id}`}>{s.nombre}</Link>
                      <span className="block font-mono text-xs text-slate-500">{s.documento}</span></td>
                    <td className="text-xs">{s.tipo === "compensadas" ? "Compensadas" : "Disfrutadas"}</td>
                    <td className="whitespace-nowrap text-xs">{fechaCorta(s.desde)}</td>
                    <td className="whitespace-nowrap text-xs">{fechaCorta(s.hasta)}</td>
                    <td className="whitespace-nowrap text-xs">{fechaCorta(s.retorno)}</td>
                    <td className="text-right tabular-nums">{s.dias_habiles ?? "—"}</td>
                    <td><Insignia color={ESTADO_SALIDA[s.estado]?.[1]}>{ESTADO_SALIDA[s.estado]?.[0] ?? s.estado}</Insignia></td>
                    <td className="max-w-[240px] text-xs text-slate-600">{s.observacion}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {(vista === "saldos" ? saldos : salidas).length === 0 && <p className="p-6 text-center text-sm text-slate-500">Sin resultados.</p>}
        </div>
        <Paginador meta={meta} onPagina={pag.setPagina} onTamano={pag.setTamano} />
      </div>
    </div>
  );
}
