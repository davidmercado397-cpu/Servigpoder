"use client";

import { FileText, Loader2, Search, Trash2, TriangleAlert, Upload } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Alerta, Titulo } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";
import { usePermiso } from "@/lib/sesion";

type Documento = { id: number; nombre: string; titulo: string; paginas: number; paginas_sin_texto: number; fragmentos: number; cargado_en: string };
type ResultadoCarga = { archivo: string; ok: boolean; duplicado?: boolean; advertencias?: string[]; error?: string; documento?: Documento };

const LOTE = 5; // PDF por petición, para no esperar demasiado en cada una

export default function BaseConocimiento() {
  const gestionar = usePermiso("siesa.gestionar");
  const [docs, setDocs] = useState<Documento[] | null>(null);
  const [q, setQ] = useState("");
  const [resultados, setResultados] = useState<ResultadoCarga[]>([]);
  const [progreso, setProgreso] = useState<{ hechos: number; total: number } | null>(null);
  const [error, setError] = useState("");
  const [arrastrando, setArrastrando] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const cargar = useCallback(() => api<Documento[]>("/siesa/documentos").then(setDocs).catch((e) => setError(mensajeError(e))), []);
  useEffect(() => {
    cargar();
  }, [cargar]);

  async function subir(lista: File[]) {
    const pdfs = lista.filter((f) => f.name.toLowerCase().endsWith(".pdf"));
    const otros = lista.filter((f) => !f.name.toLowerCase().endsWith(".pdf")).map((f) => ({ archivo: f.name, ok: false, error: "No es un PDF" }));
    if (!pdfs.length && !otros.length) return;
    setError("");
    setResultados(otros);
    setProgreso({ hechos: 0, total: pdfs.length });
    try {
      for (let i = 0; i < pdfs.length; i += LOTE) {
        const form = new FormData();
        pdfs.slice(i, i + LOTE).forEach((f) => form.append("archivos", f));
        const r = await api<ResultadoCarga[]>("/siesa/documentos", { method: "POST", body: form });
        setResultados((ant) => [...ant, ...r]);
        setProgreso({ hechos: Math.min(i + LOTE, pdfs.length), total: pdfs.length });
      }
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setProgreso(null);
      cargar();
    }
  }

  async function eliminar(d: Documento) {
    if (!window.confirm(`¿Quitar «${d.titulo}» de la base de conocimiento? El chat dejará de usarlo.`)) return;
    try {
      await api(`/siesa/documentos/${d.id}`, { method: "DELETE" });
      cargar();
    } catch (e) {
      setError(mensajeError(e));
    }
  }

  const filtrados = (docs ?? []).filter((d) => !q.trim() || `${d.titulo} ${d.nombre}`.toLowerCase().includes(q.trim().toLowerCase()));
  const paginas = (docs ?? []).reduce((s, d) => s + d.paginas, 0);
  const correctos = resultados.filter((r) => r.ok && !r.duplicado).length;

  return (
    <div className="space-y-5">
      <Titulo>Base de conocimiento</Titulo>
      <p className="-mt-4 text-sm text-slate-500">
        Instructivos de SIESA que el chat puede consultar. De cada PDF se guarda solo su texto (por página); el archivo no se almacena.
        Los PDF escaneados como imagen no tienen texto y no se pueden consultar.
      </p>
      {error && <Alerta>{error}</Alerta>}

      {gestionar && (
        <div
          onDragOver={(e) => { e.preventDefault(); setArrastrando(true); }}
          onDragLeave={() => setArrastrando(false)}
          onDrop={(e) => { e.preventDefault(); setArrastrando(false); subir(Array.from(e.dataTransfer.files)); }}
          className={`tarjeta flex flex-col items-center gap-2 border-2 border-dashed p-8 text-center transition ${arrastrando ? "border-marca-600 bg-marca-50" : "border-slate-200"}`}>
          {progreso ? (
            <>
              <Loader2 className="h-8 w-8 animate-spin text-marca-600" />
              <p className="text-sm text-slate-600">Leyendo instructivos… {progreso.hechos} de {progreso.total}</p>
            </>
          ) : (
            <>
              <Upload className="h-8 w-8 text-slate-400" />
              <p className="text-sm text-slate-600">Arrastre aquí los PDF de los instructivos (puede seleccionar muchos a la vez)</p>
              <button className="btn-primario" onClick={() => input.current?.click()}>Seleccionar PDF</button>
              <input ref={input} type="file" accept="application/pdf,.pdf" multiple hidden
                onChange={(e) => { subir(Array.from(e.target.files ?? [])); e.target.value = ""; }} />
            </>
          )}
        </div>
      )}

      {resultados.length > 0 && !progreso && (
        <div className="tarjeta space-y-1 p-4 text-sm">
          <p className="font-medium text-slate-800">{correctos} instructivos agregados de {resultados.length} archivos.</p>
          {resultados.filter((r) => !r.ok || r.duplicado || r.advertencias?.length).map((r) => (
            <p key={r.archivo} className={r.ok ? "text-amber-800" : "text-red-700"}>
              <TriangleAlert className="mr-1 inline h-4 w-4" /> <b>{r.archivo}</b>: {r.ok ? r.advertencias?.join(" · ") : r.error}
            </p>
          ))}
        </div>
      )}

      <div className="tarjeta overflow-hidden">
        <div className="flex flex-wrap items-center gap-3 px-4 py-3">
          <div className="relative w-72">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input className="input pl-8" placeholder="Buscar instructivo…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          {docs && <span className="text-sm text-slate-500">{docs.length} instructivos · {paginas.toLocaleString("es-CO")} páginas</span>}
        </div>
        <table className="tabla text-sm">
          <thead>
            <tr><th>Instructivo</th><th className="text-right">Páginas</th><th>Cargado</th>{gestionar && <th />}</tr>
          </thead>
          <tbody>
            {filtrados.map((d) => (
              <tr key={d.id}>
                <td>
                  <span className="flex items-center gap-2 font-medium"><FileText className="h-4 w-4 shrink-0 text-slate-400" /> {d.titulo}</span>
                  <span className="block pl-6 text-xs text-slate-500">{d.nombre}</span>
                  {d.paginas_sin_texto > 0 && <span className="block pl-6 text-xs text-amber-700">{d.paginas_sin_texto} páginas sin texto (imagen)</span>}
                </td>
                <td className="text-right tabular-nums">{d.paginas}</td>
                <td className="whitespace-nowrap text-slate-500">{d.cargado_en ? new Date(d.cargado_en).toLocaleDateString("es-CO") : "—"}</td>
                {gestionar && (
                  <td className="text-right">
                    <button className="rounded-md p-1.5 text-slate-500 hover:bg-red-50 hover:text-red-700" onClick={() => eliminar(d)} aria-label="Quitar"><Trash2 className="h-4 w-4" /></button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        {docs?.length === 0 && <p className="p-6 text-center text-sm text-slate-500">Aún no hay instructivos cargados.</p>}
      </div>
    </div>
  );
}
