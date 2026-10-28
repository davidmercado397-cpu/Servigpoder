"use client";

import type { ParametrosCosteo, ParametrosDefecto } from "@/lib/liquidador";

/** % de aportes del empleador y provisión de prestaciones de un costeo de nómina. */
export function ParametrosCosteoForm({ valores, def, onCambio, deshabilitado = false }: {
  valores: ParametrosCosteo; def: ParametrosDefecto; onCambio: (v: ParametrosCosteo) => void; deshabilitado?: boolean;
}) {
  const campo = (k: string) => (
    <label key={k} className="block">
      <span className="label">{def.nombres[k]}</span>
      <span className="relative block">
        <input className="input pr-7 text-right" type="number" min={0} max={100} step="0.01" disabled={deshabilitado} value={Number(valores[k])}
          onChange={(e) => onCambio({ ...valores, [k]: Number(e.target.value) })} />
        <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-sm text-slate-400">%</span>
      </span>
    </label>
  );
  return (
    <div className="space-y-4">
      <div>
        <p className="mb-2 text-sm font-semibold text-slate-700">Aportes del empleador <span className="font-normal text-slate-500">(sobre el IBC; la ARL sin vacaciones ni incapacidad)</span></p>
        <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">{def.aportes.map(campo)}</div>
        <label className="mt-3 flex items-start gap-2 text-sm text-slate-700">
          <input type="checkbox" className="mt-0.5 h-4 w-4" disabled={deshabilitado} checked={valores.exonerado}
            onChange={(e) => onCambio({ ...valores, exonerado: e.target.checked })} />
          <span>Exonerada de salud, ICBF y SENA<span className="block text-xs text-slate-500">Art. 114-1 del Estatuto Tributario: no se pagan por quien gana menos de 10 salarios mínimos.</span></span>
        </label>
      </div>
      <div>
        <p className="mb-2 text-sm font-semibold text-slate-700">Prestaciones <span className="font-normal text-slate-500">(prima, cesantías e intereses sobre lo salarial + auxilio de transporte; vacaciones sobre básico + recargo nocturno)</span></p>
        <div className="grid gap-3 sm:grid-cols-4">{def.prestaciones.map(campo)}</div>
      </div>
    </div>
  );
}
