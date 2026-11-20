"use client";

import {
  AlertTriangle, ArrowLeft, Ban, Calculator, ChevronDown, ChevronRight, Download, Lock, Save, Trash2, Unlock, UserCheck, UserMinus, UserPlus, X,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { Modal } from "@/components/costeo";
import { InputPesos } from "@/components/input-pesos";
import { CruceWorldOffice } from "@/components/speed-cruce-wo";
import { RetirarEmpleado } from "@/components/speed-retiro";
import { Paginador, usePaginacion } from "@/components/paginacion";
import { Alerta, Insignia, Pestanas, SubirArchivo } from "@/components/ui";
import { api, mensajeError, subirArchivo } from "@/lib/api";
import { usePermiso } from "@/lib/sesion";
import {
  CODIGOS_PROGRAMACION, NOMINAS, nombrePeriodo, pesos, type Nomina, type EmpleadoSpeed, type LiquidacionSpeed, type NovedadSpeed, type PendienteProgramacion,
  type PeriodoSpeed, type ProgramacionDias, type ResultadoProgramacion,
} from "@/lib/speed";

const TAMANOS = [20, 50, 100] as const;

/** Las filas de la página actual (20, 50 o 100 por página). */
function paginar<T>(lista: T[], pagina: number, tamano: number) {
  const paginas = Math.max(1, Math.ceil(lista.length / tamano));
  const actual = Math.min(pagina, paginas);
  return { filas: lista.slice((actual - 1) * tamano, actual * tamano), meta: { total: lista.length, pagina: actual, tamano, paginas } };
}

type VacacionesRetiros = {
  vacaciones: { empleado_id: number; cedula: string; nombre: string; cargo: string; puesto: string; centro: string; dias: number;
    tramos: [string, string][]; desde_antes: boolean; sigue: boolean; sin_fechas: boolean }[];
  retiros: { empleado_id: number; cedula: string; nombre: string; cargo: string; puesto: string; centro: string; primer_dia_retiro: string | null;
    ultimo_dia: string | null; dias_retiro: number; motivo: string; retirado?: string | null }[];
  incapacidad_180?: { empleado_id: number; cedula: string; nombre: string; cargo: string; puesto: string; dias: number; toda: boolean;
    tramos: [string, string][] }[];
  sin_programacion?: { empleado_id: number; cedula: string; nombre: string; cargo: string; puesto: string; motivo: string; dias: number | null;
    puestos: string[]; fecha_ingreso: string | null }[];
  programacion_cargada?: boolean;
};
const fechaCorta = (iso: string | null) => iso ? new Date(`${iso}T00:00:00`).toLocaleDateString("es-CO", { day: "2-digit", month: "short" }) : "—";

type Detalle = PeriodoSpeed & { liquidaciones: LiquidacionSpeed[]; excluidos?: number };
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
  const [pestana, setPestana] = useState<"liquidacion" | "novedades" | "vacaciones" | "cruce">("liquidacion");
  const [vr, setVr] = useState<VacacionesRetiros | null>(null);
  // Por defecto, la nómina general (sin los puestos de la señora Sandra)
  const [nomina, setNomina] = useState<Nomina>("general");
  const cargarVr = useCallback(() => api<VacacionesRetiros>(`/speed/periodos/${id}/vacaciones-retiros?grupo=${nomina}`).then(setVr).catch(() => {}), [id, nomina]);
  useEffect(() => { cargarVr(); }, [cargarVr]);
  const [msg, setMsg] = useState<{ tipo: "ok" | "error" | "info"; texto: string } | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const cargar = useCallback(() => api<Detalle>(`/speed/periodos/${id}`).then(setP).catch((e) => setMsg({ tipo: "error", texto: mensajeError(e) })), [id]);
  useEffect(() => { cargar(); }, [cargar]);

  if (!p) return msg ? <Alerta>{msg.texto}</Alerta> : <p className="text-sm text-slate-500">Cargando…</p>;
  const abierto = p.estado === "abierto";
  const liquidaciones = p.liquidaciones.filter((l) => nomina === "todos" || (l.nomina ?? "general") === nomina);
  const suma = (k: "devengado" | "deducciones" | "neto") => liquidaciones.reduce((t, l) => t + l[k], 0);

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
          <select className="input w-52" value={nomina} onChange={(e) => setNomina(e.target.value as Nomina)} title="Qué nómina ver y descargar">
            {NOMINAS.map(([v, t]) => <option key={v} value={v}>{t}{v === "sandra" && p.sandra ? ` (${p.sandra.personas})` : ""}</option>)}
          </select>
          {p.calculado_en && <a className="btn-secundario" href={`/api/speed/periodos/${id}/excel?grupo=${nomina}`}><Download className="h-4 w-4" /> Excel</a>}
          <button className="btn-secundario" title="Archivo plano de novedades por día para World Office" onClick={async () => {
            setMsg(null);
            try {
              const r = await api<{ filas: number; avisos: string[]; documento: number }>(`/speed/periodos/${id}/world-office/avisos?grupo=${nomina}`);
              if (!r.filas) { setMsg({ tipo: "error", texto: "No hay novedades con fecha para el plano: suba primero la programación de la quincena." }); return; }
              const documento = prompt("Número de documento de World Office (Encab: Documento Número, NNO NOVNO):", String(r.documento));
              if (documento === null) return;
              if (!/^\d{1,8}$/.test(documento.trim()) || Number(documento) < 1) { setMsg({ tipo: "error", texto: "El número de documento debe ser un número." }); return; }
              window.location.href = `/api/speed/periodos/${id}/world-office?grupo=${nomina}&documento=${Number(documento)}`;
              setMsg({ tipo: r.avisos.length ? "info" : "ok", texto: `Plano de World Office (documento ${Number(documento)}) con ${r.filas} filas.${r.avisos.length ? " " + r.avisos.join(" · ") : ""}` });
            } catch (e) { setMsg({ tipo: "error", texto: mensajeError(e) }); }
          }}><Download className="h-4 w-4" /> Plano World Office</button>
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
        <Dato titulo={`Personas · ${NOMINAS.find(([v]) => v === nomina)?.[1]}`} valor={String(liquidaciones.length)} />
        <Dato titulo="Total devengado" valor={pesos(suma("devengado"))} />
        <Dato titulo="Deducciones" valor={pesos(suma("deducciones"))} />
        <Dato titulo="Neto a pagar" valor={pesos(suma("neto"))} fuerte />
      </div>

      <Pestanas opciones={[["liquidacion", "Liquidación"], ["novedades", "Novedades de la quincena"],
        ["vacaciones", `Vacaciones, retiros y sin programación${vr ? ` (${vr.vacaciones.length + vr.retiros.length + (vr.incapacidad_180?.length ?? 0) + (vr.sin_programacion?.length ?? 0)})` : ""}`],
        ["cruce", "Cruce con World Office"]]} valor={pestana} onChange={(v) => { setPestana(v); cargarVr(); }} />
      {pestana !== "vacaciones" && vr && (vr.vacaciones.length + vr.retiros.length + (vr.incapacidad_180?.length ?? 0) + (vr.sin_programacion?.length ?? 0)) > 0 && (
        <Alerta tipo="info">
          <AlertTriangle className="mr-1 inline h-4 w-4 text-amber-600" />
          {vr.vacaciones.length + vr.retiros.length > 0 && <><b>{vr.vacaciones.length} con vacaciones</b> y <b>{vr.retiros.length} con retiro</b> en esta
            quincena: no se liquidan en esta nómina porque van en otra.{" "}</>}
          {(vr.incapacidad_180?.length ?? 0) > 0 && <><b>{vr.incapacidad_180!.length} con incapacidad de más de 180 días</b> (INC 180): esos días no se pagan.{" "}</>}
          {(vr.sin_programacion?.length ?? 0) > 0 && <><b>{vr.sin_programacion!.length} que dependen de la programación no están programados</b>.</>}{" "}
          <button className="font-medium text-marca-700 hover:underline" onClick={() => { setPestana("vacaciones"); cargarVr(); }}>Ver quiénes son</button>
        </Alerta>
      )}
      {pestana === "cruce" ? <CruceWorldOffice periodoId={Number(id)} nomina={nomina} editable={liquidar} />
        : pestana === "vacaciones" ? <VacacionesYRetiros periodoId={Number(id)} datos={vr} nomina={nomina} editable={liquidar}
        onCambio={async () => { await Promise.all([cargarVr(), cargar()]); setMsg({ tipo: "info", texto: "Retiro registrado: vuelva a liquidar la quincena." }); }} />
        : pestana === "liquidacion" ? <Liquidacion filas={liquidaciones} vr={vr} />
        : <Novedades periodoId={Number(id)} quincena={p.quincena} nomina={nomina} editable={liquidar && abierto} onCambio={() => setMsg({ tipo: "info", texto: "Novedades actualizadas: vuelva a liquidar la quincena." })} />}
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

function Liquidacion({ filas, vr }: { filas: LiquidacionSpeed[]; vr: VacacionesRetiros | null }) {
  const [buscar, setBuscar] = useState("");
  const [abierta, setAbierta] = useState<number | null>(null);
  const [soloAlertas, setSoloAlertas] = useState(false);
  const [filtro, setFiltro] = useState<"" | "vacaciones" | "retiro">("");
  const conVacaciones = useMemo(() => new Set(vr?.vacaciones.map((x) => x.empleado_id)), [vr]);
  const conRetiro = useMemo(() => new Set(vr?.retiros.map((x) => x.empleado_id)), [vr]);
  const visibles = useMemo(() => filas.filter((f) => (!soloAlertas || f.alertas.length)
    && (filtro !== "vacaciones" || conVacaciones.has(f.empleado_id)) && (filtro !== "retiro" || conRetiro.has(f.empleado_id))
    && (!buscar || `${f.cedula} ${f.nombre} ${f.puesto}`.toLowerCase().includes(buscar.toLowerCase()))), [filas, buscar, soloAlertas, filtro, conVacaciones, conRetiro]);
  const pag = usePaginacion([buscar, soloAlertas, filtro], TAMANOS);
  const pagina = paginar(visibles, pag.pagina, pag.tamano);
  if (!filas.length) return <p className="text-sm text-slate-500">Aún no se ha liquidado. Revise las novedades y dé <b>Liquidar</b>.</p>;
  const conAlertas = filas.filter((f) => f.alertas.length).length;
  return (
    <div className="tarjeta overflow-hidden">
      <div className="flex flex-wrap items-center gap-3 border-b border-slate-100 p-3">
        <input className="input w-72" placeholder="Buscar por cédula, nombre o puesto" value={buscar} onChange={(e) => setBuscar(e.target.value)} />
        {conAlertas > 0 && <label className="flex items-center gap-2 text-sm text-amber-800"><input type="checkbox" checked={soloAlertas} onChange={(e) => setSoloAlertas(e.target.checked)} />
          Solo con alertas ({conAlertas})</label>}
        <select className="input w-56" value={filtro} onChange={(e) => setFiltro(e.target.value as typeof filtro)}>
          <option value="">Todas las personas</option>
          <option value="vacaciones">Con vacaciones ({conVacaciones.size})</option>
          <option value="retiro">Con retiro ({conRetiro.size})</option>
        </select>
        <span className="ml-auto text-sm text-slate-500">{visibles.length} de {filas.length}</span>
      </div>
      <div className="overflow-x-auto">
        <table className="tabla">
          <thead><tr><th /><th>Colaborador</th><th className="text-right">Días</th><th className="text-right">Salario</th><th className="text-right">Aux. transp.</th>
            <th className="text-right">Variables</th><th className="text-right">T. adicionales</th><th className="text-right">Devengado</th><th className="text-right">Deducciones</th><th className="text-right">Neto</th></tr></thead>
          <tbody>
            {pagina.filas.map((f) => {
              const c = f.conceptos;
              const variables = c.horas_extras + c.comisiones + c.ley_2466 + c.bonificaciones + c.rodamiento;
              return (
                <Fragment key={f.empleado_id}>
                  <tr className="hover:bg-slate-50">
                    <td><button onClick={() => setAbierta(abierta === f.empleado_id ? null : f.empleado_id)}>
                      {abierta === f.empleado_id ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}</button></td>
                    <td><p className="font-medium">{f.nombre}{f.alertas.length > 0 && <AlertTriangle className="ml-1 inline h-4 w-4 text-amber-600" />}
                      {conVacaciones.has(f.empleado_id) && <span className="ml-1 rounded bg-violet-100 px-1.5 py-0.5 text-[10px] font-semibold text-violet-800">VACACIONES</span>}
                      {conRetiro.has(f.empleado_id) && <span className="ml-1 rounded bg-red-100 px-1.5 py-0.5 text-[10px] font-semibold text-red-800">RETIRO</span>}</p>
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
      <Paginador meta={pagina.meta} tamanos={TAMANOS} onPagina={pag.setPagina} onTamano={pag.setTamano} />
    </div>
  );
}

function Novedades({ periodoId, quincena, nomina, editable, onCambio }: {
  periodoId: number; quincena: number; nomina: Nomina; editable: boolean; onCambio: () => void;
}) {
  const [filas, setFilas] = useState<NovedadSpeed[] | null>(null);
  const [cambiadas, setCambiadas] = useState<Record<number, NovedadSpeed>>({});
  const [buscar, setBuscar] = useState("");
  const [soloCon, setSoloCon] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "ok" | "error"; texto: string } | null>(null);
  const [resultado, setResultado] = useState<ResultadoProgramacion | null>(null);
  const [verResultado, setVerResultado] = useState(true);
  const cargar = useCallback(() => api<NovedadSpeed[]>(`/speed/periodos/${periodoId}/novedades`).then(setFilas).catch((e) => setMsg({ tipo: "error", texto: mensajeError(e) })), [periodoId]);
  const cargarResultado = useCallback(() => api<ResultadoProgramacion | null>(`/speed/periodos/${periodoId}/programacion`).then(setResultado).catch(() => {}), [periodoId]);
  useEffect(() => { cargar(); cargarResultado(); }, [cargar, cargarResultado]);
  const pag = usePaginacion([buscar, soloCon], TAMANOS);
  if (!filas) return <p className="text-sm text-slate-500">Cargando…</p>;

  const tiene = (n: NovedadSpeed) => (n.dias_programados !== null && n.dias_programados < 15) || n.observacion || n.sin_programacion
    || CAMPOS.some(([k]) => k !== "dias_programados" && n[k]) || (n.programacion?.conflictos.length ?? 0) > 0;
  const visibles = filas.map((f) => cambiadas[f.empleado_id] ?? f)
    .filter((f) => (nomina === "todos" || (f.nomina ?? "general") === nomina) && (!soloCon || tiene(f)) && (!buscar || `${f.cedula} ${f.nombre}`.toLowerCase().includes(buscar.toLowerCase())));
  const pagina = paginar(visibles, pag.pagina, pag.tamano);
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
            try {
              setResultado(await subirArchivo<ResultadoProgramacion>(`/speed/periodos/${periodoId}/programacion/importar`, f));
              setVerResultado(true);
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
      {resultado && (verResultado
        ? <Resultado r={resultado} periodoId={periodoId} quincena={quincena} editable={editable} onCerrar={() => setVerResultado(false)}
          onResuelto={async () => { await Promise.all([cargar(), cargarResultado()]); onCambio(); }} />
        : <button className="text-sm text-marca-700 hover:underline" onClick={() => setVerResultado(true)}>
          Ver el resultado de la programación{resultado.no_encontrados.some((x) => x.estado === "pendiente") ? " (hay personas por revisar)" : ""}</button>)}
      <div className="tarjeta overflow-x-auto">
        <table className="tabla">
          <thead><tr><th>Colaborador</th>{CAMPOS.map(([k, t, ayuda]) => <th key={k} className="text-right" title={ayuda}>{t}</th>)}<th>Observación</th></tr></thead>
          <tbody>
            {pagina.filas.map((n) => (
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
        <Paginador meta={pagina.meta} tamanos={TAMANOS} onPagina={pag.setPagina} onTamano={pag.setTamano} />
      </div>
    </div>
  );
}

/** Los códigos de cada día de la quincena, como vienen en la programación. */
function Dias({ p, desde: inicio }: { p: ProgramacionDias; desde?: number }) {
  const dias = Object.keys(p.dias).map(Number).sort((a, b) => a - b);
  if (!dias.length) return null;
  const desde = inicio ?? (dias[0] > 15 ? 16 : 1);
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

function Resultado({ r, periodoId, quincena, editable, onCerrar, onResuelto }: {
  r: ResultadoProgramacion; periodoId: number; quincena: number; editable: boolean; onCerrar: () => void; onResuelto: () => Promise<void>;
}) {
  const s = r.resumen;
  const pendientes = r.no_encontrados.filter((x) => x.estado === "pendiente").length;
  return (
    <div className={`tarjeta space-y-2 border-l-4 p-4 text-sm ${pendientes ? "border-l-amber-500" : "border-l-green-500"}`}>
      <div className="flex items-start gap-2">
        <p className="flex-1"><b>{r.cargadas} personas cargadas</b> de {r.personas} en la programación ({r.hojas.join(", ")})
          {r.fecha ? ` · subida el ${new Date(r.fecha).toLocaleString("es-CO")}` : ""}{r.archivo ? ` · ${r.archivo}` : ""}.
          {" "}Días: {s.no_laborados} no laborados, {s.incapacidad} de incapacidad, {s.vacaciones} de vacaciones, {s.remunerados} de licencias remuneradas;
          {" "}{s.turnos_tad} TAD y {s.turnos_tan} TAN{s.sin_programacion ? `; ${s.sin_programacion} días sin programación` : ""}.
          {r.quitadas ? ` Se quitaron ${r.quitadas} novedades de una programación anterior.` : ""}</p>
        <button onClick={onCerrar} title="Ocultar"><X className="h-4 w-4 text-slate-400" /></button>
      </div>
      {r.avisos.map((a, i) => <p key={i} className="text-amber-800">• {a}</p>)}
      {r.no_encontrados.length > 0 && (
        <details open={pendientes > 0}>
          <summary className="cursor-pointer text-amber-800">{r.no_encontrados.length} personas de la programación no están en el Listado
            {pendientes ? ` (${pendientes} por revisar: mientras tanto no se liquidan)` : " (todas revisadas)"}</summary>
          <div className="mt-2 space-y-2">
            {r.no_encontrados.map((x) => <Pendiente key={x.clave} x={x} periodoId={periodoId} quincena={quincena} editable={editable} onResuelto={onResuelto} />)}
          </div>
        </details>
      )}
      <Lista titulo={`${r.sin_turnos?.length ?? 0} personas salen en la programación sin ningún turno en la quincena: no se pagan (si están incapacitadas, prográmelas con INC)`}
        items={(r.sin_turnos ?? []).map((x) => `${x.nombre} (${x.cedula})${x.puestos.length ? " · " + x.puestos.join(", ") : ""}`)} alerta />
      <Lista titulo={`${r.sin_programacion.length} personas del Listado que aplican a la regla no están en la programación (se liquida la quincena completa)`}
        items={r.sin_programacion.map((x) => `${x.nombre} (${x.cedula}) · ${x.cargo}`)} alerta />
      <Lista titulo={`${r.por_nombre.length} cruzadas por el nombre (el documento no coincide o falta en la programación)`}
        items={r.por_nombre.map((x) => `${x.nombre}${x.nombre_listado && x.nombre_listado !== x.nombre ? ` → ${x.nombre_listado} (escrito distinto en el Listado)` : ""}: `
          + `${x.cedula} en el Listado, ${x.en_archivo} en la programación`)} alerta={r.por_nombre.some((x) => x.parecido)} />
      <Lista titulo={`${r.conflictos.length} personas con códigos distintos el mismo día en dos filas (se tomó el que más afecta el pago)`}
        items={r.conflictos.map((x) => `${x.nombre} (${x.cedula}): ${x.detalle.join("; ")}`)} />
    </div>
  );
}

/** Una persona de la programación que no está en el Listado, con lo que se puede hacer con ella. */
function Pendiente({ x, periodoId, quincena, editable, onResuelto }: {
  x: PendienteProgramacion; periodoId: number; quincena: number; editable: boolean; onResuelto: () => Promise<void>;
}) {
  const [modo, setModo] = useState<"crear" | "asignar" | null>(null);
  const [error, setError] = useState("");
  const [desde, hasta] = quincena === 1 ? [1, 15] : [16, 31];
  const dias = Object.fromEntries(Object.entries(x.dias).filter(([d]) => Number(d) >= desde && Number(d) <= hasta));
  async function resolver(cuerpo: Record<string, unknown>) {
    setError("");
    try {
      await api(`/speed/periodos/${periodoId}/programacion/resolver`, { method: "POST", json: { clave: x.clave, ...cuerpo } });
      setModo(null);
      await onResuelto();
    } catch (e) { setError(mensajeError(e)); throw e; }
  }
  const estado = { creado: "Creado en el Listado", asignado: "Asignado a", descartado: "Descartado (error de la programación)", pendiente: "" }[x.estado];
  return (
    <div className={`rounded-md border p-2 ${x.estado === "pendiente" ? "border-amber-200 bg-amber-50/40" : "border-slate-200 bg-slate-50 opacity-80"}`}>
      <div className="flex flex-wrap items-start gap-2">
        <div className="min-w-[16rem] flex-1">
          <p className="font-medium">{x.nombre} <span className="font-normal text-slate-500">· {x.cedula || "sin documento"}{x.puestos.length ? ` · ${x.puestos.join(", ")}` : ""}</span></p>
          {Object.keys(dias).length > 0 ? <Dias p={{ dias, puestos: [], conflictos: [], tramos_incapacidad: [] }} desde={desde} />
            : <p className="text-xs text-slate-500">Sin turnos en esta quincena</p>}
          {x.estado === "pendiente" && (x.sugeridos?.length ?? 0) > 0 && <p className="mt-0.5 text-xs text-marca-700">
            Nombre parecido en el Listado: {x.sugeridos!.map((s) => `${s.nombre} (${s.cedula})`).join(", ")}</p>}
        </div>
        {x.estado !== "pendiente" ? (
          <Insignia color={x.estado === "descartado" ? "bg-slate-200 text-slate-700" : "bg-green-100 text-green-800"}>
            {estado}{x.empleado && x.estado === "asignado" ? ` ${x.empleado.nombre} (${x.empleado.cedula})` : ""}</Insignia>
        ) : editable && (
          <div className="flex flex-wrap gap-2">
            <button className="btn-primario" onClick={() => setModo("crear")}><UserPlus className="h-4 w-4" /> Crear en el Listado</button>
            <button className="btn-secundario" onClick={() => setModo("asignar")}><UserCheck className="h-4 w-4" /> Es un empleado del Listado</button>
            <button className="btn-secundario" onClick={async () => {
              if (confirm(`¿Descartar a ${x.nombre}? No se liquida (queda anotado como error de la programación).`)) await resolver({ accion: "descartar" }).catch(() => {});
            }}><Ban className="h-4 w-4" /> Descartar</button>
          </div>
        )}
      </div>
      {error && !modo && <p className="mt-1 text-xs text-red-700">{error}</p>}
      {modo === "crear" && <CrearEmpleado x={x} error={error} onCerrar={() => setModo(null)} onGuardar={(empleado) => resolver({ accion: "crear", empleado })} />}
      {modo === "asignar" && <AsignarEmpleado x={x} error={error} onCerrar={() => setModo(null)} onGuardar={(cedula) => resolver({ accion: "asignar", cedula })} />}
    </div>
  );
}

function CrearEmpleado({ x, error, onCerrar, onGuardar }: {
  x: PendienteProgramacion; error: string; onCerrar: () => void; onGuardar: (e: Record<string, unknown>) => Promise<void>;
}) {
  const [f, setF] = useState({
    cedula: x.cedula, nombre: x.nombre, fecha_ingreso: x.ingreso_sugerido ?? "", cargo: "Vigilante", puesto: x.puestos[0] ?? "", tipo_turno: "",
    salario: null as number | null, horas_extras: null as number | null, ley_2466: null as number | null, bonificaciones: null as number | null,
    rodamiento: null as number | null, comisiones: null as number | null, aplica_programacion: true,
  });
  const [guardando, setGuardando] = useState(false);
  useEffect(() => {
    api<{ clave: string; valor: number }[]>("/speed/parametros")
      .then((l) => setF((v) => v.salario === null ? { ...v, salario: l.find((p) => p.clave === "salario_minimo")?.valor ?? null } : v)).catch(() => {});
  }, []);
  const pesosCampo = (k: "salario" | "horas_extras" | "ley_2466" | "bonificaciones" | "rodamiento" | "comisiones", t: string) => (
    <div><label className="label">{t}</label><InputPesos vacio valor={f[k]} onValor={(v) => setF({ ...f, [k]: v })} /></div>
  );
  return (
    <Modal titulo="Crear empleado en el Listado" onCerrar={onCerrar} ancho="max-w-2xl">
      <form className="space-y-3" onSubmit={async (e) => {
        e.preventDefault();
        setGuardando(true);
        try {
          await onGuardar({ ...f, fecha_ingreso: f.fecha_ingreso || null, salario: f.salario ?? 0,
            ...Object.fromEntries((["horas_extras", "ley_2466", "bonificaciones", "rodamiento", "comisiones"] as const).map((k) => [k, f[k] ?? 0])) });
        } catch { /* el error se muestra abajo */ } finally { setGuardando(false); }
      }}>
        <p className="text-sm text-slate-600">Se crea con los valores mensuales que ponga aquí y se le cargan sus días de la programación en esta quincena.
          Agréguelo también al Excel del Listado: si no viene en la próxima importación del Listado, queda inactivo.</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <div><label className="label">Cédula</label><input className="input" required pattern="\d{3,20}" value={f.cedula}
            onChange={(e) => setF({ ...f, cedula: e.target.value.replace(/\D/g, "") })} /></div>
          <div><label className="label">Nombre</label><input className="input" required maxLength={160} value={f.nombre} onChange={(e) => setF({ ...f, nombre: e.target.value })} /></div>
          <div><label className="label">Fecha de ingreso</label><input className="input" type="date" value={f.fecha_ingreso} onChange={(e) => setF({ ...f, fecha_ingreso: e.target.value })} />
            {x.ingreso_sugerido && <p className="mt-0.5 text-xs text-slate-500">Sugerida: el primer día con turno en la programación</p>}</div>
          <div><label className="label">Cargo</label><input className="input" maxLength={120} value={f.cargo} onChange={(e) => setF({ ...f, cargo: e.target.value })} /></div>
          <div><label className="label">Puesto</label><input className="input" maxLength={120} value={f.puesto} onChange={(e) => setF({ ...f, puesto: e.target.value })} /></div>
          <div><label className="label">Tipo de turno</label><input className="input" maxLength={120} value={f.tipo_turno} placeholder="Ej. Turnos 2x2x2"
            onChange={(e) => setF({ ...f, tipo_turno: e.target.value })} /></div>
          {pesosCampo("salario", "Salario mensual")}
          {pesosCampo("horas_extras", "Horas extras (mes)")}
          {pesosCampo("ley_2466", "Ley 2466 (mes)")}
          {pesosCampo("bonificaciones", "Bonificaciones (mes)")}
          {pesosCampo("rodamiento", "Rodamiento (mes)")}
          {pesosCampo("comisiones", "Comisiones (mes)")}
        </div>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.aplica_programacion} onChange={(e) => setF({ ...f, aplica_programacion: e.target.checked })} />
          Aplica a la regla de programación (variables ÷ 30 × días con programación)</label>
        {error && <Alerta>{error}</Alerta>}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-secundario" onClick={onCerrar}>Cancelar</button>
          <button className="btn-primario" disabled={guardando || !f.salario}><UserPlus className="h-4 w-4" /> {guardando ? "Creando…" : "Crear y cargar sus días"}</button>
        </div>
      </form>
    </Modal>
  );
}

function AsignarEmpleado({ x, error, onCerrar, onGuardar }: {
  x: PendienteProgramacion; error: string; onCerrar: () => void; onGuardar: (cedula: string) => Promise<void>;
}) {
  const [empleados, setEmpleados] = useState<EmpleadoSpeed[]>([]);
  const sugerido = x.sugeridos?.[0];
  const [buscar, setBuscar] = useState(sugerido ? sugerido.cedula : x.nombre.split(" ")[0] ?? "");
  const [cedula, setCedula] = useState(sugerido?.cedula ?? "");
  const [guardando, setGuardando] = useState(false);
  useEffect(() => { api<EmpleadoSpeed[]>("/speed/empleados?inactivos=true").then(setEmpleados).catch(() => {}); }, []);
  const opciones = useMemo(() => empleados.filter((e) => !buscar || `${e.cedula} ${e.nombre}`.toLowerCase().includes(buscar.toLowerCase())).slice(0, 100),
    [empleados, buscar]);
  return (
    <Modal titulo="Asignar a un empleado del Listado" onCerrar={onCerrar} ancho="max-w-xl">
      <div className="space-y-3">
        <p className="text-sm text-slate-600">Use esta opción si en la programación la cédula o el nombre vienen mal escritos. Los días de
          <b> {x.nombre} ({x.cedula || "sin documento"})</b> se cargan a la persona que elija.</p>
        <input className="input" placeholder="Buscar por cédula o nombre" value={buscar} onChange={(e) => setBuscar(e.target.value)} />
        <select className="input" size={8} value={cedula} onChange={(e) => setCedula(e.target.value)}>
          {opciones.map((e) => <option key={e.id} value={e.cedula}>{e.nombre} · {e.cedula}{e.activo ? "" : " · inactivo"}</option>)}
        </select>
        {error && <Alerta>{error}</Alerta>}
        <div className="flex justify-end gap-2">
          <button className="btn-secundario" onClick={onCerrar}>Cancelar</button>
          <button className="btn-primario" disabled={!cedula || guardando} onClick={async () => {
            setGuardando(true);
            try { await onGuardar(cedula); } catch { /* el error se muestra arriba */ } finally { setGuardando(false); }
          }}><UserCheck className="h-4 w-4" /> Asignar</button>
        </div>
      </div>
    </Modal>
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

/** Quién tiene vacaciones y quién se retira en la quincena, con fechas, para cargarlo en World Office. */
function VacacionesYRetiros({ periodoId, datos, nomina, editable, onCambio }: {
  periodoId: number; datos: VacacionesRetiros | null; nomina: Nomina; editable: boolean; onCambio: () => Promise<void>;
}) {
  const [retirar, setRetirar] = useState<VacacionesRetiros["retiros"][number] | null>(null);
  if (!datos) return <p className="text-sm text-slate-500">Cargando…</p>;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <p className="flex-1 text-sm text-slate-600">Salen de los códigos de la programación (VAC, RUN e INC 180) y de los retiros registrados en Empleados.
          Estas personas <b>no se liquidan en esta nómina</b> ni van en su plano de novedades: van en otra nómina. Cárguelas en World Office con estas fechas.</p>
        <a className="btn-secundario" href={`/api/speed/periodos/${periodoId}/vacaciones-retiros/excel?grupo=${nomina}`}><Download className="h-4 w-4" /> Excel</a>
      </div>
      <div className="tarjeta overflow-x-auto">
        <p className="border-b border-slate-100 px-4 py-2 font-semibold text-violet-800">Vacaciones ({datos.vacaciones.length})</p>
        <table className="tabla">
          <thead><tr><th>Colaborador</th><th>Centro de costos</th><th className="text-right">Días en la quincena</th><th>Fechas</th><th>Observación</th></tr></thead>
          <tbody>
            {!datos.vacaciones.length && <tr><td colSpan={5} className="py-4 text-center text-slate-400">Nadie tiene vacaciones en esta quincena.</td></tr>}
            {datos.vacaciones.map((v) => (
              <tr key={v.empleado_id}>
                <td><p className="font-medium">{v.nombre}</p><p className="text-xs text-slate-500">{v.cedula} · {v.cargo} · {v.puesto}</p></td>
                <td>{v.centro}</td>
                <td className="text-right tabular-nums">{v.dias}</td>
                <td>{v.tramos.map(([a, b]) => a === b ? fechaCorta(a) : `${fechaCorta(a)} al ${fechaCorta(b)}`).join(", ") || "—"}</td>
                <td className="text-xs text-slate-600">{[v.desde_antes && "viene de la quincena anterior", v.sigue && "sigue en la próxima quincena",
                  v.sin_fechas && "digitadas a mano, sin fechas"].filter(Boolean).join(" · ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="tarjeta overflow-x-auto">
        <p className="border-b border-slate-100 px-4 py-2 font-semibold text-red-800">Retiros ({datos.retiros.length})</p>
        <table className="tabla">
          <thead><tr><th>Colaborador</th><th>Centro de costos</th><th>Último día con turno</th><th>Retiro desde</th><th>Motivo</th><th /></tr></thead>
          <tbody>
            {!datos.retiros.length && <tr><td colSpan={6} className="py-4 text-center text-slate-400">Nadie se retira en esta quincena.</td></tr>}
            {datos.retiros.map((r) => (
              <tr key={r.empleado_id}>
                <td><p className="font-medium">{r.nombre}</p><p className="text-xs text-slate-500">{r.cedula} · {r.cargo} · {r.puesto}</p></td>
                <td>{r.centro}</td>
                <td>{fechaCorta(r.ultimo_dia)}</td>
                <td>{fechaCorta(r.primer_dia_retiro)}</td>
                <td className="text-xs text-slate-600">{r.motivo}</td>
                <td>{r.retirado
                  ? <Insignia color="bg-slate-200 text-slate-700">Retirado el {fechaCorta(r.retirado)}</Insignia>
                  : editable && <button className="inline-flex items-center gap-1 text-sm text-red-700 hover:underline" onClick={() => setRetirar(r)}>
                    <UserMinus className="h-4 w-4" /> Retirar</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="tarjeta overflow-x-auto">
        <p className="border-b border-slate-100 px-4 py-2 font-semibold text-stone-700">Incapacidad de más de 180 días — INC 180 ({datos.incapacidad_180?.length ?? 0})</p>
        <table className="tabla">
          <thead><tr><th>Colaborador</th><th className="text-right">Días INC 180</th><th>Fechas</th><th>En esta nómina</th></tr></thead>
          <tbody>
            {!datos.incapacidad_180?.length && <tr><td colSpan={4} className="py-4 text-center text-slate-400">Nadie tiene INC 180 en esta quincena.</td></tr>}
            {datos.incapacidad_180?.map((x) => (
              <tr key={x.empleado_id}>
                <td><p className="font-medium">{x.nombre}</p><p className="text-xs text-slate-500">{x.cedula} · {x.cargo} · {x.puesto}</p></td>
                <td className="text-right tabular-nums">{x.dias}</td>
                <td>{x.tramos.map(([a, b]) => a === b ? fechaCorta(a) : `${fechaCorta(a)} al ${fechaCorta(b)}`).join(", ") || "—"}</td>
                <td className="text-xs text-slate-600">{x.toda ? "No se liquida (toda la quincena en INC 180)" : "Se liquida sin pagar los días INC 180"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="tarjeta overflow-x-auto">
        <p className="border-b border-slate-100 px-4 py-2 font-semibold text-amber-800">Dependen de la programación y no están programados ({datos.sin_programacion?.length ?? 0})</p>
        <table className="tabla">
          <thead><tr><th>Colaborador</th><th>Ingreso</th><th className="text-right">Días</th><th>Motivo</th></tr></thead>
          <tbody>
            {!datos.programacion_cargada && <tr><td colSpan={4} className="py-4 text-center text-slate-400">Suba la programación de la quincena (pestaña Novedades) para ver quién no está programado.</td></tr>}
            {datos.programacion_cargada && !datos.sin_programacion?.length && <tr><td colSpan={4} className="py-4 text-center text-slate-400">Todos los que dependen de la programación están programados.</td></tr>}
            {datos.sin_programacion?.map((s) => (
              <tr key={s.empleado_id}>
                <td><p className="font-medium">{s.nombre}</p><p className="text-xs text-slate-500">{s.cedula} · {s.cargo} · {s.puesto}{s.puestos.length ? ` · en la programación: ${s.puestos.join(", ")}` : ""}</p></td>
                <td>{fechaCorta(s.fecha_ingreso)}</td>
                <td className="text-right tabular-nums">{s.dias ?? "—"}</td>
                <td className="text-xs text-slate-600">{s.motivo}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {retirar && <RetirarEmpleado empleadoId={retirar.empleado_id} nombre={retirar.nombre} fecha={retirar.ultimo_dia}
        motivo={retirar.motivo.startsWith("Renuncia") ? "Renuncia" : ""} onCerrar={() => setRetirar(null)}
        onListo={async () => { setRetirar(null); await onCambio(); }} />}
    </div>
  );
}
