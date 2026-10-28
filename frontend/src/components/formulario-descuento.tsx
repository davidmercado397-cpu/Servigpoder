"use client";

import { X } from "lucide-react";
import { useState } from "react";
import { BuscarEmpleado } from "@/components/buscar-empleado";
import { Alerta } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";
import { pesos } from "@/lib/formato";
import { QUINCENAS, type Descuento, type Quincena } from "@/lib/liquidador";

type Formulario = {
  documento: string; tipo: "prestamo" | "embargo"; descripcion: string; forma: "valor" | "porcentaje";
  valor_mensual: string; porcentaje: string; monto_total: string; desde: string; hasta: string; quincena: Quincena; activo: boolean;
};

const hoy = () => new Date().toISOString().slice(0, 10);

function inicial(d: Descuento | null, documento: string): Formulario {
  if (!d) {
    return { documento, tipo: "prestamo", descripcion: "", forma: "valor", valor_mensual: "", porcentaje: "", monto_total: "",
      desde: hoy(), hasta: "", quincena: "ambas", activo: true };
  }
  return {
    documento: d.documento, tipo: d.tipo, descripcion: d.descripcion, forma: d.porcentaje !== null ? "porcentaje" : "valor",
    valor_mensual: d.valor_mensual?.toString() ?? "", porcentaje: d.porcentaje?.toString() ?? "", monto_total: d.monto_total?.toString() ?? "",
    desde: d.desde, hasta: d.hasta ?? "", quincena: d.quincena ?? "ambas", activo: d.activo,
  };
}

/** Nuevo préstamo o embargo, o edición de uno. Con `documento` queda fijo el empleado (ficha del empleado). */
export function FormularioDescuento({ registro, documento, onGuardado, onCancelar }: {
  registro: Descuento | null; documento?: string; onGuardado: () => void; onCancelar: () => void;
}) {
  const [f, setF] = useState<Formulario>(() => inicial(registro, documento ?? ""));
  const [error, setError] = useState("");
  const cambiar = (c: Partial<Formulario>) => setF({ ...f, ...c });

  async function guardar(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    const datos = {
      documento: f.documento.trim(), tipo: f.tipo, descripcion: f.descripcion.trim(),
      valor_mensual: f.forma === "valor" ? Number(f.valor_mensual) : null,
      porcentaje: f.forma === "porcentaje" ? Number(f.porcentaje) : null,
      monto_total: f.monto_total ? Number(f.monto_total) : null, desde: f.desde, hasta: f.hasta || null, quincena: f.quincena, activo: f.activo,
    };
    try {
      await api(registro ? `/liquidador/descuentos/${registro.id}` : "/liquidador/descuentos", { method: registro ? "PUT" : "POST", json: datos });
      onGuardado();
    } catch (err) {
      setError(mensajeError(err));
    }
  }

  return (
    <form onSubmit={guardar} className="tarjeta space-y-4 p-5">
      <div className="flex items-center">
        <h2 className="font-semibold text-slate-900">{registro ? "Editar préstamo o embargo" : "Nuevo préstamo o embargo"}</h2>
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
        <div>
          <label className="label">Tipo</label>
          <select className="input" value={f.tipo} onChange={(e) => cambiar({ tipo: e.target.value as Formulario["tipo"] })}>
            <option value="prestamo">Préstamo</option>
            <option value="embargo">Embargo</option>
          </select>
        </div>
        <div className="sm:col-span-2">
          <label className="label">Descripción</label>
          <input className="input" required maxLength={200} placeholder="p. ej. Préstamo de calamidad · Juzgado 3 de Cali" value={f.descripcion}
            onChange={(e) => cambiar({ descripcion: e.target.value })} />
        </div>
        <div>
          <label className="label">Se descuenta</label>
          <select className="input" value={f.forma} onChange={(e) => cambiar({ forma: e.target.value as Formulario["forma"] })}>
            <option value="valor">Valor fijo mensual</option>
            <option value="porcentaje">% del devengado</option>
          </select>
        </div>
        {f.forma === "valor" ? (
          <div>
            <label className="label">Cuota mensual</label>
            <input className="input" type="number" min={1} required value={f.valor_mensual} onChange={(e) => cambiar({ valor_mensual: e.target.value })} />
            {f.valor_mensual && <p className="mt-1 text-xs text-slate-500">
              {f.quincena === "ambas" ? `Por quincena: ${pesos(Number(f.valor_mensual) / 2)}` : `Completa en la ${f.quincena === "primera" ? "1.ª" : "2.ª"} quincena`}</p>}
          </div>
        ) : (
          <div>
            <label className="label">Porcentaje</label>
            <input className="input" type="number" min={0.01} max={100} step="0.01" required value={f.porcentaje} onChange={(e) => cambiar({ porcentaje: e.target.value })} />
          </div>
        )}
        <div>
          <label className="label">Quincena en que se descuenta</label>
          <select className="input" value={f.quincena} onChange={(e) => cambiar({ quincena: e.target.value as Quincena })}>
            {QUINCENAS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
          </select>
        </div>
        <div>
          <label className="label">Monto total (opcional)</label>
          <input className="input" type="number" min={1} value={f.monto_total} onChange={(e) => cambiar({ monto_total: e.target.value })} />
          <p className="mt-1 text-xs text-slate-500">Vacío: descuenta hasta desactivarlo</p>
        </div>
        <div className="grid grid-cols-2 gap-2">
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
