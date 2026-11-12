"use client";

import { Pencil, Plus, Save, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Alerta, Pestanas, Titulo } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";
import { UNIDAD, pesos, type TipoDocumento, type TipoItem } from "@/lib/costeo";
import { usePermiso } from "@/lib/sesion";

type Pestana = "parametros" | "comisiones" | "servicios" | "dotacion_tarifa" | "dotacion_puesto" | "otros" | "tipos" | "documentos" | "correos";
type Parametro = { clave: string; valor: number; nombre: string; grupo: string; ayuda: string };
type RangoC = { hasta_pct: number | null; pct_comision: number; carga_prestacional: number };
type Servicio = { id?: number; descripcion: string; tarifa: number; hombres: number; activo: boolean };
type Elemento = { id?: number; grupo: string; nombre: string; valor_unitario: number; vida_util_meses: number | null; entregas_anio: number | null; por_hombre: boolean;
  aplica?: string; cantidad?: number; activo: boolean; fuente: string; actualizado_en?: string };
// Dotación de la tarifa en el costeo por puestos: a qué puestos aplica cada elemento
const APLICA: [string, string][] = [["", "Solo a mano"], ["todos", "Todos los puestos"], ["gala", "Dotación de gala"], ["overol", "Dotación de overol"],
  ["arma", "Puestos con arma (cualquiera)"], ["fuego", "Arma de fuego"], ["fogeo", "Arma de fogeo"], ["traumatica", "Arma traumática"]];

const PESTANAS: [Pestana, string][] = [
  ["parametros", "Parámetros"], ["comisiones", "Comisiones"], ["servicios", "Servicios y tarifas"], ["dotacion_tarifa", "Dotación de la tarifa"],
  ["dotacion_puesto", "Dotación del puesto"], ["otros", "Otros costos directos"], ["tipos", "Ítems de MFP"], ["documentos", "Documentos contables"],
  ["correos", "Avisos por correo"],
];

export default function Configuracion() {
  const puede = usePermiso("costeo.configurar");
  const precios = usePermiso("costeo.precios");
  const contable = usePermiso("costeo.contable");
  const [p, setP] = useState<Pestana>("parametros");
  return (
    <>
      <Titulo>Configuración</Titulo>
      <p className="-mt-4 mb-4 text-sm text-slate-500">
        Todos los valores del costeo se cambian aquí{puede ? "" : precios ? " (con su permiso puede actualizar los precios de dotación y otros costos)" : " (solo lectura: se necesita el permiso de configurar)"}. Cada cambio queda en la
        auditoría; los costeos aprobados conservan los valores con que se aprobaron.
      </p>
      <Pestanas opciones={PESTANAS} valor={p} onChange={setP} />
      {p === "parametros" && <Parametros puede={puede} />}
      {p === "comisiones" && <Comisiones puede={puede} />}
      {p === "servicios" && <Servicios puede={puede || contable} />}
      {(p === "dotacion_tarifa" || p === "dotacion_puesto" || p === "otros") && <Catalogo key={p} grupo={p} puede={puede || precios} />}
      {p === "tipos" && <Tipos puede={puede} />}
      {p === "documentos" && <Documentos puede={puede} />}
      {p === "correos" && <Correos puede={puede} />}
    </>
  );
}

type AreaCorreo = { area: string; nombre: string; correos: string };
const QUE_RECIBE: Record<string, string> = {
  compras: "Los ítems de la MFP y la dotación adicional, para cotizar.",
  almacen: "La dotación de la primera entrega por puesto, para separarla.",
  financiero: "El inicio del contrato, la facturación mensual y los servicios facturados.",
  nomina: "El salario, las horas extras y recargos y los auxilios de cada tipo de personal.",
  programacion: "Los servicios vendidos (24 h, 12 h…) por puesto, para crearlos en el sistema.",
};

