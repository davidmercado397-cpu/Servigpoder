"use client";

import { Check, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Alerta, Titulo } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";
import { MESES, pesos } from "@/lib/formato";
import { nombrePeriodo, type Periodo, type VacacionPeriodo } from "@/lib/liquidador";
import { usePermiso } from "@/lib/sesion";

type Fila = VacacionPeriodo & { nomina: Periodo };
const claveDe = (p: Pick<Periodo, "anio" | "mes" | "quincena">) => `${p.anio}-${p.mes}-${p.quincena}`;
const clave = (v: Fila) => `${v.nomina.id}-${v.empleado_id}`;

export default function Vacaciones() {
  const gestionar = usePermiso("liquidador.nomina.gestionar");
  const [periodos, setPeriodos] = useState<Periodo[]>([]);
  const [grupo, setGrupo] = useState("");  // año-mes-quincena
  const [nominaId, setNominaId] = useState<number | "todas">("todas");
  const [lista, setLista] = useState<Fila[]>([]);
  const [promedios, setPromedios] = useState<Record<string, string>>({});
  const [guardando, setGuardando] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState("");
  const [aviso, setAviso] = useState("");

  useEffect(() => {
    api<Periodo[]>("/liquidador/periodos?tamano=150")
      .then((x) => {
        const calculados = x.filter((p) => p.estado !== "borrador");
        setPeriodos(calculados);
        if (calculados.length) setGrupo(claveDe(calculados[0]));
      })
      .catch((e) => setError(mensajeError(e)));
  }, []);

  // Periodos (quincena o mes) sin repetir, y las nóminas del elegido
  const grupos = useMemo(() => {
    const vistos = new Map<string, Periodo>();
    periodos.forEach((p) => { if (!vistos.has(claveDe(p))) vistos.set(claveDe(p), p); });
    return [...vistos.entries()];
  }, [periodos]);
  const nominas = useMemo(() => periodos.filter((p) => claveDe(p) === grupo), [periodos, grupo]);

  const cargar = useCallback(async () => {
    const elegidas = nominaId === "todas" ? nominas : nominas.filter((p) => p.id === nominaId);
    if (!elegidas.length) { setLista([]); return; }
    setCargando(true);
    try {
      const partes = await Promise.all(elegidas.map(async (n) =>
        (await api<VacacionPeriodo[]>(`/liquidador/periodos/${n.id}/vacaciones`)).map((v) => ({ ...v, nomina: n }))));
      const x = partes.flat().sort((a, b) => a.nombre.localeCompare(b.nombre));
      setLista(x);
      setPromedios(Object.fromEntries(x.map((v) => [clave(v), String(v.promedio)])));
    } finally {
      setCargando(false);
    }
  }, [nominas, nominaId]);

  useEffect(() => {
    setAviso("");
    cargar().catch((e) => setError(mensajeError(e)));
  }, [cargar]);

  async function guardar(v: Fila, promedio: number | null) {
    setError("");
    setGuardando(clave(v));
    try {
      const x = await api<VacacionPeriodo>(`/liquidador/periodos/${v.nomina.id}/vacaciones/${v.empleado_id}`, { method: "PUT", json: { promedio } });
      const nueva: Fila = { ...x, nomina: v.nomina };
      setLista((l) => l.map((y) => (clave(y) === clave(nueva) ? nueva : y)));
      setPromedios((p) => ({ ...p, [clave(nueva)]: String(x.promedio) }));
      setAviso(`Vacaciones de ${v.nombre}: ${promedio === null ? "se volvió al promedio sugerido" : "promedio guardado"} y se recalculó la nómina «${v.nomina.nombre}».`);
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setGuardando(null);
    }
  }

  const variasNominas = nominaId === "todas" && nominas.length > 1;
  const cerradas = nominas.filter((p) => p.estado === "cerrada" && (nominaId === "todas" || p.id === nominaId));
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
          <select id="periodo" className="input w-60" value={grupo} onChange={(e) => { setGrupo(e.target.value); setNominaId("todas"); }}>
            {grupos.map(([k, p]) => <option key={k} value={k}>{MESES[p.mes - 1]} {p.anio} · {nombrePeriodo(p)}</option>)}
          </select>
          <label className="text-sm text-slate-600" htmlFor="nomina">Nómina</label>
          <select id="nomina" className="input w-64" value={nominaId} onChange={(e) => setNominaId(e.target.value === "todas" ? "todas" : Number(e.target.value))}>
            <option value="todas">Todas las nóminas ({nominas.length})</option>
            {nominas.map((p) => <option key={p.id} value={p.id}>{p.nombre}{p.estado === "cerrada" ? " (cerrada)" : ""}</option>)}
          </select>
          {lista.length > 0 && <span className="text-sm text-slate-500">{lista.length} {lista.length === 1 ? "persona" : "personas"}</span>}
          {cerradas.length > 0 && (
            <span className="text-xs text-slate-500">
              {cerradas.length === 1 ? `La nómina «${cerradas[0].nombre}» está cerrada` : `${cerradas.length} nóminas están cerradas`}: para cambiar el promedio, reábrala.
            </span>
          )}
        </div>
        <div className="overflow-auto">
          <table className="tabla">
            <thead>
              <tr>
                <th>Empleado</th>{variasNominas && <th>Nómina</th>}<th className="text-right">Días hábiles</th><th className="text-right">No hábiles</th>
                <th className="text-right">Salario</th><th>Promedio variable</th><th className="text-right">Base mensual</th>
                <th className="text-right">Valor vacaciones</th><th>Saldo</th>
              </tr>
            </thead>
            <tbody>
              {lista.map((v) => {
                const valor = promedios[clave(v)] ?? "";
                const cambiado = valor.trim() !== "" && Number(valor) !== v.promedio;
                const editable = gestionar && v.editable;
                return (
                  <tr key={clave(v)} className="align-top">
                    <td>
                      <span className="font-medium">{v.nombre}</span>
                      <span className="block font-mono text-xs text-slate-500">{v.documento}</span>
                      <span className="block text-xs text-slate-500">Hábiles: {v.dias_habiles_empleado}</span>
                    </td>
                    {variasNominas && <td className="whitespace-nowrap text-sm">{v.nomina.nombre}{v.nomina.estado === "cerrada" && <span className="block text-xs text-slate-500">cerrada</span>}</td>}
                    <td className="text-right tabular-nums">{v.dias_habiles}</td>
                    <td className="text-right tabular-nums">{v.dias_no_habiles}</td>
                    <td className="text-right tabular-nums">{pesos(v.salario)}</td>
                    <td className="whitespace-nowrap">
                      <span className="flex items-center gap-1">
                        <input className="input w-32 text-right" type="number" min={0} disabled={!editable || guardando === clave(v)} value={valor}
                          onChange={(e) => setPromedios((p) => ({ ...p, [clave(v)]: e.target.value }))}
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
                <tr><td colSpan={variasNominas ? 9 : 8} className="py-6 text-center text-sm text-slate-500">
                  {periodos.length ? nominaId === "todas" ? "Nadie tiene días de vacaciones en las nóminas de este periodo." : "Nadie tiene días de vacaciones en esta nómina." : "Todavía no hay periodos calculados."}
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
