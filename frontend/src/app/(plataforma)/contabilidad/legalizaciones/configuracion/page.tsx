"use client";

import { Plus, Save, Upload } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Alerta, Titulo } from "@/components/ui";
import { api, mensajeError, subirArchivo } from "@/lib/api";
import type { Persona } from "@/lib/contabilidad";
import { usePermiso } from "@/lib/sesion";

type Config = {
  tipo_documento: string; prefijo: string; ultimo_numero: number; nota: string; cuentas: Record<string, string>; columnas: Record<string, string>;
  cuenta_reintegro: string; cuenta_anticipo: string; cuenta_por_cobrar: string;
};

function Personas({ tipo, titulo, ayuda, puede, onMsg }: { tipo: "elabora" | "empleado"; titulo: string; ayuda: string; puede: boolean; onMsg: (m: { tipo: "ok" | "error"; texto: string }) => void }) {
  const [lista, setLista] = useState<Persona[]>([]);
  const [nuevo, setNuevo] = useState({ documento: "", nombre: "" });
  const input = useRef<HTMLInputElement>(null);
  const cargar = useCallback(() => { api<Persona[]>(`/contabilidad/legalizaciones/personas/lista?tipo=${tipo}`).then(setLista).catch(() => {}); }, [tipo]);
  useEffect(() => { cargar(); }, [cargar]);
  async function importar(f: File | undefined) {
    if (!f) return;
    try {
      const r = await subirArchivo<{ personas: number }>(`/contabilidad/legalizaciones/personas/importar?tipo=${tipo}`, f);
      onMsg({ tipo: "ok", texto: `Se cargaron ${r.personas} personas.` });
      cargar();
    } catch (e) { onMsg({ tipo: "error", texto: mensajeError(e) }); }
  }
  async function guardar(documento: string, nombre: string, activo = true) {
    try {
      await api("/contabilidad/legalizaciones/personas/lista", { method: "PUT", json: { tipo, documento, nombre, activo } });
      setNuevo({ documento: "", nombre: "" });
      cargar();
    } catch (e) { onMsg({ tipo: "error", texto: mensajeError(e) }); }
  }
  return (
    <section className="tarjeta space-y-2 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="font-semibold text-slate-800">{titulo} <span className="text-sm font-normal text-slate-500">({lista.filter((p) => p.activo).length})</span></h2>
        {puede && <button className="btn-secundario ml-auto" onClick={() => input.current?.click()}><Upload className="h-4 w-4" /> Cargar Excel</button>}
        <input ref={input} type="file" accept=".xlsx" className="hidden" onChange={(e) => { importar(e.target.files?.[0]); e.target.value = ""; }} />
      </div>
      <p className="text-xs text-slate-500">{ayuda} El Excel necesita una columna de nombre y una de cédula; el archivo no se guarda.</p>
      {puede && (
        <div className="flex flex-wrap gap-2">
          <input className="input w-40" placeholder="Cédula" value={nuevo.documento} onChange={(e) => setNuevo({ ...nuevo, documento: e.target.value })} />
          <input className="input w-64" placeholder="Nombre" value={nuevo.nombre} onChange={(e) => setNuevo({ ...nuevo, nombre: e.target.value })} />
          <button className="btn-secundario" disabled={nuevo.documento.trim().length < 4} onClick={() => guardar(nuevo.documento, nuevo.nombre)}><Plus className="h-4 w-4" /> Agregar</button>
        </div>
      )}
      <div className="max-h-60 overflow-y-auto">
        <table className="tabla text-sm">
          <tbody>
            {lista.map((p) => (
              <tr key={p.id} className={p.activo ? "" : "text-slate-400 line-through"}>
                <td className="font-mono">{p.documento}</td><td>{p.nombre}</td>
                <td className="text-right">{puede && <button className="text-xs text-marca-700 hover:underline" onClick={() => guardar(p.documento, p.nombre, !p.activo)}>{p.activo ? "quitar" : "activar"}</button>}</td>
              </tr>
            ))}
            {lista.length === 0 && <tr><td className="py-3 text-center text-slate-400">Sin personas cargadas.</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function ConfiguracionLegalizaciones() {
  const puede = usePermiso("contabilidad.configurar");
  const [c, setC] = useState<Config | null>(null);
  const [msg, setMsg] = useState<{ tipo: "ok" | "error"; texto: string } | null>(null);
  useEffect(() => { api<Config>("/contabilidad/legalizaciones/config/datos").then(setC).catch((e) => setMsg({ tipo: "error", texto: mensajeError(e) })); }, []);
  if (!c) return msg ? <Alerta>{msg.texto}</Alerta> : <p className="text-sm text-slate-500">Cargando…</p>;
  const set = (x: Partial<Config>) => setC({ ...c, ...x });
  async function guardar() {
    setMsg(null);
    try { setC(await api<Config>("/contabilidad/legalizaciones/config/datos", { method: "PUT", json: c })); setMsg({ tipo: "ok", texto: "Configuración guardada." }); }
    catch (e) { setMsg({ tipo: "error", texto: mensajeError(e) }); }
  }
  const campo = (k: keyof Config, t: string, ayuda = "") => (
    <div><label className="label">{t}</label>
      <input className="input" disabled={!puede} value={String(c[k] ?? "")} onChange={(e) => set({ [k]: k === "ultimo_numero" ? Number(e.target.value.replace(/\D/g, "")) || 0 : e.target.value } as Partial<Config>)} />
      {ayuda && <p className="mt-1 text-xs text-slate-500">{ayuda}</p>}</div>
  );
  return (
    <div className="max-w-5xl space-y-5">
      <Titulo>Legalizaciones: cuentas y personas</Titulo>
      {msg && <Alerta tipo={msg.tipo}>{msg.texto}</Alerta>}
      <section className="tarjeta space-y-3 p-4">
        <h2 className="font-semibold text-slate-800">Cuenta de cada columna del formato</h2>
        <p className="text-xs text-slate-500">Cada gasto toma la cuenta de la columna donde viene en el formato. En «Transporte/parqueo/peajes» el detalle decide (peaje → peajes, parqueadero → parqueo).</p>
        <div className="grid gap-3 sm:grid-cols-3">
          {Object.entries(c.columnas).map(([k, t]) => (
            <div key={k}><label className="label">{t}</label>
              <input className="input font-mono" disabled={!puede} value={c.cuentas[k] ?? ""} onChange={(e) => set({ cuentas: { ...c.cuentas, [k]: e.target.value.replace(/\D/g, "") } })} /></div>
          ))}
        </div>
      </section>
      <section className="tarjeta space-y-3 p-4">
        <h2 className="font-semibold text-slate-800">Nota contable de World Office</h2>
        <div className="grid gap-3 sm:grid-cols-3">
          {campo("tipo_documento", "Tipo de documento")}{campo("prefijo", "Prefijo")}
          {campo("ultimo_numero", "Último número LG usado en World Office", "El plano sigue desde aquí (siguiente = este + 1).")}
          {campo("nota", "Nota del encabezado")}
          {campo("cuenta_reintegro", "Cuenta del reintegro al colaborador", "Reembolso: crédito por el total; con anticipo, si gastó más, la diferencia.")}
          {campo("cuenta_anticipo", "Cuenta de anticipos a trabajadores", "Con anticipo: crédito por el valor del anticipo.")}
          {campo("cuenta_por_cobrar", "Cuenta por cobrar (gastó menos que el anticipo)", "Débito por lo que el colaborador debe devolver.")}
        </div>
        {puede && <button className="btn-primario" onClick={guardar}><Save className="h-4 w-4" /> Guardar</button>}
      </section>
      <div className="grid gap-5 lg:grid-cols-2">
        <Personas tipo="elabora" titulo="Quienes elaboran (tercero interno)" ayuda="Columna F del plano: la persona que hace el documento." puede={puede} onMsg={setMsg} />
        <Personas tipo="empleado" titulo="Empleados (tercero externo)" ayuda="Columna G del plano: el colaborador que legaliza. Avisa si no está en el listado." puede={puede} onMsg={setMsg} />
      </div>
    </div>
  );
}
