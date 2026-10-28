"use client";

import { FileText, Paperclip, Upload, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { Alerta } from "@/components/ui";
import { api, mensajeError, subirArchivo } from "@/lib/api";
import type { DocumentoAdjunto } from "@/lib/gestion";
import type { Hallazgo } from "@/lib/liquidador";

/** Soportes adjuntos de una incapacidad, restricción o caso: abrir, quitar y adjuntar (PDF, PNG o JPG; máx. 10 MB). */
export function Soportes({ modulo, registroId, documentos, editable, onCambio, onError }: {
  modulo: "incapacidad" | "restriccion" | "caso"; registroId: number; documentos: DocumentoAdjunto[]; editable: boolean;
  onCambio: () => void; onError: (m: string) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const [subiendo, setSubiendo] = useState(false);

  async function subir(archivos: FileList | null) {
    if (!archivos?.length) return;
    setSubiendo(true);
    try {
      for (const a of Array.from(archivos)) await subirArchivo(`/liquidador/documentos/${modulo}/${registroId}`, a);
    } catch (e) {
      onError(mensajeError(e));
    } finally {
      setSubiendo(false);
      onCambio();
    }
  }

  async function quitar(d: DocumentoAdjunto) {
    if (!window.confirm(`¿Quitar el soporte «${d.nombre}»?`)) return;
    try {
      await api(`/liquidador/documentos/${d.id}`, { method: "DELETE" });
      onCambio();
    } catch (e) {
      onError(mensajeError(e));
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {documentos.map((d) => (
        <span key={d.id} className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-1.5 py-0.5 text-xs">
          <a className="inline-flex max-w-[140px] items-center gap-1 text-marca-700 hover:underline" href={`/api/liquidador/documentos/${d.id}`}
            target="_blank" rel="noopener noreferrer" title={d.nombre}>
            <FileText className="h-3.5 w-3.5 shrink-0" /><span className="truncate">{d.nombre}</span>
          </a>
          {editable && <button className="text-slate-400 hover:text-red-700" onClick={() => quitar(d)} aria-label={`Quitar ${d.nombre}`}><X className="h-3 w-3" /></button>}
        </span>
      ))}
      {editable && (
        <>
          <input ref={ref} type="file" multiple accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg" className="hidden"
            onChange={(e) => { subir(e.target.files); e.target.value = ""; }} />
          <button className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs text-slate-500 hover:bg-slate-100 hover:text-marca-700"
            disabled={subiendo} onClick={() => ref.current?.click()} title="Adjuntar soporte (PDF, PNG o JPG)">
            <Paperclip className="h-3.5 w-3.5" />{subiendo ? "Subiendo…" : "Adjuntar"}
          </button>
        </>
      )}
    </div>
  );
}

type Cie = { codigo: string; descripcion: string };

/** Campo de código CIE-10 con sugerencias por código o por nombre de la enfermedad. Admite varios separados por coma. */
export function BuscarCie({ valor, onCambio, onDiagnostico }: { valor: string; onCambio: (v: string) => void; onDiagnostico: (d: string) => void }) {
  const [abierto, setAbierto] = useState(false);
  const [opciones, setOpciones] = useState<Cie[]>([]);
  const caja = useRef<HTMLDivElement>(null);
  const lista = useId();
  const ultimo = valor.split(",").pop()?.trim() ?? "";

  useEffect(() => {
    if (!abierto || ultimo.length < 2) { setOpciones([]); return; }
    let vigente = true;
    const t = setTimeout(() => {
      api<Cie[]>(`/liquidador/cie?q=${encodeURIComponent(ultimo)}`).then((x) => { if (vigente) setOpciones(x); }).catch(() => {});
    }, 250);
    return () => { vigente = false; clearTimeout(t); };
  }, [ultimo, abierto]);

  useEffect(() => {
    function fuera(e: MouseEvent) { if (caja.current && !caja.current.contains(e.target as Node)) setAbierto(false); }
    document.addEventListener("mousedown", fuera);
    return () => document.removeEventListener("mousedown", fuera);
  }, []);

  function elegir(c: Cie) {
    const previos = valor.split(",").slice(0, -1).map((x) => x.trim()).filter(Boolean);
    onCambio([...previos, c.codigo].join(", "));
    if (previos.length === 0) onDiagnostico(c.descripcion);
    setAbierto(false);
  }

  return (
    <div className="relative" ref={caja}>
      <input className="input font-mono" autoComplete="off" placeholder="Código o enfermedad" value={valor} role="combobox"
        aria-expanded={abierto} aria-controls={lista} onFocus={() => setAbierto(true)}
        onChange={(e) => { onCambio(e.target.value); setAbierto(true); }} />
      {abierto && opciones.length > 0 && (
        <ul id={lista} role="listbox" className="absolute z-20 mt-1 max-h-72 w-[min(30rem,90vw)] overflow-auto rounded-lg border border-slate-200 bg-white py-1 shadow-lg">
          {opciones.map((c) => (
            <li key={c.codigo} role="option" aria-selected={false}>
              <button type="button" onMouseDown={(ev) => ev.preventDefault()} onClick={() => elegir(c)}
                className="flex w-full gap-2 px-3 py-1.5 text-left text-sm hover:bg-slate-100">
                <span className="w-12 shrink-0 font-mono text-xs text-marca-700">{c.codigo}</span><span>{c.descripcion}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

type Conteo = { leidas: number; creadas: number; actualizadas: number; repetidas?: number; en_varias_hojas?: number; abiertos?: number };
type ResultadoAusentismo = { incapacidades?: Conteo; restricciones?: Conteo; casos?: Conteo; hallazgos: Hallazgo[] };

/** Importa el formato de caracterización de ausentismo (FT-SST-023). El archivo se procesa y se descarta. */
export function ImportarAusentismo({ onImportado, onCerrar }: { onImportado: () => void; onCerrar: () => void }) {
  const [archivo, setArchivo] = useState<File | null>(null);
  const [cargando, setCargando] = useState(false);
  const [res, setRes] = useState<ResultadoAusentismo | null>(null);
  const [error, setError] = useState("");

  async function importar() {
    if (!archivo) return;
    setError("");
    setRes(null);
    setCargando(true);
    try {
      setRes(await subirArchivo<ResultadoAusentismo>("/liquidador/gestion/importar-ausentismo", archivo));
      onImportado();
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setCargando(false);
    }
  }

  const linea = (titulo: string, c?: Conteo) => c && (
    <span>{titulo}: <b className="tabular-nums">{c.creadas}</b> nuevas, <b className="tabular-nums">{c.actualizadas}</b> actualizadas
      {c.en_varias_hojas ? <> · {c.en_varias_hojas} estaban en dos hojas</> : null}{c.repetidas ? <> · {c.repetidas} repetidas</> : null}</span>
  );

  return (
    <section className="tarjeta space-y-3 p-5">
      <div className="flex items-center">
        <h2 className="font-semibold text-slate-900">Importar formato de ausentismo</h2>
        <button className="ml-auto rounded-md p-1 text-slate-500 hover:bg-slate-100" onClick={onCerrar} aria-label="Cerrar"><X className="h-4 w-4" /></button>
      </div>
      <p className="-mt-2 text-xs text-slate-500">
        Hojas REGISTRO INCAPACIDADES (todas las que haya), RECOMENDACIONES O RESTRICCIONES y DERECHOS, TUTELAS, DEMANDAS. Si una incapacidad
        está en dos hojas se carga una vez; volver a importar actualiza sin duplicar. Las prolongadas se calculan solas. El archivo no se guarda.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <input className="input max-w-xs" type="file" accept=".xlsx" onChange={(e) => setArchivo(e.target.files?.[0] ?? null)} />
        <button className="btn-primario inline-flex items-center gap-1.5" disabled={!archivo || cargando} onClick={importar}>
          <Upload className="h-4 w-4" /> {cargando ? "Importando…" : "Importar"}
        </button>
      </div>
      {error && <Alerta>{error}</Alerta>}
      {res && (
        <div className="space-y-3 rounded-lg border border-green-200 bg-green-50/60 p-3 text-sm">
          <div className="flex flex-col gap-1">
            {linea("Incapacidades", res.incapacidades)}{linea("Restricciones", res.restricciones)}{linea("Tutelas y demandas", res.casos)}
          </div>
          {res.hallazgos.length > 0 && (
            <div className="max-h-80 overflow-auto rounded-md border border-amber-200 bg-white">
              <p className="sticky top-0 border-b border-amber-200 bg-amber-50 px-3 py-2 font-medium text-amber-900">{res.hallazgos.length} casos para revisar</p>
              <table className="tabla text-xs">
                <thead><tr><th>Hoja</th><th className="text-right">Fila</th><th>Documento</th><th>Detalle</th></tr></thead>
                <tbody>
                  {res.hallazgos.map((h, i) => (
                    <tr key={i}><td className="whitespace-nowrap">{h.hoja}</td><td className="text-right tabular-nums">{h.fila}</td>
                      <td className="whitespace-nowrap font-mono">{h.documento ?? "—"}</td><td>{h.detalle}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
