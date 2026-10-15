"use client";

import { Plus, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Alerta, Titulo } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";
import { usePermiso } from "@/lib/sesion";

type Correccion = { id: number; plano: string; cedula: string; columna: string; valor: string; nota: string; creado_en: string };
const VACIA = { plano: "empleados", cedula: "", columna: "", valor: "", nota: "" };

export default function Correcciones() {
  const configurar = usePermiso("planos.configurar");
  const [lista, setLista] = useState<Correccion[] | null>(null);
  const [nueva, setNueva] = useState<typeof VACIA | null>(null);
  const [error, setError] = useState("");

  const cargar = useCallback(() => api<Correccion[]>("/planos/correcciones").then(setLista).catch((e) => setError(mensajeError(e))), []);
  useEffect(() => {
    cargar();
  }, [cargar]);

  async function guardar() {
    if (!nueva) return;
    setError("");
    try {
      await api("/planos/correcciones", { method: "POST", json: { ...nueva, columna: nueva.columna.toUpperCase() } });
      setNueva(null);
      cargar();
    } catch (e) {
      setError(mensajeError(e));
    }
  }

  async function eliminar(c: Correccion) {
    if (!window.confirm(`¿Eliminar la corrección de la cédula ${c.cedula}, columna ${c.columna}?`)) return;
    try {
      await api(`/planos/correcciones/${c.id}`, { method: "DELETE" });
      cargar();
    } catch (e) {
      setError(mensajeError(e));
    }
  }

  return (
    <>
      <Titulo accion={configurar && !nueva && <button className="btn-primario" onClick={() => setNueva({ ...VACIA })}><Plus className="h-4 w-4" /> Nueva corrección</button>}>
        Correcciones manuales
      </Titulo>
      <p className="-mt-4 mb-5 text-sm text-slate-500">
        Un dato que no se puede deducir (una fecha inválida, una cédula mal digitada en otra columna) solo se corrige con el valor que usted
        dicta. Se aplica por cédula y columna, no por fila, para que siga a la persona aunque cambie de posición en el archivo.
      </p>
      {error && <div className="mb-4"><Alerta>{error}</Alerta></div>}
      {nueva && (
        <div className="tarjeta mb-5 grid gap-3 p-5 sm:grid-cols-5">
          <div>
            <label className="label">Plano</label>
            <select className="input" value={nueva.plano} onChange={(e) => setNueva({ ...nueva, plano: e.target.value })}>
              <option value="empleados">Empleados</option>
              <option value="contratos">Contratos</option>
            </select>
          </div>
          <div><label className="label">Cédula</label><input className="input" value={nueva.cedula} onChange={(e) => setNueva({ ...nueva, cedula: e.target.value })} /></div>
          <div><label className="label">Columna</label><input className="input uppercase" maxLength={2} placeholder="N" value={nueva.columna} onChange={(e) => setNueva({ ...nueva, columna: e.target.value })} /></div>
          <div><label className="label">Valor</label><input className="input" placeholder="19980805" value={nueva.valor} onChange={(e) => setNueva({ ...nueva, valor: e.target.value })} /></div>
          <div><label className="label">Nota</label><input className="input" value={nueva.nota} onChange={(e) => setNueva({ ...nueva, nota: e.target.value })} /></div>
          <div className="flex justify-end gap-2 sm:col-span-5">
            <button className="btn-secundario" onClick={() => setNueva(null)}>Cancelar</button>
            <button className="btn-primario" disabled={!nueva.cedula.trim() || !nueva.columna.trim() || !nueva.valor.trim()} onClick={guardar}>Guardar</button>
          </div>
        </div>
      )}
      <div className="tarjeta overflow-x-auto">
        <table className="tabla">
          <thead><tr><th>Plano</th><th>Cédula</th><th>Columna</th><th>Valor</th><th>Nota</th><th>Creada</th>{configurar && <th />}</tr></thead>
          <tbody>
            {(lista ?? []).map((c) => (
              <tr key={c.id}>
                <td className="capitalize">{c.plano}</td>
                <td className="font-mono text-xs">{c.cedula}</td>
                <td className="font-mono text-xs">{c.columna}</td>
                <td className="font-mono text-xs">{c.valor}</td>
                <td className="text-slate-500">{c.nota}</td>
                <td className="text-slate-500">{c.creado_en ? new Date(c.creado_en).toLocaleDateString("es-CO") : ""}</td>
                {configurar && (
                  <td className="text-right">
                    <button title="Eliminar" onClick={() => eliminar(c)}><Trash2 className="h-4 w-4 text-slate-400 hover:text-red-600" /></button>
                  </td>
                )}
              </tr>
            ))}
            {lista && !lista.length && <tr><td colSpan={7} className="py-8 text-center text-slate-400">Sin correcciones</td></tr>}
          </tbody>
        </table>
      </div>
    </>
  );
}
