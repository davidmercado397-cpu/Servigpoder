"use client";

import { CalendarPlus, Save, Scale, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Alerta, Insignia, Titulo } from "@/components/ui";
import { api, apiEnvelope, mensajeError } from "@/lib/api";
import { pesos } from "@/lib/formato";
import { CONCEPTOS_PAGO, RECARGOS, type Tarifa } from "@/lib/liquidador";
import { usePermiso } from "@/lib/sesion";

type Ley = Record<"dominical_80" | "dominical_90" | "dominical_100", Record<string, number>>;
type Formulario = Omit<Tarifa, "id" | "actualizado_en">;

const formulario = ({ vigente_desde, smlmv, auxilio_transporte, horas_mes, salud_pct, pension_pct, porcentajes, nota }: Tarifa): Formulario =>
  ({ vigente_desde, smlmv, auxilio_transporte, horas_mes, salud_pct, pension_pct, porcentajes: { ...porcentajes }, nota });

const fechaLarga = (iso: string) => new Date(iso + "T12:00:00").toLocaleDateString("es-CO", { day: "numeric", month: "long", year: "numeric" });

export default function Recargos() {
  const gestionar = usePermiso("liquidador.nomina.gestionar");
  const [lista, setLista] = useState<Tarifa[]>([]);
  const [vigenteId, setVigenteId] = useState<number | null>(null);
  const [ley, setLey] = useState<Ley | null>(null);
  const [sel, setSel] = useState<number | "nueva" | null>(null);
  const [f, setF] = useState<Formulario | null>(null);
  const [error, setError] = useState("");
  const [aviso, setAviso] = useState("");
  const [ocupado, setOcupado] = useState(false);

  const cargar = useCallback(async (elegir?: number) => {
    const r = await apiEnvelope<Tarifa[]>("/liquidador/tarifas");
    const datos = r.data ?? [];
    const vigente = (r.meta.extra?.vigente_id as number | null) ?? null;
    setLista(datos);
    setVigenteId(vigente);
    setLey((r.meta.extra?.ley as Ley) ?? null);
    const id = elegir ?? vigente ?? datos[0]?.id ?? null;
    const t = datos.find((x) => x.id === id);
    setSel(id);
    if (t) setF(formulario(t));
  }, []);

  useEffect(() => {
    cargar().catch((e) => setError(mensajeError(e)));
  }, [cargar]);

  const valorHora = f ? f.smlmv / (f.horas_mes || 1) : 0;
  const cambios = useMemo(() => {
    const t = lista.find((x) => x.id === sel);
    return !!f && (!t || JSON.stringify(formulario(t)) !== JSON.stringify(f));
  }, [f, lista, sel]);

  function elegir(t: Tarifa) {
    if (cambios && !window.confirm("Hay cambios sin guardar. ¿Descartarlos?")) return;
    setSel(t.id);
    setF(formulario(t));
    setAviso("");
    setError("");
  }

  function nuevaVigencia() {
    if (!f) return;
    const hoy = new Date();
    const siguiente = new Date(hoy.getFullYear(), hoy.getMonth() + 1, 1);
    setSel("nueva");
    setF({ ...f, vigente_desde: `${siguiente.getFullYear()}-${String(siguiente.getMonth() + 1).padStart(2, "0")}-01`, nota: "" });
    setAviso("");
  }

  async function guardar() {
    if (!f) return;
    setError("");
    setAviso("");
    setOcupado(true);
    try {
      const t = sel === "nueva"
        ? await api<Tarifa>("/liquidador/tarifas", { method: "POST", json: f })
        : await api<Tarifa>(`/liquidador/tarifas/${sel}`, { method: "PUT", json: f });
      await cargar(t.id);
      setAviso("Tarifa guardada. Los periodos ya calculados cambian solo si se recalculan; los cerrados no cambian.");
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setOcupado(false);
    }
  }

  async function eliminar() {
    if (sel === "nueva" || sel === null || !f) return;
    if (!window.confirm(`¿Eliminar la tarifa vigente desde el ${fechaLarga(f.vigente_desde)}? Los días desde esa fecha usarán la tarifa anterior.`)) return;
    try {
      await api(`/liquidador/tarifas/${sel}`, { method: "DELETE" });
      await cargar();
    } catch (e) {
      setError(mensajeError(e));
    }
  }

  const pct = (k: string, v: number) => f && setF({ ...f, porcentajes: { ...f.porcentajes, [k]: v } });
  const num = (v: string) => (v === "" ? 0 : Number(v));

  return (
    <div className="space-y-5">
      <Titulo>Recargos y salario</Titulo>
      <p className="-mt-4 text-sm text-slate-500">
        Valores con los que se liquida la nómina. Cada tarifa rige desde su fecha: cada día se paga con la tarifa vigente ese día,
        así un cambio de ley (p. ej. el recargo dominical al 100 % desde el 1-jul-2027) se registra como una nueva vigencia sin alterar lo anterior.
      </p>
      {error && <Alerta>{error}</Alerta>}
      {aviso && <Alerta tipo="ok">{aviso}</Alerta>}

      <div className="grid gap-5 lg:grid-cols-[240px_1fr]">
        <aside className="tarjeta h-fit p-3">
          <h2 className="mb-2 px-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Vigencias</h2>
          <ul className="space-y-1">
            {sel === "nueva" && f && (
              <li className="rounded-md bg-marca-50 px-3 py-2 text-sm font-semibold text-marca-800">Nueva · desde {fechaLarga(f.vigente_desde)}</li>
            )}
            {lista.map((t) => (
              <li key={t.id}>
                <button onClick={() => elegir(t)}
                  className={`w-full rounded-md px-3 py-2 text-left text-sm ${sel === t.id ? "bg-marca-50 font-semibold text-marca-800" : "hover:bg-slate-50"}`}>
                  Desde {fechaLarga(t.vigente_desde)}
                  {t.id === vigenteId && <Insignia color="ml-1 bg-green-100 text-green-800">Vigente hoy</Insignia>}
                  <span className="block text-xs font-normal text-slate-500">Dominical {t.porcentajes.sunday_surcharge} % · {pesos(t.smlmv)}</span>
                </button>
              </li>
            ))}
          </ul>
          {gestionar && sel !== "nueva" && (
            <button onClick={nuevaVigencia} className="btn-secundario mt-3 inline-flex w-full items-center justify-center gap-1.5">
              <CalendarPlus className="h-4 w-4" /> Nueva vigencia
            </button>
          )}
        </aside>

        {f && (
          <section className="tarjeta space-y-5 p-5">
            <div className="grid gap-4 sm:grid-cols-3">
              <Campo etiqueta="Vigente desde">
                <input type="date" className="input" value={f.vigente_desde} disabled={!gestionar} onChange={(e) => setF({ ...f, vigente_desde: e.target.value })} />
              </Campo>
              <Campo etiqueta="Salario mínimo mensual" ayuda="Salario de quien no tiene uno propio en Empleados">
                <input type="number" min={1} className="input" value={f.smlmv} disabled={!gestionar} onChange={(e) => setF({ ...f, smlmv: num(e.target.value) })} />
              </Campo>
              <Campo etiqueta="Auxilio de transporte mensual" ayuda="Por día trabajado o de descanso, hasta 2 mínimos">
                <input type="number" min={0} className="input" value={f.auxilio_transporte} disabled={!gestionar} onChange={(e) => setF({ ...f, auxilio_transporte: num(e.target.value) })} />
              </Campo>
              <Campo etiqueta="Horas del mes" ayuda={`Valor de la hora con el mínimo: ${pesos(valorHora)}`}>
                <input type="number" min={100} max={300} className="input" value={f.horas_mes} disabled={!gestionar} onChange={(e) => setF({ ...f, horas_mes: num(e.target.value) })} />
              </Campo>
              <Campo etiqueta="Salud (empleado) %">
                <input type="number" min={0} max={100} step="0.01" className="input" value={f.salud_pct} disabled={!gestionar} onChange={(e) => setF({ ...f, salud_pct: num(e.target.value) })} />
              </Campo>
              <Campo etiqueta="Pensión (empleado) %">
                <input type="number" min={0} max={100} step="0.01" className="input" value={f.pension_pct} disabled={!gestionar} onChange={(e) => setF({ ...f, pension_pct: num(e.target.value) })} />
              </Campo>
            </div>

            <div>
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <h3 className="font-semibold text-slate-900">Recargos y horas extras</h3>
                {gestionar && ley && (
                  <div className="ml-auto flex items-center gap-1.5 text-sm">
                    <Scale className="h-4 w-4 text-slate-500" /> Llenar con la ley, dominical al
                    {(["dominical_80", "dominical_90", "dominical_100"] as const).map((k) => (
                      <button key={k} className="rounded-md border border-slate-300 px-2 py-0.5 hover:bg-slate-50" onClick={() => setF({ ...f, porcentajes: { ...ley[k] } })}>
                        {k.split("_")[1]} %
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <div className="overflow-auto rounded-lg border border-slate-200">
                <table className="tabla text-sm">
                  <thead>
                    <tr><th>Concepto</th><th>Se paga</th><th className="w-36 text-right">%</th><th className="text-right">Una hora con el mínimo</th></tr>
                  </thead>
                  <tbody>
                    {CONCEPTOS_PAGO.map(([k, largo]) => {
                      const recargo = RECARGOS.includes(k);
                      const v = f.porcentajes[k] ?? 0;
                      return (
                        <tr key={k}>
                          <td className="font-medium">{largo}</td>
                          <td className="text-xs text-slate-500">{recargo ? "Solo el adicional (la hora ya está en el salario)" : "La hora completa con su recargo"}</td>
                          <td className="text-right">
                            <input type="number" min={0} max={500} step="0.01" className="input w-28 text-right" value={v} disabled={!gestionar}
                              onChange={(e) => pct(k, num(e.target.value))} />
                          </td>
                          <td className="text-right tabular-nums text-slate-600">{pesos((valorHora * v) / 100)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            <Campo etiqueta="Nota (norma o motivo del cambio)">
              <input className="input" maxLength={300} value={f.nota} disabled={!gestionar} onChange={(e) => setF({ ...f, nota: e.target.value })} />
            </Campo>

            {gestionar && (
              <div className="flex flex-wrap gap-2">
                <button className="btn-primario inline-flex items-center gap-1.5" disabled={ocupado || !cambios} onClick={guardar}>
                  <Save className="h-4 w-4" /> {sel === "nueva" ? "Crear vigencia" : "Guardar cambios"}
                </button>
                {sel === "nueva" ? (
                  <button className="btn-secundario" onClick={() => cargar()}>Cancelar</button>
                ) : lista.length > 1 && (
                  <button className="ml-auto inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-sm text-slate-500 hover:bg-red-50 hover:text-red-700" onClick={eliminar}>
                    <Trash2 className="h-4 w-4" /> Eliminar vigencia
                  </button>
                )}
              </div>
            )}
          </section>
        )}
      </div>
    </div>
  );
}

function Campo({ etiqueta, ayuda, children }: { etiqueta: string; ayuda?: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="label">{etiqueta}</label>
      {children}
      {ayuda && <p className="mt-1 text-xs text-slate-500">{ayuda}</p>}
    </div>
  );
}