function Correos({ puede }: { puede: boolean }) {
  const [lista, setLista] = useState<AreaCorreo[]>([]);
  const m = useMensaje();
  const cargar = useCallback(() => api<AreaCorreo[]>("/costeo/areas-correo").then(setLista).catch(m.error), []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    cargar();
  }, [cargar]);
  return (
    <div className="tarjeta p-4">{m.vista}
      <p className="mb-4 text-sm text-slate-500">Cuando un costeo aprobado crea su MFP con la fecha de inicio, la plataforma le envía un correo a cada área.
        Escriba los correos de cada una separados por coma; un área sin correos no recibe nada. Lo enviado queda registrado en la MFP, donde se puede reenviar.</p>
      <div className="space-y-3">
        {lista.map((a, i) => (
          <div key={a.area} className="grid gap-2 sm:grid-cols-[14rem_1fr] sm:items-start">
            <div><p className="font-medium text-slate-700">{a.nombre}</p><p className="text-xs text-slate-500">{QUE_RECIBE[a.area]}</p></div>
            <input className="input" disabled={!puede} placeholder="persona@servigpoder.com, otra@servigpoder.com" value={a.correos}
              onChange={(e) => setLista(lista.map((x, j) => (j === i ? { ...x, correos: e.target.value } : x)))} />
          </div>
        ))}
      </div>
      {puede && (
        <div className="mt-4 flex justify-end">
          <button className="btn-primario" onClick={async () => {
            try { await api("/costeo/areas-correo", { method: "PUT", json: lista.map(({ area, correos }) => ({ area, correos })) }); m.ok("Correos guardados."); cargar(); } catch (e) { m.error(e); }
          }}><Save className="h-4 w-4" /> Guardar</button>
        </div>
      )}
    </div>
  );
}

function useMensaje() {
  const [msg, setMsg] = useState<{ tipo: "ok" | "error"; texto: string } | null>(null);
  return { msg, ok: (t: string) => setMsg({ tipo: "ok", texto: t }), error: (e: unknown) => setMsg({ tipo: "error", texto: mensajeError(e) }),
    vista: msg && <div className="mb-4"><Alerta tipo={msg.tipo}>{msg.texto}</Alerta></div> };
}

function Parametros({ puede }: { puede: boolean }) {
  const [lista, setLista] = useState<Parametro[]>([]);
  const [valores, setValores] = useState<Record<string, string>>({});
  const m = useMensaje();
  const cargar = useCallback(() => api<Parametro[]>("/costeo/parametros").then((l) => {
    setLista(l);
    setValores(Object.fromEntries(l.map((x) => [x.clave, String(x.valor)])));
  }).catch(m.error), []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    cargar();
  }, [cargar]);
  const cambiados = lista.filter((x) => Number(valores[x.clave]) !== x.valor);
  const grupos = [...new Set(lista.map((x) => x.grupo))];
  return (
    <div className="space-y-4">
      {m.vista}
      {grupos.map((g) => (
        <div key={g} className="tarjeta p-4">
          <h2 className="mb-3 font-semibold text-slate-700">{g}</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {lista.filter((x) => x.grupo === g).map((x) => (
              <div key={x.clave}>
                <label className="label">{x.nombre}</label>
                <input className="input" type="number" step="any" disabled={!puede} value={valores[x.clave] ?? ""} onChange={(e) => setValores({ ...valores, [x.clave]: e.target.value })} />
                {x.ayuda && <p className="mt-0.5 text-xs text-slate-500">{x.ayuda}</p>}
              </div>
            ))}
          </div>
        </div>
      ))}
      {puede && (
        <div className="flex justify-end">
          <button className="btn-primario" disabled={!cambiados.length} onClick={async () => {
            try {
              await api("/costeo/parametros", { method: "PUT", json: Object.fromEntries(cambiados.map((x) => [x.clave, Number(valores[x.clave])])) });
              m.ok(`${cambiados.length} parámetros actualizados.`);
              cargar();
            } catch (e) { m.error(e); }
          }}><Save className="h-4 w-4" /> Guardar parámetros</button>
        </div>
      )}
    </div>
  );
}

