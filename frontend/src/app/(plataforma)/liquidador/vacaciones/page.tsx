"use client";

import { Check, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Alerta, Titulo } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";
import { MESES, pesos } from "@/lib/formato";
import { nombrePeriodo, type Periodo, type VacacionPeriodo } from "@/lib/liquidador";
import { usePermiso } from "@/lib/sesion";

export default function Vacaciones() {
  const gestionar = usePermiso("liquidador.nomina.gestionar");
  const [periodos, setPeriodos] = useState<Periodo[]>([]);
  const [pid, setPid] = useState<number | null>(null);
  const [lista, setLista] = useState<VacacionPeriodo[]>([]);
  const [promedios, setPromedios] = useState<Record<number, string>>({});
  const [guardando, setGuardando] = useState<number | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState("");
  const [aviso, setAviso] = useState("");

  useEffect(() => {
    api<Periodo[]>("/liquidador/periodos?tamano=50")
      .then((x) => {
        const calculados = x.filter((p) => p.estado !== "borrador");
        setPeriodos(calculados);
        if (calculados.length) setPid(calculados[0].id);
      })
      .catch((e) => setError(mensajeError(e)));
  }, []);

  const cargar = useCallback(async () => {
    if (pid === null) return;
    setCargando(true);
    try {
      const x = await api<VacacionPeriodo[]>(`/liquidador/periodos/${pid}/vacaciones`);
      setLista(x);
      setPromedios(Object.fromEntries(x.map((v) => [v.empleado_id, String(v.promedio)])));
    } finally {
      setCargando(false);
    }
  }, [pid]);

  useEffect(() => {
    setAviso("");
    cargar().catch((e) => setError(mensajeError(e)));
  }, [cargar]);

  async function guardar(v: VacacionPeriodo, promedio: number | null) {
    setError("");
    setGuardando(v.empleado_id);
    try {
      const x = await api<VacacionPeriodo>(`/liquidador/periodos/${pid}/vacaciones/${v.empleado_id}`, { method: "PUT", json: { promedio } });
      setLista((l) => l.map((y) => (y.empleado_id === x.empleado_id ? x : y)));
      setPromedios((p) => ({ ...p, [x.empleado_id]: String(x.promedio) }));
      setAviso(`Vacaciones de ${v.nombre}: ${promedio === null ? "se volvió al promedio sugerido" : "promedio guardado"} y se recalculó la nómina del periodo.`);
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setGuardando(null);
    }
  }

  const periodo = periodos.find((p) => p.id === pid);
  return (
    <div className="space-y-5">
      <Titulo>Vacaciones</Titulo>
      <p className="-mt-4 text-sm text-slate-500">
        Personas con días de vacaciones en el periodo. La base es el salario del empleado más un promedio variable: el sistema sugiere el
        promedio mensual del recargo nocturno de los 12 meses anteriores cargados aquí, y nómina puede corregirlo.
      </p>
      {error && <Alerta>{error}</Alerta>}
      {aviso && <Alerta tipo="ok">{aviso}</Alerta>}
      <div className="tarjeta overflow-hidden">
        <div className="flex flex-wrap items-center gap-3 px-4 py-3">
          <label className="text-sm text-slate-600" htmlFor="periodo">Periodo</label>
          <select id="periodo" className="input w-64" value={pid ?? ""} onChange={(e) => setPid(Number(e.target.value))}>
            {periodos.map((p) => (
              <option key={p.id} value={p.id}>{MESES[p.mes - 1]} {p.anio} · {nombrePeriodo(p)}{p.estado === "cerrada" ? " (cerrado)" : ""}</option>
            ))}
          </select>
          {periodo?.estado === "cerrada" && <span className="text-xs text-slate-500">Periodo cerrado: para cambiar el promedio, reábralo.</span>}
        </div>
        <div className="overflow-auto">
          <table className="tabla">
            <thead>
              <tr>
                <th>Empleado</th><th className="text-right">Días hábiles</th><th className="text-right">No hábiles</th>
                <th className="text-right">Salario</th><th>Promedio variable</th><th className="text-right">Base mensual</th>
                <th className="text-right">Valor vacaciones</th><th>Saldo</th>
              </tr>
            </thead>
            <tbody>
              {lista.map((v) => {
                const valor = promedios[v.empleado_id] ?? "";
                const cambiado = valor.trim() !== "" && Number(valor) !== v.promedio;
                const editable = gestionar && v.editable;
                return (
                  <tr key={v.empleado_id} className="align-top">
                    <td>
                      <span className="font-medium">{v.nombre}</span>
                      <span className="block font-mono text-xs text-slate-500">{v.documento}</span>
                      <span className="block text-xs text-slate-500">Hábiles: {v.dias_habiles_empleado}</span>
                    </td>
                    <td className="text-right tabular-nums">{v.dias_habiles}</td>
                    <td className="text-right tabular-nums">{v.dias_no_habiles}</td>
                    <td className="text-right tabular-nums">{pesos(v.salario)}</td>
                    <td className="whitespace-nowrap">
                      <span className="flex items-center gap-1">
                        <input className="input w-32 text-right" type="number" min={0} disabled={!editable || guardando === v.empleado_id} value={valor}
                          onChange={(e) => setPromedios((p) => ({ ...p, [v.empleado_id]: e.target.value }))}
                          onKeyDown={(e) => { if (e.key === "Enter" && cambiado) guardar(v, Number(valor)); }} />
                        {editable && cambiado && (
                          <button className="rounded-md p-1 text-green-700 hover:bg-green-50" aria-label="Guardar promedio" onClick={() => guardar(v, Number(valor))}>
                            <Check className="h-4 w-4" />
                          </button>
                        )}
                        {editable && v.promedio_manual && !cambiado && (
                          <button className="rounded-md p-1 text-slate-500 hover:bg-slate-100" title="Volver al sugerido" aria-label="Volver al promedio sugerido"
                            onClick={() => guardar(v, null)}>
                            <RotateCcw className="h-4 w-4" />
                          </button>
                        )}
                      </span>
                      <span className="mt-1 block text-xs text-slate-500">
                        {v.promedio_manual ? "Fijado por nómina · " : ""}Sugerido {pesos(v.promedio_sugerido)}
                        {v.meses_promedio ? ` (${v.meses_promedio.toLocaleString("es-CO")} meses)` : " (sin periodos anteriores)"}
                      </span>
                    </td>
                    <td className="text-right tabular-nums">{pesos(v.base)}<span className="block text-xs text-slate-500">día {pesos(v.valor_dia)}</span></td>
                    <td className="text-right tabular-nums">
                      <b>{pesos(v.valor)}</b>
                      <span className="block text-xs text-slate-500">hábiles {pesos(v.valor_habiles)}</span>
                      {v.dias_no_habiles > 0 && <span className="block text-xs text-slate-500">no hábiles {pesos(v.valor_no_habiles)}</span>}
                    </td>
                    <td className="text-sm">
                      {v.saldo ? (
                        <span className={v.saldo.pendientes < 0 ? "font-semibold text-red-700" : ""}>{v.saldo.pendientes.toLocaleString("es-CO")} días pendientes</span>
                      ) : <span className="text-slate-500">Sin fecha de ingreso</span>}
                      {v.alertas.map((a) => <span key={a} className="mt-1 block max-w-xs text-xs text-amber-800">{a}</span>)}
                    </td>
                  </tr>
                );
              })}
              {!cargando && lista.length === 0 && (
                <tr><td colSpan={8} className="py-6 text-center text-sm text-slate-500">
                  {periodos.length ? "Nadie tiene días de vacaciones en este periodo." : "Todavía no hay periodos calculados."}
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
