"use client";

import { AlertTriangle, ArrowLeft, Calculator, ChevronDown, ChevronRight, Download, Lock, Save, Trash2, Unlock } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { Alerta, Insignia, Pestanas, SubirArchivo } from "@/components/ui";
import { api, mensajeError, subirArchivo } from "@/lib/api";
import { usePermiso } from "@/lib/sesion";
import { nombrePeriodo, pesos, type LiquidacionSpeed, type NovedadSpeed, type PeriodoSpeed } from "@/lib/speed";

type Detalle = PeriodoSpeed & { liquidaciones: LiquidacionSpeed[] };
type Campo = "dias_programados" | "ausencias" | "licencias" | "suspensiones" | "incapacidad" | "incapacidad_previos";
const CAMPOS: [Campo, string, string][] = [
  ["dias_programados", "Días programados", "Vacío = toda la quincena. Solo cuenta para quien aplica a la regla"],
  ["ausencias", "Ausencias", "Descuentan salario, auxilio y variables"],
  ["licencias", "Licencias no rem.", "Descuentan salario, auxilio y variables"],
  ["suspensiones", "Suspensiones", "Descuentan salario, auxilio y variables"],
  ["incapacidad", "Incapacidad", "2 primeros días al 100 %, desde el 3.º al 66,67 %"],
  ["incapacidad_previos", "Días previos incap.", "Los que ya llevaba la misma incapacidad antes de esta quincena"],
];

export default function QuincenaSpeed() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const liquidar = usePermiso("speed.liquidar");
  const [p, setP] = useState<Detalle | null>(null);
  const [pestana, setPestana] = useState<"liquidacion" | "novedades">("liquidacion");
  const [msg, setMsg] = useState<{ tipo: "ok" | "error" | "info"; texto: string } | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const cargar = useCallback(() => api<Detalle>(`/speed/periodos/${id}`).then(setP).catch((e) => setMsg({ tipo: "error", texto: mensajeError(e) })), [id]);
  useEffect(() => { cargar(); }, [cargar]);

  if (!p) return msg ? <Alerta>{msg.texto}</Alerta> : <p className="text-sm text-slate-500">Cargando…</p>;
  const abierto = p.estado === "abierto";

  async function accion(fn: () => Promise<unknown>, ok: string) {
    setMsg(null);
    setOcupado(true);
    try { await fn(); await cargar(); setMsg({ tipo: "ok", texto: ok }); } catch (e) { setMsg({ tipo: "error", texto: mensajeError(e) }); } finally { setOcupado(false); }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <Link href="/speed" className="text-slate-400 hover:text-slate-600"><ArrowLeft className="h-5 w-5" /></Link>
        <div>
          <h1 className="text-2xl font-bold text-marca-900">{nombrePeriodo(p)}</h1>
          <p className="text-sm text-slate-500">{p.calculado_en ? `Liquidada el ${new Date(p.calculado_en).toLocaleString("es-CO")}` : "Sin liquidar"} · {p.novedades} personas con novedades</p>
        </div>
        <Insignia color={abierto ? "bg-green-100 text-green-800" : "bg-slate-200 text-slate-700"}>{p.estado}</Insignia>
        <div className="ml-auto flex flex-wrap gap-2">
          {liquidar && abierto && <button className="btn-primario" disabled={ocupado} onClick={() => accion(() => api(`/speed/periodos/${id}/liquidar`, { method: "POST" }), "Quincena liquidada.")}>
            <Calculator className="h-4 w-4" /> {ocupado ? "Liquidando…" : p.calculado_en ? "Volver a liquidar" : "Liquidar"}</button>}
          {p.calculado_en && <a className="btn-secundario" href={`/api/speed/periodos/${id}/excel`}><Download className="h-4 w-4" /> Excel</a>}
          {liquidar && abierto && p.calculado_en && <button className="btn-secundario" onClick={() => confirm("¿Cerrar la quincena? Ya no se podrá cambiar ni volver a liquidar hasta reabrirla.")
            && accion(() => api(`/speed/periodos/${id}/estado`, { method: "POST", json: { estado: "cerrado" } }), "Quincena cerrada.")}><Lock className="h-4 w-4" /> Cerrar</button>}
          {liquidar && !abierto && <button className="btn-secundario" onClick={() => accion(() => api(`/speed/periodos/${id}/estado`, { method: "POST", json: { estado: "abierto" } }), "Quincena reabierta.")}>
            <Unlock className="h-4 w-4" /> Reabrir</button>}
          {liquidar && abierto && <button className="btn-secundario" title="Eliminar la quincena" onClick={async () => {
            if (!confirm("¿Eliminar esta quincena con sus novedades y su liquidación?")) return;
            try { await api(`/speed/periodos/${id}`, { method: "DELETE" }); router.push("/speed"); } catch (e) { setMsg({ tipo: "error", texto: mensajeError(e) }); }
          }}><Trash2 className="h-4 w-4" /></button>}
        </div>
      </div>
      {msg && <Alerta tipo={msg.tipo}>{msg.texto}</Alerta>}

      <div className="grid gap-3 sm:grid-cols-4">
        <Dato titulo="Personas" valor={String(p.personas)} />
        <Dato titulo="Total devengado" valor={pesos(p.devengado)} />
        <Dato titulo="Deducciones" valor={pesos(p.deducciones)} />
        <Dato titulo="Neto a pagar" valor={pesos(p.neto)} fuerte />
      </div>

      <Pestanas opciones={[["liquidacion", "Liquidación"], ["novedades", "Novedades de la quincena"]]} valor={pestana} onChange={setPestana} />
      {pestana === "liquidacion" ? <Liquidacion filas={p.liquidaciones} />
        : <Novedades periodoId={Number(id)} editable={liquidar && abierto} onCambio={() => setMsg({ tipo: "info", texto: "Novedades actualizadas: vuelva a liquidar la quincena." })} />}
    </div>
  );
}

