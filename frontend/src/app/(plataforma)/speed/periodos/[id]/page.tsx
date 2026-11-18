"use client";

import { AlertTriangle, ArrowLeft, Calculator, ChevronDown, ChevronRight, Download, Lock, Save, Trash2, Unlock, X } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { Alerta, Insignia, Pestanas, SubirArchivo } from "@/components/ui";
import { api, mensajeError, subirArchivo } from "@/lib/api";
import { usePermiso } from "@/lib/sesion";
import {
  CODIGOS_PROGRAMACION, nombrePeriodo, pesos, type LiquidacionSpeed, type NovedadSpeed, type PeriodoSpeed, type ProgramacionDias,
  type ResultadoProgramacion,
} from "@/lib/speed";

type Detalle = PeriodoSpeed & { liquidaciones: LiquidacionSpeed[] };
type Campo = "dias_programados" | "ausencias" | "licencias" | "suspensiones" | "desprogramados" | "permisos_remunerados" | "vacaciones"
  | "incapacidad" | "incapacidad_previos" | "turnos_tad" | "turnos_tan";
const CAMPOS: [Campo, string, string][] = [
  ["dias_programados", "Días programados", "Días con programación. Vacío = toda la quincena. Solo cuenta para quien aplica a la regla"],
  ["ausencias", "Ausencias (AUS)", "Descuentan salario, auxilio y variables"],
  ["licencias", "Lic. no rem. (PNR)", "Descuentan salario, auxilio y variables"],
  ["suspensiones", "Suspensiones (SUS)", "Descuentan salario, auxilio y variables"],
  ["desprogramados", "Renuncia / desprog.", "RUN y DESPR: descuentan salario, auxilio y variables"],
  ["permisos_remunerados", "Lic. remuneradas", "PR, CD, LUT, DDF y LYM: pagan salario, pero no auxilio ni variables"],
  ["vacaciones", "Vacaciones", "Pagan salario (aparte), pero no auxilio ni variables"],
  ["incapacidad", "Incapacidad", "2 primeros días de cada incapacidad al 100 %, desde el 3.º al 66,67 %"],
  ["incapacidad_previos", "Días previos incap.", "Los que ya llevaba la misma incapacidad antes de esta quincena"],
  ["turnos_tad", "TAD", "Turnos adicionales diurnos: se pagan aparte (valor en Parámetros)"],
  ["turnos_tan", "TAN", "Turnos adicionales nocturnos: se pagan aparte (valor en Parámetros)"],
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
  ["salario", "Salario"], ["vacaciones", "Vacaciones"], ["incapacidad", "Incapacidad"], ["auxilio_transporte", "Auxilio de transporte"], ["horas_extras", "Horas extras"],
  ["comisiones", "Comisiones"], ["ley_2466", "Ley 2466"], ["bonificaciones", "Bonificaciones"], ["rodamiento", "Rodamiento"],
  ["turnos_adicionales", "Turnos adicionales"], ["pago_adicional", "Pago adicional"],
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
            <th className="text-right">Variables</th><th className="text-right">T. adicionales</th><th className="text-right">Devengado</th><th className="text-right">Deducciones</th><th className="text-right">Neto</th></tr></thead>
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
                    <td className="text-right tabular-nums">{pesos(c.salario + (c.vacaciones ?? 0) + c.incapacidad)}</td>
                    <td className="text-right tabular-nums">{pesos(c.auxilio_transporte)}</td>
                    <td className="text-right tabular-nums">{pesos(variables)}</td>
                    <td className="text-right tabular-nums">{c.turnos_adicionales ? pesos(c.turnos_adicionales) : ""}
                      {(f.dias.turnos_tad || f.dias.turnos_tan) ? <p className="text-xs text-slate-500">{f.dias.turnos_tad ?? 0} TAD · {f.dias.turnos_tan ?? 0} TAN</p> : null}</td>
                    <td className="text-right tabular-nums">{pesos(f.devengado)}</td>
                    <td className="text-right tabular-nums">{pesos(f.deducciones)}</td>
                    <td className="text-right font-semibold tabular-nums">{pesos(f.neto)}</td>
                  </tr>
                  {abierta === f.empleado_id && (
                    <tr><td /><td colSpan={9} className="bg-slate-50">
                      <div className="grid gap-4 py-2 text-sm md:grid-cols-3">
                        <div><p className="mb-1 font-medium text-slate-700">Días</p>
                          <p className="text-slate-600">De la quincena {f.dias.contrato} · trabajados {f.dias.trabajados} · no laborados {f.dias.no_laborados}
                            {f.dias.incapacidad ? ` · incapacidad ${f.dias.incapacidad} (${f.dias.incapacidad_100} al 100 %)` : ""}
                            {f.dias.vacaciones ? ` · vacaciones ${f.dias.vacaciones}` : ""}{f.dias.remunerados ? ` · licencias remuneradas ${f.dias.remunerados}` : ""}
                            {f.dias.laborados !== undefined && f.dias.laborados !== f.dias.trabajados ? ` · laborados (auxilio) ${f.dias.laborados}` : ""}
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
  const [resultado, setResultado] = useState<ResultadoProgramacion | null>(null);
  const cargar = useCallback(() => api<NovedadSpeed[]>(`/speed/periodos/${periodoId}/novedades`).then(setFilas).catch((e) => setMsg({ tipo: "error", texto: mensajeError(e) })), [periodoId]);
  useEffect(() => { cargar(); }, [cargar]);
  if (!filas) return <p className="text-sm text-slate-500">Cargando…</p>;

  const tiene = (n: NovedadSpeed) => (n.dias_programados !== null && n.dias_programados < 15) || n.observacion || n.sin_programacion
    || CAMPOS.some(([k]) => k !== "dias_programados" && n[k]) || (n.programacion?.conflictos.length ?? 0) > 0;
  const visibles = filas.map((f) => cambiadas[f.empleado_id] ?? f)
    .filter((f) => (!soloCon || tiene(f)) && (!buscar || `${f.cedula} ${f.nombre}`.toLowerCase().includes(buscar.toLowerCase())));
  const cambiar = (n: NovedadSpeed, x: Partial<NovedadSpeed>) => setCambiadas({ ...cambiadas, [n.empleado_id]: { ...n, ...x } });

  async function guardar() {
    setMsg(null);
    try {
      for (const n of Object.values(cambiadas)) {
        await api(`/speed/periodos/${periodoId}/novedades/${n.empleado_id}`, { method: "PUT", json: {
          ...Object.fromEntries(CAMPOS.map(([k]) => [k, n[k]])), observacion: n.observacion } });
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
          {editable && <SubirArchivo texto="Subir programación" onArchivo={async (f) => {
            setMsg(null);
            setResultado(null);
            try {
              setResultado(await subirArchivo<ResultadoProgramacion>(`/speed/periodos/${periodoId}/programacion/importar`, f));
              await cargar();
              onCambio();
            } catch (e) { setMsg({ tipo: "error", texto: mensajeError(e) }); }
          }} />}
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
      <Alerta tipo="info">Suba el archivo de programación de la quincena (hojas de programación general y de la señora Sandra): se cruza por documento,
        se cuentan los códigos de cada día y el archivo se descarta. Después puede corregir a mano o con la plantilla. Quien no tiene novedad toma la quincena
        completa (desde la fecha de ingreso).</Alerta>
      {msg && <Alerta tipo={msg.tipo}>{msg.texto}</Alerta>}
      {resultado && <Resultado r={resultado} onCerrar={() => setResultado(null)} />}
      <div className="tarjeta overflow-x-auto">
        <table className="tabla">
          <thead><tr><th>Colaborador</th>{CAMPOS.map(([k, t, ayuda]) => <th key={k} className="text-right" title={ayuda}>{t}</th>)}<th>Observación</th></tr></thead>
          <tbody>
            {visibles.map((n) => (
              <tr key={n.empleado_id} className={cambiadas[n.empleado_id] ? "bg-amber-50" : ""}>
                <td><p className="font-medium">{n.nombre}</p><p className="text-xs text-slate-500">{n.cedula} · {n.aplica_programacion ? "aplica programación" : "no aplica"}
                  {n.origen ? ` · ${n.origen}` : ""}{n.sin_programacion ? ` · ${n.sin_programacion} días sin programación` : ""}</p>
                  {n.programacion && <Dias p={n.programacion} />}</td>
                {CAMPOS.map(([k]) => (
                  <td key={k} className="text-right">
                    <input className="input w-20 text-right" type="number" min={0} max={k === "incapacidad_previos" ? 1000 : k.startsWith("turnos") ? 31 : 15} step="0.5" disabled={!editable
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

/** Los códigos de cada día de la quincena, como vienen en la programación. */
function Dias({ p }: { p: ProgramacionDias }) {
  const dias = Object.keys(p.dias).map(Number).sort((a, b) => a - b);
  if (!dias.length) return null;
  const desde = dias[0] > 15 ? 16 : 1;
  const hasta = desde === 1 ? 15 : Math.max(30, dias[dias.length - 1]);
  return (
    <div className="mt-1">
      <div className="flex flex-wrap gap-0.5">
        {Array.from({ length: hasta - desde + 1 }, (_, i) => desde + i).map((d) => {
          const c = p.dias[String(d)];
          const [nombre, color] = c ? CODIGOS_PROGRAMACION[c] ?? [c, "bg-slate-100"] : ["Sin programación", "bg-white text-slate-300 ring-1 ring-slate-200"];
          return <span key={d} title={`Día ${d}: ${c ?? ""} ${nombre}`}
            className={`inline-flex h-5 min-w-[1.6rem] items-center justify-center rounded px-0.5 text-[10px] font-semibold ${color}`}>{c ?? d}</span>;
        })}
      </div>
      {p.puestos.length > 1 && <p className="mt-0.5 text-[11px] text-slate-500">Puestos: {p.puestos.join(" · ")}</p>}
      {p.conflictos.length > 0 && <p className="mt-0.5 text-[11px] text-amber-700">Dos filas con códigos distintos: {p.conflictos.join("; ")}</p>}
    </div>
  );
}

function Resultado({ r, onCerrar }: { r: ResultadoProgramacion; onCerrar: () => void }) {
  const s = r.resumen;
  return (
    <div className="tarjeta space-y-2 border-l-4 border-l-green-500 p-4 text-sm">
      <div className="flex items-start gap-2">
        <p className="flex-1"><b>{r.cargadas} personas cargadas</b> de {r.personas} en la programación ({r.hojas.join(", ")}).
          {" "}Días: {s.no_laborados} no laborados, {s.incapacidad} de incapacidad, {s.vacaciones} de vacaciones, {s.remunerados} de licencias remuneradas;
          {" "}{s.turnos_tad} TAD y {s.turnos_tan} TAN{s.sin_programacion ? `; ${s.sin_programacion} días sin programación` : ""}.
          {r.quitadas ? ` Se quitaron ${r.quitadas} novedades de una programación anterior.` : ""} Vuelva a liquidar la quincena.</p>
        <button onClick={onCerrar} title="Cerrar"><X className="h-4 w-4 text-slate-400" /></button>
      </div>
      {r.avisos.map((a, i) => <p key={i} className="text-amber-800">• {a}</p>)}
      <Lista titulo={`${r.no_encontrados.length} personas de la programación no están en el Listado (no se liquidan)`} items={r.no_encontrados.map((x) =>
        `${x.nombre} (${x.cedula || "sin documento"})${x.puestos.length ? " · " + x.puestos.join(", ") : ""}`)} alerta />
      <Lista titulo={`${r.sin_programacion.length} personas del Listado que aplican a la regla no están en la programación (se liquida la quincena completa)`}
        items={r.sin_programacion.map((x) => `${x.nombre} (${x.cedula}) · ${x.cargo}`)} alerta />
      <Lista titulo={`${r.por_nombre.length} cruzadas por el nombre (el documento no coincide o falta en la programación)`}
        items={r.por_nombre.map((x) => `${x.nombre}: ${x.cedula} en el Listado, ${x.en_archivo} en la programación`)} />
      <Lista titulo={`${r.conflictos.length} personas con códigos distintos el mismo día en dos filas (se tomó el que más afecta el pago)`}
        items={r.conflictos.map((x) => `${x.nombre} (${x.cedula}): ${x.detalle.join("; ")}`)} />
    </div>
  );
}

function Lista({ titulo, items, alerta }: { titulo: string; items: string[]; alerta?: boolean }) {
  if (!items.length) return null;
  return (
    <details>
      <summary className={`cursor-pointer ${alerta ? "text-amber-800" : "text-slate-700"}`}>{titulo}</summary>
      <ul className="mt-1 max-h-60 overflow-y-auto text-xs text-slate-600">{items.map((t, i) => <li key={i}>• {t}</li>)}</ul>
    </details>
  );
}
