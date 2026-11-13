"use client";

import { FileUp, Loader2, Sparkles, X } from "lucide-react";
import { useRef, useState } from "react";
import { Modal } from "@/components/costeo";
import { Alerta } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";

export type InformeIA = {
  resumen: string; nombre_sugerido: string | null; cliente: { nombre: string | null; nit: string | null }; municipio: string | null;
  ica_por_mil: number | null; fecha_inicio: string | null; llenado: string[]; supuestos: string[]; faltantes: string[]; conflictos: string[];
  beneficios_sin_costo: string[]; advertencias: string[]; modelo: string;
};

const MAX = 6;
const ACEPTA = ".pdf,.xlsx,.xlsm,.docx,.csv,.txt,.png,.jpg,.jpeg,.webp,.eml";

/** Sube de 1 a 3 archivos del cliente; la IA propone el costeo y el usuario decide si lo aplica (no se guarda solo). */
export function LlenarConIA<D>({ costeoId, onCerrar, onAplicar }: {
  costeoId: number; onCerrar: () => void; onAplicar: (datos: D, informe: InformeIA) => void;
}) {
  const [archivos, setArchivos] = useState<File[]>([]);
  const [indicaciones, setIndicaciones] = useState("");
  const [leyendo, setLeyendo] = useState(false);
  const [error, setError] = useState("");
  const [res, setRes] = useState<{ datos: D; informe: InformeIA } | null>(null);
  const input = useRef<HTMLInputElement>(null);

  function agregar(lista: FileList | null) {
    if (!lista) return;
    const nuevos = [...archivos, ...Array.from(lista)].slice(0, MAX);
    if (archivos.length + lista.length > MAX) setError(`Máximo ${MAX} archivos.`);
    else setError("");
    setArchivos(nuevos);
  }
  async function analizar() {
    setError("");
    setLeyendo(true);
    try {
      const form = new FormData();
      archivos.forEach((a) => form.append("archivos", a));
      form.append("indicaciones", indicaciones);
      setRes(await api<{ datos: D; informe: InformeIA }>(`/costeo/costeos/${costeoId}/ia`, { method: "POST", body: form }));
    } catch (e) { setError(mensajeError(e)); } finally { setLeyendo(false); }
  }

  return (
    <Modal titulo="Llenar el costeo con IA" onCerrar={leyendo ? () => {} : onCerrar}>
      {!res ? (
        <div className="space-y-3">
          <p className="text-sm text-slate-600">Suba hasta {MAX} archivos de la oportunidad (Excel de costeo, MFP, apoyo comercial, cotización, beneficios, formato del cliente, correo o fotos).
            El apoyo comercial y los beneficios van a la MFP (nota crédito, reinversión, otros costos y bolsa de horas).
            Si los documentos se contradicen, manda el Excel de costeo.
            La IA llena puestos, servicios, dotación, arma, horas extras y otros costos; las tarifas, los hombres y los precios salen de los catálogos.
            Los archivos se leen y se descartan: no se guardan.</p>
          <div className="cursor-pointer rounded-lg border-2 border-dashed border-slate-300 p-4 text-center text-sm text-slate-500 hover:border-marca-400"
            onClick={() => input.current?.click()} onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); agregar(e.dataTransfer.files); }}>
            <FileUp className="mx-auto mb-1 h-6 w-6" />
            Arrastre los archivos aquí o haga clic para elegirlos
            <p className="text-xs">PDF, Excel (.xlsx), Word (.docx), imágenes, CSV, TXT o correo (.eml)</p>
            <input ref={input} type="file" multiple accept={ACEPTA} className="hidden" onChange={(e) => { agregar(e.target.files); e.target.value = ""; }} />
          </div>
          {archivos.length > 0 && (
            <ul className="space-y-1 text-sm">
              {archivos.map((a, i) => (
                <li key={i} className="flex items-center justify-between rounded bg-slate-50 px-2 py-1">
                  <span className="truncate">{a.name} <span className="text-xs text-slate-400">({(a.size / 1024 / 1024).toFixed(1)} MB)</span></span>
                  <button disabled={leyendo} onClick={() => setArchivos(archivos.filter((_, j) => j !== i))}><X className="h-4 w-4 text-slate-400" /></button>
                </li>
              ))}
            </ul>
          )}
          <div>
            <label className="label">Indicaciones (opcional)</label>
            <textarea className="input" rows={3} maxLength={2000} value={indicaciones} onChange={(e) => setIndicaciones(e.target.value)}
              placeholder="Ej.: contrato a 24 meses, los puestos de parqueadero van con overol, no incluir la portería 3" />
          </div>
          {error && <Alerta>{error}</Alerta>}
          <div className="flex justify-end gap-2">
            <button className="btn-secundario" disabled={leyendo} onClick={onCerrar}>Cancelar</button>
            <button className="btn-primario" disabled={!archivos.length || leyendo} onClick={analizar}>
              {leyendo ? <><Loader2 className="h-4 w-4 animate-spin" /> Leyendo los archivos…</> : <><Sparkles className="h-4 w-4" /> Analizar</>}
            </button>
          </div>
          {leyendo && <p className="text-xs text-slate-500">Puede tardar uno o dos minutos según el tamaño de los archivos.</p>}
        </div>
      ) : (
        <div className="space-y-3 text-sm">
          <ResumenIA informe={res.informe} />
          <Alerta tipo="info">Al aplicarlo se reemplazan en pantalla los puestos, los otros costos y la dotación adicional que la IA encontró.
            Nada se guarda hasta que usted revise y dé <b>Guardar</b>.</Alerta>
          <div className="flex justify-end gap-2">
            <button className="btn-secundario" onClick={() => setRes(null)}>Volver</button>
            <button className="btn-primario" onClick={() => onAplicar(res.datos, res.informe)}><Sparkles className="h-4 w-4" /> Aplicar al costeo</button>
          </div>
        </div>
      )}
    </Modal>
  );
}

