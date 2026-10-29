"use client";

import { Download, GitCompare, Search } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Alerta, Insignia, Pestanas, Titulo } from "@/components/ui";
import { ApiError, mensajeError, subirArchivo } from "@/lib/api";
import { MESES, pesos } from "@/lib/formato";
import type { Hallazgo } from "@/lib/liquidador";

type Valores = { ingresos: number; deducciones: number; neto: number };
type Fila = {
  documento: string; nombre: string; empleado_id?: number; estado: "cuadra" | "diferencia" | "solo_siigo" | "solo_sistema";
  hojas_siigo: string[]; nominas: { periodo_id: number; nombre: string; estado: string }[];
  siigo: Valores | null; sistema: (Record<string, number> & { devengado: number; deducciones: number; neto: number }) | null;
  diferencia: Valores; pistas: string[];
};
type Resultado = {
  resumen: { personas_siigo: number; personas_sistema: number; cuadran: number; con_diferencia: number; solo_siigo: number; solo_sistema: number;
    neto_siigo: number; neto_sistema: number; diferencia_neto: number; tolerancia: number };
  hojas_siigo: Record<string, number>; nominas_sistema: Record<string, number>; filas: Fila[]; hallazgos: Hallazgo[];
};
type Vista = Fila["estado"];

const ESTADO: Record<Vista, [string, string]> = {
  diferencia: ["Con diferencia", "bg-amber-100 text-amber-900"], solo_siigo: ["Solo en Siigo", "bg-rose-100 text-rose-800"],
  solo_sistema: ["Solo aquí", "bg-sky-100 text-sky-800"], cuadra: ["Cuadra", "bg-green-100 text-green-800"],
};
const hoy = new Date();

export default function CompararSiigo() {
  const [anio, setAnio] = useState(hoy.getFullYear());
  const [mes, setMes] = useState(hoy.getMonth() + 1);
  const [quincena, setQuincena] = useState(hoy.getDate() > 15 ? 2 : 1);
  const [tolerancia, setTolerancia] = useState("1");
  const [archivo, setArchivo] = useState<File | null>(null);
  const [res, setRes] = useState<Resultado | null>(null);
  const [vista, setVista] = useState<Vista>("diferencia");
  const [q, setQ] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {  // desde la lista de periodos llega ?anio=…&mes=…&quincena=…
    const u = new URLSearchParams(window.location.search);
    if (u.get("anio")) setAnio(Number(u.get("anio")));
    if (u.get("mes")) setMes(Number(u.get("mes")));
    if (u.get("quincena")) setQuincena(Number(u.get("quincena")));
  }, []);

  const campos = () => ({ anio: String(anio), mes: String(mes), quincena: String(quincena), tolerancia: tolerancia || "0" });

  async function comparar() {
    if (!archivo) return;
    setError("");
    setOcupado(true);
    try {
      const r = await subirArchivo<Resultado>("/liquidador/comparar-siigo", archivo, campos());
      setRes(r);
      setVista(r.resumen.con_diferencia ? "diferencia" : r.resumen.solo_siigo ? "solo_siigo" : r.resumen.solo_sistema ? "solo_sistema" : "cuadra");
    } catch (e) {
      setRes(null);
      setError(mensajeError(e));
    } finally {
      setOcupado(false);
    }
  }

  async function descargar() {
    if (!archivo) return;
    setError("");
    try {
      const form = new FormData();
      form.append("archivo", archivo);
      Object.entries({ ...campos(), formato: "excel" }).forEach(([k, v]) => form.append(k, v));
      const r = await fetch("/api/liquidador/comparar-siigo", { method: "POST", body: form, credentials: "same-origin", headers: { "X-Requested-With": "fetch" } });
      if (!r.ok) {
        const cuerpo = await r.json().catch(() => null);
        throw new ApiError(r.status, cuerpo?.error?.message ?? `Error ${r.status}`);
      }
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = /filename="([^"]+)"/.exec(r.headers.get("content-disposition") ?? "")?.[1] ?? "comparacion_siigo.xlsx";
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
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
        persona con todas las nóminas liquidadas aquí en el mismo periodo, sumando sus nóminas en cada lado. Diferencia = aquí − Siigo. El archivo no se guarda.
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
          <GitCompare className="h-4 w-4" /> {ocupado ? "Comparando…" : "Comparar"}
        </button>
        {res && <button className="btn-secundario inline-flex items-center gap-1.5" onClick={descargar}><Download className="h-4 w-4" /> Excel de la comparación</button>}
      </section>

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
                  <tr><th>Persona</th><th>Nóminas</th><th className="text-right">Ingresos Siigo / aquí</th><th className="text-right">Deducciones Siigo / aquí</th>
                    <th className="text-right">Neto Siigo / aquí</th><th className="text-right">Diferencia neto</th><th>Posibles causas</th></tr>
                </thead>
                <tbody>
                  {filas.map((f) => (
                    <tr key={f.documento} className="align-top">
                      <td className="min-w-[180px]"><span className="font-medium">{f.nombre}</span><span className="block font-mono text-xs text-slate-500">{f.documento}</span>
                        <Insignia color={`mt-1 ${ESTADO[f.estado][1]}`}>{ESTADO[f.estado][0]}</Insignia></td>
                      <td className="text-xs">
                        {f.hojas_siigo.length > 0 && <span className="block">Siigo: {f.hojas_siigo.join(", ")}</span>}
                        {f.nominas.map((n) => (
                          <Link key={n.periodo_id} className="block text-marca-700 hover:underline" href={`/liquidador/quincenas/${n.periodo_id}`}>Aquí: {n.nombre}</Link>
                        ))}
                      </td>
                      <td className="whitespace-nowrap text-right text-xs tabular-nums">{f.siigo ? pesos(f.siigo.ingresos) : "—"}<br />{f.sistema ? pesos(f.sistema.devengado) : "—"}
                        {f.siigo && f.sistema && <span className="block">{dif(f.diferencia.ingresos)}</span>}</td>
                      <td className="whitespace-nowrap text-right text-xs tabular-nums">{f.siigo ? pesos(f.siigo.deducciones) : "—"}<br />{f.sistema ? pesos(f.sistema.deducciones) : "—"}
                        {f.siigo && f.sistema && <span className="block">{dif(f.diferencia.deducciones)}</span>}</td>
                      <td className="whitespace-nowrap text-right text-xs tabular-nums">{f.siigo ? pesos(f.siigo.neto) : "—"}<br />{f.sistema ? pesos(f.sistema.neto) : "—"}</td>
                      <td className="whitespace-nowrap text-right font-medium tabular-nums">{dif(f.diferencia.neto)}</td>
                      <td className="min-w-[220px] text-xs text-slate-600">
                        {f.pistas.length ? f.pistas.map((p, i) => <span key={i} className="block">{p}</span>) : f.estado === "diferencia" ? "Revise el detalle de la persona" : ""}
                      </td>
                    </tr>
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
