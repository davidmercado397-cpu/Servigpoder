"use client";

import { FileUp, Loader2, Send, Sparkles, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Modal } from "@/components/costeo";
import { Alerta } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";

export type InformeIA = {
  resumen: string; nombre_sugerido: string | null; cliente: { nombre: string | null; nit: string | null }; municipio: string | null;
  ica_por_mil: number | null; fecha_inicio?: string | null; llenado?: string[]; supuestos?: string[]; faltantes?: string[]; conflictos?: string[];
  advertencias?: string[]; modelo: string;
  /** Conversación: lo que la IA le contesta al comercial */
  respuesta?: string;
};
type Documento = { nombre: string; texto: string };
type Mensaje = { rol: "usuario" | "asistente"; texto: string };
type Respuesta<D> = { datos: D; informe: InformeIA; documentos?: Documento[] };

/** Primer mensaje de la IA en el chat: lo que necesita que el comercial le conteste */
function saludo(i: InformeIA): string {
  const faltan = i.faltantes ?? [], conflictos = i.conflictos ?? [];
  if (!faltan.length && !conflictos.length) return "Revisé los documentos y no me quedaron dudas. Si quiere cambiar algo, dígamelo aquí.";
  return "Revisé los documentos. Contésteme aquí lo que falta o lo que quiera cambiar y actualizo la propuesta."
    + (faltan.length ? `\n\nMe falta o necesito que confirme:\n${faltan.map((x) => `• ${x}`).join("\n")}` : "")
    + (conflictos.length ? `\n\nEncontré estos conflictos (tomé el Excel de costeo):\n${conflictos.map((x) => `• ${x}`).join("\n")}` : "");
}

const MAX = 6;
const ACEPTA = ".pdf,.xlsx,.xlsm,.docx,.csv,.txt,.png,.jpg,.jpeg,.webp,.eml";

/** Sube hasta 6 archivos; la IA propone el costeo, el comercial le contesta por chat y decide si lo aplica (no se guarda solo). */
export function LlenarConIA<D>({ costeoId, onCerrar, onAplicar }: {
  costeoId: number; onCerrar: () => void; onAplicar: (datos: D, informe: InformeIA) => void;
}) {
  const [archivos, setArchivos] = useState<File[]>([]);
  const [indicaciones, setIndicaciones] = useState("");
  const [leyendo, setLeyendo] = useState(false);
  const [error, setError] = useState("");
  const [res, setRes] = useState<Respuesta<D> | null>(null);
  const [documentos, setDocumentos] = useState<Documento[]>([]);
  const [mensajes, setMensajes] = useState<Mensaje[]>([]);
  const [texto, setTexto] = useState("");
  const [pensando, setPensando] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const fin = useRef<HTMLDivElement>(null);
  useEffect(() => { fin.current?.scrollIntoView({ block: "end" }); }, [mensajes, pensando]);

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
      const r = await api<Respuesta<D>>(`/costeo/costeos/${costeoId}/ia`, { method: "POST", body: form });
      setRes(r);
      setDocumentos(r.documentos ?? []);
      setMensajes([{ rol: "asistente", texto: saludo(r.informe) }]);
    } catch (e) { setError(mensajeError(e)); } finally { setLeyendo(false); }
  }
  async function enviar() {
    if (!res || !texto.trim() || pensando) return;
    const nuevos: Mensaje[] = [...mensajes, { rol: "usuario", texto: texto.trim() }];
    setMensajes(nuevos);
    setTexto("");
    setError("");
    setPensando(true);
    try {
      const r = await api<Respuesta<D>>(`/costeo/costeos/${costeoId}/ia/chat`, { method: "POST",
        json: { mensajes: nuevos.map((m) => ({ ...m, texto: m.texto.slice(0, 4000) })), datos: res.datos, informe: res.informe, documentos } });
      setRes({ ...r, documentos });
      setMensajes([...nuevos, { rol: "asistente", texto: r.informe.respuesta || "Listo, actualicé la propuesta." }]);
    } catch (e) {
      setError(mensajeError(e));
      setMensajes(mensajes);  // el mensaje no se procesó: vuelve al cuadro para reenviarlo
      setTexto(nuevos[nuevos.length - 1].texto);
    } finally { setPensando(false); }
  }

  return (
    <Modal titulo="Llenar el costeo con IA" onCerrar={leyendo || pensando ? () => {} : onCerrar} ancho={res ? "max-w-5xl" : "max-w-lg"}>
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
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="space-y-3">
              <ResumenIA informe={res.informe} />
              <DetallePropuesta datos={res.datos as unknown as DatosVista} />
            </div>
            {/* Chat: el comercial le contesta a la IA y la propuesta se actualiza */}
            <div className="flex min-h-[24rem] flex-col rounded-lg border border-slate-200">
              <p className="border-b border-slate-100 px-3 py-2 font-semibold text-slate-700">Conversación con la IA</p>
              <div className="flex-1 space-y-2 overflow-y-auto p-3 lg:max-h-[55vh]">
                {mensajes.map((m, k) => (
                  <div key={k} className={`whitespace-pre-line rounded-lg px-3 py-2 ${m.rol === "usuario" ? "ml-8 bg-marca-600 text-white" : "mr-8 bg-slate-100 text-slate-800"}`}>
                    {m.texto}
                  </div>
                ))}
                {pensando && <div className="mr-8 flex items-center gap-2 rounded-lg bg-slate-100 px-3 py-2 text-slate-500"><Loader2 className="h-4 w-4 animate-spin" /> Actualizando la propuesta… (puede tardar uno o dos minutos)</div>}
                <div ref={fin} />
              </div>
              <div className="flex gap-2 border-t border-slate-100 p-2">
                <textarea className="input flex-1" rows={2} maxLength={4000} value={texto} disabled={pensando}
                  placeholder="Ej.: el NIT es 900.123.456; las poligrafías valen $150.000; quite la supervisión diaria"
                  onChange={(e) => setTexto(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enviar(); } }} />
                <button className="btn-primario self-end" disabled={!texto.trim() || pensando} onClick={enviar} title="Enviar (Enter)"><Send className="h-4 w-4" /></button>
              </div>
            </div>
          </div>
          {error && <Alerta>{error}</Alerta>}
          <Alerta tipo="info">Al aplicarlo se reemplazan en pantalla los puestos, los otros costos, la dotación adicional y los beneficios que la IA encontró.
            Nada se guarda hasta que usted revise y dé <b>Guardar</b>.</Alerta>
          <div className="flex justify-end gap-2">
            <button className="btn-secundario" disabled={pensando} onClick={() => { setRes(null); setMensajes([]); setDocumentos([]); }}>Volver a los archivos</button>
            <button className="btn-primario" disabled={pensando} onClick={() => onAplicar(res.datos, res.informe)}><Sparkles className="h-4 w-4" /> Aplicar al costeo</button>
          </div>
        </div>
      )}
    </Modal>
  );
}

