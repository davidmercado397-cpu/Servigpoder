"use client";

import { ArrowLeft, CheckCircle2, Circle, Download, FileSpreadsheet, RefreshCw, Search, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Paginador, metaDe, usePaginacion, type MetaPagina } from "@/components/paginacion";
import { Alerta, Insignia, Pestanas, SubirArchivo } from "@/components/ui";
import { api, apiEnvelope, mensajeError, subirArchivo } from "@/lib/api";
import {
  ARCHIVOS, CLASE_DIA, ESTADOS, SEVERIDAD, VACACIONES, pesos, type Alerta as AlertaT, type Periodo, type PersonaDetalle, type PersonaLista,
  type PuestoSinModalidad,
} from "@/lib/nomina";
import { usePermiso } from "@/lib/sesion";

type Pestana = "archivos" | "resumen" | "alertas" | "vacaciones" | "personas" | "sin_modalidad";
const ESTADO = Object.fromEntries(ESTADOS.map(([k, t, c]) => [k, [t, c]])) as Record<string, [string, string]>;

export default function PeriodoNomina() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const puedeCargar = usePermiso("nomina.cargar");
  const [p, setP] = useState<Periodo | null>(null);
  const [pestana, setPestana] = useState<Pestana>("archivos");
  const [filtroTipo, setFiltroTipo] = useState("");
  const [persona, setPersona] = useState<{ nomina: string; cedula: string } | null>(null);
  const [error, setError] = useState("");
  const [aviso, setAviso] = useState("");
  const [ocupado, setOcupado] = useState(false);

  const leer = useCallback(() => api<Periodo>(`/nomina/periodos/${id}`).then((x) => {
    setP(x);
    return x;
  }), [id]);

  useEffect(() => {
    leer().then((x) => { if (x.calculado_en) setPestana("resumen"); }).catch((e) => setError(mensajeError(e)));
  }, [leer]);

  async function subir(tipo: string, f: File) {
    setError("");
    setAviso("");
    try {
      const r = await subirArchivo<{ periodo: Periodo; registros: number; calculado: boolean; codigos_nuevos?: number; grupos_nuevos?: number }>(
        `/nomina/periodos/${id}/archivos/${tipo}`, f);
      setP(r.periodo);
      const extra = [
        r.codigos_nuevos ? `${r.codigos_nuevos} códigos nuevos en la programación: revíselos en "Códigos que descuentan"` : "",
        r.grupos_nuevos ? `${r.grupos_nuevos} grupos de empleados nuevos: defina si se validan en "Grupos y parámetros"` : "",
      ].filter(Boolean);
      setAviso(`Archivo cargado: ${r.registros.toLocaleString("es-CO")} registros.${r.calculado ? " Validación recalculada." : ""} ${extra.join(". ")}`);
    } catch (e) {
      setError(mensajeError(e));
    }
  }

  async function recalcular() {
    setError("");
    setOcupado(true);
    try {
      setP(await api<Periodo>(`/nomina/periodos/${id}/recalcular`, { method: "POST" }));
      setAviso("Validación recalculada con los archivos y reglas actuales.");
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setOcupado(false);
    }
  }

  async function eliminar() {
    if (!window.confirm("¿Eliminar este periodo con sus archivos, alertas y revisiones? No se puede deshacer.")) return;
    try {
      await api(`/nomina/periodos/${id}`, { method: "DELETE" });
      router.push("/nomina");
    } catch (e) {
      setError(mensajeError(e));
    }
  }

  if (!p) return error ? <Alerta>{error}</Alerta> : <p className="text-slate-500">Cargando…</p>;
  const calculado = !!p.calculado_en;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Link href="/nomina" className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100" aria-label="Volver"><ArrowLeft className="h-5 w-5" /></Link>
        <div>
          <h1 className="text-2xl font-bold text-marca-900">{p.nombre}</h1>
          <p className="text-sm text-slate-500">{calculado ? `Calculado el ${new Date(p.calculado_en!).toLocaleString("es-CO")}` : "Aún sin calcular"}</p>
        </div>
        <div className="ml-auto flex flex-wrap gap-2">
          {calculado && <a className="btn-secundario inline-flex items-center gap-1.5" href={`/api/nomina/periodos/${id}/informe`}><Download className="h-4 w-4" /> Informe Excel</a>}
          {puedeCargar && calculado && (
            <button className="btn-secundario inline-flex items-center gap-1.5" disabled={ocupado} onClick={recalcular}>
              <RefreshCw className={`h-4 w-4 ${ocupado ? "animate-spin" : ""}`} /> Recalcular
            </button>
          )}
          {puedeCargar && <button onClick={eliminar} className="rounded-md px-2 py-1 text-sm text-slate-500 hover:bg-red-50 hover:text-red-700"><Trash2 className="h-4 w-4" /></button>}
        </div>
      </div>
      {error && <Alerta>{error}</Alerta>}
      {aviso && <Alerta tipo="ok">{aviso}</Alerta>}

      <Pestanas<Pestana>
        valor={pestana}
        onChange={setPestana}
        opciones={[
          ["archivos", `Archivos (${p.requeridos.filter((t) => p.archivos[t]).length}/${p.requeridos.length})`],
          ...(calculado ? [
            ["resumen", "Resumen"],
            ["alertas", `Alertas (${p.pendientes.toLocaleString("es-CO")} pendientes)`],
            ["vacaciones", `Vacaciones (${p.resumen?.vacaciones ?? 0})`],
            ["personas", "Personas"],
            ["sin_modalidad", `Puestos sin modalidad (${p.resumen?.puestos_sin_modalidad_pendientes ?? 0})`],
          ] as [Pestana, string][] : []),
        ]}
      />

      {pestana === "archivos" && <Archivos p={p} puedeCargar={puedeCargar} onSubir={subir} onCambio={setP} />}
      {pestana === "resumen" && p.resumen && (
        <Resumen p={p} onTipo={(t) => { setFiltroTipo(t); setPestana("alertas"); }} />
      )}
      {pestana === "alertas" && <Alertas key="alertas" p={p} tipoInicial={filtroTipo} onPersona={setPersona} onCambio={leer} />}
      {pestana === "vacaciones" && (
        <div className="space-y-3">
          <Alerta tipo="info">
            Personas con vacaciones en el periodo. Los días trabajados <b>antes</b> de las vacaciones se pagan en la liquidación de vacaciones, así que
            es correcto que esta nómina no los pague; los días trabajados <b>después</b> del regreso sí van en la nómina. Verifique cada caso en la
            liquidación de vacaciones y márquelo como revisado. Si la nómina les paga de más, aparece como alerta en la pestaña Alertas.
          </Alerta>
          <Alertas key="vacaciones" p={p} tipoInicial={VACACIONES} fijo onPersona={setPersona} onCambio={leer} />
        </div>
      )}
      {pestana === "personas" && <Personas id={id} onPersona={setPersona} />}
      {pestana === "sin_modalidad" && <SinModalidad id={id} onCambio={leer} />}
      {persona && <DetallePersona id={id} {...persona} onCerrar={() => setPersona(null)} />}
    </div>
  );
}

