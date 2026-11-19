"use client";

import { UserMinus } from "lucide-react";
import { useState } from "react";
import { Modal } from "@/components/costeo";
import { Alerta } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";

/** Retiro de un empleado de Speed (renuncia ya liquidada aparte): no se liquida y el Listado no lo vuelve a activar. */
export function RetirarEmpleado({ empleadoId, nombre, fecha: fechaInicial, motivo: motivoInicial = "Renuncia", onCerrar, onListo }: {
  empleadoId: number; nombre: string; fecha?: string | null; motivo?: string; onCerrar: () => void; onListo: () => Promise<void>;
}) {
  const [fecha, setFecha] = useState(fechaInicial || new Date().toISOString().slice(0, 10));
  const [motivo, setMotivo] = useState(motivoInicial);
  const [error, setError] = useState("");
  const [guardando, setGuardando] = useState(false);
  return (
    <Modal titulo={`Retirar a ${nombre}`} onCerrar={onCerrar}>
      <form className="space-y-3" onSubmit={async (ev) => {
        ev.preventDefault();
        setGuardando(true);
        setError("");
        try { await api(`/speed/empleados/${empleadoId}/retirar`, { method: "POST", json: { fecha_retiro: fecha, motivo } }); await onListo(); }
        catch (err) { setError(mensajeError(err)); } finally { setGuardando(false); }
      }}>
        <p className="text-sm text-slate-600">Queda inactivo y <b>no se liquida</b> en las quincenas (su liquidación va aparte). Sale en la pestaña
          «Vacaciones y retiros» de la quincena, y si sigue en el Excel del Listado no se vuelve a activar. Se puede reintegrar desde Empleados.</p>
        <div><label className="label">Fecha de retiro (último día)</label>
          <input className="input" type="date" required value={fecha} onChange={(x) => setFecha(x.target.value)} /></div>
        <div><label className="label">Motivo</label><input className="input" maxLength={200} value={motivo} onChange={(x) => setMotivo(x.target.value)}
          placeholder="Ej. Renuncia, ya tiene liquidación" /></div>
        {error && <Alerta>{error}</Alerta>}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-secundario" onClick={onCerrar}>Cancelar</button>
          <button className="btn-primario" disabled={guardando}><UserMinus className="h-4 w-4" /> {guardando ? "Retirando…" : "Retirar"}</button>
        </div>
      </form>
    </Modal>
  );
}
