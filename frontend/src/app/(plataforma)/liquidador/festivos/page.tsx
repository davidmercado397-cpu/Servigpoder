"use client";

import { Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Alerta, Insignia, Titulo } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";
import type { Festivo } from "@/lib/liquidador";
import { usePermiso } from "@/lib/sesion";

const ORIGEN: Record<string, [string, string]> = {
  nacional: ["Calendario nacional", "bg-marca-50 text-marca-700"],
  manual: ["Agregado a mano", "bg-emerald-50 text-emerald-700"],
  quitado: ["Quitado a mano", "bg-slate-200 text-slate-600"],
};

export default function Festivos() {
  const gestionar = usePermiso("liquidador.turnos.gestionar");
  const [anio, setAnio] = useState(new Date().getFullYear());
  const [lista, setLista] = useState<Festivo[]>([]);
  const [nuevo, setNuevo] = useState({ fecha: "", descripcion: "" });
  const [error, setError] = useState("");

  const cargar = useCallback(() => api<Festivo[]>(`/liquidador/festivos?anio=${anio}`).then(setLista), [anio]);

  useEffect(() => {
    cargar().catch((e) => setError(mensajeError(e)));
  }, [cargar]);

  async function ejecutar(fn: () => Promise<unknown>) {
    setError("");
    try {
      await fn();
      await cargar();
    } catch (e) {
      setError(mensajeError(e));
    }
  }

  return (
    <div className="space-y-5">
      <Titulo>Festivos {anio}</Titulo>
      <p className="-mt-4 text-sm text-slate-500">Calendario nacional de Colombia con ajustes manuales. Los cambios aplican a las quincenas que se carguen o recalculen después.</p>

      <div className="tarjeta flex flex-wrap items-end gap-3 p-4">
        <div>
          <label className="label">Año</label>
          <input className="input w-28" type="number" min={2000} max={2100} value={anio} onChange={(e) => setAnio(Number(e.target.value))} />
        </div>
        {gestionar && (
          <form className="flex flex-wrap items-end gap-3" onSubmit={(e) => {
            e.preventDefault();
            ejecutar(() => api("/liquidador/festivos", { method: "POST", json: nuevo }).then(() => setNuevo({ fecha: "", descripcion: "" })));
          }}>
            <div><label className="label">Fecha</label><input className="input" type="date" required value={nuevo.fecha} onChange={(e) => setNuevo({ ...nuevo, fecha: e.target.value })} /></div>
            <div><label className="label">Descripción</label><input className="input w-64" required maxLength={120} value={nuevo.descripcion} onChange={(e) => setNuevo({ ...nuevo, descripcion: e.target.value })} /></div>
            <button className="btn-primario inline-flex items-center gap-1.5"><Plus className="h-4 w-4" /> Añadir festivo</button>
          </form>
        )}
      </div>
      {error && <Alerta>{error}</Alerta>}

      <div className="tarjeta overflow-auto">
        <table className="tabla">
          <thead><tr><th>Fecha</th><th>Día</th><th>Descripción</th><th>Origen</th><th /></tr></thead>
          <tbody>
            {lista.map((f) => {
              const d = new Date(f.fecha + "T12:00:00");
              const [texto, color] = ORIGEN[f.origen];
              return (
                <tr key={f.fecha} className={f.vigente ? "" : "text-slate-400 line-through decoration-slate-300"}>
                  <td className="tabular-nums">{f.fecha}</td>
                  <td className="capitalize">{d.toLocaleDateString("es-CO", { weekday: "long" })}</td>
                  <td>{f.descripcion}</td>
                  <td className="no-underline"><Insignia color={color}>{texto}</Insignia></td>
                  <td className="text-right text-sm">
                    {gestionar && f.origen === "nacional" && (
                      <button className="text-slate-500 hover:text-red-700 hover:underline"
                        onClick={() => window.confirm(`¿Dejar de tratar el ${f.fecha} como festivo?`) && ejecutar(() => api("/liquidador/festivos/quitar", { method: "POST", json: { fecha: f.fecha } }))}>
                        Quitar
                      </button>
                    )}
                    {gestionar && f.ajuste_id !== null && (
                      <button className="text-marca-600 hover:underline" onClick={() => ejecutar(() => api(`/liquidador/festivos/ajustes/${f.ajuste_id}`, { method: "DELETE" }))}>
                        {f.origen === "manual" ? "Eliminar" : "Restablecer"}
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
