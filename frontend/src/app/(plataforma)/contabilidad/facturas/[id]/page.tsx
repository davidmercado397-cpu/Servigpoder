"use client";

import { ArrowLeft, Ban, CheckCircle2, Loader2, RotateCcw, Save, Sparkles, Undo2, X } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AprenderCorrecciones } from "@/components/aprender-regla";
import { Alerta } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";
import { fecha, plata, type Centro, type Correccion, type FacturaCompleta, type Producto } from "@/lib/contabilidad";
import { usePermiso } from "@/lib/sesion";

const RETENCION: Record<string, string> = { rete_fuente: "Rete fuente", rete_iva: "Rete IVA", rete_ica: "Rete ICA", otra: "Otra retención" };

export default function DetalleFactura() {
  const { id } = useParams<{ id: string }>();
  const revisar = usePermiso("contabilidad.revisar");
  const [f, setF] = useState<FacturaCompleta | null>(null);
  const [productos, setProductos] = useState<Producto[]>([]);
  const [centros, setCentros] = useState<Centro[]>([]);
  const [ocupado, setOcupado] = useState("");
  const [correcciones, setCorrecciones] = useState<Correccion[]>([]);
  const [msg, setMsg] = useState<{ tipo: "ok" | "error"; texto: string } | null>(null);

  useEffect(() => {
    api<FacturaCompleta>(`/contabilidad/facturas/${id}`).then(setF).catch((e) => setMsg({ tipo: "error", texto: mensajeError(e) }));
    api<Producto[]>("/contabilidad/productos").then((p) => setProductos(p.filter((x) => x.activo))).catch(() => {});
    api<Centro[]>("/contabilidad/centros").then((c) => setCentros(c.filter((x) => x.activo))).catch(() => {});
  }, [id]);

  if (!f) return msg ? <Alerta>{msg.texto}</Alerta> : <p className="text-sm text-slate-500">Cargando…</p>;
  const editable = revisar && (f.estado === "pendiente" || f.estado === "lista" || f.estado === "aparte");
  const setLinea = (i: number, x: Partial<FacturaCompleta["lineas"][number]>) => setF({ ...f, lineas: f.lineas.map((l, j) => (j === i ? { ...l, ...x } : l)) });

  async function guardar(lista: boolean) {
    setMsg(null);
    setOcupado(lista ? "lista" : "guardar");
    try {
      const r = await api<FacturaCompleta & { correcciones?: Correccion[] }>(`/contabilidad/facturas/${f!.id}`, { method: "PUT", json: {
        nota: f!.nota, lista, cuenta_cobro: f!.cuenta_cobro, lineas: f!.lineas.map((l) => ({ id: l.id, producto: l.producto, centro_costos: l.centro_costos, nota: l.nota, excluida: !!l.excluida })) } });
      setF(r);
      // Si cambió cuentas que propuso el agente, se le ofrece que las aprenda
      if (r.correcciones?.length) setCorrecciones(r.correcciones);
      setMsg({ tipo: "ok", texto: lista ? "Lista: sale en el próximo plano." : "Guardada." });
    } catch (e) { setMsg({ tipo: "error", texto: mensajeError(e) }); } finally { setOcupado(""); }
  }
  async function accion(ruta: string, json?: object) {
    setMsg(null);
    setOcupado(ruta);
    try {
      setF(await api<FacturaCompleta>(`/contabilidad/facturas/${f!.id}/${ruta}`, { method: "POST", json }));
    } catch (e) { setMsg({ tipo: "error", texto: mensajeError(e) }); } finally { setOcupado(""); }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start gap-3">
        <Link href="/contabilidad" className="mt-1 text-slate-400 hover:text-slate-600"><ArrowLeft className="h-5 w-5" /></Link>
        <div>
          <h1 className="text-2xl font-bold text-marca-900">{f.cuenta_cobro ? "Cuenta de cobro" : "Factura"} {f.prefijo}{f.numero}</h1>
          <p className="text-sm text-slate-500">{f.emisor_nombre} · NIT {f.emisor_nit}{f.emisor_dv ? `-${f.emisor_dv}` : ""} · emitida {fecha(f.fecha_emision)}
            · vence {fecha(f.fecha_vencimiento)} · {f.forma_pago}</p>
          <p className="text-xs text-slate-400">Comprador: {f.comprador_nombre} (NIT {f.comprador_nit}) · {f.origen === "correo" ? `correo de ${f.correo_de}` : "cargada a mano"}
            · leída {f.leida_con === "ia" ? "por la IA desde el PDF" : "del XML de la DIAN"} · CUFE {f.cufe.slice(0, 24)}…</p>
        </div>
        <span className="mt-1 rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium">{f.estado}{f.documento_numero ? ` · ${f.documento_numero}` : ""}</span>
        {editable && (
          <div className="ml-auto flex flex-wrap gap-2">
            {f.estado === "aparte" ? (
              <button className="btn-primario" disabled={!!ocupado} onClick={() => accion("estado", { accion: "incluir" })}><CheckCircle2 className="h-4 w-4" /> Incluir (sí se contabiliza)</button>
            ) : (
              <>
                <button className="btn-secundario" disabled={!!ocupado} onClick={() => accion("proponer")} title="La IA vuelve a proponer cuentas, centros y notas">
                  {ocupado === "proponer" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} Proponer con IA</button>
                <button className="btn-secundario" disabled={!!ocupado} onClick={() => guardar(false)}><Save className="h-4 w-4" /> Guardar</button>
                <button className="btn-primario" disabled={!!ocupado} onClick={() => guardar(true)}><CheckCircle2 className="h-4 w-4" /> {f.estado === "lista" ? "Guardar (sigue lista)" : "Lista para el plano"}</button>
              </>
            )}
            <button className="btn-secundario text-red-700" disabled={!!ocupado} onClick={() => confirm("¿Descartar esta factura? No saldrá en el plano.") && accion("estado", { accion: "descartar" })}><Ban className="h-4 w-4" /> Descartar</button>
          </div>
        )}
        {revisar && f.estado === "descartada" && <button className="btn-secundario ml-auto" onClick={() => accion("estado", { accion: "reabrir" })}><RotateCcw className="h-4 w-4" /> Reabrir</button>}
      </div>
      {msg && <Alerta tipo={msg.tipo}>{msg.texto}</Alerta>}
      {f.motivo_aparte && f.estado === "aparte" && <Alerta tipo="info">{f.motivo_aparte}. Confirme si se contabiliza.</Alerta>}
      {f.avisos.length > 0 && <div className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900"><ul className="ml-4 list-disc">{f.avisos.map((a, i) => <li key={i}>{a}</li>)}</ul></div>}

      <section className="tarjeta space-y-3 p-4">
        <div className="flex flex-wrap items-end gap-6">
          <div className="w-full max-w-xl"><label className="label">Nota del documento (encabezado)</label>
            <input className="input" maxLength={300} disabled={!editable} value={f.nota} onChange={(e) => setF({ ...f, nota: e.target.value })} placeholder="Ej.: COMPRA DE VUELO" /></div>
          <label className="flex items-center gap-2 pb-2 text-sm" title="En el plano va con Tipo FC y Prefijo DSS, con su propio consecutivo">
            <input type="checkbox" disabled={!editable} checked={f.cuenta_cobro} onChange={(e) => setF({ ...f, cuenta_cobro: e.target.checked })} />
            Es cuenta de cobro (en el plano: FC / DSS)
          </label>
        </div>
        <div className="overflow-x-auto">
          <table className="tabla text-sm">
            <thead><tr><th>#</th><th>Producto de la factura</th><th className="text-right">Cant.</th><th className="text-right">Valor unitario</th><th className="text-right">IVA</th>
              <th>Producto / cuenta WO</th><th>Centro de costos</th><th>Nota del detalle</th><th /></tr></thead>
            <tbody>
              {f.lineas.map((l, i) => l.excluida ? (
                <tr key={l.id} className="bg-slate-50 text-slate-400">
                  <td>{l.orden}</td>
                  <td className="max-w-xs"><p className="text-xs line-through">{l.descripcion}</p></td>
                  <td className="text-right tabular-nums line-through">{l.cantidad.toLocaleString("es-CO")}</td>
                  <td className={`text-right tabular-nums line-through ${l.valor_unitario < 0 ? "text-red-400" : ""}`}>{plata(l.valor_unitario)}</td>
                  <td />
                  <td colSpan={3} className="text-xs italic">Fuera del plano{l.valor_unitario < 0 ? ": se resta de los otros productos" : ""}</td>
                  <td>{editable && l.valor_unitario >= 0 && <button className="inline-flex items-center gap-1 text-xs text-marca-700 hover:underline" title="Volver a llevar esta línea al plano"
                    onClick={() => setLinea(i, { excluida: false })}><Undo2 className="h-3.5 w-3.5" /> Incluir</button>}</td>
                </tr>
              ) : (
                <tr key={l.id}>
                  <td>{l.orden}</td>
                  <td className="max-w-xs"><p className="text-xs">{l.descripcion}</p></td>
                  <td className="text-right tabular-nums">{l.cantidad.toLocaleString("es-CO")}</td>
                  <td className={`text-right tabular-nums ${l.valor_unitario < 0 ? "font-semibold text-red-700" : ""}`}>{plata(l.valor_unitario)}
                    {l.valor_plano != null && <p className="text-xs font-normal text-amber-700" title="Se le restaron los valores negativos de la factura">en el plano {plata(l.valor_plano)}</p>}</td>
                  <td className="text-right tabular-nums">{l.iva_pct} %</td>
                  <td>
                    <input className={`input w-56 ${!l.producto ? "border-amber-400" : ""}`} list="productos-wo" disabled={!editable} value={l.producto}
                      onChange={(e) => setLinea(i, { producto: e.target.value.split(" ")[0] })} placeholder="Código" />
                    <p className="mt-0.5 max-w-56 truncate text-xs text-slate-500">{productos.find((p) => p.codigo === l.producto)?.nombre ?? (l.producto ? "No está en el catálogo" : "")}</p>
                    {l.producto_ia && l.producto !== l.producto_ia && <p className="text-xs text-slate-400">El agente propuso {l.producto_ia}</p>}
                  </td>
                  <td><select className={`input w-44 ${!l.centro_costos ? "border-amber-400" : ""}`} disabled={!editable} value={l.centro_costos} onChange={(e) => setLinea(i, { centro_costos: e.target.value })}>
                    <option value="">—</option>{centros.map((c) => <option key={c.id} value={c.nombre}>{c.nombre}</option>)}
                    {l.centro_costos && !centros.some((c) => c.nombre === l.centro_costos) && <option value={l.centro_costos}>{l.centro_costos}</option>}
                  </select></td>
                  <td><input className="input w-48" maxLength={200} disabled={!editable} value={l.nota} onChange={(e) => setLinea(i, { nota: e.target.value })} /></td>
                  <td>{editable && <button className="text-slate-400 hover:text-red-600" title="Quitar esta línea del plano"
                    onClick={() => setLinea(i, { excluida: true })}><X className="h-4 w-4" /></button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <datalist id="productos-wo">{productos.map((p) => <option key={p.codigo} value={p.codigo}>{p.nombre}</option>)}</datalist>
        </div>
        {(f.ajuste_negativos ?? []).length > 0 && (
          <div className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
            <p className="font-medium">Valores negativos restados de otros productos (no van en el plano)</p>
            <ul className="ml-4 list-disc">{f.ajuste_negativos!.map((t, k) => <li key={k}>{t}</li>)}</ul>
          </div>
        )}
        {(f.opciones_proveedor ?? []).length > 0 && (
          <div className="rounded-lg bg-slate-50 p-3 text-sm">
            <p className="mb-1 font-medium text-slate-700">Así se ha registrado este proveedor en World Office</p>
            <div className="flex flex-wrap gap-2">
              {f.opciones_proveedor!.map((o) => (
                <span key={o.producto} className="inline-flex items-center gap-2 rounded-full bg-white px-3 py-1 ring-1 ring-slate-200">
                  <span className="font-mono">{o.producto}</span> {o.nombre}
                  <span className="text-xs text-slate-500">· {o.compras} compra(s){o.ultima_fecha ? ` · última ${fecha(o.ultima_fecha)}` : ""}{o.ultimo_precio ? ` · ${plata(o.ultimo_precio)}` : ""}</span>
                  {editable && f.lineas.length > 0 && (
                    <button className="text-xs text-marca-700 hover:underline" title="Poner este producto en todas las líneas"
                      onClick={() => setF({ ...f, lineas: f.lineas.map((l) => ({ ...l, producto: o.producto })) })}>usar en todas</button>
                  )}
                </span>
              ))}
            </div>
          </div>
        )}
        <div className="flex flex-wrap justify-end gap-6 border-t border-slate-100 pt-3 text-sm">
          <span>Subtotal <b className="tabular-nums">{plata(f.subtotal)}</b></span>
          <span>IVA <b className="tabular-nums">{plata(f.iva)}</b></span>
          {Object.entries(f.retenciones).map(([k, v]) => v ? <span key={k}>{RETENCION[k] ?? k} <b className="tabular-nums">{plata(v)}</b></span> : null)}
          <span>Total <b className="tabular-nums">{plata(f.total)}</b></span>
        </div>
      </section>
      {f.faltantes.length > 0 && editable && <p className="text-sm text-amber-800">Para el plano falta: {f.faltantes.join("; ")}.</p>}
      {correcciones.length > 0 && <AprenderCorrecciones facturaId={f.id} correcciones={correcciones} productos={productos} onCerrar={() => setCorrecciones([])} />}
    </div>
  );
}
