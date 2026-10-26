"use client";

import { Paperclip, ShieldAlert, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Alerta } from "@/components/ui";
import { ApiError, api, apiEnvelope, mensajeError, subirArchivo } from "@/lib/api";
import { hoyISO, valorItem, type ItemMfp, type Mfp, type TipoDocumento } from "@/lib/costeo";

export const MAX_SOPORTES = 5;
export const ACEPTA_SOPORTE = "application/pdf,image/png,image/jpeg,.pdf,.png,.jpg,.jpeg";

/** Sube los soportes de un movimiento uno por uno; devuelve los nombres que no se pudieron subir con el motivo. */
export async function subirSoportes(movimientoId: number, archivos: File[]): Promise<string[]> {
  const fallas: string[] = [];
  for (const a of archivos) {
    try {
      await subirArchivo(`/costeo/movimientos/${movimientoId}/soportes`, a);
    } catch (e) {
      fallas.push(`${a.name}: ${mensajeError(e)}`);
    }
  }
  return fallas;
}

/** Ventana modal y registro de movimientos de MFP (pagos, aplicaciones y solicitudes de horas). */

export function Modal({ titulo, onCerrar, children }: { titulo: string; onCerrar: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-4" onClick={onCerrar}>
      <div className="tarjeta max-h-[90vh] w-full max-w-lg overflow-y-auto p-5" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-semibold text-slate-800">{titulo}</h2>
          <button onClick={onCerrar}><X className="h-5 w-5 text-slate-400" /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function ModalMovimiento({ item, onCerrar, onGuardado }: { item: ItemMfp; onCerrar: () => void; onGuardado: (m: Mfp) => void }) {
  const horas = item.unidad === "horas";
  const [f, setF] = useState({ fecha: hoyISO(), valor: "", descripcion: "", tipo_documento: "", numero_documento: "", soporte: "", autorizacion: "" });
  const [tipos, setTipos] = useState<TipoDocumento[]>([]);
  const [archivos, setArchivos] = useState<File[]>([]);
  const [tope, setTope] = useState<{ mensaje: string; puede: boolean } | null>(null);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState("");
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    api<TipoDocumento[]>("/costeo/tipos-documento").then((t) => setTipos(t.filter((x) => x.activo))).catch(() => {});
  }, []);
  async function guardar() {
    setError("");
    setGuardando(true);
    try {
      const r = await apiEnvelope<Mfp>(`/costeo/items/${item.id}/movimientos`, { method: "POST", json: { ...f, valor: Number(f.valor) } });
      const movId = r.meta.extra?.movimiento_id as number | undefined;
      if (movId && archivos.length) {
        const fallas = await subirSoportes(movId, archivos);
        const m = await api<Mfp>(`/costeo/mfp/${r.data!.id}`);
        if (fallas.length) {
          setError(`El movimiento quedó registrado, pero no se pudieron subir estos soportes (adjúntelos desde la lista de movimientos): ${fallas.join(" · ")}`);
          setArchivos([]);
          return;
        }
        onGuardado(m);
      } else onGuardado(r.data!);
    } catch (e) {
      if (e instanceof ApiError && e.code === "TOPE_EXCEDIDO") {
        const d = (e.details?.[0] ?? {}) as { puede_autorizar?: boolean };
        setTope({ mensaje: e.message, puede: !!d.puede_autorizar });
      } else setError(mensajeError(e));
    } finally {
      setGuardando(false);
    }
  }
  const faltaDocumento = !horas && (!f.tipo_documento || !f.numero_documento.trim());
  const disponible = horas ? item.anios.find((a) => a.actual)?.saldo ?? 0 : item.pendiente;
  return (
    <Modal titulo={`${horas ? "Solicitud de horas" : "Registrar ejecución"} · ${item.tipo}`} onCerrar={onCerrar}>
      <div className="space-y-3">
        <p className="text-sm text-slate-600">Disponible: <b>{valorItem(disponible, item.unidad)}</b>{horas ? " en el año en curso del contrato" : ""}</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <div><label className="label">Fecha {horas ? "del servicio" : ""}</label><input type="date" className="input" value={f.fecha} onChange={(e) => setF({ ...f, fecha: e.target.value })} /></div>
          <div><label className="label">{horas ? "Horas" : "Valor"}</label><input type="number" className="input" value={f.valor} onChange={(e) => setF({ ...f, valor: e.target.value })} /></div>
          <div className="sm:col-span-2"><label className="label">Descripción</label>
            <input className="input" placeholder={horas ? "Ej. acompañamiento 2 h por cumpleaños" : "Ej. pago bono de libre inversión"} value={f.descripcion} onChange={(e) => setF({ ...f, descripcion: e.target.value })} /></div>
          <div><label className="label">Tipo de documento contable{horas ? " (opcional)" : ""}</label>
            <select className="input" value={f.tipo_documento} onChange={(e) => setF({ ...f, tipo_documento: e.target.value })}>
              <option value="">Seleccione…</option>{tipos.map((t) => <option key={t.codigo} value={t.codigo}>{t.codigo} · {t.nombre}</option>)}
            </select></div>
          <div><label className="label">Número del documento{horas ? " (opcional)" : ""}</label>
            <input className="input" placeholder="Ej. 4521" value={f.numero_documento} onChange={(e) => setF({ ...f, numero_documento: e.target.value })} /></div>
          <div className="sm:col-span-2"><label className="label">Observación</label>
            <input className="input" placeholder={horas ? "Quién lo solicitó, orden de servicio…" : "Proveedor, factura cruzada…"} value={f.soporte} onChange={(e) => setF({ ...f, soporte: e.target.value })} /></div>
          <div className="sm:col-span-2">
            <label className="label">Soporte contable (PDF o foto, hasta 10 MB)</label>
            <input ref={input} type="file" multiple accept={ACEPTA_SOPORTE} className="hidden"
              onChange={(e) => { setArchivos([...archivos, ...Array.from(e.target.files ?? [])].slice(0, MAX_SOPORTES)); e.target.value = ""; }} />
            <button type="button" className="btn-secundario" disabled={archivos.length >= MAX_SOPORTES} onClick={() => input.current?.click()}>
              <Paperclip className="h-4 w-4" /> Adjuntar soporte
            </button>
            {archivos.length > 0 && (
              <ul className="mt-2 space-y-1 text-sm">
                {archivos.map((a, i) => (
                  <li key={i} className="flex items-center gap-2 text-slate-600">
                    <Paperclip className="h-3.5 w-3.5" /><span className="truncate">{a.name}</span>
                    <span className="text-xs text-slate-400">{Math.ceil(a.size / 1024)} KB</span>
                    <button type="button" className="ml-auto text-slate-400 hover:text-red-600" aria-label="Quitar" onClick={() => setArchivos(archivos.filter((_, j) => j !== i))}><X className="h-4 w-4" /></button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
        {tope && (
          <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">
            <p className="flex items-start gap-1.5"><ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />{tope.mensaje}</p>
            {tope.puede && (
              <div className="mt-2"><label className="label">Autorización (quién lo aprobó y el soporte)</label>
                <input className="input" value={f.autorizacion} onChange={(e) => setF({ ...f, autorizacion: e.target.value })} /></div>
            )}
          </div>
        )}
        {error && <Alerta>{error}</Alerta>}
        <div className="flex justify-end gap-2">
          <button className="btn-secundario" onClick={onCerrar}>Cancelar</button>
          <button className="btn-primario" disabled={guardando || !f.valor || f.descripcion.trim().length < 2 || faltaDocumento || (tope !== null && !tope.puede)} onClick={guardar}>
            {guardando ? "Guardando…" : tope?.puede ? "Registrar con autorización" : "Registrar"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