export function ResumenIA({ informe, onCerrar }: { informe: InformeIA; onCerrar?: () => void }) {
  // Las listas pueden no venir (versión distinta del servidor o respuesta incompleta): nunca deben tumbar la pantalla
  const i = { ...informe, cliente: informe.cliente ?? { nombre: null, nit: null }, llenado: informe.llenado ?? [], supuestos: informe.supuestos ?? [],
    faltantes: informe.faltantes ?? [], conflictos: informe.conflictos ?? [], advertencias: informe.advertencias ?? [] };
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
      {i.advertencias.length > 0 && <p className="text-xs text-slate-500">{i.advertencias.join(" · ")}</p>}
      <p className="text-xs text-slate-400">Modelo: {i.modelo}</p>
    </div>
  );
}

type DatosVista = {
  duracion_meses?: number; pct_nota_credito?: number; pct_cupo_inversion?: number; horas_bolsa_total?: number | null;
  servicios?: { descripcion?: string; puesto?: string; cantidad?: number; dotacion?: string; arma?: string }[];
  personal?: { nombre?: string; horas_extras?: number; auxilios_no_salariales?: number; rodamiento?: number }[];
  otros?: { nombre?: string; valor_unitario?: number; cantidad?: number }[];
  dotacion_puesto?: { nombre?: string; cantidad?: number }[];
  beneficios?: { nombre?: string; cantidad?: number; periodo?: string; valor_unitario?: number }[];
};
const ARMA: Record<string, string> = { sin: "sin arma", fuego: "arma de fuego", fogeo: "arma de fogeo", traumatica: "arma traumática", noletal: "arma no letal" };
const plata = (v?: number) => "$" + Math.round(v ?? 0).toLocaleString("es-CO");

/** Lo que quedaría en el costeo con la propuesta actual, para conversar sobre ella */
function DetallePropuesta({ datos: d }: { datos: DatosVista }) {
  const bloque = (titulo: string, filas: string[]) => filas.length > 0 && (
    <div><p className="font-medium text-slate-700">{titulo}</p><ul className="ml-5 list-disc text-slate-600">{filas.map((x, k) => <li key={k}>{x}</li>)}</ul></div>
  );
  return (
    <div className="space-y-2 rounded-lg border border-slate-200 p-3 text-sm">
      <p className="font-semibold text-slate-700">Lo que quedaría en el costeo</p>
      <p className="text-xs text-slate-500">{d.duracion_meses ?? "—"} meses · nota crédito {((d.pct_nota_credito ?? 0) * 100).toLocaleString("es-CO")} %
        · cupo {((d.pct_cupo_inversion ?? 0) * 100).toLocaleString("es-CO")} %{d.horas_bolsa_total ? ` · ${d.horas_bolsa_total} h de obsequio en el contrato` : ""}</p>
      {bloque("Puestos", (d.servicios ?? []).map((s) => `${s.cantidad ?? 1} × ${s.puesto || "puesto"}: ${s.descripcion ?? ""} (${s.dotacion ?? "gala"}, ${ARMA[s.arma ?? "sin"] ?? s.arma})`))}
      {bloque("Personal", (d.personal ?? []).filter((p) => p.horas_extras || p.auxilios_no_salariales || p.rodamiento)
        .map((p) => `${p.nombre}: horas extras ${plata(p.horas_extras)}${p.auxilios_no_salariales ? `, auxilios ${plata(p.auxilios_no_salariales)}` : ""}${p.rodamiento ? `, rodamiento ${plata(p.rodamiento)}` : ""}`))}
      {bloque("Dotación adicional", (d.dotacion_puesto ?? []).map((x) => `${x.nombre} × ${x.cantidad}`))}
      {bloque("Otros costos (MFP)", (d.otros ?? []).map((x) => `${x.nombre}: ${x.cantidad ?? 1} × ${plata(x.valor_unitario)}`))}
      {bloque("Beneficios (MFP)", (d.beneficios ?? []).map((b) => `${b.nombre}: ${b.cantidad} ${b.periodo === "contrato" ? "en el contrato" : "por año"}${b.valor_unitario ? ` a ${plata(b.valor_unitario)} c/u` : " (sin costo)"}`))}
    </div>
  );
}
