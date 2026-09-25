"use client";

import { useEffect, useState } from "react";
import { api, type MesDisponible } from "@/lib/api";
import { nombreMes } from "@/lib/formato";

/** Selector del mes con programación; entrega el análisis vigente de ese mes. */
export function useMesAnalizado() {
  const [meses, setMeses] = useState<MesDisponible[]>([]);
  const [mes, setMes] = useState<MesDisponible | null>(null);
  const [cargado, setCargado] = useState(false);

  useEffect(() => {
    api<MesDisponible[]>("/analisis/meses").then((m) => {
      setMeses(m);
      setMes(m.find((x) => x.analisis_id) ?? m[0] ?? null);
      setCargado(true);
    });
  }, []);

  const selector =
    meses.length > 0 ? (
      <select className="input w-52" value={mes?.carga_id ?? ""} onChange={(e) => setMes(meses.find((m) => m.carga_id === Number(e.target.value)) ?? null)}>
        {meses.map((m) => (
          <option key={m.carga_id} value={m.carga_id}>{nombreMes(m.anio, m.mes)}{m.analisis_id ? "" : " (sin análisis)"}</option>
        ))}
      </select>
    ) : null;

  return { mes, analisisId: mes?.analisis_id ?? null, selector, cargado };
}
