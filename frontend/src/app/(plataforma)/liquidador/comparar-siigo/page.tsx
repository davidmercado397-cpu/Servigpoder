"use client";

import { ChevronDown, ChevronRight, Download, GitCompare, RefreshCw, Search, Trash2 } from "lucide-react";
import Link from "next/link";
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { NominaPersona } from "@/components/nomina-persona";
import { Alerta, Insignia, Pestanas, Titulo } from "@/components/ui";
import { ApiError, api, apiEnvelope, mensajeError, subirArchivo } from "@/lib/api";
import { MESES, pesos } from "@/lib/formato";
import type { Hallazgo, Resultado as ResultadoPersona } from "@/lib/liquidador";

type Valores = { ingresos: number; deducciones: number; neto: number };
type HojaSiigo = Valores & { hoja: string };
type Fila = {
  documento: string; nombre: string; empleado_id?: number; estado: "cuadra" | "diferencia" | "solo_siigo" | "solo_sistema";
  hojas_siigo: string[]; nominas: { periodo_id: number; nombre: string; estado: string }[];
  siigo: (Valores & { hojas: HojaSiigo[] }) | null; sistema: (Record<string, number> & { devengado: number; deducciones: number; neto: number }) | null;
  diferencia: Valores; pistas: string[];
};
type Resultado = {
  resumen: { personas_siigo: number; personas_sistema: number; cuadran: number; con_diferencia: number; solo_siigo: number; solo_sistema: number;
    neto_siigo: number; neto_sistema: number; diferencia_neto: number; tolerancia: number };
  hojas_siigo: Record<string, number>; nominas_sistema: Record<string, number>; filas: Fila[]; hallazgos: Hallazgo[];
  /** Reporte guardado 24 horas para volver a comparar sin subirlo */
  carga: { archivo: string; cargado_en: string; vence_en: string };
};
type Vista = Fila["estado"];

const ESTADO: Record<Vista, [string, string]> = {
  diferencia: ["Con diferencia", "bg-amber-100 text-amber-900"], solo_siigo: ["Solo en Siigo", "bg-rose-100 text-rose-800"],
  solo_sistema: ["Solo aquí", "bg-sky-100 text-sky-800"], cuadra: ["Cuadra", "bg-green-100 text-green-800"],
};
const hoy = new Date();

