"use client";

import { AlertTriangle, BookOpenCheck, Pencil, Plus, Save, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Alerta } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";
import { fecha, type Regla, type UsoAgente } from "@/lib/contabilidad";
import { usePermiso } from "@/lib/sesion";

type Edicion = { id?: number; texto: string; cuentas: string; activa: boolean };

/** Lo que el agente contable aprende de cómo se hace en la empresa: estas reglas mandan sobre la norma general. */
export default function ReglasAgente() {
  const puede = usePermiso("contabilidad.revisar");
  const [reglas, setReglas] = useState<Regla[] | null>(null);
  const [edicion, setEdicion] = useState<Edicion | null>(null);
  const [msg, setMsg] = useState<{ tipo: "ok" | "error"; texto: string } | null>(null);
  const [uso, setUso] = useState<UsoAgente | null>(null);
  const cargar = useCallback(() => {
    api<Regla[]>("/contabilidad/reglas").then(setReglas).catch((e) => setMsg({ tipo: "error", texto: mensajeError(e) }));
    api<UsoAgente>("/contabilidad/agente/uso").then(setUso).catch(() => {});
  }, []);
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
      {uso && <Consumo uso={uso} />}
      <details className="tarjeta p-4 text-sm text-slate-600">
        <summary className="cursor-pointer font-medium text-slate-700">Buenas prácticas para que el agente aprenda bien</summary>
        <ul className="ml-5 mt-2 list-disc space-y-1">
          <li><b>Una regla por concepto</b> y en general («los intereses de mora…»), no por factura ni con valores.</li>
          <li>Diga <b>cuándo aplica y a qué cuenta va</b>, con el código si lo sabe (p. ej. «al costo 7 o al gasto 5 según el concepto principal»).</li>
          <li>Si el agente se equivoca, <b>corrija la cuenta y acepte aprenderlo</b>: si ya hay una regla parecida, la actualiza en vez de duplicarla.</li>
          <li>Revise las reglas marcadas como <b>corregidas varias veces</b>: probablemente están mal redactadas o quedaron viejas.</li>
          <li>Desactive en vez de borrar si no está seguro: el agente deja de usarla y la puede volver a activar.</li>
          <li>Lo que ya se contabilizó igual con un proveedor se repite <b>sin costo de IA</b>; si cambia una regla, el agente vuelve a decidir.</li>
        </ul>
      </details>
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
                {r.corregida > 0 && (
                  <p className="flex items-center gap-1 text-xs text-amber-700"><AlertTriangle className="h-3.5 w-3.5" />
                    Corregida {r.corregida} {r.corregida === 1 ? "vez" : "veces"} en facturas donde se aplicó: revísela</p>
                )}
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

/** Consumo del agente en el mes: cuántas facturas propuso con IA y cuántas resolvió con la memoria (sin costo) */
function Consumo({ uso }: { uso: UsoAgente }) {
  const t = (k: string) => uso.por_tipo[k] ?? { veces: 0, tokens_entrada: 0, tokens_salida: 0 };
  const conIA = t("propuesta").veces, memoria = t("memoria").veces;
  const n = (v: number) => v.toLocaleString("es-CO");
  return (
    <div className="grid gap-3 sm:grid-cols-4">
      {[
        ["Facturas propuestas con IA", n(conIA), `modelo ${uso.modelo}`],
        ["Resueltas con la memoria", n(memoria), conIA + memoria ? `${Math.round((memoria / (conIA + memoria)) * 100)} % sin costo de IA` : "sin costo de IA"],
        ["Tokens del modelo", n(t("propuesta").tokens_entrada + t("regla").tokens_entrada), `+ ${n(uso.tokens_salida)} de respuesta`],
        ["Tokens de vectores (RAG)", n(t("vectores").tokens_entrada), uso.modelo_vectores],
      ].map(([titulo, valor, nota]) => (
        <div key={titulo} className="tarjeta p-3">
          <p className="text-xs text-slate-500">{titulo} · este mes</p>
          <p className="text-lg font-semibold text-marca-900">{valor}</p>
          <p className="truncate text-xs text-slate-400" title={nota}>{nota}</p>
        </div>
      ))}
    </div>
  );
}
