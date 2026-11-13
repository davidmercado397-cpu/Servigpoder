"use client";

import { Check, ExternalLink, FileText, Link2, Loader2, Pencil, Search, Trash2, TriangleAlert, Upload, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Alerta, Titulo } from "@/components/ui";
import { api, apiEnvelope, mensajeError } from "@/lib/api";
import { usePermiso } from "@/lib/sesion";

type Documento = {
  id: number; nombre: string; titulo: string; modulo: string; fecha: string | null; objetivo: string; enlace: string; secciones: number;
  paginas: number; paginas_sin_texto: number; fragmentos: number; cargado_en: string;
};
type Edicion = { id: number; titulo: string; modulo: string; fecha: string; objetivo: string; enlace: string };
type Pendiente = { archivo: File; enlace: string };

// Enlaces de OneDrive/SharePoint (los mismos que acepta el servidor)
const ENLACE = /^https:\/\/([a-z0-9-]+\.)*(sharepoint\.com|onedrive\.live\.com|1drv\.ms|onedrive\.com)(\/|$)/i;
const enlaceValido = (e: string) => !e.trim() || ENLACE.test(e.trim());
const AYUDA_ENLACE = "En OneDrive o SharePoint: clic derecho al archivo → Compartir → en la configuración del vínculo elija «Cualquier persona con el vínculo» y «Puede ver» → Copiar vínculo.";
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
  const [modulo, setModulo] = useState("");
  const [modulos, setModulos] = useState<string[]>([]);
  const [filtroModulo, setFiltroModulo] = useState("");
  const [edicion, setEdicion] = useState<Edicion | null>(null);
  // PDF elegidos que esperan su enlace antes de cargarse
  const [pendientes, setPendientes] = useState<Pendiente[]>([]);
  const input = useRef<HTMLInputElement>(null);

  const cargar = useCallback(() => apiEnvelope<Documento[]>("/siesa/documentos").then((r) => {
    setDocs(r.data ?? []);
    setModulos((r.meta.extra?.modulos as string[]) ?? []);
  }).catch((e) => setError(mensajeError(e))), []);
  useEffect(() => {
    cargar();
  }, [cargar]);

  // Al elegir los PDF quedan pendientes para escribirles el enlace; luego se cargan
  function elegir(lista: File[]) {
    // PDF y Word (.docx); el Word antiguo (.doc) se rechaza con la indicación de guardarlo como .docx
    const admitido = (f: File) => /\.(pdf|docx)$/i.test(f.name);
    const pdfs = lista.filter(admitido);
    const otros = lista.filter((f) => !admitido(f)).map((f) => ({ archivo: f.name, ok: false,
      error: /\.doc$/i.test(f.name) ? "Word antiguo (.doc): ábralo en Word y guárdelo como .docx" : "No es un PDF ni un Word (.docx)" }));
    setResultados(otros);
    setPendientes((p) => [...p, ...pdfs.filter((f) => !p.some((x) => x.archivo.name === f.name)).map((archivo) => ({ archivo, enlace: "" }))]);
  }

  async function subir(lista: Pendiente[]) {
    const pdfs = lista;
    if (!pdfs.length) return;
    setError("");
    setPendientes([]);
    setResultados([]);
    setProgreso({ hechos: 0, total: pdfs.length });
    try {
      for (let i = 0; i < pdfs.length; i += LOTE) {
        const form = new FormData();
        pdfs.slice(i, i + LOTE).forEach((p) => { form.append("archivos", p.archivo); form.append("enlaces", p.enlace.trim()); });
        form.append("modulo", modulo.trim());
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

  const editar = (d: Documento) => setEdicion({ id: d.id, titulo: d.titulo, modulo: d.modulo, fecha: d.fecha ?? "", objetivo: d.objetivo, enlace: d.enlace });

  async function guardarEdicion() {
    if (!edicion) return;
    try {
      await api(`/siesa/documentos/${edicion.id}`, {
        method: "PATCH", json: { titulo: edicion.titulo, modulo: edicion.modulo, fecha: edicion.fecha || null, objetivo: edicion.objetivo, enlace: edicion.enlace.trim() },
      });
      setEdicion(null);
      cargar();
    } catch (e) {
      setError(mensajeError(e));
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

  const filtrados = (docs ?? []).filter((d) => (!filtroModulo || d.modulo === filtroModulo) &&
    (!q.trim() || `${d.titulo} ${d.nombre} ${d.modulo}`.toLowerCase().includes(q.trim().toLowerCase())));
  const paginas = (docs ?? []).reduce((s, d) => s + d.paginas, 0);
  const correctos = resultados.filter((r) => r.ok && !r.duplicado).length;

  return (
    <div className="space-y-5">
      <Titulo>Base de conocimiento</Titulo>
      <p className="-mt-4 text-sm text-slate-500">
        Instructivos de SIESA que el chat puede consultar (PDF o Word .docx). De cada archivo se guarda solo su texto, dividido por secciones (del índice
        del PDF o de sus títulos), con el módulo, el instructivo, la sección y la página; el archivo no se almacena. Para que el chat
        entregue el instructivo con la respuesta, cada uno lleva el enlace de OneDrive o SharePoint donde está el archivo. En Word, las
        secciones salen de los estilos de título (Título 1, Título 2…). Los PDF escaneados como imagen no tienen texto y no se pueden consultar.
      </p>
      {error && <Alerta>{error}</Alerta>}

      {gestionar && (
        <div
          onDragOver={(e) => { e.preventDefault(); setArrastrando(true); }}
          onDragLeave={() => setArrastrando(false)}
          onDrop={(e) => { e.preventDefault(); setArrastrando(false); elegir(Array.from(e.dataTransfer.files)); }}
          className={`tarjeta flex flex-col items-center gap-2 border-2 border-dashed p-8 text-center transition ${arrastrando ? "border-marca-600 bg-marca-50" : "border-slate-200"}`}>
          {progreso ? (
            <>
              <Loader2 className="h-8 w-8 animate-spin text-marca-600" />
              <p className="text-sm text-slate-600">Leyendo instructivos… {progreso.hechos} de {progreso.total}</p>
            </>
          ) : (
            <>
              <Upload className="h-8 w-8 text-slate-400" />
              <p className="text-sm text-slate-600">Arrastre aquí los instructivos en PDF o Word (.docx); puede seleccionar muchos a la vez</p>
              <div className="flex flex-wrap items-center justify-center gap-2 text-sm">
                <label htmlFor="modulo-carga" className="text-slate-600">Módulo de SIESA de estos instructivos:</label>
                <input id="modulo-carga" className="input w-56" list="modulos-siesa" maxLength={80} placeholder="p. ej. Nómina, Contabilidad"
                  value={modulo} onChange={(e) => setModulo(e.target.value)} />
                <datalist id="modulos-siesa">{modulos.map((m) => <option key={m} value={m} />)}</datalist>
              </div>
              <button className="btn-primario" onClick={() => input.current?.click()}>Seleccionar archivos</button>
              <input ref={input} type="file" accept="application/pdf,.pdf,.docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" multiple hidden
                onChange={(e) => { elegir(Array.from(e.target.files ?? [])); e.target.value = ""; }} />
            </>
          )}
        </div>
      )}

      {pendientes.length > 0 && !progreso && (
        <div className="tarjeta space-y-3 p-4">
          <div>
            <p className="font-medium text-slate-800"><Link2 className="mr-1 inline h-4 w-4" />Enlace de cada instructivo</p>
            <p className="text-xs text-slate-500">{AYUDA_ENLACE} Sin enlace se carga igual, pero el chat no podrá entregar el instructivo.</p>
          </div>
          {pendientes.map((p, i) => (
            <div key={p.archivo.name} className="grid items-center gap-2 sm:grid-cols-[minmax(0,16rem)_1fr_auto]">
              <span className="flex min-w-0 items-center gap-2 text-sm"><FileText className="h-4 w-4 shrink-0 text-slate-400" /><span className="truncate" title={p.archivo.name}>{p.archivo.name}</span></span>
              <input className={`input ${enlaceValido(p.enlace) ? "" : "border-red-400"}`} placeholder="https://…sharepoint.com/… o https://1drv.ms/…" value={p.enlace}
                onChange={(e) => setPendientes(pendientes.map((x, j) => (j === i ? { ...x, enlace: e.target.value } : x)))} />
              <button className="rounded-md p-1.5 text-slate-400 hover:bg-slate-100" aria-label="Quitar" onClick={() => setPendientes(pendientes.filter((_, j) => j !== i))}><X className="h-4 w-4" /></button>
            </div>
          ))}
          {pendientes.some((p) => !enlaceValido(p.enlace)) && <p className="text-xs text-red-700">Los enlaces deben ser de OneDrive o SharePoint.</p>}
          <div className="flex justify-end gap-2">
            <button className="btn-secundario" onClick={() => setPendientes([])}>Cancelar</button>
            <button className="btn-primario" disabled={pendientes.some((p) => !enlaceValido(p.enlace))} onClick={() => subir(pendientes)}>
              <Upload className="h-4 w-4" /> Cargar {pendientes.length} {pendientes.length === 1 ? "instructivo" : "instructivos"}
              {pendientes.some((p) => !p.enlace.trim()) ? ` (${pendientes.filter((p) => !p.enlace.trim()).length} sin enlace)` : ""}
            </button>
          </div>
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
          {gestionar && resultados.some((r) => r.ok && !r.duplicado) && (
            <div className="space-y-1 border-t border-slate-100 pt-2">
              <p className="text-slate-600">Agregue el objetivo de cada instructivo nuevo para dar más contexto a la IA:</p>
              {resultados.filter((r) => r.ok && !r.duplicado && r.documento).map((r) => {
                const d = docs?.find((x) => x.id === r.documento!.id) ?? r.documento!;
                return (
                  <p key={r.archivo} className="flex items-center gap-2">
                    <FileText className="h-4 w-4 text-slate-400" /> {d.titulo}
                    {d.objetivo ? <span className="text-xs text-green-700">✓ con objetivo</span>
                      : <button className="text-sm font-medium text-marca-600 hover:underline" onClick={() => editar(d)}>Agregar objetivo</button>}
                  </p>
                );
              })}
            </div>
          )}
        </div>
      )}

      <div className="tarjeta overflow-hidden">
        <div className="flex flex-wrap items-center gap-3 px-4 py-3">
          <div className="relative w-72">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input className="input pl-8" placeholder="Buscar instructivo…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          {modulos.length > 0 && (
            <select className="input w-48" value={filtroModulo} onChange={(e) => setFiltroModulo(e.target.value)}>
              <option value="">Todos los módulos</option>
              {modulos.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          )}
          {docs && <span className="text-sm text-slate-500">{docs.length} instructivos · {paginas.toLocaleString("es-CO")} páginas</span>}
        </div>
        <div className="overflow-x-auto">
        <table className="tabla text-sm">
          <thead>
            <tr><th>Instructivo</th><th>Módulo</th><th>Fecha</th><th className="text-right">Secciones</th><th className="text-right">Páginas</th><th>Cargado</th>{gestionar && <th />}</tr>
          </thead>
          <tbody>
            {filtrados.map((d) => edicion?.id === d.id ? (
              <tr key={d.id} className="bg-marca-50/40">
                <td className="min-w-[22rem] space-y-2">
                  <input className="input" maxLength={255} aria-label="Título" value={edicion.titulo} onChange={(e) => setEdicion({ ...edicion, titulo: e.target.value })} />
                  <label className="label mb-0">Objetivo del instructivo</label>
                  <textarea className="input min-h-[4.5rem]" maxLength={1000} aria-label="Objetivo" autoFocus
                    placeholder="Objetivo: para qué sirve este instructivo, qué procesos cubre y a quién va dirigido"
                    value={edicion.objetivo} onChange={(e) => setEdicion({ ...edicion, objetivo: e.target.value })} />
                  <label className="label mb-0">Enlace de OneDrive o SharePoint</label>
                  <input className={`input ${enlaceValido(edicion.enlace) ? "" : "border-red-400"}`} maxLength={1000} aria-label="Enlace"
                    placeholder="https://…sharepoint.com/… o https://1drv.ms/…" value={edicion.enlace} onChange={(e) => setEdicion({ ...edicion, enlace: e.target.value })} />
                  <p className="text-xs text-slate-500">{AYUDA_ENLACE}</p>
                  {!enlaceValido(edicion.enlace) && <p className="text-xs text-red-700">El enlace debe ser de OneDrive o SharePoint (https://…).</p>}
                  {/* Los botones van debajo de los campos: así siempre se ven, aunque la tabla sea más ancha que la pantalla */}
                  <div className="flex items-center gap-2 pt-1">
                    <button className="btn-primario inline-flex items-center gap-1" disabled={!enlaceValido(edicion.enlace)} onClick={guardarEdicion}><Check className="h-4 w-4" /> Guardar</button>
                    <button className="btn-secundario inline-flex items-center gap-1" onClick={() => setEdicion(null)}><X className="h-4 w-4" /> Cancelar</button>
                  </div>
                </td>
                <td className="align-top"><input className="input w-40" list="modulos-siesa" maxLength={80} aria-label="Módulo" value={edicion.modulo} onChange={(e) => setEdicion({ ...edicion, modulo: e.target.value })} /></td>
                <td className="align-top"><input className="input w-40" type="date" aria-label="Fecha" value={edicion.fecha} onChange={(e) => setEdicion({ ...edicion, fecha: e.target.value })} /></td>
                <td colSpan={3} className="align-top text-xs text-slate-500">
                  El módulo y el título forman el encabezado de cada fragmento; el objetivo le dice a la IA para qué sirve el instructivo.
                </td>
                <td />
              </tr>
            ) : (
              <tr key={d.id}>
                <td>
                  <span className="flex items-center gap-2 font-medium"><FileText className="h-4 w-4 shrink-0 text-slate-400" /> {d.titulo}</span>
                  <span className="block pl-6 text-xs text-slate-500">{d.nombre}</span>
                  {d.objetivo
                    ? <span className="block max-w-xl pl-6 text-xs text-slate-600" title={d.objetivo}><b>Objetivo:</b> {d.objetivo.length > 160 ? `${d.objetivo.slice(0, 160)}…` : d.objetivo}</span>
                    : gestionar
                      ? <button className="ml-6 mt-1 rounded-md border border-amber-300 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800 hover:bg-amber-100" onClick={() => editar(d)}>
                          + Agregar objetivo
                        </button>
                      : <span className="block pl-6 text-xs text-amber-700">Sin objetivo</span>}
                  {d.enlace
                    ? <a className="ml-6 mt-1 inline-flex items-center gap-1 text-xs text-marca-700 hover:underline" href={d.enlace} target="_blank" rel="noopener noreferrer"><ExternalLink className="h-3 w-3" /> Abrir instructivo</a>
                    : gestionar
                      ? <button className="ml-6 mt-1 rounded-md border border-amber-300 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800 hover:bg-amber-100" onClick={() => editar(d)}>
                          + Agregar enlace
                        </button>
                      : <span className="block pl-6 text-xs text-amber-700">Sin enlace</span>}
                  {d.paginas_sin_texto > 0 && <span className="block pl-6 text-xs text-amber-700">{d.paginas_sin_texto} páginas sin texto (imagen)</span>}
                </td>
                <td>{d.modulo || <span className="text-xs text-amber-700">Sin módulo</span>}</td>
                <td className="whitespace-nowrap text-slate-500">{d.fecha ? new Date(d.fecha + "T12:00:00").toLocaleDateString("es-CO") : "—"}</td>
                <td className="text-right tabular-nums" title={d.secciones ? undefined : "Sin índice ni títulos reconocibles: el contexto es solo el nombre del instructivo"}>
                  {d.secciones || <span className="text-amber-700">0</span>}
                </td>
                <td className="text-right tabular-nums">{d.paginas}</td>
                <td className="whitespace-nowrap text-slate-500">{d.cargado_en ? new Date(d.cargado_en).toLocaleDateString("es-CO") : "—"}</td>
                {gestionar && (
                  <td className="whitespace-nowrap text-right">
                    <button className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100" aria-label="Editar"
                      title="Editar título, objetivo, enlace, módulo y fecha" onClick={() => editar(d)}><Pencil className="h-4 w-4" /></button>
                    <button className="rounded-md p-1.5 text-slate-500 hover:bg-red-50 hover:text-red-700" onClick={() => eliminar(d)} aria-label="Quitar"><Trash2 className="h-4 w-4" /></button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        </div>
        {docs?.length === 0 && <p className="p-6 text-center text-sm text-slate-500">Aún no hay instructivos cargados.</p>}
      </div>
    </div>
  );
}