function Dato({ titulo, valor, fuerte }: { titulo: string; valor: string; fuerte?: boolean }) {
  return (
    <div className="tarjeta p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{titulo}</p>
      <p className={`text-xl tabular-nums ${fuerte ? "font-bold text-marca-900" : "font-semibold text-slate-800"}`}>{valor}</p>
    </div>
  );
}

const DEVENGOS: [keyof LiquidacionSpeed["conceptos"], string][] = [
  ["salario", "Salario"], ["incapacidad", "Incapacidad"], ["auxilio_transporte", "Auxilio de transporte"], ["horas_extras", "Horas extras"],
  ["comisiones", "Comisiones"], ["ley_2466", "Ley 2466"], ["bonificaciones", "Bonificaciones"], ["rodamiento", "Rodamiento"], ["pago_adicional", "Pago adicional"],
];
const DEDUCCIONES: [keyof LiquidacionSpeed["conceptos"], string][] = [
  ["salud", "Salud"], ["pension", "Pensión"], ["embargos", "Embargos"], ["prestamos", "Préstamos"], ["cuotas", "Cuotas"],
];

function Liquidacion({ filas }: { filas: LiquidacionSpeed[] }) {
  const [buscar, setBuscar] = useState("");
  const [abierta, setAbierta] = useState<number | null>(null);
  const [soloAlertas, setSoloAlertas] = useState(false);
  const visibles = useMemo(() => filas.filter((f) => (!soloAlertas || f.alertas.length)
    && (!buscar || `${f.cedula} ${f.nombre} ${f.puesto}`.toLowerCase().includes(buscar.toLowerCase()))), [filas, buscar, soloAlertas]);
  if (!filas.length) return <p className="text-sm text-slate-500">Aún no se ha liquidado. Revise las novedades y dé <b>Liquidar</b>.</p>;
  const conAlertas = filas.filter((f) => f.alertas.length).length;
  return (
    <div className="tarjeta overflow-hidden">
      <div className="flex flex-wrap items-center gap-3 border-b border-slate-100 p-3">
        <input className="input w-72" placeholder="Buscar por cédula, nombre o puesto" value={buscar} onChange={(e) => setBuscar(e.target.value)} />
        {conAlertas > 0 && <label className="flex items-center gap-2 text-sm text-amber-800"><input type="checkbox" checked={soloAlertas} onChange={(e) => setSoloAlertas(e.target.checked)} />
          Solo con alertas ({conAlertas})</label>}
        <span className="ml-auto text-sm text-slate-500">{visibles.length} de {filas.length}</span>
      </div>
      <div className="overflow-x-auto">
        <table className="tabla">
          <thead><tr><th /><th>Colaborador</th><th className="text-right">Días</th><th className="text-right">Salario</th><th className="text-right">Aux. transp.</th>
            <th className="text-right">Variables</th><th className="text-right">Devengado</th><th className="text-right">Deducciones</th><th className="text-right">Neto</th></tr></thead>
          <tbody>
            {visibles.map((f) => {
              const c = f.conceptos;
              const variables = c.horas_extras + c.comisiones + c.ley_2466 + c.bonificaciones + c.rodamiento;
              return (
                <Fragment key={f.empleado_id}>
                  <tr className="hover:bg-slate-50">
                    <td><button onClick={() => setAbierta(abierta === f.empleado_id ? null : f.empleado_id)}>
                      {abierta === f.empleado_id ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}</button></td>
                    <td><p className="font-medium">{f.nombre}{f.alertas.length > 0 && <AlertTriangle className="ml-1 inline h-4 w-4 text-amber-600" />}</p>
                      <p className="text-xs text-slate-500">{f.cedula} · {f.cargo} · {f.puesto}{f.aplica_programacion ? "" : " · no aplica programación"}</p></td>
                    <td className="text-right tabular-nums">{f.dias.trabajados}{f.dias.variables !== f.dias.trabajados && <p className="text-xs text-slate-500">variables {f.dias.variables}</p>}</td>
                    <td className="text-right tabular-nums">{pesos(c.salario + c.incapacidad)}</td>
                    <td className="text-right tabular-nums">{pesos(c.auxilio_transporte)}</td>
                    <td className="text-right tabular-nums">{pesos(variables)}</td>
                    <td className="text-right tabular-nums">{pesos(f.devengado)}</td>
                    <td className="text-right tabular-nums">{pesos(f.deducciones)}</td>
                    <td className="text-right font-semibold tabular-nums">{pesos(f.neto)}</td>
                  </tr>
                  {abierta === f.empleado_id && (
                    <tr><td /><td colSpan={8} className="bg-slate-50">
                      <div className="grid gap-4 py-2 text-sm md:grid-cols-3">
                        <div><p className="mb-1 font-medium text-slate-700">Días</p>
                          <p className="text-slate-600">De la quincena {f.dias.contrato} · trabajados {f.dias.trabajados} · no laborados {f.dias.no_laborados}
                            {f.dias.incapacidad ? ` · incapacidad ${f.dias.incapacidad} (${f.dias.incapacidad_100} al 100 %)` : ""}
                            {f.dias.programados !== null ? ` · programados ${f.dias.programados}` : ""} · para variables {f.dias.variables}</p>
                          <p className="mt-1 text-slate-600">Base de salud y pensión {pesos(f.ibc)}</p></div>
                        <div><p className="mb-1 font-medium text-slate-700">Devengado</p>
                          {DEVENGOS.filter(([k]) => c[k]).map(([k, t]) => <p key={k} className="flex justify-between"><span>{t}</span><span className="tabular-nums">{pesos(c[k])}</span></p>)}</div>
                        <div><p className="mb-1 font-medium text-slate-700">Deducciones</p>
                          {DEDUCCIONES.filter(([k]) => c[k]).map(([k, t]) => <p key={k} className="flex justify-between"><span>{t}</span><span className="tabular-nums">{pesos(c[k])}</span></p>)}
                          {f.descuentos.map((d) => <p key={d.id} className="text-xs text-slate-500">{d.descripcion}: {pesos(d.valor)}</p>)}</div>
                      </div>
                      {f.alertas.length > 0 && <ul className="pb-2 text-sm text-amber-800">{f.alertas.map((a, i) => <li key={i}>• {a}</li>)}</ul>}
                    </td></tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Novedades({ periodoId, editable, onCambio }: { periodoId: number; editable: boolean; onCambio: () => void }) {
  const [filas, setFilas] = useState<NovedadSpeed[] | null>(null);
  const [cambiadas, setCambiadas] = useState<Record<number, NovedadSpeed>>({});
  const [buscar, setBuscar] = useState("");
  const [soloCon, setSoloCon] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "ok" | "error"; texto: string } | null>(null);
  const cargar = useCallback(() => api<NovedadSpeed[]>(`/speed/periodos/${periodoId}/novedades`).then(setFilas).catch((e) => setMsg({ tipo: "error", texto: mensajeError(e) })), [periodoId]);
  useEffect(() => { cargar(); }, [cargar]);
  if (!filas) return <p className="text-sm text-slate-500">Cargando…</p>;

  const tiene = (n: NovedadSpeed) => n.dias_programados !== null || n.ausencias || n.licencias || n.suspensiones || n.incapacidad || n.observacion;
  const visibles = filas.map((f) => cambiadas[f.empleado_id] ?? f)
    .filter((f) => (!soloCon || tiene(f)) && (!buscar || `${f.cedula} ${f.nombre}`.toLowerCase().includes(buscar.toLowerCase())));
  const cambiar = (n: NovedadSpeed, x: Partial<NovedadSpeed>) => setCambiadas({ ...cambiadas, [n.empleado_id]: { ...n, ...x } });

  async function guardar() {
    setMsg(null);
    try {
      for (const n of Object.values(cambiadas)) {
        await api(`/speed/periodos/${periodoId}/novedades/${n.empleado_id}`, { method: "PUT", json: {
          dias_programados: n.dias_programados, ausencias: n.ausencias, licencias: n.licencias, suspensiones: n.suspensiones,
          incapacidad: n.incapacidad, incapacidad_previos: n.incapacidad_previos, observacion: n.observacion } });
      }
      const total = Object.keys(cambiadas).length;
      setCambiadas({});
      await cargar();
      setMsg({ tipo: "ok", texto: `${total} ${total === 1 ? "novedad guardada" : "novedades guardadas"}.` });
      onCambio();
    } catch (e) { setMsg({ tipo: "error", texto: mensajeError(e) }); }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <input className="input w-72" placeholder="Buscar por cédula o nombre" value={buscar} onChange={(e) => setBuscar(e.target.value)} />
        <label className="flex items-center gap-2 text-sm text-slate-600"><input type="checkbox" checked={soloCon} onChange={(e) => setSoloCon(e.target.checked)} /> Solo con novedades</label>
        <div className="ml-auto flex flex-wrap gap-2">
          <a className="btn-secundario" href={`/api/speed/periodos/${periodoId}/novedades/plantilla`}><Download className="h-4 w-4" /> Plantilla</a>
          {editable && <SubirArchivo texto="Subir plantilla" onArchivo={async (f) => {
            setMsg(null);
            try {
              const r = await subirArchivo<{ cargadas: number; advertencias: string[] }>(`/speed/periodos/${periodoId}/novedades/importar`, f);
              await cargar();
              setMsg({ tipo: r.advertencias.length ? "error" : "ok", texto: `${r.cargadas} filas cargadas.${r.advertencias.length ? " " + r.advertencias.slice(0, 5).join(" · ") : ""}` });
              onCambio();
            } catch (e) { setMsg({ tipo: "error", texto: mensajeError(e) }); }
          }} />}
          {editable && <button className="btn-primario" disabled={!Object.keys(cambiadas).length} onClick={guardar}><Save className="h-4 w-4" /> Guardar ({Object.keys(cambiadas).length})</button>}
        </div>
      </div>
      <Alerta tipo="info">Mientras llega el archivo de programación, los días se digitan aquí o con la plantilla. Lo que se deje vacío toma la quincena completa
        (desde la fecha de ingreso).</Alerta>
      {msg && <Alerta tipo={msg.tipo}>{msg.texto}</Alerta>}
      <div className="tarjeta overflow-x-auto">
        <table className="tabla">
          <thead><tr><th>Colaborador</th>{CAMPOS.map(([k, t, ayuda]) => <th key={k} className="text-right" title={ayuda}>{t}</th>)}<th>Observación</th></tr></thead>
          <tbody>
            {visibles.map((n) => (
              <tr key={n.empleado_id} className={cambiadas[n.empleado_id] ? "bg-amber-50" : ""}>
                <td><p className="font-medium">{n.nombre}</p><p className="text-xs text-slate-500">{n.cedula} · {n.aplica_programacion ? "aplica programación" : "no aplica"}
                  {n.origen ? ` · ${n.origen}` : ""}</p></td>
                {CAMPOS.map(([k]) => (
                  <td key={k} className="text-right">
                    <input className="input w-20 text-right" type="number" min={0} max={k === "incapacidad_previos" ? 1000 : 15} step="0.5" disabled={!editable
                      || (k === "dias_programados" && !n.aplica_programacion)}
                      placeholder={k === "dias_programados" ? (n.aplica_programacion ? "15" : "—") : "0"}
                      value={k === "dias_programados" ? (n.dias_programados ?? "") : (n[k] || "")}
                      onChange={(e) => cambiar(n, { [k]: e.target.value === "" ? (k === "dias_programados" ? null : 0) : Number(e.target.value) })} />
                  </td>
                ))}
                <td><input className="input w-48" disabled={!editable} value={n.observacion} maxLength={300} onChange={(e) => cambiar(n, { observacion: e.target.value })} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
