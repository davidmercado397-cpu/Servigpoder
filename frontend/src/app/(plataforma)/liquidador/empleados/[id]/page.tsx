"use client";

import { ArrowLeft, ArrowRight, Pencil, Plus, Trash2, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { DatosPersonalesForm, HistorialLaboral, HistorialVacaciones } from "@/components/ficha-personal";
import { FormularioAuxilio } from "@/components/formulario-auxilio";
import { FormularioDescuento } from "@/components/formulario-descuento";
import { Alerta, Insignia } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";
import { MESES, pesos } from "@/lib/formato";
import {
  CLASES_ARL, DIAS_SEMANA, ESTADO_PERIODO, QUINCENAS, TIPOS_DESCUENTO, horas, nombrePeriodo, type Auxilio, type Contrato, type DatosPersonales,
  type Descuento, type Empleado, type SalidaVacaciones, type TramoVacaciones,
} from "@/lib/liquidador";
import { usePermiso } from "@/lib/sesion";

type NominaFicha = {
  periodo_id: number; etiqueta: string; anio: number; mes: number; quincena: number; nombre: string; estado: string;
  total_horas: number; dias: Record<string, number>; alertas: number; devengado?: number; neto?: number;
};
type Ficha = Empleado & {
  nominas: NominaFicha[];
  /** Solo con el permiso de la ficha del personal */
  personal?: DatosPersonales; contratos?: Contrato[]; salidas?: SalidaVacaciones[]; vacaciones_liquidadas?: TramoVacaciones[];
};
type Datos = { salario: string; arl: string; dias: number[]; ingreso: string; previas: string };

const datosDe = (f: Ficha): Datos => ({
  salario: f.salario?.toString() ?? "", arl: f.arl_clase ? String(f.arl_clase) : "", dias: f.dias_habiles,
  ingreso: f.fecha_ingreso ?? "", previas: f.vacaciones_previas ? String(f.vacaciones_previas) : "",
});

export default function FichaEmpleado() {
  const { id } = useParams<{ id: string }>();
  const verNomina = usePermiso("liquidador.nomina.ver");
  const gestionar = usePermiso("liquidador.nomina.gestionar");
  const gestionarPersonal = usePermiso("liquidador.personal.gestionar");
  const [version, setVersion] = useState(0);
  const [f, setF] = useState<Ficha | null>(null);
  const [d, setD] = useState<Datos | null>(null);
  const [descuentos, setDescuentos] = useState<Descuento[]>([]);
  const [auxilios, setAuxilios] = useState<Auxilio[]>([]);
  const [editDesc, setEditDesc] = useState<{ registro: Descuento | null } | null>(null);
  const [editAux, setEditAux] = useState<{ registro: Auxilio | null } | null>(null);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState("");
  const [aviso, setAviso] = useState("");

  const cargarFicha = useCallback(async () => {
    const x = await api<Ficha>(`/liquidador/empleados/${id}`);
    setF(x);
    setD(datosDe(x));
    setVersion((v) => v + 1);
  }, [id]);

  const cargarDescuentos = useCallback(async () => {
    if (!verNomina) return;
    const [ds, as] = await Promise.all([
      api<Descuento[]>(`/liquidador/descuentos?empleado_id=${id}&tamano=150`),
      api<Auxilio[]>(`/liquidador/auxilios?empleado_id=${id}&tamano=150`),
    ]);
    setDescuentos(ds);
    setAuxilios(as);
  }, [id, verNomina]);

  useEffect(() => {
    cargarFicha().catch((e) => setError(mensajeError(e)));
  }, [cargarFicha]);

  useEffect(() => {
    cargarDescuentos().catch((e) => setError(mensajeError(e)));
  }, [cargarDescuentos]);

  async function guardar() {
    if (!d) return;
    setError("");
    setAviso("");
    setGuardando(true);
    try {
      await api(`/liquidador/empleados/${id}/ficha`, {
        method: "PUT",
        json: { salario: d.salario.trim() ? Number(d.salario) : null, arl_clase: d.arl ? Number(d.arl) : null, dias_habiles: d.dias,
          fecha_ingreso: d.ingreso || null, vacaciones_previas: Number(d.previas || 0) },
      });
      await cargarFicha();
      setAviso("Datos guardados. Los periodos ya calculados cambian solo si se recalculan; los cerrados no cambian.");
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setGuardando(false);
    }
  }

  async function eliminar(ruta: string, texto: string) {
    if (!window.confirm(`¿Eliminar "${texto}"?`)) return;
    try {
      await api(ruta, { method: "DELETE" });
      await cargarDescuentos();
    } catch (e) {
      setError(mensajeError(e));
    }
  }

  if (!f || !d) return error ? <Alerta>{error}</Alerta> : <p className="text-slate-500">Cargando…</p>;
  const cambios = JSON.stringify(d) !== JSON.stringify(datosDe(f));
  const s = f.saldo_vacaciones;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <Link href="/liquidador/empleados" className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100" aria-label="Volver"><ArrowLeft className="h-5 w-5" /></Link>
        <div>
          <h1 className="flex flex-wrap items-center gap-2 text-2xl font-bold text-marca-900">
            {f.nombre}
            {f.estado === "retirado"
              ? <Insignia color="bg-rose-100 text-rose-800">Retirado{f.fecha_retiro ? ` el ${f.fecha_retiro.split("-").reverse().join("/")}` : ""}</Insignia>
              : <Insignia color="bg-green-100 text-green-800">Activo</Insignia>}
          </h1>
          <p className="text-sm text-slate-500">
            <span className="font-mono">{f.documento}</span> · {f.cargo}{f.tipo_personal ? ` (${f.tipo_personal})` : ""}{f.puesto ? ` · ${f.puesto}` : ""}
            {" "}· {f.quincenas} {f.quincenas === 1 ? "nómina" : "nóminas"}{f.ultima ? ` · última ${f.ultima}` : ""}
          </p>
        </div>
      </div>
      {error && <Alerta>{error}</Alerta>}
      {aviso && <Alerta tipo="ok">{aviso}</Alerta>}

      {f.personal && (
        <DatosPersonalesForm key={`datos-${version}`} empleadoId={f.id} personal={f.personal} nombre={f.nombre} cargo={f.cargo} editable={gestionarPersonal}
          onGuardado={(texto) => { setAviso(texto); cargarFicha().catch(() => {}); }} />
      )}

      {/* Datos editables */}
      <section className="tarjeta space-y-4 p-5">
        <h2 className="font-semibold text-slate-900">Nómina y vacaciones</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {verNomina && (
            <div>
              <label className="label">Salario mensual</label>
              <input className="input" type="number" min={1} placeholder="Vacío = salario mínimo" disabled={!gestionar} value={d.salario}
                onChange={(e) => setD({ ...d, salario: e.target.value })} />
              <p className="mt-1 text-xs text-slate-500">{d.salario ? pesos(Number(d.salario)) : "Gana el salario mínimo vigente"}</p>
            </div>
          )}
          <div>
            <label className="label">Clase de riesgo ARL</label>
            <select className="input" disabled={!gestionar} value={d.arl} onChange={(e) => setD({ ...d, arl: e.target.value })}>
              <option value="">Sin definir</option>
              {CLASES_ARL.map(([n, romano]) => <option key={n} value={n}>Clase {romano}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Fecha de ingreso</label>
            <input className="input" type="date" disabled={!gestionar} value={d.ingreso} onChange={(e) => setD({ ...d, ingreso: e.target.value })} />
            <p className="mt-1 text-xs text-slate-500">Para el saldo: 15 días hábiles por año</p>
          </div>
          <div>
            <label className="label">Vacaciones disfrutadas antes del liquidador</label>
            <input className="input" type="number" min={0} step="0.5" disabled={!gestionar} value={d.previas} placeholder="0"
              onChange={(e) => setD({ ...d, previas: e.target.value })} />
            <p className="mt-1 text-xs text-slate-500">Días hábiles</p>
          </div>
        </div>
        <div>
          <p className="label">Días hábiles para vacaciones</p>
          <div className="flex flex-wrap gap-x-4 gap-y-2">
            {DIAS_SEMANA.map((nombre, i) => (
              <label key={nombre} className="flex items-center gap-1.5 text-sm text-slate-700">
                <input type="checkbox" className="h-4 w-4" disabled={!gestionar} checked={d.dias.includes(i)}
                  onChange={(e) => setD({ ...d, dias: e.target.checked ? [...d.dias, i].sort() : d.dias.filter((x) => x !== i) })} />
                {nombre}
              </label>
            ))}
          </div>
          <p className="mt-1 text-xs text-slate-500">Los festivos nunca son hábiles. Los días de vacaciones no hábiles también se pagan, pero no descuentan del saldo.</p>
        </div>
        {gestionar && (
          <div className="flex gap-2">
            <button className="btn-primario" disabled={!cambios || guardando || d.dias.length === 0} onClick={guardar}>{guardando ? "Guardando…" : "Guardar cambios"}</button>
            {cambios && <button className="btn-secundario" onClick={() => setD(datosDe(f))}>Deshacer</button>}
          </div>
        )}
      </section>

      {/* Saldo de vacaciones */}
      <section className="tarjeta p-5">
        <h2 className="mb-3 font-semibold text-slate-900">Saldo de vacaciones</h2>
        {s ? (
          <div className="grid gap-3 sm:grid-cols-4">
            {([["Causados", s.causados],
              [s.corte_libro ? `Disfrutados hasta el ${s.corte_libro.split("-").reverse().join("/")} (libro)` : "Disfrutados antes del liquidador", s.previos],
              [s.corte_libro ? "Liquidados en nóminas después del corte" : "Liquidados en el liquidador", s.liquidador],
              ["Pendientes", s.pendientes]] as const).map(([t, v], i) => (
              <div key={t} className={`rounded-lg border p-3 ${i === 3 ? (v < 0 ? "border-red-200 bg-red-50" : "border-marca-200 bg-marca-50") : "border-slate-200"}`}>
                <p className="text-xs text-slate-500">{t}</p>
                <p className={`text-xl font-bold tabular-nums ${i === 3 && v < 0 ? "text-red-700" : "text-slate-900"}`}>{v.toLocaleString("es-CO")}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-slate-500">Sin fecha de ingreso: registre la fecha arriba para llevar el saldo. Liquidados en el liquidador: {f.vacaciones_liquidador} días hábiles.</p>
        )}
      </section>

      {f.salidas && (
        <HistorialVacaciones empleadoId={f.id} salidas={f.salidas} liquidadas={f.vacaciones_liquidadas ?? []} editable={gestionarPersonal}
          onCambio={(texto) => { setAviso(texto); cargarFicha().catch(() => {}); }} />
      )}

      {/* Préstamos, embargos y cuotas */}
      {verNomina && (
        <section className="space-y-3">
          <div className="flex items-center">
            <h2 className="font-semibold text-slate-900">Préstamos, embargos y cuotas</h2>
            {gestionar && !editDesc && (
              <button className="btn-secundario ml-auto inline-flex items-center gap-1.5" onClick={() => setEditDesc({ registro: null })}>
                <Plus className="h-4 w-4" /> Nuevo
              </button>
            )}
          </div>
          {editDesc && (
            <FormularioDescuento key={editDesc.registro?.id ?? "nuevo"} registro={editDesc.registro} documento={f.documento}
              onCancelar={() => setEditDesc(null)}
              onGuardado={() => { setEditDesc(null); setAviso("Descuento guardado."); cargarDescuentos().catch(() => {}); }} />
          )}
          <div className="tarjeta overflow-auto">
            <table className="tabla text-sm">
              <thead><tr><th>Tipo</th><th>Descripción</th><th className="text-right">Cuota</th><th>Quincena</th><th className="text-right">Descontado</th>
                <th className="text-right">Saldo</th><th>Vigencia</th><th /></tr></thead>
              <tbody>
                {descuentos.map((x) => (
                  <tr key={x.id} className={x.activo ? "" : "text-slate-400"}>
                    <td>{TIPOS_DESCUENTO[x.tipo]?.[0] ?? x.tipo}{!x.activo && <Insignia color="ml-1">Inactivo</Insignia>}</td>
                    <td>{x.descripcion}</td>
                    <td className="whitespace-nowrap text-right tabular-nums">{x.porcentaje !== null ? `${x.porcentaje} %` : `${pesos(x.valor_mensual)}/mes`}</td>
                    <td className="whitespace-nowrap text-xs">{QUINCENAS.find(([v]) => v === x.quincena)?.[1]}</td>
                    <td className="text-right tabular-nums">{pesos(x.descontado)}</td>
                    <td className="text-right tabular-nums">{x.saldo === null ? "—" : pesos(x.saldo)}</td>
                    <td className="whitespace-nowrap text-xs">{x.desde}{x.hasta ? ` → ${x.hasta}` : " en adelante"}</td>
                    <td className="whitespace-nowrap text-right">
                      {gestionar && (
                        <>
                          <button className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100" onClick={() => setEditDesc({ registro: x })} aria-label="Editar"><Pencil className="h-4 w-4" /></button>
                          {x.descontado === 0 && (
                            <button className="rounded-md p-1.5 text-slate-500 hover:bg-red-50 hover:text-red-700" aria-label="Eliminar"
                              onClick={() => eliminar(`/liquidador/descuentos/${x.id}`, x.descripcion)}><Trash2 className="h-4 w-4" /></button>
                          )}
                        </>
                      )}
                    </td>
                  </tr>
                ))}
                {descuentos.length === 0 && <tr><td colSpan={8} className="py-4 text-center text-sm text-slate-500">Sin préstamos, embargos ni cuotas.</td></tr>}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Auxilios no prestacionales */}
      {verNomina && (
        <section className="space-y-3">
          <div className="flex items-center">
            <h2 className="font-semibold text-slate-900">Auxilios no prestacionales</h2>
            {gestionar && !editAux && (
              <button className="btn-secundario ml-auto inline-flex items-center gap-1.5" onClick={() => setEditAux({ registro: null })}>
                <Plus className="h-4 w-4" /> Nuevo
              </button>
            )}
          </div>
          {editAux && (
            <FormularioAuxilio key={editAux.registro?.id ?? "nuevo"} registro={editAux.registro} documento={f.documento}
              onCancelar={() => setEditAux(null)}
              onGuardado={() => { setEditAux(null); setAviso("Auxilio guardado."); cargarDescuentos().catch(() => {}); }} />
          )}
          <div className="tarjeta overflow-auto">
            <table className="tabla text-sm">
              <thead><tr><th>Descripción</th><th className="text-right">Valor mensual</th><th>Quincena</th><th className="text-right">Pagado</th><th>Vigencia</th><th /></tr></thead>
              <tbody>
                {auxilios.map((x) => (
                  <tr key={x.id} className={x.activo ? "" : "text-slate-400"}>
                    <td>{x.descripcion}{!x.activo && <Insignia color="ml-1">Inactivo</Insignia>}</td>
                    <td className="text-right tabular-nums">{pesos(x.valor_mensual)}</td>
                    <td className="whitespace-nowrap text-xs">{QUINCENAS.find(([v]) => v === x.quincena)?.[1]}</td>
                    <td className="text-right tabular-nums">{pesos(x.pagado)}</td>
                    <td className="whitespace-nowrap text-xs">{x.desde}{x.hasta ? ` → ${x.hasta}` : " en adelante"}</td>
                    <td className="whitespace-nowrap text-right">
                      {gestionar && (
                        <>
                          <button className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100" onClick={() => setEditAux({ registro: x })} aria-label="Editar"><Pencil className="h-4 w-4" /></button>
                          {x.pagado === 0 && (
                            <button className="rounded-md p-1.5 text-slate-500 hover:bg-red-50 hover:text-red-700" aria-label="Eliminar"
                              onClick={() => eliminar(`/liquidador/auxilios/${x.id}`, x.descripcion)}><Trash2 className="h-4 w-4" /></button>
                          )}
                        </>
                      )}
                    </td>
                  </tr>
                ))}
                {auxilios.length === 0 && <tr><td colSpan={6} className="py-4 text-center text-sm text-slate-500">Sin auxilios no prestacionales.</td></tr>}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {f.contratos && (
        <HistorialLaboral empleadoId={f.id} contratos={f.contratos} editable={gestionarPersonal}
          onCambio={(texto) => { setAviso(texto); cargarFicha().catch(() => {}); }} />
      )}

      {/* Historial de nóminas */}
      <section className="space-y-3">
        <h2 className="font-semibold text-slate-900">Nóminas en que aparece</h2>
        <div className="tarjeta overflow-auto">
          <table className="tabla text-sm">
            <thead>
              <tr><th>Periodo</th><th>Nómina</th><th>Estado</th><th className="text-right">Horas</th>
                {verNomina && <><th className="text-right">Devengado</th><th className="text-right">Neto</th></>}<th /></tr>
            </thead>
            <tbody>
              {f.nominas.map((n) => {
                const [texto, color] = ESTADO_PERIODO[n.estado] ?? [n.estado, ""];
                return (
                  <tr key={n.periodo_id}>
                    <td className="whitespace-nowrap">{MESES[n.mes - 1]} {n.anio} · {nombrePeriodo(n)}</td>
                    <td>
                      {n.nombre}
                      {n.alertas > 0 && <TriangleAlert className="ml-1.5 inline h-3.5 w-3.5 text-amber-600" aria-label={`${n.alertas} alertas`} />}
                    </td>
                    <td><Insignia color={color}>{texto}</Insignia></td>
                    <td className="text-right tabular-nums">{horas(n.total_horas)}</td>
                    {verNomina && <><td className="text-right tabular-nums">{pesos(n.devengado ?? 0)}</td><td className="text-right tabular-nums">{pesos(n.neto ?? 0)}</td></>}
                    <td className="text-right">
                      <Link href={`/liquidador/quincenas/${n.periodo_id}`} className="inline-flex items-center gap-1 text-sm font-medium text-marca-600 hover:underline">
                        Abrir <ArrowRight className="h-4 w-4" />
                      </Link>
                    </td>
                  </tr>
                );
              })}
              {f.nominas.length === 0 && <tr><td colSpan={7} className="py-4 text-center text-sm text-slate-500">Todavía no aparece en ninguna nómina.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
