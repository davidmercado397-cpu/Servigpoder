"use client";

import { CheckCheck, Download, Loader2 } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Alerta, Titulo } from "@/components/ui";
import { ApiError, api, mensajeError } from "@/lib/api";
import { fecha, fechaHora, plata, type Factura } from "@/lib/contabilidad";
import { usePermiso } from "@/lib/sesion";

type Plano = { id: number; fecha: string; creado_en: string | null; facturas: (Factura & { documento: number; serie: string })[] };
const hoy = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };

export default function PlanoWorldOffice() {
  const revisar = usePermiso("contabilidad.revisar");
  const [listas, setListas] = useState<Factura[]>([]);
  const [elegidas, setElegidas] = useState<number[]>([]);
  const [fechaWo, setFechaWo] = useState("");
  const [planos, setPlanos] = useState<Plano[]>([]);
  const [marcar, setMarcar] = useState<Record<number, number[]>>({});
  const [ocupado, setOcupado] = useState("");
  const [msg, setMsg] = useState<{ tipo: "ok" | "error"; texto: string } | null>(null);

  const cargar = useCallback(() => {
    api<Factura[]>("/contabilidad/facturas?estado=lista").then((l) => { setListas(l); setElegidas(l.map((f) => f.id)); }).catch(() => {});
    api<Plano[]>("/contabilidad/planos").then((p) => {
      setPlanos(p);
      setMarcar(Object.fromEntries(p.map((x) => [x.id, x.facturas.filter((f) => f.estado === "lista").map((f) => f.id)])));
    }).catch(() => {});
  }, []);
  useEffect(() => { cargar(); }, [cargar]);

  async function descargar() {
    setMsg(null);
    setOcupado("plano");
    try {
      const res = await fetch("/api/contabilidad/plano", { method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-Requested-With": "fetch" }, body: JSON.stringify({ fecha: fechaWo, ids: elegidas }) });
      if (!res.ok) {
        const cuerpo = await res.json().catch(() => null);
        throw new ApiError(res.status, cuerpo?.error?.message ?? `Error ${res.status}`);
      }
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = /filename="([^"]+)"/.exec(res.headers.get("content-disposition") ?? "")?.[1] ?? "plano.xls";
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
      setMsg({ tipo: "ok", texto: "Plano descargado. Cárguelo en World Office y luego marque abajo las facturas que quedaron contabilizadas." });
      cargar();
    } catch (e) { setMsg({ tipo: "error", texto: mensajeError(e) }); } finally { setOcupado(""); }
  }
  async function contabilizar(p: Plano) {
    const ids = marcar[p.id] ?? [];
    if (!ids.length || !confirm(`¿Marcar ${ids.length} factura(s) como contabilizadas? Ya no saldrán en el plano.`)) return;
    setMsg(null);
    setOcupado(`p${p.id}`);
    try {
      const r = await api<{ contabilizadas: number }>(`/contabilidad/planos/${p.id}/contabilizar`, { method: "POST", json: { ids } });
      setMsg({ tipo: "ok", texto: `${r.contabilizadas} factura(s) quedaron contabilizadas.` });
      cargar();
    } catch (e) { setMsg({ tipo: "error", texto: mensajeError(e) }); } finally { setOcupado(""); }
  }
  const alternar = (lista: number[], id: number) => (lista.includes(id) ? lista.filter((x) => x !== id) : [...lista, id]);
  const total = listas.filter((f) => elegidas.includes(f.id)).reduce((s, f) => s + f.total, 0);

  return (
    <div className="space-y-5">
      <Titulo>Plano para World Office</Titulo>
      {msg && <Alerta tipo={msg.tipo}>{msg.texto}</Alerta>}

      <section className="tarjeta space-y-3 p-4">
        <h2 className="font-semibold text-slate-800">1. Descargar el plano</h2>
        <p className="text-sm text-slate-500">Salen las facturas <b>listas</b> que aún no están contabilizadas: una fila por producto, con el número de documento
          AAMM + consecutivo del mes en las facturas (FC) y número seguido en las cuentas de cobro (DS). Las que marque como contabilizadas ya no vuelven a salir.</p>
        <div className="flex flex-wrap items-end gap-3">
          <div><label className="label">Fecha de cargue en World Office</label>
            <input type="date" className="input" value={fechaWo} onChange={(e) => setFechaWo(e.target.value)} /></div>
          <button className="btn-secundario" onClick={() => setFechaWo(hoy())}>Hoy</button>
          {revisar && <button className="btn-primario" disabled={!fechaWo || !elegidas.length || !!ocupado} onClick={descargar}>
            {ocupado === "plano" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />} Descargar plano (.xls)</button>}
        </div>
        {!fechaWo && <p className="text-xs text-amber-700">Digite la fecha de cargue antes de descargar.</p>}
        <div className="overflow-x-auto">
          <table className="tabla text-sm">
            <thead><tr><th className="w-8" /><th>Factura</th><th>Proveedor</th><th>Emisión</th><th className="text-right">Productos</th><th className="text-right">Total</th></tr></thead>
            <tbody>
              {listas.length === 0 && <tr><td colSpan={6} className="py-6 text-center text-slate-400">No hay facturas listas. <Link className="text-marca-700 underline" href="/contabilidad">Revise las recibidas</Link>.</td></tr>}
              {listas.map((f) => (
                <tr key={f.id} className="cursor-pointer hover:bg-slate-50" onClick={() => setElegidas(alternar(elegidas, f.id))}>
                  <td><input type="checkbox" readOnly checked={elegidas.includes(f.id)} /></td>
                  <td>{f.prefijo}{f.numero}{f.cuenta_cobro && <span className="ml-1 rounded bg-violet-100 px-1 text-xs text-violet-800">DS</span>}</td>
                  <td>{f.emisor_nombre}</td><td>{fecha(f.fecha_emision)}</td>
                  <td className="text-right">{f.lineas}</td><td className="text-right tabular-nums">{plata(f.total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {listas.length > 0 && <p className="text-right text-sm text-slate-600">{elegidas.length} factura(s) · total {plata(total)}</p>}
      </section>

      <section className="tarjeta space-y-3 p-4">
        <h2 className="font-semibold text-slate-800">2. Marcar las que quedaron contabilizadas</h2>
        {planos.length === 0 && <p className="text-sm text-slate-400">Aún no se ha descargado ningún plano.</p>}
        {planos.map((p) => {
          const pendientes = p.facturas.filter((f) => f.estado === "lista");
          return (
            <div key={p.id} className="rounded-lg border border-slate-200 p-3">
              <div className="mb-2 flex flex-wrap items-center gap-3">
                <p className="font-medium">Plano #{p.id} · cargue {fecha(p.fecha)} <span className="text-xs font-normal text-slate-500">(descargado {fechaHora(p.creado_en)})</span></p>
                {revisar && pendientes.length > 0 && (
                  <button className="btn-primario ml-auto px-3 py-1.5 text-sm" disabled={!!ocupado || !(marcar[p.id] ?? []).length} onClick={() => contabilizar(p)}>
                    {ocupado === `p${p.id}` ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCheck className="h-4 w-4" />} Marcar contabilizadas
                  </button>
                )}
              </div>
              <table className="tabla text-sm">
                <thead><tr><th className="w-8" /><th>Documento</th><th>Factura</th><th>Proveedor</th><th className="text-right">Total</th><th>Estado</th></tr></thead>
                <tbody>
                  {p.facturas.map((f) => {
                    const puede = f.estado === "lista";
                    return (
                      <tr key={f.id} className={puede ? "cursor-pointer hover:bg-slate-50" : "text-slate-400"}
                        onClick={() => puede && setMarcar({ ...marcar, [p.id]: alternar(marcar[p.id] ?? [], f.id) })}>
                        <td>{puede && <input type="checkbox" readOnly checked={(marcar[p.id] ?? []).includes(f.id)} />}</td>
                        <td className="font-mono">{f.serie} {f.documento}</td><td>{f.prefijo}{f.numero}</td><td>{f.emisor_nombre}</td>
                        <td className="text-right tabular-nums">{f.total != null ? plata(f.total) : "—"}</td>
                        <td className="text-xs">{f.estado === "contabilizada" ? `contabilizada (${f.documento_numero})` : f.estado === "lista" ? "por marcar" : f.estado}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          );
        })}
      </section>
    </div>
  );
}
