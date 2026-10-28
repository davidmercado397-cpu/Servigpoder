"use client";

import { CLASES_ARL, pct, type ParametrosCosteo, type ParametrosDefecto } from "@/lib/liquidador";

/** % de aportes del empleador y provisión de prestaciones de un costeo de nómina. */
export function ParametrosCosteoForm({ valores, def, onCambio, deshabilitado = false }: {
  valores: ParametrosCosteo; def: ParametrosDefecto; onCambio: (v: ParametrosCosteo) => void; deshabilitado?: boolean;
}) {
  const campo = (k: string) => (
    <label key={k} className="block">
      <span className="label">{def.nombres[k]}</span>
      <span className="relative block">
        <input className="input pr-7 text-right" type="number" min={0} max={100} step="0.01" disabled={deshabilitado} value={pct(valores, k)}
          onChange={(e) => onCambio({ ...valores, [k]: Number(e.target.value) })} />
        <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-sm text-slate-400">%</span>
      </span>
    </label>
  );
  return (
    <div className="space-y-4">
      <div>
        <p className="mb-2 text-sm font-semibold text-slate-700">Aportes del empleador <span className="font-normal text-slate-500">(sobre el IBC; la ARL sin vacaciones ni incapacidad)</span></p>
        <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-5">{def.aportes.filter((k) => k !== "arl").map(campo)}</div>
        <div className="mt-3">
          <p className="label">ARL por clase de riesgo <span className="font-normal text-slate-500">(la clase de cada persona viene de la columna «arl» del Excel)</span></p>
          <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {CLASES_ARL.map(([n, romano]) => (
              <label key={n} className="block">
                <span className="text-xs text-slate-500">Clase {romano}</span>
                <span className="relative block">
                  <input className="input pr-7 text-right" type="number" min={0} max={100} step="0.001" disabled={deshabilitado}
                    value={valores.arl_tarifas[String(n)] ?? 0}
                    onChange={(e) => onCambio({ ...valores, arl_tarifas: { ...valores.arl_tarifas, [String(n)]: Number(e.target.value) } })} />
                  <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-sm text-slate-400">%</span>
                </span>
              </label>
            ))}
            <label className="block">
              <span className="text-xs text-slate-500">Si no trae clase</span>
              <select className="input" disabled={deshabilitado} value={valores.arl_clase} onChange={(e) => onCambio({ ...valores, arl_clase: Number(e.target.value) })}>
                {CLASES_ARL.map(([n, romano]) => <option key={n} value={n}>Clase {romano}</option>)}
              </select>
            </label>
          </div>
        </div>
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
