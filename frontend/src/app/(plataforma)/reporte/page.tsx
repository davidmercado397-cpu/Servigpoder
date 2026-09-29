"use client";

import { Download, Eye, FileSpreadsheet, Loader2, Search, Upload, X } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { Alerta, Titulo } from "@/components/ui";
import { ApiError, mensajeError, subirArchivo } from "@/lib/api";

type Ubicacion = { codigo: string; nombre: string; ciudad: string; puestos: number; empleados: number };
type Resumen = {
  compania: string; desde: string; hasta: string; dias: number;
  ubicaciones: Ubicacion[]; ciudades: string[]; puestos: number; filas: number;
};

function fecha(iso: string) {
  return new Date(iso + "T12:00:00").toLocaleDateString("es-CO", { day: "numeric", month: "long", year: "numeric" });
}

export default function ReportePage() {
  const input = useRef<HTMLInputElement>(null);
  const [archivo, setArchivo] = useState<File | null>(null);
  const [resumen, setResumen] = useState<Resumen | null>(null);
  const [ciudades, setCiudades] = useState<string[]>([]);
  const [ubicaciones, setUbicaciones] = useState<string[]>([]);
  const [q, setQ] = useState("");
  const [leyendo, setLeyendo] = useState(false);
  const [generando, setGenerando] = useState(false);
  const [error, setError] = useState("");

  async function elegir(f: File | undefined) {
    if (!f) return;
    setError("");
    setResumen(null);
    setCiudades([]);
    setUbicaciones([]);
    setArchivo(f);
    setLeyendo(true);
    try {
      setResumen(await subirArchivo<Resumen>("/reporte/analizar", f));
    } catch (e) {
      setArchivo(null);
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

  async function generar(ver: boolean) {
    if (!archivo) return;
    setError("");
    setGenerando(true);
    // Si se abre en otra pestaña, se abre ya (antes de esperar) para que el navegador no la bloquee
    const pestana = ver ? window.open("", "_blank") : null;
    try {
      const form = new FormData();
      form.append("archivo", archivo);
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
        Cargue el Excel <b>ReporteAsignacionResumido</b> de SIESA (quincena o mes completo) y descargue el listado ordenado por ubicación y puesto,
        en hoja Carta horizontal. El archivo se procesa en memoria y no queda guardado en el servidor.
      </p>

      <div
        className="tarjeta flex cursor-pointer flex-col items-center gap-2 border-2 border-dashed border-slate-300 p-8 text-center transition hover:border-marca-600 hover:bg-marca-50/40"
        onClick={() => input.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => { e.preventDefault(); elegir(e.dataTransfer.files?.[0]); }}
      >
        <input ref={input} type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" className="hidden"
          onChange={(e) => { elegir(e.target.files?.[0]); e.target.value = ""; }} />
        {leyendo ? <Loader2 className="h-8 w-8 animate-spin text-marca-600" /> : archivo ? <FileSpreadsheet className="h-8 w-8 text-emerald-600" /> : <Upload className="h-8 w-8 text-slate-400" />}
        <p className="font-medium text-slate-800">{leyendo ? "Leyendo el archivo…" : archivo ? archivo.name : "Arrastre el Excel aquí o haga clic para elegirlo"}</p>
        <p className="text-xs text-slate-500">Solo archivos .xlsx exportados de SIESA</p>
      </div>

      {error && <Alerta>{error}</Alerta>}

      {resumen && (
        <>
          <div className="grid gap-3 sm:grid-cols-4">
            {[
              ["Periodo", `${fecha(resumen.desde)} – ${fecha(resumen.hasta)}`, `${resumen.dias} días`],
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
                <button className="btn-secundario inline-flex items-center gap-1.5" disabled={generando || !incluidas.length} onClick={() => generar(true)}>
                  <Eye className="h-4 w-4" /> Ver en el navegador
                </button>
                <button className="btn-primario inline-flex items-center gap-1.5" disabled={generando || !incluidas.length} onClick={() => generar(false)}>
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
