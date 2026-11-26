"use client";

import { BookOpenCheck, Pencil, Plus, Save, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Alerta } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";
import { fecha, type Regla } from "@/lib/contabilidad";
import { usePermiso } from "@/lib/sesion";

type Edicion = { id?: number; texto: string; cuentas: string; activa: boolean };

/** Lo que el agente contable aprende de cómo se hace en la empresa: estas reglas mandan sobre la norma general. */
export default function ReglasAgente() {
  const puede = usePermiso("contabilidad.revisar");
  const [reglas, setReglas] = useState<Regla[] | null>(null);
  const [edicion, setEdicion] = useState<Edicion | null>(null);
  const [msg, setMsg] = useState<{ tipo: "ok" | "error"; texto: string } | null>(null);
  const cargar = useCallback(() => api<Regla[]>("/contabilidad/reglas").then(setReglas).catch((e) => setMsg({ tipo: "error", texto: mensajeError(e) })), []);
  useEffect(() => { cargar(); }, [cargar]);

  async function guardar() {
    if (!edicion) return;
    setMsg(null);
    try {
      await api(`/contabilidad/reglas${edicion.id ? `/${edicion.id}` : ""}`, { method: edicion.id ? "PUT" : "POST",
        json: { texto: edicion.texto, cuentas: edicion.cuentas, activa: edicion.activa } });
      setEdicion(null);
      setMsg({ tipo: "ok", texto: "Regla guardada: el agente la usa desde la próxima factura." });
      cargar();
    } catch (e) { setMsg({ tipo: "error", texto: mensajeError(e) }); }
  }
  async function alternar(r: Regla) {
    try {
      await api(`/contabilidad/reglas/${r.id}`, { method: "PUT", json: { texto: r.texto, cuentas: r.cuentas, activa: !r.activa } });
      cargar();
    } catch (e) { setMsg({ tipo: "error", texto: mensajeError(e) }); }
  }
  async function eliminar(r: Regla) {
    if (!confirm("¿Eliminar esta regla? El agente deja de usarla.")) return;
    try { await api(`/contabilidad/reglas/${r.id}`, { method: "DELETE" }); cargar(); } catch (e) { setMsg({ tipo: "error", texto: mensajeError(e) }); }
  }

  const formulario = edicion && (
    <div className="tarjeta space-y-3 p-4">
      <div><label className="label">Regla (en palabras normales)</label>
        <textarea className="input" rows={3} maxLength={2000} autoFocus value={edicion.texto} onChange={(e) => setEdicion({ ...edicion, texto: e.target.value })}
          placeholder="Ej.: En Speed los intereses de mora no van a la cuenta de intereses de mora: van al costo (cuenta 7) o al gasto (cuenta 5) del concepto principal de la factura." /></div>
      <div className="flex flex-wrap items-end gap-4">
        <div className="w-64"><label className="label">Cuentas que menciona (opcional)</label>
          <input className="input" maxLength={200} value={edicion.cuentas} onChange={(e) => setEdicion({ ...edicion, cuentas: e.target.value })} placeholder="Ej.: 5, 7" /></div>
        <label className="flex items-center gap-2 pb-2 text-sm"><input type="checkbox" checked={edicion.activa} onChange={(e) => setEdicion({ ...edicion, activa: e.target.checked })} /> Activa</label>
        <div className="ml-auto flex gap-2">
          <button className="btn-secundario" onClick={() => setEdicion(null)}><X className="h-4 w-4" /> Cancelar</button>
          <button className="btn-primario" disabled={edicion.texto.trim().length < 5} onClick={guardar}><Save className="h-4 w-4" /> Guardar</button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="max-w-5xl space-y-4">
      <div className="flex flex-wrap items-start gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-marca-900"><BookOpenCheck className="h-6 w-6" /> Reglas de la empresa</h1>
          <p className="text-sm text-slate-500">Cómo se contabiliza aquí. El agente contable las aplica al proponer cada factura y <b>mandan sobre la norma general</b>.
            También aprende de sus correcciones: si cambia una cuenta que él propuso, le ofrece guardarlo como regla.</p>
        </div>
        {puede && !edicion && <button className="btn-primario ml-auto" onClick={() => setEdicion({ texto: "", cuentas: "", activa: true })}><Plus className="h-4 w-4" /> Regla</button>}
      </div>
      {msg && <Alerta tipo={msg.tipo}>{msg.texto}</Alerta>}
      {edicion && !edicion.id && formulario}
      {!reglas ? <p className="text-sm text-slate-500">Cargando…</p> : reglas.length === 0 ? (
        <p className="tarjeta p-6 text-center text-sm text-slate-500">Todavía no hay reglas. El agente usa la norma contable general y el historial de cada proveedor.</p>
      ) : (
        <div className="space-y-2">
          {reglas.map((r, k) => edicion?.id === r.id ? <div key={r.id}>{formulario}</div> : (
            <div key={r.id} className={`tarjeta flex gap-3 p-4 ${r.activa ? "" : "opacity-60"}`}>
              <span className="mt-0.5 text-sm font-semibold text-slate-400">{k + 1}.</span>
              <div className="flex-1 space-y-1">
                <p className="text-sm text-slate-800">{r.texto}</p>
                <p className="text-xs text-slate-500">
                  {r.cuentas && <>Cuentas: {r.cuentas} · </>}
                  {r.origen === "correccion" ? "Aprendida de una corrección" : "Escrita a mano"} · {fecha(r.creado_en)}
                  {" · "}{r.usos ? `aplicada ${r.usos} ${r.usos === 1 ? "vez" : "veces"}` : "aún no aplicada"}{!r.activa && " · desactivada"}
                </p>
                {r.ejemplo && <p className="text-xs text-slate-400">Salió de: {r.ejemplo}</p>}
              </div>
              {puede && (
                <div className="flex items-start gap-2">
                  <button className="text-xs text-marca-700 hover:underline" onClick={() => alternar(r)}>{r.activa ? "Desactivar" : "Activar"}</button>
                  <button title="Editar" onClick={() => setEdicion({ id: r.id, texto: r.texto, cuentas: r.cuentas, activa: r.activa })}><Pencil className="h-4 w-4 text-slate-400 hover:text-marca-700" /></button>
                  <button title="Eliminar" onClick={() => eliminar(r)}><Trash2 className="h-4 w-4 text-slate-400 hover:text-red-600" /></button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
