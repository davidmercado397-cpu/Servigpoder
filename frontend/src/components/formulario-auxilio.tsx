"use client";

import { X } from "lucide-react";
import { useState } from "react";
import { BuscarEmpleado } from "@/components/buscar-empleado";
import { Alerta } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";
import { pesos } from "@/lib/formato";
import { QUINCENAS, type Auxilio, type Quincena } from "@/lib/liquidador";

type Formulario = { documento: string; descripcion: string; valor_mensual: string; desde: string; hasta: string; quincena: Quincena; activo: boolean };

const hoy = () => new Date().toISOString().slice(0, 10);

/** Nuevo auxilio no prestacional o edición de uno. Con `documento` queda fijo el empleado (ficha del empleado). */
export function FormularioAuxilio({ registro, documento, onGuardado, onCancelar }: {
  registro: Auxilio | null; documento?: string; onGuardado: () => void; onCancelar: () => void;
}) {
  const [f, setF] = useState<Formulario>(() => registro
    ? { documento: registro.documento, descripcion: registro.descripcion, valor_mensual: String(registro.valor_mensual), desde: registro.desde,
      hasta: registro.hasta ?? "", quincena: registro.quincena, activo: registro.activo }
    : { documento: documento ?? "", descripcion: "", valor_mensual: "", desde: hoy(), hasta: "", quincena: "ambas", activo: true });
  const [error, setError] = useState("");
  const cambiar = (c: Partial<Formulario>) => setF({ ...f, ...c });

  async function guardar(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    const datos = { documento: f.documento.trim(), descripcion: f.descripcion.trim(), valor_mensual: Number(f.valor_mensual), desde: f.desde,
      hasta: f.hasta || null, quincena: f.quincena, activo: f.activo };
    try {
      await api(registro ? `/liquidador/auxilios/${registro.id}` : "/liquidador/auxilios", { method: registro ? "PUT" : "POST", json: datos });
      onGuardado();
    } catch (err) {
      setError(mensajeError(err));
    }
  }

  return (
    <form onSubmit={guardar} className="tarjeta space-y-4 p-5">
      <div className="flex items-center">
        <h2 className="font-semibold text-slate-900">{registro ? "Editar auxilio" : "Nuevo auxilio"}</h2>
        <button type="button" className="ml-auto rounded-md p-1 text-slate-500 hover:bg-slate-100" onClick={onCancelar} aria-label="Cerrar"><X className="h-5 w-5" /></button>
      </div>
      {error && <Alerta>{error}</Alerta>}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {!documento && (
          <div>
            <label className="label">Cédula del empleado</label>
            <BuscarEmpleado key={registro?.id ?? "nuevo"} valor={f.documento} nombreInicial={registro?.nombre} onCambio={(d) => cambiar({ documento: d })} />
          </div>
        )}
        <div className="sm:col-span-2">
          <label className="label">Descripción</label>
          <input className="input" required maxLength={200} placeholder="p. ej. Auxilio de rodamiento · Alimentación" value={f.descripcion}
            onChange={(e) => cambiar({ descripcion: e.target.value })} />
        </div>
        <div>
          <label className="label">Valor mensual</label>
          <input className="input" type="number" min={1} required value={f.valor_mensual} onChange={(e) => cambiar({ valor_mensual: e.target.value })} />
          {f.valor_mensual && <p className="mt-1 text-xs text-slate-500">
            {f.quincena === "ambas" ? `Por quincena: ${pesos(Number(f.valor_mensual) / 2)}` : `Completo en la ${f.quincena === "primera" ? "1.ª" : "2.ª"} quincena`}
            {` · ${pesos(Number(f.valor_mensual) / 30)} menos por día no laborado`}</p>}
        </div>
        <div>
          <label className="label">Quincena en que se paga</label>
          <select className="input" value={f.quincena} onChange={(e) => cambiar({ quincena: e.target.value as Quincena })}>
            {QUINCENAS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
          </select>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:col-span-2">
          <div>
            <label className="label">Desde</label>
            <input className="input" type="date" required value={f.desde} onChange={(e) => cambiar({ desde: e.target.value })} />
          </div>
          <div>
            <label className="label">Hasta</label>
            <input className="input" type="date" value={f.hasta} onChange={(e) => cambiar({ hasta: e.target.value })} />
          </div>
        </div>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={f.activo} onChange={(e) => cambiar({ activo: e.target.checked })} /> Activo
      </label>
      <div className="flex gap-2">
        <button className="btn-primario">Guardar</button>
        <button type="button" className="btn-secundario" onClick={onCancelar}>Cancelar</button>
      </div>
    </form>
  );
}
