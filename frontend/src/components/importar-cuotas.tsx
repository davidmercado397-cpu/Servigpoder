"use client";

import { Upload, X } from "lucide-react";
import { useState } from "react";
import { Alerta } from "@/components/ui";
import { mensajeError, subirArchivo } from "@/lib/api";
import { pesos } from "@/lib/formato";
import { QUINCENAS, type Hallazgo, type Quincena } from "@/lib/liquidador";

type Resultado = { filas: number; personas: number; creadas: number; actualizadas: number; desactivadas: number; total: number; hallazgos: Hallazgo[] };
const primeroDelMes = () => { const h = new Date(); return new Date(h.getFullYear(), h.getMonth(), 1).toISOString().slice(0, 10); };

/** Cuotas desde la lista de una entidad (mutual, Recordar…): una cuota por cédula, con el valor de la columna indicada. */
export function ImportarCuotas({ onImportado, onCerrar }: { onImportado: () => void; onCerrar: () => void }) {
  const [f, setF] = useState({ descripcion: "", columna_valor: "", quincena: "segunda" as Quincena, desde: primeroDelMes(), desactivar_ausentes: true });
  const [archivo, setArchivo] = useState<File | null>(null);
  const [res, setRes] = useState<Resultado | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState("");
  const cambiar = (c: Partial<typeof f>) => setF({ ...f, ...c });

  async function importar(e: React.FormEvent) {
    e.preventDefault();
    if (!archivo) return;
    setError("");
    setRes(null);
    setCargando(true);
    try {
      setRes(await subirArchivo<Resultado>("/liquidador/descuentos/importar-cuotas", archivo,
        { ...f, desactivar_ausentes: String(f.desactivar_ausentes) }));
      onImportado();
    } catch (err) {
      setError(mensajeError(err));
    } finally {
      setCargando(false);
    }
  }

  return (
    <form onSubmit={importar} className="tarjeta space-y-4 p-5">
      <div className="flex items-center">
        <h2 className="font-semibold text-slate-900">Importar cuotas desde Excel</h2>
        <button type="button" className="ml-auto rounded-md p-1 text-slate-500 hover:bg-slate-100" onClick={onCerrar} aria-label="Cerrar"><X className="h-5 w-5" /></button>
      </div>
      <p className="-mt-2 text-sm text-slate-500">
        La lista de la entidad (mutual, Recordar, plan exequial…): se busca la columna de la cédula (IDENTIFICACION, CEDULA o DOCUMENTO) y el
        valor sale de la columna que indique. Cada persona queda con una cuota mensual con este nombre. Si la importa de nuevo, se actualizan los
        valores. El archivo no se guarda.
      </p>
      {error && <Alerta>{error}</Alerta>}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="sm:col-span-2">
          <label className="label">Nombre del descuento</label>
          <input className="input" required minLength={2} maxLength={200} list="nombres-cuota" placeholder="p. ej. Cuota mutual" value={f.descripcion}
            onChange={(e) => cambiar({ descripcion: e.target.value })} />
          <datalist id="nombres-cuota"><option value="Cuota mutual" /><option value="Cuota recordar" /></datalist>
        </div>
        <div>
          <label className="label">Columna del valor</label>
          <input className="input uppercase" required maxLength={3} pattern="[A-Za-z]{1,3}" placeholder="p. ej. I" value={f.columna_valor}
            onChange={(e) => cambiar({ columna_valor: e.target.value.toUpperCase() })} />
        </div>
        <div>
          <label className="label">Se descuenta en</label>
          <select className="input" value={f.quincena} onChange={(e) => cambiar({ quincena: e.target.value as Quincena })}>
            {QUINCENAS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
          </select>
          <p className="mt-1 text-xs text-slate-500">Solo 2.ª quincena: el valor completo en esa quincena</p>
        </div>
        <div>
          <label className="label">Desde</label>
          <input className="input" type="date" required value={f.desde} onChange={(e) => cambiar({ desde: e.target.value })} />
        </div>
        <div className="sm:col-span-2">
          <label className="label">Archivo (.xlsx)</label>
          <input className="input" type="file" accept=".xlsx" required onChange={(e) => setArchivo(e.target.files?.[0] ?? null)} />
        </div>
        <div className="flex items-end pb-2">
          <label className="inline-flex items-center gap-2 text-sm">
            <input type="checkbox" checked={f.desactivar_ausentes} onChange={(e) => cambiar({ desactivar_ausentes: e.target.checked })} />
            Desactivar esta cuota a quien ya no esté en la lista
          </label>
        </div>
      </div>
      <button className="btn-primario inline-flex items-center gap-1.5" disabled={!archivo || cargando}>
        <Upload className="h-4 w-4" /> {cargando ? "Importando…" : "Importar"}
      </button>
      {res && (
        <div className="space-y-2 rounded-lg border border-green-200 bg-green-50/60 p-3 text-sm">
          <p>
            <b>{res.personas}</b> personas por <b>{pesos(res.total)}</b>: {res.creadas} cuotas nuevas, {res.actualizadas} actualizadas
            {res.desactivadas ? `, ${res.desactivadas} desactivadas (ya no estaban en la lista)` : ""}.
          </p>
          {res.hallazgos.length > 0 && (
            <ul className="list-disc pl-5 text-xs text-amber-900">
              {res.hallazgos.map((h, i) => <li key={i}>Fila {h.fila} ({h.documento}): {h.detalle}</li>)}
            </ul>
          )}
        </div>
      )}
    </form>
  );
}