export function ResumenIA({ informe, onCerrar }: { informe: InformeIA; onCerrar?: () => void }) {
  const i = informe;
  return (
    <div className="space-y-2 rounded-lg border border-marca-100 bg-marca-50/40 p-3 text-sm">
      <div className="flex items-start justify-between gap-2">
        <p className="font-semibold text-marca-900"><Sparkles className="mr-1 inline h-4 w-4" />Propuesta de la IA</p>
        {onCerrar && <button onClick={onCerrar} title="Ocultar"><X className="h-4 w-4 text-slate-400" /></button>}
      </div>
      {i.resumen && <p className="text-slate-700">{i.resumen}</p>}
      <p className="text-xs text-slate-500">
        {i.llenado.length ? `Llenó: ${i.llenado.join(", ")}.` : "No encontró datos para llenar."}
        {i.cliente.nombre && ` Cliente: ${i.cliente.nombre}${i.cliente.nit ? ` (NIT ${i.cliente.nit})` : ""}.`}
        {i.municipio && ` Municipio: ${i.municipio}${i.ica_por_mil != null ? ` (ICA ${i.ica_por_mil} por mil; lo ajusta contabilidad)` : ""}.`}
        {i.nombre_sugerido && ` Nombre sugerido: ${i.nombre_sugerido}.`}
        {i.fecha_inicio && ` Inicio del contrato: ${i.fecha_inicio} (se usa al crear la MFP).`}
      </p>
      {i.conflictos.length > 0 && (
        <div><p className="font-medium text-red-800">Conflictos entre documentos (se tomó el Excel de costeo)</p>
          <ul className="ml-5 list-disc text-red-900">{i.conflictos.map((x, k) => <li key={k}>{x}</li>)}</ul></div>
      )}
      {i.faltantes.length > 0 && (
        <div><p className="font-medium text-amber-800">Faltantes / por revisar</p>
          <ul className="ml-5 list-disc text-amber-900">{i.faltantes.map((x, k) => <li key={k}>{x}</li>)}</ul></div>
      )}
      {i.supuestos.length > 0 && (
        <div><p className="font-medium text-slate-700">Supuestos</p>
          <ul className="ml-5 list-disc text-slate-600">{i.supuestos.map((x, k) => <li key={k}>{x}</li>)}</ul></div>
      )}
      {i.beneficios_sin_costo.length > 0 && (
        <div><p className="font-medium text-slate-700">Beneficios ofrecidos sin costo directo (no entran al costeo)</p>
          <ul className="ml-5 list-disc text-slate-600">{i.beneficios_sin_costo.map((x, k) => <li key={k}>{x}</li>)}</ul></div>
      )}
      {i.advertencias.length > 0 && <p className="text-xs text-slate-500">{i.advertencias.join(" · ")}</p>}
      <p className="text-xs text-slate-400">Modelo: {i.modelo}</p>
    </div>
  );
}
