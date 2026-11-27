"use client";

import { ArrowLeft, Ban, CheckCircle2, Loader2, RotateCcw, Save, ShieldCheck, Undo2, X } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Alerta } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";
import { COLUMNAS_LEG, fecha, plata, type LegalizacionCompleta, type Persona, type Producto } from "@/lib/contabilidad";
import { usePermiso } from "@/lib/sesion";

export default function DetalleLegalizacion() {
  const { id } = useParams<{ id: string }>();
  const revisar = usePermiso("contabilidad.revisar");
  const [x, setX] = useState<LegalizacionCompleta | null>(null);
  const [elaboran, setElaboran] = useState<Persona[]>([]);
  const [empleados, setEmpleados] = useState<Persona[]>([]);
  const [productos, setProductos] = useState<Producto[]>([]);
  const [ocupado, setOcupado] = useState("");
  const [msg, setMsg] = useState<{ tipo: "ok" | "error"; texto: string } | null>(null);
  const soportes = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api<LegalizacionCompleta>(`/contabilidad/legalizaciones/${id}`).then(setX).catch((e) => setMsg({ tipo: "error", texto: mensajeError(e) }));
    api<Persona[]>("/contabilidad/legalizaciones/personas/lista?tipo=elabora").then((p) => setElaboran(p.filter((y) => y.activo))).catch(() => {});
    api<Persona[]>("/contabilidad/legalizaciones/personas/lista?tipo=empleado").then((p) => setEmpleados(p.filter((y) => y.activo))).catch(() => {});
    api<Producto[]>("/contabilidad/productos").then((p) => setProductos(p.filter((y) => y.activo))).catch(() => {});
  }, [id]);

  if (!x) return msg ? <Alerta>{msg.texto}</Alerta> : <p className="text-sm text-slate-500">Cargando…</p>;
  const editable = revisar && (x.estado === "pendiente" || x.estado === "lista");
  const setLinea = (i: number, y: Partial<LegalizacionCompleta["lineas"][number]>) => setX({ ...x, lineas: x.lineas.map((l, j) => (j === i ? { ...l, ...y } : l)) });

  async function hacer(clave: string, fn: () => Promise<LegalizacionCompleta>, texto: string) {
    setMsg(null);
    setOcupado(clave);
    try { setX(await fn()); setMsg({ tipo: "ok", texto }); } catch (e) { setMsg({ tipo: "error", texto: mensajeError(e) }); } finally { setOcupado(""); }
  }
  const guardar = (lista: boolean) => hacer(lista ? "lista" : "guardar", () => api<LegalizacionCompleta>(`/contabilidad/legalizaciones/${x.id}`, {
    method: "PUT", json: { colaborador_nombre: x.colaborador_nombre, colaborador_documento: x.colaborador_documento, elabora_documento: x.elabora_documento,
      nota: x.nota, anticipo_valor: x.anticipo_valor, lista,
      lineas: x.lineas.map((l) => ({ id: l.id, cuenta: l.cuenta, documento: l.documento, columna: l.columna, excluida: l.excluida })) } }),
  lista ? "Lista: sale en el próximo plano de legalizaciones." : "Guardada.");
  const revisarSoportes = (f: File | undefined) => f && hacer("soportes", () => {
    const form = new FormData();
    form.append("archivo", f);
    return api<LegalizacionCompleta>(`/contabilidad/legalizaciones/${x.id}/soportes`, { method: "POST", body: form });
  }, "Soportes revisados.");
  const estado = (accion: string) => hacer(accion, () => api<LegalizacionCompleta>(`/contabilidad/legalizaciones/${x.id}/estado`, { method: "POST", json: { accion } }),
    accion === "descartar" ? "Descartada." : "Reabierta.");
  const debitos = x.movimientos.reduce((s, m) => s + m.debito, 0), creditos = x.movimientos.reduce((s, m) => s + m.credito, 0);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start gap-3">
        <Link href="/contabilidad/legalizaciones" className="mt-1 text-slate-400 hover:text-slate-600"><ArrowLeft className="h-5 w-5" /></Link>
        <div>
          <h1 className="text-2xl font-bold text-marca-900">Legalización #{x.numero_formato || x.id}</h1>
          <p className="text-sm text-slate-500">{x.colaborador_nombre} · {x.sucursal} · legalizada {fecha(x.fecha_legalizacion)} ·
            {x.anticipo_valor ? ` anticipo ${plata(x.anticipo_valor)}${x.anticipo_fecha ? ` del ${fecha(x.anticipo_fecha)}` : ""}` : " reembolso"}</p>
          <p className="text-xs text-slate-400">{x.motivo} · {x.archivo} ({x.leida_con === "excel" ? "Excel" : "PDF leído por la IA"})</p>
        </div>
        <span className="mt-1 rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium">{x.estado}{x.documento_numero ? ` · LG ${x.documento_numero}` : ""}</span>
        {editable && (
          <div className="ml-auto flex flex-wrap gap-2">
            <button className="btn-secundario" disabled={!!ocupado} onClick={() => soportes.current?.click()} title="La IA revisa que cada gasto tenga su soporte">
              {ocupado === "soportes" ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />} Revisar soportes</button>
            <input ref={soportes} type="file" accept=".pdf" className="hidden" onChange={(e) => { revisarSoportes(e.target.files?.[0]); e.target.value = ""; }} />
            <button className="btn-secundario" disabled={!!ocupado} onClick={() => guardar(false)}><Save className="h-4 w-4" /> Guardar</button>
            <button className="btn-primario" disabled={!!ocupado} onClick={() => guardar(true)}><CheckCircle2 className="h-4 w-4" /> Lista para el plano</button>
            <button className="btn-secundario text-red-700" disabled={!!ocupado} onClick={() => confirm("¿Descartar esta legalización?") && estado("descartar")}><Ban className="h-4 w-4" /> Descartar</button>
          </div>
        )}
        {revisar && x.estado === "descartada" && <button className="btn-secundario ml-auto" onClick={() => estado("reabrir")}><RotateCcw className="h-4 w-4" /> Reabrir</button>}
      </div>
      {msg && <Alerta tipo={msg.tipo}>{msg.texto}</Alerta>}
      {x.avisos.length > 0 && <div className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900"><ul className="ml-4 list-disc">{x.avisos.map((a, i) => <li key={i}>{a}</li>)}</ul></div>}

      <section className="tarjeta space-y-3 p-4">
        <div className="grid gap-3 md:grid-cols-4">
          <div><label className="label">Elabora (tercero interno)</label>
            <select className={`input ${!x.elabora_documento ? "border-amber-400" : ""}`} disabled={!editable} value={x.elabora_documento} onChange={(e) => setX({ ...x, elabora_documento: e.target.value })}>
              <option value="">—</option>{elaboran.map((p) => <option key={p.id} value={p.documento}>{p.nombre} · {p.documento}</option>)}
              {x.elabora_documento && !elaboran.some((p) => p.documento === x.elabora_documento) && <option value={x.elabora_documento}>{x.elabora_documento}</option>}
            </select></div>
          <div><label className="label">Colaborador que legaliza (tercero externo)</label>
            <input className={`input ${!x.colaborador_documento ? "border-amber-400" : ""}`} list="empleados" disabled={!editable} value={x.colaborador_documento}
              onChange={(e) => { const d = e.target.value.split(" ")[0]; setX({ ...x, colaborador_documento: d, colaborador_nombre: empleados.find((p) => p.documento === d)?.nombre ?? x.colaborador_nombre }); }} />
            <p className="mt-0.5 text-xs text-slate-500">{x.colaborador_nombre}{empleados.length > 0 && !empleados.some((p) => p.documento === x.colaborador_documento) ? " · no está en el listado de empleados" : ""}</p>
            <datalist id="empleados">{empleados.map((p) => <option key={p.id} value={p.documento}>{p.nombre}</option>)}</datalist></div>
          <div><label className="label">Anticipo (0 = reembolso)</label>
            <input className="input" type="number" disabled={!editable} value={x.anticipo_valor} onChange={(e) => setX({ ...x, anticipo_valor: Number(e.target.value) || 0 })} /></div>
          <div><label className="label">Nota del documento</label>
            <input className="input" maxLength={300} disabled={!editable} value={x.nota} onChange={(e) => setX({ ...x, nota: e.target.value })} /></div>
        </div>
        <div className="overflow-x-auto">
          <table className="tabla text-sm">
            <thead><tr><th>#</th><th>Fecha</th><th>Beneficiario</th><th>Cédula / NIT</th><th>Columna</th><th className="text-right">Valor</th><th>Detalle</th><th>Cuenta</th><th>Soporte</th><th /></tr></thead>
            <tbody>
              {x.lineas.map((l, i) => (
                <tr key={l.id} className={l.excluida ? "bg-slate-50 text-slate-400" : ""}>
                  <td>{l.orden}</td><td className="whitespace-nowrap">{fecha(l.fecha)}</td>
                  <td className={l.excluida ? "line-through" : ""}>{l.beneficiario}</td>
                  <td><input className="input w-32" disabled={!editable || l.excluida} value={l.documento} onChange={(e) => setLinea(i, { documento: e.target.value })} /></td>
                  <td><select className="input w-36" disabled={!editable || l.excluida} value={l.columna} onChange={(e) => setLinea(i, { columna: e.target.value })}>
                    {Object.entries(COLUMNAS_LEG).map(([k, t]) => <option key={k} value={k}>{t}</option>)}</select></td>
                  <td className={`text-right tabular-nums ${l.excluida ? "line-through" : ""}`}>{plata(l.valor)}</td>
                  <td className="max-w-xs text-xs">{l.detalle}</td>
                  <td><input className={`input w-28 ${!l.cuenta && !l.excluida ? "border-amber-400" : ""}`} list="cuentas-leg" disabled={!editable || l.excluida} value={l.cuenta}
                    onChange={(e) => setLinea(i, { cuenta: e.target.value.split(" ")[0] })} />
                    <p className="max-w-28 truncate text-xs text-slate-500">{productos.find((p) => p.codigo === l.cuenta)?.nombre ?? ""}</p></td>
                  <td className="text-xs">{l.soporte === null ? <span className="text-slate-400">sin revisar</span> : l.soporte
                    ? <span className="text-green-700" title={l.soporte_nota}>✓ {l.soporte_nota.slice(0, 40)}</span> : <span className="font-medium text-amber-700">✗ sin soporte</span>}</td>
                  <td>{editable && (l.excluida
                    ? <button className="inline-flex items-center gap-1 text-xs text-marca-700 hover:underline" onClick={() => setLinea(i, { excluida: false })}><Undo2 className="h-3.5 w-3.5" /> Incluir</button>
                    : <button className="text-slate-400 hover:text-red-600" title="Quitar este gasto de la nota contable" onClick={() => setLinea(i, { excluida: true })}><X className="h-4 w-4" /></button>)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <datalist id="cuentas-leg">{productos.map((p) => <option key={p.codigo} value={p.codigo}>{p.nombre}</option>)}</datalist>
        </div>
        <p className="text-right text-sm">Total de gastos <b className="tabular-nums">{plata(x.total)}</b>{x.total_formato && Math.abs(x.total_formato - x.total) > 1 ? <span className="text-amber-700"> (el formato dice {plata(x.total_formato)})</span> : ""}</p>
      </section>

      {x.movimientos.length > 0 && (
        <section className="tarjeta p-4">
          <h2 className="mb-2 font-semibold text-slate-800">Nota contable (así sale en el plano)</h2>
          <table className="tabla text-sm">
            <thead><tr><th>Cuenta</th><th>Nota</th><th>Tercero</th><th className="text-right">Débito</th><th className="text-right">Crédito</th></tr></thead>
            <tbody>
              {x.movimientos.map((m, k) => (
                <tr key={k}><td className="font-mono">{m.cuenta}</td><td className="max-w-md truncate text-xs">{m.nota}</td><td>{m.tercero}</td>
                  <td className="text-right tabular-nums">{m.debito ? plata(m.debito) : ""}</td><td className="text-right tabular-nums">{m.credito ? plata(m.credito) : ""}</td></tr>
              ))}
              <tr className="font-semibold"><td colSpan={3}>Sumas</td><td className="text-right tabular-nums">{plata(debitos)}</td><td className="text-right tabular-nums">{plata(creditos)}</td></tr>
            </tbody>
          </table>
        </section>
      )}
      {x.faltantes.length > 0 && editable && <p className="text-sm text-amber-800">Para el plano falta: {x.faltantes.join("; ")}.</p>}
    </div>
  );
}
