"use client";

import { ShieldAlert, X } from "lucide-react";
import { useState } from "react";
import { Alerta } from "@/components/ui";
import { ApiError, api, mensajeError } from "@/lib/api";
import { hoyISO, valorItem, type ItemMfp, type Mfp } from "@/lib/costeo";

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
  const [f, setF] = useState({ fecha: hoyISO(), valor: "", descripcion: "", soporte: "", autorizacion: "" });
  const [tope, setTope] = useState<{ mensaje: string; puede: boolean } | null>(null);
  const [error, setError] = useState("");
  async function guardar() {
    setError("");
    try {
      onGuardado(await api<Mfp>(`/costeo/items/${item.id}/movimientos`, { method: "POST", json: { ...f, valor: Number(f.valor) } }));
    } catch (e) {
      if (e instanceof ApiError && e.code === "TOPE_EXCEDIDO") {
        const d = (e.details?.[0] ?? {}) as { puede_autorizar?: boolean };
        setTope({ mensaje: e.message, puede: !!d.puede_autorizar });
      } else setError(mensajeError(e));
    }
  }
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
          <div className="sm:col-span-2"><label className="label">Soporte</label>
            <input className="input" placeholder={horas ? "Quién lo solicitó, orden de servicio…" : "Factura cruzada, proveedor, comprobante…"} value={f.soporte} onChange={(e) => setF({ ...f, soporte: e.target.value })} /></div>
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
          <button className="btn-primario" disabled={!f.valor || f.descripcion.trim().length < 2 || (tope !== null && !tope.puede)} onClick={guardar}>
            {tope?.puede ? "Registrar con autorización" : "Registrar"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

