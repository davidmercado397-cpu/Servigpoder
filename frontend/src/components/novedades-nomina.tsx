"use client";

import { FileDown, Pencil, Plus, Trash2, Upload, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { BuscarEmpleado } from "@/components/buscar-empleado";
import { Alerta } from "@/components/ui";
import { api, mensajeError, subirArchivo } from "@/lib/api";
import { pesos } from "@/lib/formato";
import { CONCEPTOS_PAGO, TIPOS_NOVEDAD, type Hallazgo, type Novedad } from "@/lib/liquidador";

type Formulario = {
  documento: string; tipo: string; descripcion: string; valor: string; fecha_causacion: string; salarial: boolean; nomina_origen: string;
  horas: Record<string, string>;
};
const DE_HORAS = ["horas_extras", "recargos"];
const RECARGOS = ["ordinary_night", "holiday_day_surcharge", "holiday_night_surcharge", "sunday_surcharge", "sunday_night_surcharge"];

function FormularioNovedad({ periodoId, registro, onGuardado, onCancelar }: {
  periodoId: number; registro: Novedad | null; onGuardado: () => void; onCancelar: () => void;
}) {
  const [f, setF] = useState<Formulario>(() => ({
    documento: registro?.documento ?? "", tipo: registro?.tipo ?? "menor_valor", descripcion: registro?.descripcion ?? "",
    valor: registro?.valor_escrito?.toString() ?? "", fecha_causacion: registro?.fecha_causacion ?? "", salarial: registro?.salarial ?? true,
    nomina_origen: registro?.nomina_origen ?? "", horas: Object.fromEntries(Object.entries(registro?.horas ?? {}).map(([k, v]) => [k, String(v)])),
  }));
  const [error, setError] = useState("");
  const cambiar = (c: Partial<Formulario>) => setF({ ...f, ...c });
  const deHoras = DE_HORAS.includes(f.tipo);
  const conceptos = CONCEPTOS_PAGO.filter(([k]) => (f.tipo === "recargos") === RECARGOS.includes(k));

  async function guardar(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    const horas = deHoras ? Object.fromEntries(Object.entries(f.horas).filter(([, v]) => Number(v) > 0).map(([k, v]) => [k, Number(v)])) : {};
    const datos = { documento: f.documento, tipo: f.tipo, descripcion: f.descripcion, horas, valor: f.valor ? Number(f.valor) : null,
      fecha_causacion: deHoras && f.fecha_causacion ? f.fecha_causacion : null, salarial: f.salarial, nomina_origen: f.nomina_origen || null };
    try {
      await api(registro ? `/liquidador/novedades/${registro.id}` : `/liquidador/periodos/${periodoId}/novedades`,
        { method: registro ? "PUT" : "POST", json: datos });
      onGuardado();
    } catch (err) {
      setError(mensajeError(err));
    }
  }

  return (
    <form onSubmit={guardar} className="space-y-3 rounded-lg border border-marca-200 bg-marca-50/40 p-4">
      <div className="flex items-center">
        <h3 className="font-semibold text-slate-900">{registro ? "Editar novedad" : "Nueva novedad"}</h3>
        <button type="button" className="ml-auto rounded-md p-1 text-slate-500 hover:bg-white" onClick={onCancelar} aria-label="Cerrar"><X className="h-4 w-4" /></button>
      </div>
      {error && <Alerta>{error}</Alerta>}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <label className="label">Cédula</label>
          <BuscarEmpleado key={registro?.id ?? "nueva"} valor={f.documento} nombreInicial={registro?.nombre} onCambio={(d) => cambiar({ documento: d })} />
        </div>
        <div>
          <label className="label">Tipo</label>
          <select className="input" value={f.tipo} onChange={(e) => cambiar({ tipo: e.target.value, horas: {} })}>
            {TIPOS_NOVEDAD.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
          </select>
          <p className="mt-1 text-xs text-slate-500">{TIPOS_NOVEDAD.find(([v]) => v === f.tipo)?.[2]}</p>
        </div>
        <div className="sm:col-span-2">
          <label className="label">Descripción</label>
          <input className="input" required maxLength={200} value={f.descripcion} placeholder="p. ej. Recargos dominicales no pagados en octubre"
            onChange={(e) => cambiar({ descripcion: e.target.value })} />
        </div>
        <div>
          <label className="label">Nómina de origen</label>
          <input className="input" maxLength={80} value={f.nomina_origen} placeholder="p. ej. Octubre 2.ª quincena" onChange={(e) => cambiar({ nomina_origen: e.target.value })} />
        </div>
        {deHoras && (
          <div>
            <label className="label">Fecha en que se causaron</label>
            <input className="input" type="date" value={f.fecha_causacion} onChange={(e) => cambiar({ fecha_causacion: e.target.value })} />
            <p className="mt-1 text-xs text-slate-500">Se usa la tarifa (% de recargos) de esa fecha</p>
          </div>
        )}
        <div>
          <label className="label">{deHoras ? "Valor (opcional: reemplaza el calculado)" : "Valor"}</label>
          <input className="input" type="number" min={1} required={!deHoras} value={f.valor} onChange={(e) => cambiar({ valor: e.target.value })} />
        </div>
        {f.tipo === "otro_devengo" && (
          <div className="flex items-end pb-2">
            <label className="inline-flex items-center gap-2 text-sm">
              <input type="checkbox" checked={f.salarial} onChange={(e) => cambiar({ salarial: e.target.checked })} /> Salarial (hace base de salud y pensión)
            </label>
          </div>
        )}
      </div>
      {deHoras && (
        <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-6">
          {conceptos.map(([k, texto]) => (
            <div key={k}>
              <label className="label text-xs">{texto}</label>
              <input className="input" type="number" min={0} step="0.5" value={f.horas[k] ?? ""} placeholder="horas"
                onChange={(e) => cambiar({ horas: { ...f.horas, [k]: e.target.value } })} />
            </div>
          ))}
        </div>
      )}
      <div className="flex gap-2">
        <button className="btn-primario">Guardar y recalcular</button>
        <button type="button" className="btn-secundario" onClick={onCancelar}>Cancelar</button>
      </div>
    </form>
  );
}

/** Novedades manuales de una nómina: lo pagado de más o de menos en nóminas anteriores y las horas pendientes. */
export function NovedadesNomina({ periodoId, editable, onCambio }: { periodoId: number; editable: boolean; onCambio: () => void }) {
  const [lista, setLista] = useState<Novedad[]>([]);
  const [edicion, setEdicion] = useState<{ registro: Novedad | null } | null>(null);
  const [archivo, setArchivo] = useState<File | null>(null);
  const [importando, setImportando] = useState(false);
  const [resultado, setResultado] = useState<{ cargadas: number; reemplazadas: number; hallazgos: Hallazgo[] } | null>(null);
  const [error, setError] = useState("");

  const cargar = useCallback(() => api<Novedad[]>(`/liquidador/periodos/${periodoId}/novedades`).then(setLista), [periodoId]);
  useEffect(() => { cargar().catch((e) => setError(mensajeError(e))); }, [cargar]);

  const listo = () => { cargar().catch(() => {}); onCambio(); };

  async function eliminar(x: Novedad) {
    if (!window.confirm(`¿Eliminar «${x.descripcion}» de ${x.nombre}? Se recalcula la nómina.`)) return;
    try {
      await api(`/liquidador/novedades/${x.id}`, { method: "DELETE" });
      listo();
    } catch (e) {
      setError(mensajeError(e));
    }
  }

  async function importar() {
    if (!archivo) return;
    setError("");
    setImportando(true);
    try {
      setResultado(await subirArchivo(`/liquidador/periodos/${periodoId}/novedades/importar`, archivo));
      listo();
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setImportando(false);
    }
  }

  const devengo = lista.filter((x) => x.deduccion === false).reduce((s, x) => s + (x.valor ?? 0), 0);
  const deduccion = lista.filter((x) => x.deduccion).reduce((s, x) => s + (x.valor ?? 0), 0);

  return (
    <section className="tarjeta space-y-3 p-5">
      <div className="flex flex-wrap items-start gap-3">
        <div>
          <h2 className="font-semibold text-slate-900">Novedades de la nómina</h2>
          <p className="text-sm text-slate-500">
            Lo que se pagó de más (se descuenta) o de menos (se paga) en nóminas anteriores, y horas extras o recargos pendientes.
            {lista.length > 0 && <> Esta nómina: <b>{pesos(devengo)}</b> a pagar y <b>{pesos(deduccion)}</b> a descontar.</>}
          </p>
        </div>
        <div className="ml-auto flex flex-wrap gap-2">
          <a className="btn-secundario inline-flex items-center gap-1.5" href={`/api/liquidador/periodos/${periodoId}/novedades/plantilla`}>
            <FileDown className="h-4 w-4" /> Plantilla
          </a>
          {editable && !edicion && (
            <button className="btn-primario inline-flex items-center gap-1.5" onClick={() => setEdicion({ registro: null })}><Plus className="h-4 w-4" /> Nueva novedad</button>
          )}
        </div>
      </div>
      {error && <Alerta>{error}</Alerta>}
      {edicion && (
        <FormularioNovedad key={edicion.registro?.id ?? "nueva"} periodoId={periodoId} registro={edicion.registro} onCancelar={() => setEdicion(null)}
          onGuardado={() => { setEdicion(null); listo(); }} />
      )}
      {editable && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-slate-500">Cargar desde la plantilla:</span>
          <input className="input max-w-xs" type="file" accept=".xlsx" onChange={(e) => setArchivo(e.target.files?.[0] ?? null)} />
          <button className="btn-secundario inline-flex items-center gap-1.5" disabled={!archivo || importando} onClick={importar}>
            <Upload className="h-4 w-4" /> {importando ? "Importando…" : "Importar"}
          </button>
          <span className="text-xs text-slate-500">Reemplaza las cargadas antes por Excel; las registradas a mano se conservan.</span>
        </div>
      )}
      {resultado && (
        <Alerta tipo={resultado.hallazgos.length ? "info" : "ok"}>
          Se cargaron {resultado.cargadas} novedades{resultado.reemplazadas ? ` (reemplazaron ${resultado.reemplazadas})` : ""}.
          {resultado.hallazgos.length > 0 && (
            <ul className="mt-1 list-disc pl-5 text-xs">{resultado.hallazgos.map((h, i) => <li key={i}>Fila {h.fila} ({h.documento}): {h.detalle}</li>)}</ul>
          )}
        </Alerta>
      )}
      {lista.length > 0 && (
        <div className="overflow-auto">
          <table className="tabla text-sm">
            <thead><tr><th>Persona</th><th>Tipo</th><th>Descripción y cálculo</th><th className="text-right">Valor</th><th /></tr></thead>
            <tbody>
              {lista.map((x) => (
                <tr key={x.id} className="align-top">
                  <td><span className="font-medium">{x.nombre}</span><span className="block font-mono text-xs text-slate-500">{x.documento}</span></td>
                  <td className="whitespace-nowrap text-xs">{TIPOS_NOVEDAD.find(([v]) => v === x.tipo)?.[1]}
                    <span className={`block ${x.deduccion ? "text-red-700" : "text-green-700"}`}>{x.deduccion ? "Descuenta" : x.salarial ? "Paga (salarial)" : "Paga (no salarial)"}</span></td>
                  <td className="text-xs">{x.descripcion}{x.nomina_origen && <span className="text-slate-500"> · origen: {x.nomina_origen}</span>}
                    <span className="block text-slate-500">{x.calculo}</span>{x.observacion && <span className="block text-amber-700">{x.observacion}</span>}</td>
                  <td className={`whitespace-nowrap text-right tabular-nums ${x.deduccion ? "text-red-700" : ""}`}>{x.valor !== null ? `${x.deduccion ? "−" : ""}${pesos(x.valor)}` : "—"}</td>
                  <td className="whitespace-nowrap text-right">
                    {editable && (
                      <>
                        <button className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100" onClick={() => setEdicion({ registro: x })} aria-label="Editar"><Pencil className="h-4 w-4" /></button>
                        <button className="rounded-md p-1.5 text-slate-500 hover:bg-red-50 hover:text-red-700" onClick={() => eliminar(x)} aria-label="Eliminar"><Trash2 className="h-4 w-4" /></button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
