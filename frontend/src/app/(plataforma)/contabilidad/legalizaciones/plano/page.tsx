"use client";

import { CheckCheck, Download, Loader2, Trash2 } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Paginador, metaDe, usePaginacion, type MetaPagina } from "@/components/paginacion";
import { Alerta, Titulo } from "@/components/ui";
import { ApiError, api, apiEnvelope, mensajeError } from "@/lib/api";
import { TAMANOS, fecha, fechaHora, plata, type Legalizacion } from "@/lib/contabilidad";
import { usePermiso } from "@/lib/sesion";

type Plano = { id: number; fecha: string; creado_en: string | null; legalizaciones: (Legalizacion & { documento: number })[] };
const hoy = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
const alternar = (lista: number[], id: number) => (lista.includes(id) ? lista.filter((x) => x !== id) : [...lista, id]);

export default function PlanoLegalizaciones() {
  const revisar = usePermiso("contabilidad.revisar");
  const [listas, setListas] = useState<Legalizacion[]>([]);
  const [elegidas, setElegidas] = useState<number[]>([]);
  const [fechaWo, setFechaWo] = useState("");
  const [planos, setPlanos] = useState<Plano[]>([]);
  const [meta, setMeta] = useState<MetaPagina | null>(null);
  const [marcar, setMarcar] = useState<Record<number, number[]>>({});
  const [ocupado, setOcupado] = useState("");
  const [msg, setMsg] = useState<{ tipo: "ok" | "error"; texto: string } | null>(null);
  const pag = usePaginacion([], TAMANOS);

  const cargar = useCallback(() => {
    api<Legalizacion[]>("/contabilidad/legalizaciones/plano/todas").then((l) => { setListas(l); setElegidas(l.map((x) => x.id)); }).catch(() => {});
    apiEnvelope<Plano[]>(`/contabilidad/legalizaciones/plano/planos?${pag.query}`).then((r) => {
      const p = r.data ?? [];
      setPlanos(p);
      setMeta(metaDe(r));
      setMarcar(Object.fromEntries(p.map((x) => [x.id, x.legalizaciones.filter((y) => y.estado === "lista").map((y) => y.id)])));
    }).catch(() => {});
  }, [pag.query]);
  useEffect(() => { cargar(); }, [cargar]);

  async function descargar() {
    setMsg(null);
    setOcupado("plano");
    try {
      const res = await fetch("/api/contabilidad/legalizaciones/plano/descargar", { method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-Requested-With": "fetch" }, body: JSON.stringify({ fecha: fechaWo, ids: elegidas }) });
      if (!res.ok) {
        const cuerpo = await res.json().catch(() => null);
        throw new ApiError(res.status, cuerpo?.error?.message ?? `Error ${res.status}`);
      }
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = /filename="([^"]+)"/.exec(res.headers.get("content-disposition") ?? "")?.[1] ?? "plano_legalizaciones.xls";
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
      setMsg({ tipo: "ok", texto: "Plano descargado. Cárguelo en World Office y marque abajo las legalizaciones que quedaron contabilizadas." });
      cargar();
    } catch (e) { setMsg({ tipo: "error", texto: mensajeError(e) }); } finally { setOcupado(""); }
  }
  async function accion(p: Plano, tipo: "contabilizar" | "eliminar") {
    const ids = marcar[p.id] ?? [];
    if (tipo === "contabilizar" && (!ids.length || !confirm(`¿Marcar ${ids.length} legalización(es) como contabilizadas?`))) return;
    if (tipo === "eliminar" && !confirm(`¿Eliminar el plano #${p.id}? Las legalizaciones que se marcaron con él vuelven a «lista».`)) return;
    setMsg(null);
    setOcupado(`${tipo}${p.id}`);
    try {
      if (tipo === "contabilizar") {
        const r = await api<{ contabilizadas: number }>(`/contabilidad/legalizaciones/plano/planos/${p.id}/contabilizar`, { method: "POST", json: { ids } });
        setMsg({ tipo: "ok", texto: `${r.contabilizadas} legalización(es) contabilizadas.` });
      } else {
        const r = await api<{ devueltas: number }>(`/contabilidad/legalizaciones/plano/planos/${p.id}`, { method: "DELETE" });
        setMsg({ tipo: "ok", texto: `Plano #${p.id} eliminado${r.devueltas ? `: ${r.devueltas} volvieron a «lista»` : ""}.` });
      }
      cargar();
    } catch (e) { setMsg({ tipo: "error", texto: mensajeError(e) }); } finally { setOcupado(""); }
  }

  return (
    <div className="space-y-5">
      <Titulo>Plano de legalizaciones</Titulo>
      {msg && <Alerta tipo={msg.tipo}>{msg.texto}</Alerta>}
      <section className="tarjeta space-y-3 p-4">
        <h2 className="font-semibold text-slate-800">1. Descargar el plano (nota contable NC / LG)</h2>
        <div className="flex flex-wrap items-end gap-3">
          <div><label className="label">Fecha de cargue en World Office</label><input type="date" className="input" value={fechaWo} onChange={(e) => setFechaWo(e.target.value)} /></div>
          <button className="btn-secundario" onClick={() => setFechaWo(hoy())}>Hoy</button>
          {revisar && <button className="btn-primario" disabled={!fechaWo || !elegidas.length || !!ocupado} onClick={descargar}>
            {ocupado === "plano" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />} Descargar plano (.xls)</button>}
        </div>
        <table className="tabla text-sm">
          <thead><tr><th className="w-8" /><th>Formato</th><th>Colaborador</th><th>Legalización</th><th className="text-right">Gastos</th><th className="text-right">Total</th></tr></thead>
          <tbody>
            {listas.length === 0 && <tr><td colSpan={6} className="py-6 text-center text-slate-400">No hay legalizaciones listas. <Link className="text-marca-700 underline" href="/contabilidad/legalizaciones">Revise las cargadas</Link>.</td></tr>}
            {listas.map((x) => (
              <tr key={x.id} className="cursor-pointer hover:bg-slate-50" onClick={() => setElegidas(alternar(elegidas, x.id))}>
                <td><input type="checkbox" readOnly checked={elegidas.includes(x.id)} /></td><td>#{x.numero_formato || x.id}</td>
                <td>{x.colaborador_nombre}</td><td>{fecha(x.fecha_legalizacion)}</td><td className="text-right">{x.gastos}</td><td className="text-right tabular-nums">{plata(x.total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="tarjeta space-y-3 p-4">
        <h2 className="font-semibold text-slate-800">2. Marcar las que quedaron contabilizadas</h2>
        {planos.length === 0 && <p className="text-sm text-slate-400">Aún no se ha descargado ningún plano.</p>}
        {planos.map((p) => (
          <div key={p.id} className="rounded-lg border border-slate-200 p-3">
            <div className="mb-2 flex flex-wrap items-center gap-3">
              <p className="font-medium">Plano #{p.id} · cargue {fecha(p.fecha)} <span className="text-xs font-normal text-slate-500">(descargado {fechaHora(p.creado_en)})</span></p>
              {revisar && <button className="btn-secundario ml-auto px-3 py-1.5 text-sm text-red-700" disabled={!!ocupado} onClick={() => accion(p, "eliminar")}><Trash2 className="h-4 w-4" /> Eliminar</button>}
              {revisar && p.legalizaciones.some((y) => y.estado === "lista") && (
                <button className="btn-primario px-3 py-1.5 text-sm" disabled={!!ocupado || !(marcar[p.id] ?? []).length} onClick={() => accion(p, "contabilizar")}>
                  <CheckCheck className="h-4 w-4" /> Marcar contabilizadas</button>
              )}
            </div>
            <table className="tabla text-sm">
              <thead><tr><th className="w-8" /><th>Documento</th><th>Formato</th><th>Colaborador</th><th className="text-right">Total</th><th>Estado</th></tr></thead>
              <tbody>
                {p.legalizaciones.map((y) => {
                  const puede = y.estado === "lista";
                  return (
                    <tr key={y.id} className={puede ? "cursor-pointer hover:bg-slate-50" : "text-slate-400"}
                      onClick={() => puede && setMarcar({ ...marcar, [p.id]: alternar(marcar[p.id] ?? [], y.id) })}>
                      <td>{puede && <input type="checkbox" readOnly checked={(marcar[p.id] ?? []).includes(y.id)} />}</td>
                      <td className="font-mono">LG {y.documento}</td><td>#{y.numero_formato || y.id}</td><td>{y.colaborador_nombre}</td>
                      <td className="text-right tabular-nums">{y.total != null ? plata(y.total) : "—"}</td>
                      <td className="text-xs">{y.estado === "lista" ? "por marcar" : y.estado}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ))}
        {planos.length > 0 && <Paginador meta={meta} onPagina={pag.setPagina} onTamano={pag.setTamano} tamanos={TAMANOS} />}
      </section>
    </div>
  );
}
