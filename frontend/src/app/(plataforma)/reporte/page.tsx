"use client";

import { Download, Eye, FileSpreadsheet, Loader2, Search, Upload, X } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { Alerta, Titulo } from "@/components/ui";
import { ApiError, api, mensajeError } from "@/lib/api";

type Ubicacion = { codigo: string; nombre: string; ciudad: string; puestos: number; empleados: number };
type Resumen = {
  compania: string; desde: string; hasta: string; dias: number;
  ubicaciones: Ubicacion[]; ciudades: string[]; puestos: number; filas: number;
};

function fecha(iso: string) {
  return new Date(iso + "T12:00:00").toLocaleDateString("es-CO", { day: "numeric", month: "long", year: "numeric" });
}

const MAX_ARCHIVOS = 3;
const MAX_DIAS = 35;
/** Fecha ISO + n días */
function sumar(iso: string, n: number) {
  const d = new Date(iso + "T12:00:00");
  d.setDate(d.getDate() + n);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
const diasEntre = (a: string, b: string) => Math.round((new Date(b + "T12:00:00").getTime() - new Date(a + "T12:00:00").getTime()) / 86_400_000) + 1;
const menor = (a: string, b: string) => (a < b ? a : b);

export default function ReportePage() {
  const input = useRef<HTMLInputElement>(null);
  const [archivos, setArchivos] = useState<File[]>([]);
  const [desde, setDesde] = useState("");
  const [hasta, setHasta] = useState("");
  const [resumen, setResumen] = useState<Resumen | null>(null);
  const [ciudades, setCiudades] = useState<string[]>([]);
  const [ubicaciones, setUbicaciones] = useState<string[]>([]);
  const [q, setQ] = useState("");
  const [leyendo, setLeyendo] = useState(false);
  const [generando, setGenerando] = useState(false);
  const [error, setError] = useState("");

  /** Uno o varios Excel (p. ej. octubre y noviembre para un PDF del 15 al 15) */
  async function elegir(nuevos: File[], agregar = false) {
    if (!nuevos.length) return;
    const lista = (agregar ? [...archivos, ...nuevos] : nuevos).slice(0, MAX_ARCHIVOS);
    setError("");
    setResumen(null);
    setCiudades([]);
    setUbicaciones([]);
    setArchivos(lista);
    setLeyendo(true);
    try {
      const form = new FormData();
      lista.forEach((a) => form.append("archivos", a));
      const r = await api<Resumen>("/reporte/analizar", { method: "POST", body: form });
      setResumen(r);
      setDesde(r.desde);
      setHasta(menor(r.hasta, sumar(r.desde, MAX_DIAS - 1)));
    } catch (e) {
      setArchivos([]);
      setError(mensajeError(e));
    } finally {
      setLeyendo(false);
    }
  }

  // Ubicaciones visibles según las ciudades elegidas y la búsqueda
  const visibles = useMemo(() => {
    const t = q.trim().toLowerCase();
    return (resumen?.ubicaciones ?? []).filter((u) =>
      (!ciudades.length || ciudades.includes(u.ciudad)) && (!t || `${u.codigo} ${u.nombre}`.toLowerCase().includes(t)));
  }, [resumen, ciudades, q]);

  const incluidas = (resumen?.ubicaciones ?? []).filter((u) =>
    (!ciudades.length || ciudades.includes(u.ciudad)) && (!ubicaciones.length || ubicaciones.includes(u.codigo)));
  const totalEmpleados = incluidas.reduce((s, u) => s + u.empleados, 0);
  const totalPuestos = incluidas.reduce((s, u) => s + u.puestos, 0);

  const diasRango = desde && hasta ? diasEntre(desde, hasta) : 0;
  const rangoMal = !resumen ? "" : !desde || !hasta ? "Elija el rango" : desde > hasta ? "La fecha Desde es posterior a la fecha Hasta"
    : desde < resumen.desde || hasta > resumen.hasta ? `El rango debe estar entre el ${fecha(resumen.desde)} y el ${fecha(resumen.hasta)}`
    : diasRango > MAX_DIAS ? `El PDF admite hasta ${MAX_DIAS} días (eligió ${diasRango})` : "";
  /** Atajo: n días desde la fecha Desde (sin pasarse de lo que traen los archivos) */
  const atajo = (n: number) => resumen && desde && setHasta(menor(resumen.hasta, sumar(desde, n - 1)));
  // Del 15 de un mes al 15 del siguiente, si los archivos lo cubren
  const quince = (() => {
    if (!resumen) return null;
    const d = resumen.desde.slice(8) <= "15" ? `${resumen.desde.slice(0, 8)}15` : sumar(`${resumen.desde.slice(0, 8)}01`, 31).slice(0, 8) + "15";
    const h = sumar(`${d.slice(0, 8)}01`, 31).slice(0, 8) + "15";
    return d >= resumen.desde && h <= resumen.hasta ? { d, h } : null;
  })();

  async function generar(ver: boolean) {
    if (!archivos.length || rangoMal) return;
    setError("");
    setGenerando(true);
    // Si se abre en otra pestaña, se abre ya (antes de esperar) para que el navegador no la bloquee
    const pestana = ver ? window.open("", "_blank") : null;
    try {
      const form = new FormData();
      archivos.forEach((a) => form.append("archivos", a));
      form.append("desde", desde);
      form.append("hasta", hasta);
      form.append("ciudades", ciudades.join("|"));
      form.append("ubicaciones", ubicaciones.join("|"));
      const res = await fetch("/api/reporte/pdf", { method: "POST", body: form, credentials: "same-origin", headers: { "X-Requested-With": "fetch" } });
      if (!res.ok) {
        const cuerpo = await res.json().catch(() => null);
        throw new ApiError(res.status, cuerpo?.error?.message ?? `Error ${res.status}`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const nombre = /filename="([^"]+)"/.exec(res.headers.get("content-disposition") ?? "")?.[1] ?? "programacion.pdf";
      if (pestana) {
        pestana.location.href = url;
      } else {
        const a = document.createElement("a");
        a.href = url;
        a.download = nombre;
        a.click();
      }
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (e) {
      pestana?.close();
      setError(mensajeError(e));
    } finally {
      setGenerando(false);
    }
  }

  function alternar<T>(lista: T[], valor: T, set: (v: T[]) => void) {
    set(lista.includes(valor) ? lista.filter((x) => x !== valor) : [...lista, valor]);
  }

  return (
    <div className="max-w-6xl space-y-5">
      <Titulo>Reporte de programación en PDF</Titulo>
      <p className="-mt-4 text-sm text-slate-500">
        Cargue el Excel <b>ReporteAsignacionResumido</b> de SIESA y descargue el listado ordenado por ubicación y puesto, en hoja Carta horizontal,
        para el rango que necesite: una semana, tres semanas, el mes o del 15 al 15 (para cruzar de mes, cargue los dos meses).
        Los archivos se procesan en memoria y no quedan guardados en el servidor.
      </p>

      <div
        className="tarjeta flex cursor-pointer flex-col items-center gap-2 border-2 border-dashed border-slate-300 p-8 text-center transition hover:border-marca-600 hover:bg-marca-50/40"
        onClick={() => input.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => { e.preventDefault(); elegir(Array.from(e.dataTransfer.files ?? []), archivos.length > 0); }}
      >
        <input ref={input} type="file" multiple accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" className="hidden"
          onChange={(e) => { elegir(Array.from(e.target.files ?? []), archivos.length > 0); e.target.value = ""; }} />
        {leyendo ? <Loader2 className="h-8 w-8 animate-spin text-marca-600" /> : archivos.length ? <FileSpreadsheet className="h-8 w-8 text-emerald-600" /> : <Upload className="h-8 w-8 text-slate-400" />}
        <p className="font-medium text-slate-800">{leyendo ? "Leyendo los archivos…" : archivos.length ? archivos.map((a) => a.name).join(" + ") : "Arrastre el Excel aquí o haga clic para elegirlo"}</p>
        <p className="text-xs text-slate-500">
          {archivos.length ? `Haga clic o arrastre otro mes para agregarlo (máximo ${MAX_ARCHIVOS})` : "Archivos .xlsx exportados de SIESA; puede cargar varios meses"}
        </p>
      </div>
      {archivos.length > 0 && !leyendo && (
        <button className="-mt-3 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800"
          onClick={() => { setArchivos([]); setResumen(null); setError(""); }}><X className="h-4 w-4" /> Quitar los archivos</button>
      )}

      {error && <Alerta>{error}</Alerta>}

      {resumen && (
        <>
          <div className="grid gap-3 sm:grid-cols-4">
            {[
              ["Los archivos traen", `${fecha(resumen.desde)} – ${fecha(resumen.hasta)}`, `${resumen.dias} días`],
              ["Ubicaciones", resumen.ubicaciones.length.toLocaleString("es-CO"), resumen.compania],
              ["Puestos", resumen.puestos.toLocaleString("es-CO"), ""],
              ["Filas de empleados", resumen.filas.toLocaleString("es-CO"), ""],
            ].map(([t, v, n]) => (
              <div key={t} className="tarjeta p-4">
                <p className="text-xs text-slate-500">{t}</p>
                <p className="mt-1 text-lg font-semibold text-marca-900">{v}</p>
                {n && <p className="truncate text-xs text-slate-400" title={n}>{n}</p>}
              </div>
            ))}
          </div>

          <section className="tarjeta space-y-3 p-5">
            <h2 className="font-semibold text-slate-900">Rango del PDF</h2>
            <div className="flex flex-wrap items-end gap-3">
              <div><label className="label">Desde</label>
                <input type="date" className="input" min={resumen.desde} max={resumen.hasta} value={desde} onChange={(e) => setDesde(e.target.value)} /></div>
              <div><label className="label">Hasta</label>
                <input type="date" className="input" min={resumen.desde} max={resumen.hasta} value={hasta} onChange={(e) => setHasta(e.target.value)} /></div>
              <div className="flex flex-wrap gap-2">
                {([[7, "1 semana"], [14, "2 semanas"], [21, "3 semanas"]] as const).map(([n, t]) => (
                  <button key={n} className="btn-secundario px-3 py-1.5 text-sm" onClick={() => atajo(n)}>{t}</button>
                ))}
                {quince && <button className="btn-secundario px-3 py-1.5 text-sm" onClick={() => { setDesde(quince.d); setHasta(quince.h); }}>Del 15 al 15</button>}
                {resumen.dias <= MAX_DIAS && <button className="btn-secundario px-3 py-1.5 text-sm" onClick={() => { setDesde(resumen.desde); setHasta(resumen.hasta); }}>Todo el archivo</button>}
              </div>
            </div>
            {rangoMal ? <Alerta>{rangoMal}</Alerta>
              : <p className="text-sm text-slate-600">El PDF va del <b>{fecha(desde)}</b> al <b>{fecha(hasta)}</b> ({diasRango} días).</p>}
          </section>

          <section className="tarjeta space-y-4 p-5">
            <div>
              <h2 className="font-semibold text-slate-900">Qué incluir <span className="text-sm font-normal text-slate-500">(opcional: sin filtros sale todo)</span></h2>
            </div>
            {resumen.ciudades.length > 1 && (
              <div>
                <p className="label">Ciudades</p>
                <div className="flex flex-wrap gap-2">
                  {resumen.ciudades.map((c) => (
                    <button key={c} onClick={() => alternar(ciudades, c, setCiudades)}
                      className={`rounded-full px-3 py-1 text-sm ${ciudades.includes(c) ? "bg-marca-600 text-white" : "bg-white text-slate-600 ring-1 ring-slate-300 hover:bg-slate-50"}`}>
                      {c}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <div>
              <div className="mb-2 flex flex-wrap items-center gap-3">
                <p className="label mb-0">Ubicaciones {ubicaciones.length > 0 && <span className="text-marca-700">({ubicaciones.length} elegidas)</span>}</p>
                <div className="relative">
                  <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  <input className="input w-72 pl-8" placeholder="Buscar por código o nombre…" value={q} onChange={(e) => setQ(e.target.value)} />
                </div>
                {ubicaciones.length > 0 && (
                  <button className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800" onClick={() => setUbicaciones([])}>
                    <X className="h-4 w-4" /> Quitar selección
                  </button>
                )}
              </div>
              <div className="max-h-64 overflow-auto rounded-lg border border-slate-200">
                <table className="tabla text-sm">
                  <thead className="sticky top-0"><tr><th className="w-8" /><th>Ubicación</th><th>Ciudad</th><th className="text-right">Puestos</th><th className="text-right">Empleados</th></tr></thead>
                  <tbody>
                    {visibles.map((u) => (
                      <tr key={u.codigo} className="cursor-pointer hover:bg-marca-50" onClick={() => alternar(ubicaciones, u.codigo, setUbicaciones)}>
                        <td><input type="checkbox" readOnly checked={ubicaciones.includes(u.codigo)} className="h-4 w-4" /></td>
                        <td><span className="font-mono font-semibold">{u.codigo}</span> · {u.nombre}</td>
                        <td>{u.ciudad}</td>
                        <td className="text-right tabular-nums">{u.puestos}</td>
                        <td className="text-right tabular-nums">{u.empleados}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3 border-t border-slate-200 pt-4">
              <p className="text-sm text-slate-600">
                El PDF tendrá <b>{incluidas.length.toLocaleString("es-CO")}</b> ubicaciones, <b>{totalPuestos.toLocaleString("es-CO")}</b> puestos y{" "}
                <b>{totalEmpleados.toLocaleString("es-CO")}</b> filas de empleados.
              </p>
              <div className="ml-auto flex gap-2">
                <button className="btn-secundario inline-flex items-center gap-1.5" disabled={generando || !incluidas.length || !!rangoMal} onClick={() => generar(true)}>
                  <Eye className="h-4 w-4" /> Ver en el navegador
                </button>
                <button className="btn-primario inline-flex items-center gap-1.5" disabled={generando || !incluidas.length || !!rangoMal} onClick={() => generar(false)}>
                  {generando ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />} {generando ? "Generando…" : "Descargar PDF"}
                </button>
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
