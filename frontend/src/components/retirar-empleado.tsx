"use client";

import { UserMinus } from "lucide-react";
import { useEffect, useState } from "react";
import { Alerta } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";

const hoy = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

/** Retira a una persona: cierra su contrato abierto con la fecha y el motivo del retiro. */
export function RetirarEmpleado({ empleado, onRetirado, onCancelar }: {
  empleado: { id: number; nombre: string; documento: string }; onRetirado: () => void; onCancelar: () => void;
}) {
  const [f, setF] = useState({ fecha_retiro: hoy(), motivo_retiro: "", otro: "", observacion: "" });
  const [motivos, setMotivos] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [guardando, setGuardando] = useState(false);
  useEffect(() => {
    api<string[]>("/liquidador/personal/motivos-retiro").then(setMotivos).catch(() => {});
  }, []);
  const motivo = f.motivo_retiro === "__otro" ? f.otro.trim() : f.motivo_retiro;

  async function retirar(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setGuardando(true);
    try {
      await api(`/liquidador/empleados/${empleado.id}/retiro`, { method: "POST", json: {
        fecha_retiro: f.fecha_retiro, motivo_retiro: motivo, observacion: f.observacion.trim() || null } });
      onRetirado();
    } catch (err) {
      setError(mensajeError(err));
      setGuardando(false);
    }
  }

  return (
    <form onSubmit={retirar} className="space-y-4 p-5">
      <div>
        <h2 className="flex items-center gap-2 text-lg font-semibold text-slate-800"><UserMinus className="h-5 w-5 text-rose-600" /> Retirar a {empleado.nombre}</h2>
        <p className="text-sm text-slate-500">Documento <span className="font-mono">{empleado.documento}</span>. Se cierra su contrato con esta fecha y pasa a retirados;
          queda en su historial laboral, donde se puede corregir.</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div><label className="label">Fecha del retiro</label>
          <input className="input" type="date" required value={f.fecha_retiro} onChange={(e) => setF({ ...f, fecha_retiro: e.target.value })} /></div>
        <div><label className="label">Motivo del retiro</label>
          <select className="input" required value={f.motivo_retiro} onChange={(e) => setF({ ...f, motivo_retiro: e.target.value })}>
            <option value="">Seleccione…</option>
            {motivos.map((m) => <option key={m} value={m}>{m}</option>)}
            <option value="__otro">Otro (escribirlo)</option>
          </select></div>
        {f.motivo_retiro === "__otro" && (
          <div className="sm:col-span-2"><label className="label">¿Cuál motivo?</label>
            <input className="input" required maxLength={200} value={f.otro} onChange={(e) => setF({ ...f, otro: e.target.value })} /></div>
        )}
        <div className="sm:col-span-2"><label className="label">Observación (opcional)</label>
          <input className="input" maxLength={300} value={f.observacion} onChange={(e) => setF({ ...f, observacion: e.target.value })} /></div>
      </div>
      {error && <Alerta>{error}</Alerta>}
      <div className="flex justify-end gap-2">
        <button type="button" className="btn-secundario" onClick={onCancelar}>Cancelar</button>
        <button type="submit" className="btn-primario bg-rose-600 hover:bg-rose-700" disabled={guardando || !f.fecha_retiro || motivo.length < 2}>
          {guardando ? "Retirando…" : "Retirar"}
        </button>
      </div>
    </form>
  );
}
