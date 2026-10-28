"use client";

import { Check, Pencil, Search, TreePalm, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Paginador, metaDe, usePaginacion, type MetaPagina } from "@/components/paginacion";
import { Alerta, Titulo } from "@/components/ui";
import { api, apiEnvelope, mensajeError } from "@/lib/api";
import { pesos } from "@/lib/formato";
import { CLASES_ARL, DIAS_SEMANA, type Empleado } from "@/lib/liquidador";
import { usePermiso } from "@/lib/sesion";

export default function Empleados() {
  const verNomina = usePermiso("liquidador.nomina.ver");
  const gestionarNomina = usePermiso("liquidador.nomina.gestionar");
  const [editando, setEditando] = useState<{ id: number; valor: string } | null>(null);
  const [vac, setVac] = useState<{ e: Empleado; dias: number[]; ingreso: string; previas: string; arl: string } | null>(null);
  const [aviso, setAviso] = useState("");
  const [lista, setLista] = useState<Empleado[]>([]);
  const [meta, setMeta] = useState<MetaPagina | null>(null);
  const [q, setQ] = useState("");
  const [error, setError] = useState("");
  const pag = usePaginacion([q]);

  const cargar = useCallback(async () => {
    const r = await apiEnvelope<Empleado[]>(`/liquidador/empleados?q=${encodeURIComponent(q)}&${pag.query}`);
    setLista(r.data ?? []);
    setMeta(metaDe(r));
  }, [q, pag.query]);

  useEffect(() => {
    const t = setTimeout(() => cargar().catch((e) => setError(mensajeError(e))), 250);
    return () => clearTimeout(t);
  }, [cargar]);

  async function guardarSalario(e: Empleado, valor: string) {
    setError("");
    try {
      await api(`/liquidador/empleados/${e.id}/salario`, { method: "PUT", json: { salario: valor.trim() ? Number(valor) : null } });
      setEditando(null);
      setAviso(`Salario de ${e.nombre} actualizado. Se aplica al calcular o recalcular cada periodo.`);
      await cargar();
    } catch (err) {
      setError(mensajeError(err));
    }
  }

  async function guardarVacaciones() {
    if (!vac) return;
    setError("");
    try {
      await api(`/liquidador/empleados/${vac.e.id}/configuracion`, {
        method: "PUT", json: { dias_habiles: vac.dias, fecha_ingreso: vac.ingreso || null, vacaciones_previas: Number(vac.previas || 0),
          arl_clase: vac.arl ? Number(vac.arl) : null },
      });
      setAviso(`Configuración de ${vac.e.nombre} actualizada. Los periodos ya calculados cambian solo si se recalculan.`);
      setVac(null);
      await cargar();
    } catch (err) {
      setError(mensajeError(err));
    }
  }

  const habilesTexto = (d: number[]) => {
    const s = [...d].sort();
    const seguidos = s.length > 2 && s.every((x, i) => i === 0 || x === s[i - 1] + 1);
    return seguidos ? `${DIAS_SEMANA[s[0]]} a ${DIAS_SEMANA[s[s.length - 1]].toLowerCase()}` : s.map((x) => DIAS_SEMANA[x].slice(0, 3)).join(", ");
  };

  return (
    <div className="space-y-5">
      <Titulo>Empleados</Titulo>
      <p className="-mt-4 text-sm text-slate-500">Consulta histórica: se crean y actualizan solos al cargar el Excel de cada periodo.</p>
      {error && <Alerta>{error}</Alerta>}
      {aviso && <Alerta tipo="ok">{aviso}</Alerta>}
      {vac && (
        <div className="tarjeta space-y-4 p-5">
          <div className="flex items-center">
            <h2 className="font-semibold text-slate-900">Configuración de {vac.e.nombre}</h2>
            <button type="button" className="ml-auto rounded-md p-1 text-slate-500 hover:bg-slate-100" onClick={() => setVac(null)} aria-label="Cerrar"><X className="h-5 w-5" /></button>
          </div>
          <div>
            <p className="label">Días hábiles para vacaciones</p>
            <div className="flex flex-wrap gap-x-4 gap-y-2">
              {DIAS_SEMANA.map((nombre, i) => (
                <label key={nombre} className="flex items-center gap-1.5 text-sm text-slate-700">
                  <input type="checkbox" className="h-4 w-4" checked={vac.dias.includes(i)}
                    onChange={(ev) => setVac({ ...vac, dias: ev.target.checked ? [...vac.dias, i].sort() : vac.dias.filter((x) => x !== i) })} />
                  {nombre}
                </label>
              ))}
            </div>
            <p className="mt-1 text-xs text-slate-500">Los festivos nunca son hábiles. Los días de vacaciones que no sean hábiles también se pagan, pero no descuentan del saldo.</p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <label className="label">Clase de riesgo ARL</label>
              <select className="input" value={vac.arl} onChange={(ev) => setVac({ ...vac, arl: ev.target.value })}>
                <option value="">Sin definir</option>
                {CLASES_ARL.map(([n, romano]) => <option key={n} value={n}>Clase {romano}</option>)}
              </select>
            </div>
            <div>
              <label className="label">Fecha de ingreso</label>
              <input className="input" type="date" value={vac.ingreso} onChange={(ev) => setVac({ ...vac, ingreso: ev.target.value })} />
              <p className="mt-1 text-xs text-slate-500">Con ella se calcula el saldo: 15 días hábiles por año trabajado.</p>
            </div>
            <div>
              <label className="label">Días hábiles disfrutados antes del liquidador</label>
              <input className="input" type="number" min={0} step="0.5" value={vac.previas} onChange={(ev) => setVac({ ...vac, previas: ev.target.value })} />
              <p className="mt-1 text-xs text-slate-500">Vacaciones tomadas desde el ingreso que no están en los periodos cargados aquí.</p>
            </div>
          </div>
          <div className="flex gap-2">
            <button className="btn-primario" disabled={vac.dias.length === 0} onClick={guardarVacaciones}>Guardar</button>
            <button className="btn-secundario" onClick={() => setVac(null)}>Cancelar</button>
          </div>
        </div>
      )}
      <div className="tarjeta overflow-hidden">
        <div className="px-4 py-3">
          <div className="relative w-72">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input className="input pl-8" placeholder="Buscar por cédula o nombre…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
        </div>
        <div className="overflow-auto">
          <table className="tabla">
            <thead><tr><th>Documento</th><th>Nombre</th><th>Cargo</th><th>Último periodo</th><th className="text-right">Periodos</th>{verNomina && <th>Salario mensual</th>}<th>ARL</th><th>Vacaciones</th></tr></thead>
            <tbody>
              {lista.map((e) => (
                <tr key={e.id}>
                  <td className="font-mono">{e.documento}</td>
                  <td>{e.nombre}</td>
                  <td>{e.cargo}</td>
                  <td>{e.ultima ?? "—"}</td>
                  <td className="text-right tabular-nums">{e.quincenas}</td>
                  {verNomina && (
                    <td className="whitespace-nowrap">
                      {editando?.id === e.id ? (
                        <span className="flex items-center gap-1">
                          <input className="input w-36" type="number" min={1} placeholder="Vacío = mínimo" autoFocus value={editando.valor}
                            onChange={(ev) => setEditando({ id: e.id, valor: ev.target.value })}
                            onKeyDown={(ev) => { if (ev.key === "Enter") guardarSalario(e, editando.valor); if (ev.key === "Escape") setEditando(null); }} />
                          <button className="rounded-md p-1 text-green-700 hover:bg-green-50" onClick={() => guardarSalario(e, editando.valor)} aria-label="Guardar"><Check className="h-4 w-4" /></button>
                          <button className="rounded-md p-1 text-slate-500 hover:bg-slate-100" onClick={() => setEditando(null)} aria-label="Cancelar"><X className="h-4 w-4" /></button>
                        </span>
                      ) : (
                        <span className="flex items-center gap-1">
                          {e.salario ? <span className="tabular-nums">{pesos(e.salario)}</span> : <span className="text-slate-500">Salario mínimo</span>}
                          {gestionarNomina && (
                            <button className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700" aria-label="Editar salario"
                              onClick={() => setEditando({ id: e.id, valor: e.salario?.toString() ?? "" })}><Pencil className="h-3.5 w-3.5" /></button>
                          )}
                        </span>
                      )}
                    </td>
                  )}
                  <td className="whitespace-nowrap text-sm">
                    {e.arl_clase ? `Clase ${CLASES_ARL.find(([n]) => n === e.arl_clase)?.[1]}` : <span className="text-slate-500">Sin definir</span>}
                  </td>
                  <td className="whitespace-nowrap text-sm">
                    <span className="flex items-center gap-1">
                      <span>
                        <span className="block text-xs text-slate-500">Hábiles: {habilesTexto(e.dias_habiles)}</span>
                        {e.saldo_vacaciones ? (
                          <span className={`tabular-nums ${e.saldo_vacaciones.pendientes < 0 ? "font-semibold text-red-700" : ""}`}>
                            {e.saldo_vacaciones.pendientes.toLocaleString("es-CO")} días pendientes
                          </span>
                        ) : <span className="text-slate-500">Sin fecha de ingreso</span>}
                      </span>
                      {gestionarNomina && (
                        <button className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700" aria-label="Configurar ARL y vacaciones"
                          title="Configurar ARL y vacaciones"
                          onClick={() => { setAviso(""); setVac({ e, dias: e.dias_habiles, ingreso: e.fecha_ingreso ?? "", previas: String(e.vacaciones_previas || ""), arl: e.arl_clase ? String(e.arl_clase) : "" }); }}>
                          <TreePalm className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Paginador meta={meta} onPagina={pag.setPagina} onTamano={pag.setTamano} />
      </div>
    </div>
  );
}
