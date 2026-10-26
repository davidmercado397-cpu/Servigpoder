"use client";

import { Download, Plus, Search, TriangleAlert, Upload } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { Alerta, SubirArchivo, Titulo } from "@/components/ui";
import { api, apiEnvelope, mensajeError, subirArchivo } from "@/lib/api";
import { ESTADO_MFP, fecha, pct, pesos, type Cliente, type Mfp, type TipoItem } from "@/lib/costeo";
import { usePermiso } from "@/lib/sesion";

type Totales = { facturacion_total: number; pactado: number; ejecutado: number; pendiente: number; reembolso: number };
type Importacion = { creadas: number; omitidas: number; clientes: number; advertencias: string[] };

export default function ListaMfpPagina() {
  return <Suspense><ListaMfp /></Suspense>;
}

function ListaMfp() {
  const gestionar = usePermiso("costeo.mfp");
  const params = useSearchParams();
  const [lista, setLista] = useState<Omit<Mfp, "items">[] | null>(null);
  const [totales, setTotales] = useState<Totales | null>(null);
  const [q, setQ] = useState("");
  const [estado, setEstado] = useState("");
  const [cliente, setCliente] = useState(params.get("cliente") ?? "");
  const [conAlertas, setConAlertas] = useState(params.get("alertas") === "1");
  const [clientes, setClientes] = useState<Cliente[]>([]);
  const [nueva, setNueva] = useState(false);
  const [importacion, setImportacion] = useState<Importacion | null>(null);
  const [error, setError] = useState("");

  const cargar = useCallback(() => {
    const qs = new URLSearchParams({ q, estado, ...(cliente ? { cliente_id: cliente } : {}), ...(conAlertas ? { con_alertas: "true" } : {}) });
    apiEnvelope<Omit<Mfp, "items">[]>(`/costeo/mfp?${qs}`).then((r) => {
      setLista(r.data ?? []);
      setTotales((r.meta.extra?.totales as Totales) ?? null);
    }).catch((e) => setError(mensajeError(e)));
  }, [q, estado, cliente, conAlertas]);
  useEffect(() => {
    const t = setTimeout(cargar, 250);
    return () => clearTimeout(t);
  }, [cargar]);
  useEffect(() => {
    api<Cliente[]>("/costeo/clientes").then(setClientes).catch(() => {});
  }, []);

  async function importar(f: File) {
    setError("");
    try {
      setImportacion(await subirArchivo<Importacion>("/costeo/mfp/importar", f));
      cargar();
    } catch (e) {
      setError(mensajeError(e));
    }
  }

  return (
    <>
      <Titulo accion={
        <div className="flex flex-wrap gap-2">
          <a className="btn-secundario" href="/api/costeo/mfp-excel"><Download className="h-4 w-4" /> Excel</a>
          {gestionar && <SubirArchivo texto="Importar Excel de MFP" onArchivo={importar} />}
          {gestionar && <button className="btn-primario" onClick={() => setNueva(true)}><Plus className="h-4 w-4" /> Nueva MFP</button>}
        </div>
      }>MFP</Titulo>
      {error && <div className="mb-4"><Alerta>{error}</Alerta></div>}
      {importacion && (
        <div className="mb-4">
          <Alerta tipo="info">
            <p className="font-medium"><Upload className="mr-1 inline h-4 w-4" />Importación: {importacion.creadas} MFP creadas, {importacion.omitidas} ya existían, {importacion.clientes} clientes.</p>
            {importacion.advertencias.length > 0 && (
              <ul className="mt-1 list-disc pl-5 text-xs">{importacion.advertencias.map((a) => <li key={a}>{a}</li>)}</ul>
            )}
          </Alerta>
        </div>
      )}
      {nueva && <NuevaMfp clientes={clientes} onCerrar={() => setNueva(false)} />}

      <div className="tarjeta overflow-hidden">
        <div className="flex flex-wrap items-center gap-3 border-b border-slate-100 p-4">
          <div className="relative w-72">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-slate-400" />
            <input className="input pl-8" placeholder="Número, cliente, NIT o contrato" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <select className="input w-56" value={cliente} onChange={(e) => setCliente(e.target.value)}>
            <option value="">Todos los clientes</option>
            {clientes.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
          </select>
          <select className="input w-40" value={estado} onChange={(e) => setEstado(e.target.value)}>
            <option value="">Todos los estados</option><option value="vigente">Vigentes</option><option value="vencida">Vencidas</option><option value="terminada">Terminadas</option>
          </select>
          <label className="flex items-center gap-2 text-sm text-slate-600"><input type="checkbox" checked={conAlertas} onChange={(e) => setConAlertas(e.target.checked)} /> Solo con alertas</label>
        </div>
        <div className="overflow-x-auto">
          <table className="tabla">
            <thead><tr><th>MFP</th><th>Cliente</th><th>Vigencia</th><th>Estado</th><th className="text-right">Facturación</th><th className="text-right">Pactado</th>
              <th className="text-right">% MFP / comercial</th><th className="text-right">Ejecutado</th><th className="text-right">Pendiente</th><th className="text-right">Reembolso</th><th /></tr></thead>
            <tbody>
              {(lista ?? []).map((m) => (
                <tr key={m.id} className="hover:bg-slate-50">
                  <td><Link className="font-medium text-marca-700 hover:underline" href={`/costeo/mfp/${m.id}`}>{m.numero}</Link><p className="text-xs text-slate-500">{m.contrato}</p></td>
                  <td><p className="max-w-xs truncate">{m.cliente.nombre}</p><p className="text-xs text-slate-500">{m.cliente.nit}</p></td>
                  <td className="whitespace-nowrap text-xs text-slate-600">{fecha(m.fecha_inicio)} – {fecha(m.fecha_fin)}<br />{m.duracion_meses ?? "—"} meses</td>
                  <td><span className={`rounded-full px-2 py-0.5 text-xs font-medium ${ESTADO_MFP[m.estado]}`}>{m.estado}</span></td>
                  <td className="text-right tabular-nums">{pesos(m.facturacion_total)}</td>
                  <td className="text-right tabular-nums">{pesos(m.pactado)}</td>
                  <td className={`text-right tabular-nums ${m.diferencia_pct !== null && m.diferencia_pct > 0.0005 ? "font-semibold text-red-700" : ""}`}>{pct(m.pct_mfp)} / {pct(m.pct_comercial)}</td>
                  <td className="text-right tabular-nums">{pesos(m.ejecutado)}</td>
                  <td className="text-right tabular-nums">{pesos(m.pendiente)}</td>
                  <td className="text-right tabular-nums">{pesos(m.reembolso)}</td>
                  <td>{m.alertas.length > 0 && <span title={m.alertas.map((a) => a.mensaje).join("\n")}><TriangleAlert className="h-4 w-4 text-amber-600" /></span>}</td>
                </tr>
              ))}
              {lista && !lista.length && <tr><td colSpan={11} className="py-8 text-center text-slate-400">No hay MFP{gestionar ? ": importe el Excel o cree una nueva" : ""}.</td></tr>}
            </tbody>
            {totales && lista && lista.length > 0 && (
              <tfoot><tr className="font-semibold">
                <td colSpan={4} className="px-4 py-2">{lista.length} MFP</td>
                <td className="px-4 text-right tabular-nums">{pesos(totales.facturacion_total)}</td><td className="px-4 text-right tabular-nums">{pesos(totales.pactado)}</td>
                <td className="px-4 text-right tabular-nums">{pct(totales.facturacion_total ? totales.pactado / totales.facturacion_total : null)}</td>
                <td className="px-4 text-right tabular-nums">{pesos(totales.ejecutado)}</td><td className="px-4 text-right tabular-nums">{pesos(totales.pendiente)}</td>
                <td className="px-4 text-right tabular-nums">{pesos(totales.reembolso)}</td><td />
              </tr></tfoot>
            )}
          </table>
        </div>
      </div>
    </>
  );
}

type ItemNuevo = { tipo_id: string; pactado: string; descripcion: string };

function NuevaMfp({ clientes, onCerrar }: { clientes: Cliente[]; onCerrar: () => void }) {
  const router = useRouter();
  const [tipos, setTipos] = useState<TipoItem[]>([]);
  const [f, setF] = useState({ numero: "", cliente_id: "", contrato: "", fecha_inicio: "", duracion_meses: "12", valor_mensual: "", pct_comercial: "", notas: "" });
  const [items, setItems] = useState<ItemNuevo[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    api<TipoItem[]>("/costeo/tipos-item").then((t) => setTipos(t.filter((x) => x.activo))).catch(() => {});
  }, []);

  async function guardar() {
    setError("");
    try {
      const m = await api<Mfp>("/costeo/mfp", {
        method: "POST", json: {
          numero: f.numero, cliente_id: Number(f.cliente_id), contrato: f.contrato, fecha_inicio: f.fecha_inicio || null,
          duracion_meses: f.duracion_meses ? Number(f.duracion_meses) : null, valor_mensual: Number(f.valor_mensual || 0),
          pct_comercial: f.pct_comercial ? Number(f.pct_comercial.replace(",", ".")) / 100 : null, notas: f.notas,
          items: items.filter((i) => i.tipo_id && i.pactado).map((i) => ({ tipo_id: Number(i.tipo_id), pactado: Number(i.pactado), descripcion: i.descripcion })),
        },
      });
      router.push(`/costeo/mfp/${m.id}`);
    } catch (e) {
      setError(mensajeError(e));
    }
  }
  const campo = (k: keyof typeof f, etiqueta: string, tipo = "text", extra = "") => (
    <div className={extra}><label className="label">{etiqueta}</label><input className="input" type={tipo} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></div>
  );
  const unidad = (id: string) => tipos.find((t) => String(t.id) === id)?.unidad;
  return (
    <div className="tarjeta mb-5 space-y-4 p-5">
      <h2 className="font-semibold text-slate-800">Nueva MFP</h2>
      <div className="grid gap-3 sm:grid-cols-4">
        {campo("numero", "Número de MFP física")}
        <div className="sm:col-span-2">
          <label className="label">Cliente</label>
          <select className="input" value={f.cliente_id} onChange={(e) => setF({ ...f, cliente_id: e.target.value })}>
            <option value="">Seleccione… (créelo en Clientes si no existe)</option>
            {clientes.map((c) => <option key={c.id} value={c.id}>{c.nombre} · {c.nit}</option>)}
          </select>
        </div>
        {campo("contrato", "Contrato")}
        {campo("fecha_inicio", "Fecha de inicio", "date")}
        {campo("duracion_meses", "Duración (meses)", "number")}
        {campo("valor_mensual", "Facturación mensual", "number")}
        {campo("pct_comercial", "% de la MFP física", "text")}
        {campo("notas", "Notas / otrosí", "text", "sm:col-span-4")}
      </div>
      <div>
        <p className="label">Ítems pactados</p>
        {items.map((it, i) => (
          <div key={i} className="mb-2 grid gap-2 sm:grid-cols-[1.2fr_0.8fr_1.5fr_auto]">
            <select className="input" value={it.tipo_id} onChange={(e) => setItems(items.map((x, j) => (j === i ? { ...x, tipo_id: e.target.value } : x)))}>
              <option value="">Ítem…</option>{tipos.map((t) => <option key={t.id} value={t.id}>{t.nombre}</option>)}
            </select>
            <input className="input" type="number" placeholder={unidad(it.tipo_id) === "horas" ? "Horas por año" : unidad(it.tipo_id) === "pesos_mes" ? "Valor mensual" : "Valor total"}
              value={it.pactado} onChange={(e) => setItems(items.map((x, j) => (j === i ? { ...x, pactado: e.target.value } : x)))} />
            <input className="input" placeholder="Descripción" value={it.descripcion} onChange={(e) => setItems(items.map((x, j) => (j === i ? { ...x, descripcion: e.target.value } : x)))} />
            <button className="btn-secundario" onClick={() => setItems(items.filter((_, j) => j !== i))}>Quitar</button>
          </div>
        ))}
        <button className="btn-secundario" onClick={() => setItems([...items, { tipo_id: "", pactado: "", descripcion: "" }])}><Plus className="h-4 w-4" /> Ítem</button>
      </div>
      {error && <Alerta>{error}</Alerta>}
      <div className="flex justify-end gap-2">
        <button className="btn-secundario" onClick={onCerrar}>Cancelar</button>
        <button className="btn-primario" disabled={!f.numero || !f.cliente_id} onClick={guardar}>Crear MFP</button>
      </div>
    </div>
  );
}