function Archivos({ p, puedeCargar, onSubir, onCambio }: { p: Periodo; puedeCargar: boolean; onSubir: (t: string, f: File) => Promise<void>; onCambio: (p: Periodo) => void }) {
  async function quitar(tipo: string) {
    if (!window.confirm("¿Quitar este archivo del periodo?")) return;
    onCambio(await api<Periodo>(`/nomina/periodos/${p.id}/archivos/${tipo}`, { method: "DELETE" }));
  }
  return (
    <div className="space-y-3">
      {p.faltan && p.faltan.length > 0 && (
        <Alerta tipo="info">Cargue todos los archivos del día para revisar la nómina. Falta: {p.faltan.join(", ")}. Al completarlos se calcula solo.</Alerta>
      )}
      {p.faltan?.length === 0 && (
        <Alerta tipo="ok">Archivos completos. Si corrige la nómina en SIESA, vuelva a cargar solo la nómina: se recalcula y verá qué se corrigió en el Resumen.</Alerta>
      )}
      <div className="grid gap-3 md:grid-cols-2">
        {ARCHIVOS.filter((a) => p.requeridos.includes(a.tipo)).map((a) => {
          const c = p.archivos[a.tipo];
          const esNomina = a.tipo === p.nomina;
          return (
            <div key={a.tipo} className={`tarjeta flex items-start gap-3 p-4 ${c ? "" : "border-dashed"} ${esNomina ? "ring-2 ring-marca-200 md:col-span-2" : ""}`}>
              {c ? <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-emerald-600" /> : <Circle className="mt-0.5 h-5 w-5 shrink-0 text-slate-300" />}
              <div className="min-w-0 flex-1">
                <p className="font-medium text-slate-900">{a.titulo} {esNomina && p.revisiones > 0 && <span className="text-xs font-normal text-marca-700">· {p.revisiones} cálculos</span>}</p>
                <p className="text-xs text-slate-500">{a.ayuda}</p>
                {c && (
                  <p className="mt-1 flex items-center gap-1 truncate text-xs text-slate-600" title={c.nombre}>
                    <FileSpreadsheet className="h-3.5 w-3.5" /> {c.nombre} · {c.registros.toLocaleString("es-CO")} registros · {new Date(c.cargado_en).toLocaleString("es-CO")}
                  </p>
                )}
              </div>
              {puedeCargar && (
                <div className="flex shrink-0 flex-col items-end gap-1">
                  <SubirArchivo texto={c ? (esNomina ? "Recargar nómina" : "Reemplazar") : "Cargar"} onArchivo={(f) => onSubir(a.tipo, f)} />
                  {c && <button className="text-xs text-slate-400 hover:text-red-600" onClick={() => quitar(a.tipo)}>Quitar</button>}
                </div>
              )}
            </div>
          );
        })}
      </div>
      <p className="text-xs text-slate-500">Los Excel se procesan en memoria y no quedan guardados; solo se conservan los datos extraídos de este periodo.</p>
    </div>
  );
}

function Resumen({ p, onTipo }: { p: Periodo; onTipo: (t: string) => void }) {
  const r = p.resumen!;
  const tipos = p.tipos ?? {};
  const grupos: Record<string, [string, Record<string, number>][]> = {};
  for (const [t, por] of Object.entries(r.por_tipo)) {
    if (t === VACACIONES) continue;
    const g = tipos[t]?.grupo ?? "Otras";
    (grupos[g] ??= []).push([t, por]);
  }
  const tile = (titulo: string, valor: number | string, nota = "") => (
    <div className="tarjeta p-4">
      <p className="text-xs text-slate-500">{titulo}</p>
      <p className="mt-1 text-2xl font-semibold text-marca-900">{typeof valor === "number" ? valor.toLocaleString("es-CO") : valor}</p>
      {nota && <p className="text-xs text-slate-400">{nota}</p>}
    </div>
  );
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {tile("Personas validadas", (r.personas.quincenal ?? 0) + (r.personas.mensual ?? 0))}
        {tile("Fuera de la revisión (los 7)", Object.values(r.excluidas).reduce((s, n) => s + n, 0))}
        {tile("Alertas", r.alertas, `${r.personas_con_alertas.toLocaleString("es-CO")} personas`)}
        {tile("Pendientes de revisar", p.pendientes)}
        {tile("Puestos sin modalidad", r.puestos_sin_modalidad_pendientes, `de ${r.puestos_sin_modalidad} por decidir`)}
        {tile("Con vacaciones (por verificar)", r.vacaciones ?? 0, "en la liquidación de vacaciones")}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        {Object.entries(grupos).map(([g, lista]) => (
          <section key={g} className="tarjeta overflow-hidden">
            <h2 className="border-b border-slate-200 bg-slate-50 px-4 py-2 text-sm font-semibold text-slate-700">{g}</h2>
            <table className="tabla text-sm">
              <thead><tr><th>Alerta</th><th className="text-right">Quincenal</th><th className="text-right">Mensual</th></tr></thead>
              <tbody>
                {lista.sort((a, b) => sumar(b[1]) - sumar(a[1])).map(([t, por]) => (
                  <tr key={t} className="cursor-pointer hover:bg-marca-50" onClick={() => onTipo(t)}>
                    <td><span className={`mr-2 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${SEVERIDAD[tipos[t]?.severidad ?? "baja"]}`}>{tipos[t]?.severidad}</span>{tipos[t]?.titulo ?? t}</td>
                    <td className="text-right tabular-nums">{por.quincenal ?? 0}</td>
                    <td className="text-right tabular-nums">{por.mensual ?? 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        ))}
      </div>
      {Object.keys(grupos).length === 0 && <Alerta tipo="ok">Sin alertas en este periodo.</Alerta>}
      {p.historial && p.historial.length > 0 && (
        <section className="tarjeta overflow-hidden">
          <h2 className="border-b border-slate-200 bg-slate-50 px-4 py-2 text-sm font-semibold text-slate-700">Revisiones (cada carga de la nómina o recálculo)</h2>
          <table className="tabla text-sm">
            <thead>
              <tr><th>#</th><th>Fecha</th><th>Motivo</th><th>Archivo de nómina</th><th className="text-right">Alertas</th>
                <th className="text-right">Corregidas</th><th className="text-right">Persisten</th><th className="text-right">Nuevas</th></tr>
            </thead>
            <tbody>
              {p.historial.map((h) => (
                <tr key={h.n}>
                  <td className="font-semibold">{h.n}</td>
                  <td className="whitespace-nowrap">{new Date(h.fecha).toLocaleString("es-CO")}</td>
                  <td>{h.motivo}</td>
                  <td className="max-w-xs truncate text-xs text-slate-500" title={h.archivo_nomina}>{h.archivo_nomina}</td>
                  <td className="text-right tabular-nums">{h.alertas}</td>
                  <td className="text-right tabular-nums">{h.n > 1 ? <b className="text-emerald-700">{h.corregidas}</b> : "—"}</td>
                  <td className="text-right tabular-nums">{h.n > 1 ? h.persisten : "—"}</td>
                  <td className="text-right tabular-nums">{h.n > 1 ? (h.nuevas ? <b className="text-red-700">{h.nuevas}</b> : 0) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="px-4 py-2 text-xs text-slate-500">Corregidas: alertas de la carga anterior que ya no aparecen. Nuevas: no estaban en la carga anterior (filtre &quot;Solo nuevas&quot; en Alertas).</p>
        </section>
      )}
    </div>
  );
}

function sumar(x: Record<string, number>) {
  return Object.values(x).reduce((s, n) => s + n, 0);
}

function Alertas({ p, tipoInicial, fijo = false, onPersona, onCambio }: {
  p: Periodo; tipoInicial: string; fijo?: boolean; onPersona: (x: { nomina: string; cedula: string }) => void; onCambio: () => void;
}) {
  const puedeRevisar = usePermiso("nomina.revisar");
  // En la bandeja principal no salen las de vacaciones (tienen su pestaña); en la de vacaciones el tipo es fijo
  const [f, setF] = useState({ tipo: tipoInicial, nomina: "", estado: "pendiente", severidad: "", q: "", solo_nuevas: "",
    excluir_tipo: fijo ? "" : VACACIONES });
  const [lista, setLista] = useState<AlertaT[]>([]);
  const [meta, setMeta] = useState<MetaPagina | null>(null);
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [comentario, setComentario] = useState("");
  const [error, setError] = useState("");
  const pag = usePaginacion([f]);

  const leer = useCallback(async () => {
    const qs = new URLSearchParams(Object.entries(f).filter(([, v]) => v));
    const r = await apiEnvelope<AlertaT[]>(`/nomina/periodos/${p.id}/alertas?${qs}&${pag.query}`);
    setLista(r.data ?? []);
    setMeta(metaDe(r));
    setSel(new Set());
  }, [p.id, f, pag.query]);

  useEffect(() => {
    const t = setTimeout(() => leer().catch((e) => setError(mensajeError(e))), 250);
    return () => clearTimeout(t);
  }, [leer]);

  async function decidir(estado: string) {
    setError("");
    const items = lista.filter((a) => sel.has(a.id)).map(({ nomina, cedula, tipo, referencia }) => ({ nomina, cedula, tipo, referencia }));
    try {
      await api(`/nomina/periodos/${p.id}/alertas/decision`, { method: "PUT", json: { items, estado, comentario } });
      setComentario("");
      await leer();
      onCambio();
    } catch (e) {
      setError(mensajeError(e));
    }
  }

  const tipos = Object.entries(p.tipos ?? {}).filter(([t]) => p.resumen?.por_tipo[t] && t !== VACACIONES);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-2">
        {!fijo && (
          <select className="input w-72" value={f.tipo} onChange={(e) => setF({ ...f, tipo: e.target.value })}>
            <option value="">Todas las alertas</option>
            {tipos.map(([t, x]) => <option key={t} value={t}>{x.grupo} · {x.titulo} ({sumar(p.resumen!.por_tipo[t])})</option>)}
          </select>
        )}
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input type="checkbox" className="h-4 w-4" checked={!!f.solo_nuevas} onChange={(e) => setF({ ...f, solo_nuevas: e.target.checked ? "true" : "" })} />
          Solo nuevas en la última carga
        </label>
        <select className="input w-44" value={f.estado} onChange={(e) => setF({ ...f, estado: e.target.value })}>
          <option value="">Todos los estados</option>
          {ESTADOS.map(([k, t]) => <option key={k} value={k}>{t}</option>)}
        </select>
        {!fijo && (
          <select className="input w-32" value={f.severidad} onChange={(e) => setF({ ...f, severidad: e.target.value })}>
            <option value="">Severidad</option><option value="alta">Alta</option><option value="media">Media</option>
          </select>
        )}
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input className="input w-56 pl-8" placeholder="Cédula, nombre o texto…" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} />
        </div>
      </div>
      {error && <Alerta>{error}</Alerta>}
      {puedeRevisar && sel.size > 0 && (
        <div className="tarjeta flex flex-wrap items-center gap-2 border-marca-200 bg-marca-50 p-3">
          <span className="text-sm font-medium text-marca-900">{sel.size} seleccionadas</span>
          <input className="input min-w-64 flex-1" placeholder="Comentario (obligatorio para justificar o marcar error)" value={comentario} onChange={(e) => setComentario(e.target.value)} />
          <button className="btn-secundario" onClick={() => decidir("revisada")}>Revisada (correcta)</button>
          <button className="btn-secundario" onClick={() => decidir("justificada")}>Justificar</button>
          <button className="btn-secundario text-red-700" onClick={() => decidir("error")}>Error a corregir</button>
          <button className="text-sm text-slate-500 hover:underline" onClick={() => decidir("pendiente")}>Volver a pendiente</button>
        </div>
      )}
      <div className="tarjeta max-h-[65vh] overflow-auto">
        <table className="tabla text-sm">
          <thead className="sticky top-0 z-10">
            <tr>
              {puedeRevisar && (
                <th className="w-8">
                  <input type="checkbox" className="h-4 w-4" checked={lista.length > 0 && sel.size === lista.length}
                    onChange={(e) => setSel(e.target.checked ? new Set(lista.map((a) => a.id)) : new Set())} />
                </th>
              )}
              <th>Persona</th><th>Alerta</th><th>Detalle</th><th className="text-right">Esperado</th><th className="text-right">Pagado</th><th>Estado</th>
            </tr>
          </thead>
          <tbody>
            {lista.map((a) => {
              const [et, ec] = ESTADO[a.estado] ?? [a.estado, ""];
              return (
                <tr key={a.id} className="align-top hover:bg-slate-50">
                  {puedeRevisar && (
                    <td><input type="checkbox" className="h-4 w-4" checked={sel.has(a.id)}
                      onChange={() => setSel((s) => { const n = new Set(s); if (n.has(a.id)) n.delete(a.id); else n.add(a.id); return n; })} /></td>
                  )}
                  <td className="whitespace-nowrap">
                    <button className="text-left font-medium text-marca-700 hover:underline" onClick={() => onPersona({ nomina: a.nomina, cedula: a.cedula })}>{a.nombre}</button>
                    <span className="block text-xs text-slate-500">{a.cedula} · {a.nomina}</span>
                  </td>
                  <td className="min-w-48">
                    <span className={`mr-1 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${SEVERIDAD[a.severidad]}`}>{a.severidad}</span>
                    {a.titulo}
                    {a.nueva && <span className="ml-1 rounded bg-red-600 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-white">nueva</span>}
                  </td>
                  <td className="max-w-md text-slate-600">{a.mensaje}{a.comentario && <span className="mt-1 block text-xs italic text-slate-500">“{a.comentario}”</span>}</td>
                  <td className="whitespace-nowrap text-right tabular-nums">{a.esperado !== null && a.referencia !== "100" ? pesos(a.esperado) : a.esperado ?? "—"}</td>
                  <td className="whitespace-nowrap text-right tabular-nums">{a.pagado !== null && a.referencia !== "100" ? pesos(a.pagado) : a.pagado ?? "—"}</td>
                  <td><Insignia color={ec}>{et}</Insignia></td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {lista.length === 0 && <p className="p-6 text-center text-sm text-slate-500">No hay alertas con estos filtros.</p>}
        <Paginador className="sticky bottom-0" meta={meta} onPagina={pag.setPagina} onTamano={pag.setTamano} />
      </div>
    </div>
  );
}

function Personas({ id, onPersona }: { id: string; onPersona: (x: { nomina: string; cedula: string }) => void }) {
  const [f, setF] = useState({ q: "", nomina: "", con_alertas: false });
  const [lista, setLista] = useState<PersonaLista[]>([]);
  const [meta, setMeta] = useState<MetaPagina | null>(null);
  const pag = usePaginacion([f]);

  useEffect(() => {
    const t = setTimeout(async () => {
      const qs = new URLSearchParams({ q: f.q, nomina: f.nomina, con_alertas: String(f.con_alertas) });
      const r = await apiEnvelope<PersonaLista[]>(`/nomina/periodos/${id}/personas?${qs}&${pag.query}`);
      setLista(r.data ?? []);
      setMeta(metaDe(r));
    }, 250);
    return () => clearTimeout(t);
  }, [id, f, pag.query]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input className="input w-64 pl-8" placeholder="Cédula o nombre…" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} />
        </div>
        <select className="input w-36" value={f.nomina} onChange={(e) => setF({ ...f, nomina: e.target.value })}>
          <option value="">Ambas nóminas</option><option value="quincenal">Quincenal</option><option value="mensual">Mensual</option>
        </select>
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input type="checkbox" className="h-4 w-4" checked={f.con_alertas} onChange={(e) => setF({ ...f, con_alertas: e.target.checked })} /> Solo con alertas
        </label>
      </div>
      <div className="tarjeta overflow-auto">
        <table className="tabla text-sm">
          <thead><tr><th>Persona</th><th>Nómina</th><th>Grupo</th><th className="text-right">Días pagables</th><th className="text-right">Días de salario</th><th className="text-right">Novedad</th><th className="text-right">Neto</th><th className="text-right">Alertas</th></tr></thead>
          <tbody>
            {lista.map((x) => (
              <tr key={`${x.nomina}-${x.cedula}`} className="cursor-pointer hover:bg-marca-50" onClick={() => onPersona({ nomina: x.nomina, cedula: x.cedula })}>
                <td><span className="font-medium">{x.nombre}</span><span className="block text-xs text-slate-500">{x.cedula}</span></td>
                <td className="capitalize">{x.nomina}</td>
                <td className="text-xs">{x.grupo}</td>
                <td className="text-right tabular-nums">{x.dias_pagables}</td>
                <td className={`text-right tabular-nums ${Math.abs(x.dias_salario - x.dias_pagables) > 0.5 ? "font-semibold text-red-700" : ""}`}>{x.dias_salario}</td>
                <td className="text-right tabular-nums">{x.novedad || "–"}</td>
                <td className="text-right tabular-nums">{pesos(x.neto)}</td>
                <td className="text-right">{x.alertas ? <Insignia color="bg-red-100 text-red-700">{x.alertas}</Insignia> : "–"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <Paginador meta={meta} onPagina={pag.setPagina} onTamano={pag.setTamano} />
      </div>
    </div>
  );
}

const MOTIVO: Record<string, string> = {
  sin_modalidad: "Sin modalidad en el puesto ni en la ubicación",
  no_esta_en_maestro: "Está en la programación pero no en el maestro de ubicaciones",
  modalidad_desconocida: "Su modalidad no existe en el maestro de modalidades",
};

function SinModalidad({ id, onCambio }: { id: string; onCambio: () => void }) {
  const puedeRevisar = usePermiso("nomina.revisar");
  const [lista, setLista] = useState<PuestoSinModalidad[]>([]);
  const [soloPendientes, setSoloPendientes] = useState(true);
  const [error, setError] = useState("");

  const leer = useCallback(() => api<PuestoSinModalidad[]>(`/nomina/periodos/${id}/sin-modalidad`).then(setLista), [id]);
  useEffect(() => {
    leer().catch((e) => setError(mensajeError(e)));
  }, [leer]);

  async function decidir(x: PuestoSinModalidad, estado: string) {
    let comentario = "";
    if (estado === "error") {
      comentario = window.prompt(`¿Qué se debe corregir en SIESA para el puesto ${x.puesto}?`) ?? "";
      if (!comentario.trim()) return;
    }
    setError("");
    try {
      await api(`/nomina/puestos-sin-modalidad?periodo_id=${id}`, { method: "PUT", json: { ubicacion: x.ubicacion, puesto: x.puesto, estado, comentario } });
      await leer();
      onCambio();
    } catch (e) {
      setError(mensajeError(e));
    }
  }

  const visibles = lista.filter((x) => !soloPendientes || x.estado === "pendiente");
  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-600">
        Puestos sin modalidad de pago. <b>Aprobar</b> = el puesto no lleva modalidad (queda así para los meses siguientes). <b>Error</b> = se debe
        corregir en SIESA. Los días programados en estos puestos no suman valor esperado de modalidad.
      </p>
      <label className="flex items-center gap-2 text-sm text-slate-600">
        <input type="checkbox" className="h-4 w-4" checked={soloPendientes} onChange={(e) => setSoloPendientes(e.target.checked)} /> Solo pendientes
      </label>
      {error && <Alerta>{error}</Alerta>}
      <div className="tarjeta overflow-auto">
        <table className="tabla text-sm">
          <thead><tr><th>Ubicación</th><th>Puesto</th><th>Motivo</th><th className="text-right">Personas</th><th className="text-right">Días programados</th><th>Estado</th><th /></tr></thead>
          <tbody>
            {visibles.map((x) => (
              <tr key={`${x.ubicacion}-${x.puesto}`}>
                <td><span className="font-mono font-semibold">{x.ubicacion}</span> · {x.ubicacion_nombre}</td>
                <td><span className="font-mono font-semibold">{x.puesto}</span> · {x.puesto_nombre}</td>
                <td className="text-xs text-slate-600">{MOTIVO[x.motivo]}{x.modalidad_texto && ` (${x.modalidad_texto})`}</td>
                <td className="text-right tabular-nums">{x.personas}</td>
                <td className="text-right tabular-nums">{x.dias}</td>
                <td>
                  <Insignia color={x.estado === "aprobado" ? "bg-green-100 text-green-800" : x.estado === "error" ? "bg-red-100 text-red-800" : "bg-amber-100 text-amber-800"}>
                    {x.estado === "aprobado" ? "Aprobado: no lleva" : x.estado === "error" ? "Error en SIESA" : "Pendiente"}
                  </Insignia>
                  {x.comentario && <span className="block text-xs italic text-slate-500">{x.comentario}</span>}
                </td>
                <td className="whitespace-nowrap text-right">
                  {puedeRevisar && x.estado !== "aprobado" && <button className="text-sm font-medium text-emerald-700 hover:underline" onClick={() => decidir(x, "aprobado")}>Aprobar</button>}
                  {puedeRevisar && x.estado !== "error" && <button className="ml-3 text-sm text-red-700 hover:underline" onClick={() => decidir(x, "error")}>Error</button>}
                  {puedeRevisar && x.estado !== "pendiente" && <button className="ml-3 text-sm text-slate-500 hover:underline" onClick={() => decidir(x, "pendiente")}>Deshacer</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {visibles.length === 0 && <p className="p-6 text-center text-sm text-slate-500">No hay puestos pendientes.</p>}
      </div>
    </div>
  );
}

const DIA_SEMANA = ["do", "lu", "ma", "mi", "ju", "vi", "sá"];

function DetallePersona({ id, nomina, cedula, onCerrar }: { id: string; nomina: string; cedula: string; onCerrar: () => void }) {
  const [d, setD] = useState<PersonaDetalle | null>(null);
  const nombrePuesto = (puesto: string, ubicacion?: string) =>
    d?.puestos?.find((x) => x.puesto === puesto && (!ubicacion || x.ubicacion === ubicacion))?.puesto_nombre ?? "";
  const [error, setError] = useState("");
  useEffect(() => {
    api<PersonaDetalle>(`/nomina/periodos/${id}/personas/${nomina}/${cedula}`).then(setD).catch((e) => setError(mensajeError(e)));
  }, [id, nomina, cedula]);

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/40" onClick={onCerrar}>
      <aside className="h-full w-full max-w-5xl overflow-y-auto bg-white shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <header className="sticky top-0 z-10 flex items-start gap-3 border-b border-slate-200 bg-white p-5">
          <div className="min-w-0 flex-1">
            <h2 className="text-lg font-bold text-marca-900">{d?.nombre ?? cedula}</h2>
            <p className="text-sm text-slate-500">
              {cedula} · nómina {nomina}{d ? ` · ${d.grupo || "sin contrato"} · ${d.cargo}` : ""}
              {d?.contrato?.ingreso ? ` · ingreso ${d.contrato.ingreso}` : ""}
            </p>
          </div>
          <button onClick={onCerrar} className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100" aria-label="Cerrar"><X className="h-5 w-5" /></button>
        </header>
        {error && <div className="p-5"><Alerta>{error}</Alerta></div>}
        {d && (
          <div className="space-y-5 p-5">
            {d.alertas_lista.length > 0 && (
              <section className="space-y-1.5">
                {d.alertas_lista.map((a) => (
                  <div key={a.id} className={`rounded-md px-3 py-2 text-sm ${SEVERIDAD[a.severidad]}`}>
                    <b>{a.titulo}:</b> {a.mensaje} <span className="text-xs opacity-75">({ESTADO[a.estado]?.[0] ?? a.estado})</span>
                  </div>
                ))}
              </section>
            )}
            <div className="grid gap-3 sm:grid-cols-4">
              {[
                ["Días a pagar en esta nómina", d.conteo.pagables, d.conteo.antes_vacaciones ? `${d.conteo.antes_vacaciones} antes de vacaciones van en la liquidación` : "turnos + descansos (Z, L, IND)"],
                ["Días de salario pagados", d.dias_salario, "horas del concepto 100 ÷ 7"],
                ["Días de novedad", d.conteo.novedad, d.conteo.vacaciones ? `${d.conteo.vacaciones} de vacaciones` : "descuentan"],
                ["Neto", pesos(d.neto), `devengado ${pesos(d.devengado)}`],
              ].map(([t, v, n]) => (
                <div key={String(t)} className="rounded-lg bg-slate-50 p-3">
                  <p className="text-xs text-slate-500">{t}</p>
                  <p className="text-xl font-semibold text-marca-900">{v}</p>
                  <p className="text-xs text-slate-400">{n}</p>
                </div>
              ))}
            </div>

            <section>
              <h3 className="mb-2 font-semibold text-slate-900">Programación del {d.desde.slice(8)} al {d.hasta.slice(8)}</h3>
              <div className="grid grid-cols-5 gap-1.5 sm:grid-cols-8 lg:grid-cols-10">
                {Object.entries(d.dias).map(([f, x]) => {
                  const fecha = new Date(f + "T12:00:00");
                  const [t, c] = CLASE_DIA[x.clase] ?? [x.clase, ""];
                  return (
                    <div key={f} className={`rounded-md p-1.5 text-center text-[11px] leading-tight ${c}`}
                      title={`${t}${x.puesto ? ` · puesto ${x.puesto} ${nombrePuesto(x.puesto, x.ubicacion)}` : ""}${x.modalidad ? ` · modalidad ${x.modalidad}` : ""}`}>
                      <span className="block text-[10px] opacity-70">{DIA_SEMANA[fecha.getDay()]} {fecha.getDate()}</span>
                      <span className="block truncate font-semibold">{x.codigo || "—"}</span>
                      {x.puesto && <span className="block truncate text-[10px] opacity-80">{nombrePuesto(x.puesto, x.ubicacion) || x.puesto}</span>}
                    </div>
                  );
                })}
              </div>
              {d.puestos && d.puestos.length > 0 && (
                <p className="mt-2 text-xs text-slate-600">
                  Programada en: {d.puestos.map((x) => `${x.puesto} ${x.puesto_nombre} (${x.ubicacion_nombre}) × ${x.dias_periodo} días`).join(" · ")}
                </p>
              )}
            </section>

            {d.puestos && d.puestos.length > 0 && (
              <section>
                <h3 className="mb-2 font-semibold text-slate-900">Puestos donde está programada</h3>
                <table className="tabla text-sm">
                  <thead>
                    <tr><th>Puesto</th><th>Ubicación</th><th>Modalidad que aplica</th><th>Valor por día</th>
                      <th className="text-right" title="Días que se pagan en esta nómina con la modalidad de este puesto">Días a pagar</th>
                      <th className="text-right" title="Días con algún código en el periodo de la nómina">Días en el periodo</th>
                      <th className="text-right">Días en el mes</th></tr>
                  </thead>
                  <tbody>
                    {d.puestos.map((x) => (
                      <tr key={`${x.ubicacion}-${x.puesto}`} className="align-top">
                        <td><span className="font-semibold">{x.puesto_nombre || x.puesto}</span><span className="block font-mono text-xs text-slate-500">Puesto {x.puesto}</span></td>
                        <td>{x.ubicacion_nombre}<span className="block font-mono text-xs text-slate-500">Ubicación {x.ubicacion}</span></td>
                        <td>
                          {x.modalidad ? (
                            <>
                              <span className="font-medium">{x.modalidad}</span>
                              <span className="block text-xs text-slate-500">
                                {x.origen === "puesto" ? "asignada en el puesto" : "heredada de la ubicación"}{x.modalidad_texto ? ` · ${x.modalidad_texto}` : ""}
                              </span>
                            </>
                          ) : (
                            <Insignia color={x.origen === "aprobado_sin_modalidad" ? "bg-green-100 text-green-800" : "bg-amber-100 text-amber-800"}>
                              {x.origen === "aprobado_sin_modalidad" ? "Aprobado: no lleva modalidad" : x.origen === "no_esta_en_maestro" ? "No está en el maestro de ubicaciones" : "Sin modalidad"}
                            </Insignia>
                          )}
                        </td>
                        <td className="whitespace-nowrap text-xs">
                          {Object.entries(x.conceptos).map(([c, v]) => <span key={c} className="block">{c}: {pesos(v)}</span>)}
                        </td>
                        <td className="text-right tabular-nums">{x.dias_pagables}</td>
                        <td className="text-right tabular-nums">{x.dias_periodo}</td>
                        <td className="text-right tabular-nums text-slate-500">{x.dias_mes}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {d.puestos.length > 1 && <p className="mt-1 text-xs text-slate-500">Cada día se paga con la modalidad del puesto donde trabajó ese día (ver el calendario).</p>}
              </section>
            )}

            <section>
              <h3 className="mb-2 font-semibold text-slate-900">Modalidad y auxilio: esperado contra pagado</h3>
              <table className="tabla text-sm">
                <thead><tr><th>Concepto</th><th className="text-right">Esperado</th><th className="text-right">Pagado</th><th className="text-right">Diferencia</th></tr></thead>
                <tbody>
                  {d.conceptos.map((c) => (
                    <tr key={c.concepto}>
                      <td>{c.concepto} · {c.descripcion}</td>
                      <td className="text-right tabular-nums">{pesos(c.esperado)}</td>
                      <td className="text-right tabular-nums">{pesos(c.pagado)}</td>
                      <td className={`text-right tabular-nums ${Math.abs(c.pagado - c.esperado) > 1000 ? "font-semibold text-red-700" : "text-slate-400"}`}>{pesos(c.pagado - c.esperado)}</td>
                    </tr>
                  ))}
                  <tr>
                    <td>103 · Auxilio de transporte ({d.auxilio.dias_esperados} días esperados, {d.auxilio.dias_pagados} pagados)</td>
                    <td className="text-right tabular-nums">{pesos(d.auxilio.esperado)}</td>
                    <td className="text-right tabular-nums">{pesos(d.auxilio.pagado)}</td>
                    <td className={`text-right tabular-nums ${Math.abs(d.auxilio.pagado - d.auxilio.esperado) > 1000 ? "font-semibold text-red-700" : "text-slate-400"}`}>{pesos(d.auxilio.pagado - d.auxilio.esperado)}</td>
                  </tr>
                </tbody>
              </table>
            </section>

            {d.cuotas && d.cuotas.length > 0 && (
              <section>
                <h3 className="mb-2 font-semibold text-slate-900">Cuotas</h3>
                <table className="tabla text-sm">
                  <thead><tr><th>Concepto</th><th>Tipo</th><th className="text-right">Esperado</th><th className="text-right">En la nómina</th></tr></thead>
                  <tbody>
                    {d.cuotas.map((c) => (
                      <tr key={c.concepto}>
                        <td>{c.concepto} · {c.descripcion || "—"} {c.cuotas > 1 && <span className="text-xs text-slate-500">({c.cuotas} cuotas)</span>}{c.pendiente && <span className="ml-1 text-xs text-amber-700">pendiente</span>}</td>
                        <td className="text-xs">{c.devengo ? "Devengo" : "Deducción"}</td>
                        <td className="text-right tabular-nums">{pesos(c.esperado)}</td>
                        <td className={`text-right tabular-nums ${Math.abs(c.pagado - c.esperado) > 1000 ? "font-semibold text-red-700" : ""}`}>{pesos(c.pagado)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            )}
          </div>
        )}
      </aside>
    </div>
  );
}