function Comisiones({ puede }: { puede: boolean }) {
  const [rangos, setRangos] = useState<RangoC[]>([]);
  const m = useMensaje();
  useEffect(() => {
    api<RangoC[]>("/costeo/comisiones").then(setRangos).catch(m.error);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const set = (i: number, x: Partial<RangoC>) => setRangos(rangos.map((r, j) => (j === i ? { ...r, ...x } : r)));
  return (
    <div className="tarjeta max-w-3xl p-4">
      {m.vista}
      <p className="mb-3 text-sm text-slate-500">El % de MFP con que se vende define la comisión y la carga prestacional del vendedor. El último rango, sin tope, aplica de ahí en adelante.</p>
      <table className="w-full text-sm">
        <thead><tr className="text-left text-xs text-slate-500"><th className="pb-1">MFP hasta (%)</th><th>Comisión (%)</th><th>Carga prestacional</th><th /></tr></thead>
        <tbody className="[&_td]:py-1 [&_td]:pr-2">
          {rangos.map((r, i) => (
            <tr key={i}>
              <td><input className="input" type="number" step="any" disabled={!puede} placeholder="En adelante" value={r.hasta_pct === null ? "" : +(r.hasta_pct * 100).toFixed(4)}
                onChange={(e) => set(i, { hasta_pct: e.target.value === "" ? null : Number(e.target.value) / 100 })} /></td>
              <td><input className="input" type="number" step="any" disabled={!puede} value={+(r.pct_comision * 100).toFixed(4)} onChange={(e) => set(i, { pct_comision: Number(e.target.value) / 100 })} /></td>
              <td><input className="input" type="number" step="any" disabled={!puede} value={r.carga_prestacional} onChange={(e) => set(i, { carga_prestacional: Number(e.target.value) })} /></td>
              <td>{puede && <button onClick={() => setRangos(rangos.filter((_, j) => j !== i))}><Trash2 className="h-4 w-4 text-slate-400 hover:text-red-600" /></button>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {puede && (
        <div className="mt-3 flex justify-between">
          <button className="btn-secundario" onClick={() => setRangos([...rangos, { hasta_pct: null, pct_comision: 0, carga_prestacional: 1.37872 }])}><Plus className="h-4 w-4" /> Rango</button>
          <button className="btn-primario" onClick={async () => {
            try { await api("/costeo/comisiones", { method: "PUT", json: rangos }); m.ok("Tabla de comisiones guardada."); } catch (e) { m.error(e); }
          }}><Save className="h-4 w-4" /> Guardar</button>
        </div>
      )}
    </div>
  );
}

function Servicios({ puede }: { puede: boolean }) {
  const [lista, setLista] = useState<Servicio[]>([]);
  const [edicion, setEdicion] = useState<Servicio | null>(null);
  const m = useMensaje();
  const cargar = useCallback(() => api<Servicio[]>("/costeo/servicios").then(setLista).catch(m.error), []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    cargar();
  }, [cargar]);
  return (
    <div className="tarjeta overflow-hidden">
      <div className="p-4">{m.vista}
        {puede && !edicion && <button className="btn-primario" onClick={() => setEdicion({ descripcion: "", tarifa: 0, hombres: 3, activo: true })}><Plus className="h-4 w-4" /> Servicio</button>}
        {edicion && (
          <div className="grid gap-3 sm:grid-cols-[3fr_1fr_1fr_auto_auto] sm:items-end">
            <div><label className="label">Descripción</label><input className="input" value={edicion.descripcion} onChange={(e) => setEdicion({ ...edicion, descripcion: e.target.value })} /></div>
            <div><label className="label">Tarifa</label><input className="input" type="number" value={edicion.tarifa} onChange={(e) => setEdicion({ ...edicion, tarifa: Number(e.target.value) })} /></div>
            <div><label className="label">Hombres</label><input className="input" type="number" step="any" value={edicion.hombres} onChange={(e) => setEdicion({ ...edicion, hombres: Number(e.target.value) })} /></div>
            <label className="flex items-center gap-2 pb-2 text-sm"><input type="checkbox" checked={edicion.activo} onChange={(e) => setEdicion({ ...edicion, activo: e.target.checked })} /> Activo</label>
            <div className="flex gap-2"><button className="btn-secundario" onClick={() => setEdicion(null)}>Cancelar</button>
              <button className="btn-primario" onClick={async () => {
                try { await api("/costeo/servicios", { method: "PUT", json: edicion }); setEdicion(null); m.ok("Servicio guardado."); cargar(); } catch (e) { m.error(e); }
              }}>Guardar</button></div>
          </div>
        )}
      </div>
      <table className="tabla">
        <thead><tr><th>Servicio</th><th className="text-right">Tarifa</th><th className="text-right">Hombres</th><th /></tr></thead>
        <tbody>{lista.map((s) => (
          <tr key={s.id} className={s.activo ? "" : "opacity-50"}>
            <td>{s.descripcion}</td><td className="text-right tabular-nums">{pesos(s.tarifa)}</td><td className="text-right tabular-nums">{s.hombres}</td>
            <td>{puede && <button onClick={() => setEdicion(s)}><Pencil className="h-4 w-4 text-slate-400 hover:text-marca-700" /></button>}</td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

function Catalogo({ grupo, puede }: { grupo: string; puede: boolean }) {
  const [lista, setLista] = useState<Elemento[]>([]);
  const [edicion, setEdicion] = useState<Elemento | null>(null);
  const m = useMensaje();
  const cargar = useCallback(() => api<Elemento[]>(`/costeo/catalogo?grupo=${grupo}`).then(setLista).catch(m.error), [grupo]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    cargar();
  }, [cargar]);
  const num = (v: string) => (v === "" ? null : Number(v));
  return (
    <div className="tarjeta overflow-hidden">
      <div className="p-4">{m.vista}
        <p className="mb-3 text-sm text-slate-500">Precios de referencia para los costeos (los actualizan compras y contabilidad, idealmente dos veces al año). Cada elemento
          se costea mensual por su vida útil (vacía = los meses del contrato) o anual por sus entregas al año. Los costeos ya hechos conservan el precio con que se hicieron.</p>
        {(() => {
          const viejos = lista.filter((x) => x.activo && x.actualizado_en && Date.now() - new Date(x.actualizado_en).getTime() > 183 * 864e5).length;
          return viejos > 0 ? <div className="mb-3"><Alerta tipo="info">{viejos} precios llevan más de 6 meses sin actualizar.</Alerta></div> : null;
        })()}
        {grupo === "dotacion_tarifa" && <p className="mb-3 text-sm text-slate-500">En el costeo por puestos, cada elemento entra solo en los puestos a los que aplica
          (según la dotación y el arma que escoge el comercial), con su cantidad por hombre o por puesto.</p>}
        {puede && !edicion && <button className="btn-primario" onClick={() => setEdicion({ grupo, nombre: "", valor_unitario: 0, vida_util_meses: null, entregas_anio: null, por_hombre: false, aplica: "", cantidad: 1, activo: true, fuente: "" })}><Plus className="h-4 w-4" /> Elemento</button>}
        {edicion && (
          <div className="grid gap-3 sm:grid-cols-4 sm:items-end">
            <div className="sm:col-span-2"><label className="label">Nombre</label><input className="input" value={edicion.nombre} onChange={(e) => setEdicion({ ...edicion, nombre: e.target.value })} /></div>
            <div><label className="label">Valor unitario</label><input className="input" type="number" value={edicion.valor_unitario} onChange={(e) => setEdicion({ ...edicion, valor_unitario: Number(e.target.value) })} /></div>
            <div><label className="label">Fuente</label><input className="input" value={edicion.fuente} onChange={(e) => setEdicion({ ...edicion, fuente: e.target.value })} /></div>
            <div><label className="label">Vida útil (meses)</label><input className="input" type="number" value={edicion.vida_util_meses ?? ""} onChange={(e) => setEdicion({ ...edicion, vida_util_meses: num(e.target.value) })} /></div>
            <div><label className="label">Entregas al año</label><input className="input" type="number" step="any" value={edicion.entregas_anio ?? ""} onChange={(e) => setEdicion({ ...edicion, entregas_anio: num(e.target.value) })} /></div>
            <label className="flex items-center gap-2 pb-2 text-sm"><input type="checkbox" checked={edicion.por_hombre} onChange={(e) => setEdicion({ ...edicion, por_hombre: e.target.checked })} /> Por hombre (si no, por puesto)</label>
            {grupo === "dotacion_tarifa" && <>
              <div><label className="label">Aplica a</label><select className="input" value={edicion.aplica ?? ""} onChange={(e) => setEdicion({ ...edicion, aplica: e.target.value })}>
                {APLICA.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></div>
              <div><label className="label">Cantidad {edicion.por_hombre ? "por hombre" : "por puesto"}</label><input className="input" type="number" step="any" min={0} value={edicion.cantidad ?? 1} onChange={(e) => setEdicion({ ...edicion, cantidad: Number(e.target.value) })} /></div>
            </>}
            <label className="flex items-center gap-2 pb-2 text-sm"><input type="checkbox" checked={edicion.activo} onChange={(e) => setEdicion({ ...edicion, activo: e.target.checked })} /> Activo</label>
            <div className="flex justify-end gap-2 sm:col-span-4"><button className="btn-secundario" onClick={() => setEdicion(null)}>Cancelar</button>
              <button className="btn-primario" onClick={async () => {
                try { await api("/costeo/catalogo", { method: "PUT", json: edicion }); setEdicion(null); m.ok("Elemento guardado."); cargar(); } catch (e) { m.error(e); }
              }}>Guardar</button></div>
          </div>
        )}
      </div>
      <table className="tabla">
        <thead><tr><th>Elemento</th><th className="text-right">Valor</th><th className="text-right">Vida útil</th><th className="text-right">Entregas/año</th><th>Por hombre</th>
          {grupo === "dotacion_tarifa" && <><th>Aplica a</th><th className="text-right">Cantidad</th></>}<th>Fuente</th><th>Actualizado</th><th /></tr></thead>
        <tbody>{lista.map((x) => (
          <tr key={x.id} className={x.activo ? "" : "opacity-50"}>
            <td>{x.nombre}</td><td className="text-right tabular-nums">{pesos(x.valor_unitario)}</td>
            <td className="text-right tabular-nums">{x.vida_util_meses ?? (x.entregas_anio === null ? "contrato" : "—")}</td>
            <td className="text-right tabular-nums">{x.entregas_anio ?? "—"}</td><td>{x.por_hombre ? "Sí" : ""}</td>
            {grupo === "dotacion_tarifa" && <><td className="text-xs">{APLICA.find(([v]) => v === (x.aplica ?? ""))?.[1]}</td><td className="text-right tabular-nums">{x.cantidad ?? 1}</td></>}
            <td className="text-xs text-slate-500">{x.fuente}</td>
            <td className="whitespace-nowrap text-xs text-slate-500">{x.actualizado_en ? new Date(x.actualizado_en).toLocaleDateString("es-CO") : ""}</td>
            <td>{puede && <button onClick={() => setEdicion(x)}><Pencil className="h-4 w-4 text-slate-400 hover:text-marca-700" /></button>}</td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

function Tipos({ puede }: { puede: boolean }) {
  const [lista, setLista] = useState<TipoItem[]>([]);
  const [edicion, setEdicion] = useState<Partial<TipoItem> | null>(null);
  const m = useMensaje();
  const cargar = useCallback(() => api<TipoItem[]>("/costeo/tipos-item").then(setLista).catch(m.error), []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    cargar();
  }, [cargar]);
  return (
    <div className="tarjeta overflow-hidden">
      <div className="p-4">{m.vista}
        <p className="mb-3 text-sm text-slate-500">
          «Reembolsable»: si el cliente termina antes, devuelve la parte no amortizada de lo ejecutado. «Cuenta en la MFP»: suma en el % de MFP del
          cliente (las bolsas internas, como publicidad, no).
        </p>
        {puede && !edicion && <button className="btn-primario" onClick={() => setEdicion({ codigo: "", nombre: "", unidad: "pesos", reembolsable: true, cuenta_en_mfp: true, activo: true })}><Plus className="h-4 w-4" /> Ítem</button>}
        {edicion && (
          <div className="grid gap-3 sm:grid-cols-4 sm:items-end">
            <div><label className="label">Código</label><input className="input uppercase" value={edicion.codigo} onChange={(e) => setEdicion({ ...edicion, codigo: e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, "_") })} /></div>
            <div className="sm:col-span-2"><label className="label">Nombre</label><input className="input" value={edicion.nombre} onChange={(e) => setEdicion({ ...edicion, nombre: e.target.value })} /></div>
            <div><label className="label">Unidad</label>
              <select className="input" value={edicion.unidad} onChange={(e) => setEdicion({ ...edicion, unidad: e.target.value as TipoItem["unidad"] })}>
                {Object.entries(UNIDAD).map(([k, t]) => <option key={k} value={k}>{t}</option>)}</select></div>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!edicion.reembolsable} onChange={(e) => setEdicion({ ...edicion, reembolsable: e.target.checked })} /> Reembolsable</label>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!edicion.cuenta_en_mfp} onChange={(e) => setEdicion({ ...edicion, cuenta_en_mfp: e.target.checked })} /> Cuenta en la MFP</label>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!edicion.activo} onChange={(e) => setEdicion({ ...edicion, activo: e.target.checked })} /> Activo</label>
            <div className="flex justify-end gap-2"><button className="btn-secundario" onClick={() => setEdicion(null)}>Cancelar</button>
              <button className="btn-primario" onClick={async () => {
                try { await api("/costeo/tipos-item", { method: "PUT", json: edicion }); setEdicion(null); m.ok("Ítem guardado."); cargar(); } catch (e) { m.error(e); }
              }}>Guardar</button></div>
          </div>
        )}
      </div>
      <table className="tabla">
        <thead><tr><th>Código</th><th>Nombre</th><th>Unidad</th><th>Reembolsable</th><th>Cuenta en la MFP</th><th /></tr></thead>
        <tbody>{lista.map((t) => (
          <tr key={t.id} className={t.activo ? "" : "opacity-50"}>
            <td className="font-mono text-xs">{t.codigo}</td><td>{t.nombre}</td><td>{UNIDAD[t.unidad]}</td><td>{t.reembolsable ? "Sí" : "No"}</td><td>{t.cuenta_en_mfp ? "Sí" : "No"}</td>
            <td>{puede && <button onClick={() => setEdicion(t)}><Pencil className="h-4 w-4 text-slate-400 hover:text-marca-700" /></button>}</td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

function Documentos({ puede }: { puede: boolean }) {
  const [lista, setLista] = useState<TipoDocumento[]>([]);
  const [edicion, setEdicion] = useState<TipoDocumento | null>(null);
  const m = useMensaje();
  const cargar = useCallback(() => api<TipoDocumento[]>("/costeo/tipos-documento").then(setLista).catch(m.error), []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    cargar();
  }, [cargar]);
  return (
    <div className="tarjeta max-w-3xl overflow-hidden">
      <div className="p-4">{m.vista}
        <p className="mb-3 text-sm text-slate-500">Tipos de documento contable con que se respalda cada pago o aplicación de una MFP (comprobante de egreso, factura, nota crédito…).</p>
        {puede && !edicion && <button className="btn-primario" onClick={() => setEdicion({ codigo: "", nombre: "", activo: true })}><Plus className="h-4 w-4" /> Tipo de documento</button>}
        {edicion && (
          <div className="grid gap-3 sm:grid-cols-[1fr_2fr_auto_auto] sm:items-end">
            <div><label className="label">Código</label><input className="input uppercase" value={edicion.codigo} onChange={(e) => setEdicion({ ...edicion, codigo: e.target.value.toUpperCase() })} /></div>
            <div><label className="label">Nombre</label><input className="input" value={edicion.nombre} onChange={(e) => setEdicion({ ...edicion, nombre: e.target.value })} /></div>
            <label className="flex items-center gap-2 pb-2 text-sm"><input type="checkbox" checked={edicion.activo} onChange={(e) => setEdicion({ ...edicion, activo: e.target.checked })} /> Activo</label>
            <div className="flex gap-2"><button className="btn-secundario" onClick={() => setEdicion(null)}>Cancelar</button>
              <button className="btn-primario" onClick={async () => {
                try { await api("/costeo/tipos-documento", { method: "PUT", json: edicion }); setEdicion(null); m.ok("Tipo de documento guardado."); cargar(); } catch (e) { m.error(e); }
              }}>Guardar</button></div>
          </div>
        )}
      </div>
      <table className="tabla">
        <thead><tr><th>Código</th><th>Nombre</th><th>Estado</th><th /></tr></thead>
        <tbody>{lista.map((t) => (
          <tr key={t.codigo} className={t.activo ? "" : "opacity-50"}>
            <td className="font-mono text-xs">{t.codigo}</td><td>{t.nombre}</td><td>{t.activo ? "Activo" : "Inactivo"}</td>
            <td>{puede && <button onClick={() => setEdicion(t)}><Pencil className="h-4 w-4 text-slate-400 hover:text-marca-700" /></button>}</td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}