/** Detalle de una persona: lo de Siigo (totales por hoja) frente a la liquidación de aquí, concepto por concepto. */
function DetallePersona({ f, tolerancia }: { f: Fila; tolerancia: number }) {
  const [nominas, setNominas] = useState<{ nombre: string; periodo_id: number; r: ResultadoPersona | null }[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!f.empleado_id) return;
    Promise.all(f.nominas.map(async (n) => ({
      nombre: n.nombre, periodo_id: n.periodo_id,
      r: (await api<{ empleado: ResultadoPersona }>(`/liquidador/periodos/${n.periodo_id}/empleados/${f.empleado_id}`)).empleado,
    }))).then(setNominas).catch((e) => setError(mensajeError(e)));
  }, [f]);

  const color = (v: number) => (Math.abs(v) <= tolerancia ? "text-slate-500" : v > 0 ? "text-sky-700" : "text-red-700");
  const filas: [string, number | undefined, number | undefined, number][] = [
    ["Ingresos (devengado)", f.siigo?.ingresos, f.sistema?.devengado, f.diferencia.ingresos],
    ["Deducciones", f.siigo?.deducciones, f.sistema?.deducciones, f.diferencia.deducciones],
    ["Neto a pagar", f.siigo?.neto, f.sistema?.neto, f.diferencia.neto],
  ];
  return (
    <div className="space-y-4 bg-slate-50 px-4 py-4">
      {error && <Alerta>{error}</Alerta>}
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-2">
          <table className="tabla rounded-lg border border-slate-200 bg-white text-sm">
            <thead><tr><th>Concepto</th><th className="text-right">Siigo</th><th className="text-right">Aquí</th><th className="text-right">Diferencia (aquí − Siigo)</th></tr></thead>
            <tbody>
              {filas.map(([t, s, a, d]) => (
                <tr key={t} className={t === "Neto a pagar" ? "font-semibold" : ""}>
                  <td>{t}</td><td className="text-right tabular-nums">{s !== undefined ? pesos(s) : "—"}</td>
                  <td className="text-right tabular-nums">{a !== undefined ? pesos(a) : "—"}</td>
                  <td className={`text-right tabular-nums ${color(d)}`}>{d > 0 ? "+" : ""}{pesos(d)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {f.pistas.length > 0 && (
            <ul className="list-disc space-y-0.5 pl-5 text-xs text-slate-700">{f.pistas.map((p, i) => <li key={i}>{p}</li>)}</ul>
          )}
        </div>
        <div className="space-y-2">
          <p className="text-sm font-semibold text-slate-900">Siigo {f.siigo ? `(${f.siigo.hojas.length === 1 ? "1 hoja" : `${f.siigo.hojas.length} hojas`})` : ""}</p>
          {f.siigo ? (
            <table className="tabla rounded-lg border border-slate-200 bg-white text-xs">
              <thead><tr><th>Hoja</th><th className="text-right">Ingresos</th><th className="text-right">Deducciones</th><th className="text-right">Neto</th></tr></thead>
              <tbody>
                {f.siigo.hojas.map((h, i) => (
                  <tr key={i}><td>{h.hoja}</td><td className="text-right tabular-nums">{pesos(h.ingresos)}</td>
                    <td className="text-right tabular-nums">{pesos(h.deducciones)}</td><td className="text-right tabular-nums">{pesos(h.neto)}</td></tr>
                ))}
              </tbody>
            </table>
          ) : <p className="text-sm text-slate-500">No está en el archivo de Siigo.</p>}
          <p className="text-xs text-slate-500">
            El reporte de netos de Siigo solo trae ingresos, deducciones y neto. Para ver qué concepto difiere, compare con el detalle de Siigo
            («Ver detalle») la liquidación de aquí que está abajo.
          </p>
        </div>
      </div>
      {f.empleado_id ? (
        nominas.length === 0 && !error ? <p className="text-sm text-slate-500">Cargando la liquidación de aquí…</p> : (
          nominas.map((n) => n.r?.nomina ? (
            <div key={n.periodo_id} className="space-y-1">
              <Link className="text-sm font-medium text-marca-700 hover:underline" href={`/liquidador/quincenas/${n.periodo_id}`}>Abrir la nómina {n.nombre}</Link>
              <div className="bg-white"><NominaPersona n={n.r.nomina} titulo={`Aquí: nómina ${n.nombre}`} /></div>
            </div>
          ) : null)
        )
      ) : <p className="text-sm text-slate-500">No está liquidado aquí en este periodo.</p>}
    </div>
  );
}

export default function CompararSiigo() {
  const [anio, setAnio] = useState(hoy.getFullYear());
  const [mes, setMes] = useState(hoy.getMonth() + 1);
  const [quincena, setQuincena] = useState(hoy.getDate() > 15 ? 2 : 1);
  const [tolerancia, setTolerancia] = useState("1000");  // diferencias de hasta $1.000 por persona se toman como cuadradas
  const [archivo, setArchivo] = useState<File | null>(null);
  const [res, setRes] = useState<Resultado | null>(null);
  const [vista, setVista] = useState<Vista>("diferencia");
  const [q, setQ] = useState("");
  const [abierto, setAbierto] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {  // desde la lista de periodos llega ?anio=…&mes=…&quincena=…
    const u = new URLSearchParams(window.location.search);
    if (u.get("anio")) setAnio(Number(u.get("anio")));
    if (u.get("mes")) setMes(Number(u.get("mes")));
    if (u.get("quincena")) setQuincena(Number(u.get("quincena")));
  }, []);

  const consulta = `anio=${anio}&mes=${mes}&quincena=${quincena}`;

  function mostrar(x: Resultado) {
    setRes(x);
    setVista(x.resumen.con_diferencia ? "diferencia" : x.resumen.solo_siigo ? "solo_siigo" : x.resumen.solo_sistema ? "solo_sistema" : "cuadra");
  }

  // El reporte del periodo queda 24 horas: al entrar o cambiar de periodo se vuelve a comparar con la nómina actual
  const cargarGuardada = useCallback(async (tol: string) => {
    setError("");
    try {
      mostrar((await apiEnvelope<Resultado>(`/liquidador/comparar-siigo?${consulta}&tolerancia=${tol || "0"}`)).data as Resultado);
    } catch (e) {
      setRes(null);
      if (!(e instanceof ApiError && e.status === 404)) setError(mensajeError(e));
    }
  }, [consulta]);

  useEffect(() => {
    const t = setTimeout(() => { cargarGuardada(tolerancia).catch(() => {}); }, 300);
    return () => clearTimeout(t);
  }, [cargarGuardada]);  // eslint-disable-line react-hooks/exhaustive-deps

  async function comparar() {
    if (!archivo) return;
    setError("");
    setOcupado(true);
    try {
      mostrar(await subirArchivo<Resultado>("/liquidador/comparar-siigo", archivo,
        { anio: String(anio), mes: String(mes), quincena: String(quincena), tolerancia: tolerancia || "0" }));
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setOcupado(false);
    }
  }

  async function recomparar() {
    setOcupado(true);
    await cargarGuardada(tolerancia);
    setOcupado(false);
  }

  async function quitar() {
    if (!window.confirm("¿Quitar el reporte de Siigo guardado de este periodo?")) return;
    try {
      await api(`/liquidador/comparar-siigo?${consulta}`, { method: "DELETE" });
      setRes(null);
    } catch (e) {
      setError(mensajeError(e));
    }
  }

  const filas = useMemo(() => {
    const t = q.trim().toLowerCase();
    return (res?.filas ?? []).filter((f) => f.estado === vista && (!t || f.documento.includes(t) || f.nombre.toLowerCase().includes(t)));
  }, [res, vista, q]);

  const r = res?.resumen;
  const cifra = (titulo: string, valor: string, clase = "bg-slate-50") => (
    <div className={`rounded-lg px-4 py-3 ${clase}`}><p className="text-xs text-slate-500">{titulo}</p><p className="text-lg font-semibold tabular-nums">{valor}</p></div>
  );
  const dif = (v: number) => (
    <span className={Math.abs(v) <= (r?.tolerancia ?? 0) ? "text-slate-400" : v > 0 ? "text-sky-700" : "text-red-700"}>{v > 0 ? "+" : ""}{pesos(v)}</span>
  );

  return (
    <div className="space-y-5">
      <Titulo>Comparar con Siigo</Titulo>
      <p className="-mt-4 text-sm text-slate-500">
        Sube el reporte de netos de nómina de Siigo (una hoja por nómina, con CEDULA, INGRESOS, DEDUCCIONES y NETO A PAGAR). Se cruza persona por
        persona con todas las nóminas liquidadas aquí en el mismo periodo, sumando sus nóminas en cada lado. Diferencia = aquí − Siigo. El archivo no
        se guarda: sus datos quedan 24 horas para volver a comparar contra la nómina actual sin subirlo otra vez.
      </p>
      {error && <Alerta>{error}</Alerta>}
      <section className="tarjeta flex flex-wrap items-end gap-3 p-5">
        <div>
          <label className="label">Año</label>
          <input className="input w-24" type="number" min={2020} max={2100} value={anio} onChange={(e) => setAnio(Number(e.target.value))} />
        </div>
        <div>
          <label className="label">Mes</label>
          <select className="input w-36" value={mes} onChange={(e) => setMes(Number(e.target.value))}>
            {MESES.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
          </select>
        </div>
        <div>
          <label className="label">Periodo</label>
          <select className="input w-36" value={quincena} onChange={(e) => setQuincena(Number(e.target.value))}>
            <option value={1}>Quincena 1</option>
            <option value={2}>Quincena 2</option>
            <option value={0}>Mes completo</option>
          </select>
        </div>
        <div>
          <label className="label">Tolerancia por persona ($)</label>
          <input className="input w-28" type="number" min={0} value={tolerancia} onChange={(e) => setTolerancia(e.target.value)} />
        </div>
        <div>
          <label className="label">Reporte de Siigo (.xlsx)</label>
          <input className="input max-w-xs" type="file" accept=".xlsx" onChange={(e) => setArchivo(e.target.files?.[0] ?? null)} />
        </div>
        <button className="btn-primario inline-flex items-center gap-1.5" disabled={!archivo || ocupado} onClick={comparar}>
          <GitCompare className="h-4 w-4" /> {ocupado ? "Comparando…" : res ? "Subir otro reporte" : "Comparar"}
        </button>
      </section>

      {res && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg bg-marca-50 px-4 py-2 text-sm text-marca-900">
          <span>
            Reporte <b>{res.carga.archivo}</b> cargado el {new Date(res.carga.cargado_en).toLocaleString("es-CO")} · disponible hasta el{" "}
            {new Date(res.carga.vence_en).toLocaleString("es-CO")}
          </span>
          <div className="ml-auto flex flex-wrap gap-2">
            <button className="btn-secundario inline-flex items-center gap-1.5" disabled={ocupado} onClick={recomparar}
              title="Vuelve a comparar con la nómina actual y la tolerancia escrita">
              <RefreshCw className="h-4 w-4" /> Volver a comparar
            </button>
            <a className="btn-secundario inline-flex items-center gap-1.5" href={`/api/liquidador/comparar-siigo/excel?${consulta}&tolerancia=${tolerancia || "0"}`}>
              <Download className="h-4 w-4" /> Excel de la comparación
            </a>
            <button className="btn-secundario inline-flex items-center gap-1.5" onClick={quitar}><Trash2 className="h-4 w-4" /> Quitar</button>
          </div>
        </div>
      )}

      {r && res && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
            {cifra("Neto Siigo", pesos(r.neto_siigo))}
            {cifra("Neto aquí", pesos(r.neto_sistema))}
            {cifra("Diferencia (aquí − Siigo)", pesos(r.diferencia_neto), Math.abs(r.diferencia_neto) > r.tolerancia ? "bg-amber-50" : "bg-green-50")}
            {cifra("Cuadran", `${r.cuadran}`, "bg-green-50")}
            {cifra("Con diferencia", `${r.con_diferencia}`, r.con_diferencia ? "bg-amber-50" : "bg-slate-50")}
            {cifra("Solo en Siigo", `${r.solo_siigo}`, r.solo_siigo ? "bg-rose-50" : "bg-slate-50")}
            {cifra("Solo aquí", `${r.solo_sistema}`, r.solo_sistema ? "bg-sky-50" : "bg-slate-50")}
          </div>
          <details className="tarjeta p-4 text-sm">
            <summary className="cursor-pointer font-medium text-marca-700">Neto por hoja de Siigo y por nómina de aquí</summary>
            <div className="mt-3 grid gap-6 sm:grid-cols-2">
              {([["Siigo", res.hojas_siigo], ["Aquí", res.nominas_sistema]] as [string, Record<string, number>][]).map(([t, m]) => (
                <table key={t} className="tabla text-xs">
                  <thead><tr><th>{t}</th><th className="text-right">Neto</th></tr></thead>
                  <tbody>{Object.entries(m).map(([k, v]) => <tr key={k}><td>{k}</td><td className="text-right tabular-nums">{pesos(v)}</td></tr>)}</tbody>
                </table>
              ))}
            </div>
          </details>
          {res.hallazgos.length > 0 && (
            <Alerta tipo="info">{res.hallazgos.length} filas de Siigo no se pudieron comparar: {res.hallazgos.slice(0, 5).map((h) => `${h.hoja} fila ${h.fila}`).join(", ")}</Alerta>
          )}
          <div className="tarjeta overflow-hidden">
            <div className="px-4 pt-3">
              <Pestanas<Vista> opciones={(Object.keys(ESTADO) as Vista[]).map((k) => [k, `${ESTADO[k][0]} (${res.filas.filter((f) => f.estado === k).length})`])}
                valor={vista} onChange={setVista} />
            </div>
            <div className="px-4 pb-3">
              <div className="relative w-72">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input className="input pl-8" placeholder="Buscar por cédula o nombre…" value={q} onChange={(e) => setQ(e.target.value)} />
              </div>
            </div>
            <div className="overflow-auto">
              <table className="tabla text-sm">
                <thead>
                  <tr><th /><th>Persona</th><th>Nóminas</th><th className="text-right">Ingresos Siigo / aquí</th><th className="text-right">Deducciones Siigo / aquí</th>
                    <th className="text-right">Neto Siigo / aquí</th><th className="text-right">Diferencia neto</th><th>Posibles causas</th></tr>
                </thead>
                <tbody>
                  {filas.map((f) => (
                    <Fragment key={f.documento}>
                    <tr className="cursor-pointer align-top hover:bg-marca-50" onClick={() => setAbierto(abierto === f.documento ? null : f.documento)}
                      title="Ver el detalle de la persona">
                      <td className="w-6 text-slate-400">{abierto === f.documento ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}</td>
                      <td className="min-w-[180px]"><span className="font-medium">{f.nombre}</span><span className="block font-mono text-xs text-slate-500">{f.documento}</span>
                        <Insignia color={`mt-1 ${ESTADO[f.estado][1]}`}>{ESTADO[f.estado][0]}</Insignia></td>
                      <td className="text-xs">
                        {f.hojas_siigo.length > 0 && <span className="block">Siigo: {f.hojas_siigo.join(", ")}</span>}
                        {f.nominas.map((n) => (
                          <span key={n.periodo_id} className="block">Aquí: {n.nombre}</span>
                        ))}
                      </td>
                      <td className="whitespace-nowrap text-right text-xs tabular-nums">{f.siigo ? pesos(f.siigo.ingresos) : "—"}<br />{f.sistema ? pesos(f.sistema.devengado) : "—"}
                        {f.siigo && f.sistema && <span className="block">{dif(f.diferencia.ingresos)}</span>}</td>
                      <td className="whitespace-nowrap text-right text-xs tabular-nums">{f.siigo ? pesos(f.siigo.deducciones) : "—"}<br />{f.sistema ? pesos(f.sistema.deducciones) : "—"}
                        {f.siigo && f.sistema && <span className="block">{dif(f.diferencia.deducciones)}</span>}</td>
                      <td className="whitespace-nowrap text-right text-xs tabular-nums">{f.siigo ? pesos(f.siigo.neto) : "—"}<br />{f.sistema ? pesos(f.sistema.neto) : "—"}</td>
                      <td className="whitespace-nowrap text-right font-medium tabular-nums">{dif(f.diferencia.neto)}</td>
                      <td className="min-w-[220px] text-xs text-slate-600">
                        {f.pistas.length ? f.pistas.map((p, i) => <span key={i} className="block">{p}</span>) : f.estado === "diferencia" ? "Abra el detalle de la persona" : ""}
                      </td>
                    </tr>
                    {abierto === f.documento && (
                      <tr><td colSpan={8} className="p-0"><DetallePersona f={f} tolerancia={r.tolerancia} /></td></tr>
                    )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
              {filas.length === 0 && <p className="p-6 text-center text-sm text-slate-500">Nadie en este grupo.</p>}
            </div>
          </div>
        </>
      )}
      {!res && <p className="text-sm text-slate-500">Elija el periodo ({MESES[mes - 1]} {anio}), suba el archivo y pulse Comparar.</p>}
    </div>
  );
}
