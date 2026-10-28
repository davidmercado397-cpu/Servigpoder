"use client";

import { X } from "lucide-react";
import { useState } from "react";
import { Alerta } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";

/** Crea un empleado desde la plataforma con los datos básicos; lo demás se completa en su ficha. */
export function NuevoEmpleado({ onCreado, onCancelar }: { onCreado: (id: number) => void; onCancelar: () => void }) {
  const [f, setF] = useState({ documento: "", nombre: "", cargo: "Operario de aseo", tipo_personal: "operativo", puesto: "", tipo_contrato: "", fecha_ingreso: "" });
  const [error, setError] = useState("");
  const [guardando, setGuardando] = useState(false);
  const cambiar = (c: Partial<typeof f>) => setF({ ...f, ...c });

  async function guardar(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setGuardando(true);
    try {
      const r = await api<{ id: number }>("/liquidador/empleados", { method: "POST", json: {
        ...f, puesto: f.puesto || null, tipo_contrato: f.tipo_contrato || null, fecha_ingreso: f.fecha_ingreso || null } });
      onCreado(r.id);
    } catch (err) {
      setError(mensajeError(err));
      setGuardando(false);
    }
  }

  return (
    <form onSubmit={guardar} className="tarjeta space-y-4 p-5">
      <div className="flex items-center">
        <h2 className="font-semibold text-slate-900">Nuevo empleado</h2>
        <button type="button" className="ml-auto rounded-md p-1 text-slate-500 hover:bg-slate-100" onClick={onCancelar} aria-label="Cerrar"><X className="h-5 w-5" /></button>
      </div>
      {error && <Alerta>{error}</Alerta>}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <label className="label">Cédula o documento</label>
          <input className="input font-mono" required minLength={3} maxLength={32} value={f.documento} onChange={(e) => cambiar({ documento: e.target.value })} />
        </div>
        <div className="sm:col-span-2">
          <label className="label">Nombre completo</label>
          <input className="input" required minLength={3} maxLength={200} value={f.nombre} onChange={(e) => cambiar({ nombre: e.target.value })} />
        </div>
        <div>
          <label className="label">Tipo de personal</label>
          <select className="input" value={f.tipo_personal} onChange={(e) => cambiar({ tipo_personal: e.target.value })}>
            <option value="operativo">Operativo</option>
            <option value="administrativo">Administrativo</option>
          </select>
        </div>
        <div>
          <label className="label">Cargo</label>
          <input className="input" required maxLength={80} value={f.cargo} onChange={(e) => cambiar({ cargo: e.target.value })} />
        </div>
        <div className="sm:col-span-2">
          <label className="label">Puesto</label>
          <input className="input" maxLength={200} value={f.puesto} placeholder="p. ej. 002 - 19 GOBERNACIÓN" onChange={(e) => cambiar({ puesto: e.target.value })} />
        </div>
        <div>
          <label className="label">Fecha de ingreso</label>
          <input className="input" type="date" value={f.fecha_ingreso} onChange={(e) => cambiar({ fecha_ingreso: e.target.value })} />
        </div>
        <div>
          <label className="label">Tipo de contrato</label>
          <input className="input" maxLength={40} value={f.tipo_contrato} placeholder="p. ej. OBRA A LABOR" onChange={(e) => cambiar({ tipo_contrato: e.target.value })} />
        </div>
      </div>
      <p className="text-xs text-slate-500">
        Con la fecha de ingreso queda registrado su contrato y empieza a causar vacaciones. Salario, ARL, días hábiles y datos personales se
        completan en la ficha, que se abre al crear. Cuando aparezca en el Excel de una nómina se reconoce por su documento.
      </p>
      <div className="flex gap-2">
        <button className="btn-primario" disabled={guardando}>{guardando ? "Creando…" : "Crear y abrir la ficha"}</button>
        <button type="button" className="btn-secundario" onClick={onCancelar}>Cancelar</button>
      </div>
    </form>
  );
}
