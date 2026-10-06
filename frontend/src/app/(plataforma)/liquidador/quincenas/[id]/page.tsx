"use client";

import { ArrowLeft, Banknote, Download, FileDown, Lock, LockOpen, RefreshCw, Search, Trash2, TriangleAlert, X } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Fragment, useCallback, useEffect, useState } from "react";
import { Paginador, metaDe, usePaginacion, type MetaPagina } from "@/components/paginacion";
import { Alerta, Insignia, SubirArchivo } from "@/components/ui";
import { api, apiEnvelope, mensajeError, subirArchivo } from "@/lib/api";
import { MESES, pesos } from "@/lib/formato";
import {
  CLASES, CONCEPTOS, CONCEPTOS_PAGO, ESTADO_PERIODO, TIPOS_DIA, nombrePeriodo, horas,
  type Dia, type Nomina, type Periodo, type Resultado, type TotalesNomina,
} from "@/lib/liquidador";
import { usePermiso } from "@/lib/sesion";

type Carga = { periodo: Periodo; empleados: number; dias: number; fechas: number; advertencias: string[] };
type Totales = { horas: Record<string, number>; dias: Record<string, number>; nomina?: TotalesNomina };
const TIPO_DIA = Object.fromEntries(TIPOS_DIA);
const DIA_SEMANA = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];

export default function DetalleQuincena() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const gestionar = usePermiso("liquidador.periodos.gestionar");
  const verNomina = usePermiso("liquidador.nomina.ver");
  const [p, setP] = useState<Periodo | null>(null);
  const [filas, setFilas] = useState<Resultado[]>([]);
  const [meta, setMeta] = useState<MetaPagina | null>(null);
  const [totales, setTotales] = useState<Totales | null>(null);
  const [nominaPendiente, setNominaPendiente] = useState(false);
  const [q, setQ] = useState("");
  const [orden, setOrden] = useState("documento");
  const [carga, setCarga] = useState<Carga | null>(null);
  const [error, setError] = useState("");
  const [aviso, setAviso] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [detalle, setDetalle] = useState<{ empleado: Resultado; dias: Dia[] } | null>(null);
  const pag = usePaginacion([q, orden]);

  const cargarPeriodo = useCallback(() => api<Periodo>(`/liquidador/periodos/${id}`).then(setP), [id]);

  const cargarResultados = useCallback(async () => {
    const r = await apiEnvelope<Resultado[]>(`/liquidador/periodos/${id}/resultados?q=${encodeURIComponent(q)}&orden=${orden}&${pag.query}`);
    setFilas(r.data ?? []);
    setMeta(metaDe(r));
    setTotales((r.meta.extra?.totales as Totales) ?? null);
    setNominaPendiente(!!r.meta.extra?.nomina_pendiente);
  }, [id, q, orden, pag.query]);

  useEffect(() => {
    cargarPeriodo().catch((e) => setError(mensajeError(e)));
  }, [cargarPeriodo]);

  useEffect(() => {
    const t = setTimeout(() => cargarResultados().catch(() => {}), 250);
    return () => clearTimeout(t);
  }, [cargarResultados]);

  async function accion(ruta: string, texto: string, confirmar?: string) {
    if (confirmar && !window.confirm(confirmar)) return;
    setError("");
    setAviso("");
    setOcupado(true);
    try {
      setP(await api<Periodo>(`/liquidador/periodos/${id}/${ruta}`, { method: "POST" }));
      await cargarResultados();
      setAviso(texto);
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setOcupado(false);
    }
  }

  async function subir(archivo: File) {
    setError("");
    setAviso("");
    setCarga(null);
    try {
      const r = await subirArchivo<Carga>(`/liquidador/periodos/${id}/cargar`, archivo);
      setCarga(r);
      setP(r.periodo);
      await cargarResultados();
    } catch (e) {
      setError(mensajeError(e));
    }
  }

  async function eliminar() {
    if (!window.confirm("¿Eliminar este periodo y todo lo cargado? No se puede deshacer.")) return;
    try {
      await api(`/liquidador/periodos/${id}`, { method: "DELETE" });
      router.push("/liquidador");
    } catch (e) {
      setError(mensajeError(e));
    }
  }

  async function verPersona(r: Resultado) {
    try {
      setDetalle(await api(`/liquidador/periodos/${id}/empleados/${r.empleado_id}`));
    } catch (e) {
      setError(mensajeError(e));
    }
  }

  if (!p) return error ? <Alerta>{error}</Alerta> : <p className="text-slate-500">Cargando…</p>;
  const [estadoTexto, estadoColor] = ESTADO_PERIODO[p.estado] ?? [p.estado, ""];
  const cerrada = p.estado === "cerrada";
  const advertencias = carga?.advertencias ?? p.advertencias ?? [];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <Link href="/liquidador" className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100" aria-label="Volver"><ArrowLeft className="h-5 w-5" /></Link>
        <div>
          <h1 className="text-2xl font-bold text-marca-900">{MESES[p.mes - 1]} {p.anio} — {nombrePeriodo(p)}</h1>
          <p className="text-sm text-slate-500">Del {p.desde} al {p.hasta}{p.archivo ? ` · Archivo: ${p.archivo}` : ""}</p>
        </div>
        <Insignia color={estadoColor}>{estadoTexto}</Insignia>
        {gestionar && !cerrada && (
          <button onClick={eliminar} className="ml-auto inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-sm text-slate-500 hover:bg-red-50 hover:text-red-700">
            <Trash2 className="h-4 w-4" /> Eliminar periodo
          </button>
        )}
      </div>

      {error && <Alerta>{error}</Alerta>}
      {aviso && <Alerta tipo="ok">{aviso}</Alerta>}

      {/* Carga del Excel */}
      <section className="tarjeta space-y-3 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="font-semibold text-slate-900">Cargar calendario de turnos</h2>
            <p className="text-sm text-slate-500">Sube el Excel con la cédula de cada empleado y el turno que trabajó cada día. Cargar de nuevo reemplaza lo anterior.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <a className="btn-secundario inline-flex items-center gap-1.5" href={`/api/liquidador/periodos/${id}/plantilla`}><FileDown className="h-4 w-4" /> Descargar plantilla</a>
            {gestionar && <SubirArchivo texto="Subir y calcular" onArchivo={subir} deshabilitado={cerrada} />}
          </div>
        </div>
        {cerrada && <Alerta tipo="info">El periodo está cerrado: para cargar otro archivo o recalcular, primero reábralo.</Alerta>}
        <details className="text-sm text-slate-600">
          <summary className="cursor-pointer font-medium text-marca-700">Ver formato esperado del Excel</summary>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            <li><b>Columna A</b>: <code>documento</code> (cédula del empleado).</li>
            <li><b>Columna B</b>: nombre del empleado (o la cédula). El encabezado puede ser el nombre del mes (p. ej. SEPTIEMBRE); es informativo.</li>
            <li><b>Columnas siguientes</b>: una por día. Encabezado = número del día (16, 17, …) o fecha completa. Una columna <code>salario</code> o <code>cargo</code> se reconoce y no se toma como día.</li>
            <li><b>Celdas</b>: código del turno (D, N, Z, L, AUS, INC, V…) o vacío si no tuvo turno. Los códigos que no existan en Turnos se omiten con una advertencia.</li>
          </ul>
        </details>
        {carga && (
          <Alerta tipo="ok">
            Se cargaron {carga.empleados.toLocaleString("es-CO")} empleados y {carga.dias.toLocaleString("es-CO")} días ({carga.fechas} fechas). Las horas ya están contadas.
          </Alerta>
        )}
        {advertencias.length > 0 && (
          <details className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900" open={!!carga}>
            <summary className="flex cursor-pointer items-center gap-1.5 font-medium"><TriangleAlert className="h-4 w-4" /> {advertencias.length} advertencias de la carga</summary>
            <ul className="mt-2 max-h-48 list-disc overflow-auto pl-5">{advertencias.map((a, i) => <li key={i}>{a}</li>)}</ul>
          </details>
        )}
      </section>

      {/* Horas contadas */}
      {p.estado !== "borrador" && (
        <section className="tarjeta overflow-hidden">
          <div className="flex flex-wrap items-center gap-3 border-b border-slate-200 p-4">
            <div>
              <h2 className="font-semibold text-slate-900">Horas contadas · {p.empleados.toLocaleString("es-CO")} empleados</h2>
              {p.calculado_en && <p className="text-xs text-slate-500">Calculado el {new Date(p.calculado_en).toLocaleString("es-CO")}{p.cerrado_en ? ` · cerrada el ${new Date(p.cerrado_en).toLocaleString("es-CO")}` : ""}</p>}
            </div>
            <div className="ml-auto flex flex-wrap gap-2">
              {gestionar && !cerrada && (
                <button className="btn-secundario inline-flex items-center gap-1.5" disabled={ocupado}
                  onClick={() => accion("recalcular", "Horas recalculadas con los turnos y festivos vigentes.", "¿Recalcular? Se volverán a contar las horas del Excel cargado con los turnos y festivos actuales.")}>
                  <RefreshCw className="h-4 w-4" /> Recalcular
                </button>
              )}
              {gestionar && !cerrada && (
                <button className="btn-secundario inline-flex items-center gap-1.5" disabled={ocupado}
                  onClick={() => accion("cerrar", "Periodo cerrado.", "¿Cerrar el periodo? No se podrá cargar otro archivo ni recalcular hasta reabrirlo.")}>
                  <Lock className="h-4 w-4" /> Cerrar periodo
                </button>
              )}
              {gestionar && cerrada && (
                <button className="btn-secundario inline-flex items-center gap-1.5" disabled={ocupado}
                  onClick={() => accion("reabrir", "Periodo reabierto.", "¿Reabrir el periodo para hacer cambios?")}>
                  <LockOpen className="h-4 w-4" /> Reabrir
                </button>
              )}
              <a className="btn-primario inline-flex items-center gap-1.5" href={`/api/liquidador/periodos/${id}/liquidacion`}>
                <Download className="h-4 w-4" /> Calendario + Liquidación
              </a>
              {verNomina && (
                <a className="btn-primario inline-flex items-center gap-1.5" href={`/api/liquidador/periodos/${id}/nomina`}
                  title="Valor por concepto, devengado, deducciones y neto por persona">
                  <Banknote className="h-4 w-4" /> Nómina
                </a>
              )}
            </div>
          </div>

          {nominaPendiente && (
            <div className="border-b border-slate-200 p-4">
              <Alerta tipo="info">Este periodo se calculó antes de existir la nómina. {cerrada ? "Reábralo y recalcúlelo" : "Recalcúlelo"} para ver el devengado y el neto.</Alerta>
            </div>
          )}
          {totales?.nomina && (
            <div className="grid gap-3 border-b border-slate-200 p-4 sm:grid-cols-3 lg:grid-cols-6">
              <Cifra titulo="Sueldo básico + incapacidades" valor={totales.nomina.basico + totales.nomina.incapacidad} />
              <Cifra titulo="Recargos" valor={totales.nomina.recargos} />
              <Cifra titulo="Horas extras" valor={totales.nomina.extras} />
              <Cifra titulo="Auxilio de transporte" valor={totales.nomina.auxilio} />
              <Cifra titulo="Total devengado" valor={totales.nomina.devengado} fuerte
                detalle={`Deducciones ${pesos(totales.nomina.deducciones)}: salud ${pesos(totales.nomina.salud)}, pensión ${pesos(totales.nomina.pension)}, embargos ${pesos(totales.nomina.embargos)}, préstamos ${pesos(totales.nomina.prestamos)}`} />
              <Cifra titulo="Neto a pagar" valor={totales.nomina.neto} fuerte />
            </div>
          )}

          {totales && (
            <div className="flex flex-wrap gap-2 border-b border-slate-200 bg-slate-50 px-4 py-3">
              {CLASES.map(([k, texto, color]) => (
                <span key={k} className={`rounded-full px-2.5 py-1 text-xs font-medium ${color}`}>{texto}: <b className="tabular-nums">{(totales.dias[k] ?? 0).toLocaleString("es-CO")}</b></span>
              ))}
            </div>
          )}

          <div className="flex flex-wrap items-center gap-3 px-4 py-3">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input className="input w-64 pl-8" placeholder="Buscar por cédula o nombre…" value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
            <label className="flex items-center gap-2 text-sm text-slate-600">
              Ordenar por
              <select className="input w-48" value={orden} onChange={(e) => setOrden(e.target.value)}>
                <option value="documento">Documento</option>
                <option value="nombre">Nombre</option>
                <option value="horas">Más horas trabajadas</option>
                <option value="novedad">Más días con novedad</option>
                {verNomina && <option value="devengado">Mayor devengado</option>}
                {verNomina && <option value="neto">Mayor neto</option>}
              </select>
            </label>
            <span className="text-xs text-slate-500">Clic en una fila para ver el día a día.</span>
          </div>

          <div className="max-h-[65vh] overflow-auto">
            <table className="tabla text-xs">
              <thead className="sticky top-0 z-10">
                <tr>
                  <th className="sticky left-0 z-20 bg-slate-50">Documento</th>
                  <th>Empleado</th>
                  {CONCEPTOS.map(([k, largo, corto]) => <th key={k} className="text-right" title={largo}>{corto}</th>)}
                  {CLASES.map(([k, texto, , corto]) => <th key={k} className="text-right" title={texto}>{corto}</th>)}
                  {verNomina && <th className="text-right">Devengado</th>}
                  {verNomina && <th className="text-right">Neto</th>}
                </tr>
              </thead>
              <tbody>
                {filas.map((r) => (
                  <tr key={r.empleado_id} className="cursor-pointer hover:bg-marca-50" onClick={() => verPersona(r)}>
                    <td className="sticky left-0 bg-white font-mono">{r.documento}</td>
                    <td className="max-w-[180px] truncate" title={r.nombre}>{r.nombre}</td>
                    {CONCEPTOS.map(([k]) => <td key={k} className="text-right tabular-nums">{horas(r.horas[k])}</td>)}
                    {CLASES.map(([k]) => <td key={k} className="text-right tabular-nums">{r.dias[k] || "–"}</td>)}
                    {verNomina && <td className="whitespace-nowrap text-right tabular-nums">{pesos(r.devengado)}</td>}
                    {verNomina && <td className="whitespace-nowrap text-right font-semibold tabular-nums">{pesos(r.neto)}</td>}
                  </tr>
                ))}
              </tbody>
              {totales && (
                <tfoot className="sticky bottom-0 bg-slate-100 font-semibold">
                  <tr>
                    <td className="sticky left-0 bg-slate-100" colSpan={2}>Totales ({meta?.total.toLocaleString("es-CO")} empleados)</td>
                    {CONCEPTOS.map(([k]) => <td key={k} className="text-right tabular-nums">{horas(totales.horas[k])}</td>)}
                    {CLASES.map(([k]) => <td key={k} className="text-right tabular-nums">{totales.dias[k] || "–"}</td>)}
                    {verNomina && <td className="whitespace-nowrap text-right tabular-nums">{pesos(totales.nomina?.devengado)}</td>}
                    {verNomina && <td className="whitespace-nowrap text-right tabular-nums">{pesos(totales.nomina?.neto)}</td>}
                  </tr>
                </tfoot>
              )}
            </table>
          </div>
          <Paginador meta={meta} onPagina={pag.setPagina} onTamano={pag.setTamano} />
        </section>
      )}

      {detalle && <DetallePersona detalle={detalle} onCerrar={() => setDetalle(null)} />}
    </div>
  );
}

function DetallePersona({ detalle, onCerrar }: { detalle: { empleado: Resultado; dias: Dia[] }; onCerrar: () => void }) {
  const { empleado: e, dias } = detalle;
  const usados = CONCEPTOS.filter(([k]) => e.horas[k]);
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/40" onClick={onCerrar}>
      <aside className="h-full w-full max-w-4xl overflow-y-auto bg-white shadow-2xl" onClick={(ev) => ev.stopPropagation()}>
        <header className="sticky top-0 flex items-start gap-3 border-b border-slate-200 bg-white p-5">
          <div className="min-w-0 flex-1">
            <h2 className="text-lg font-bold text-marca-900">{e.nombre}</h2>
            <p className="text-sm text-slate-500">Documento {e.documento} · {e.cargo} · {e.total_horas.toLocaleString("es-CO")} horas trabajadas</p>
          </div>
          <button onClick={onCerrar} className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100" aria-label="Cerrar"><X className="h-5 w-5" /></button>
        </header>
        <div className="space-y-4 p-5">
          <div className="flex flex-wrap gap-2">
            {CLASES.filter(([k]) => e.dias[k]).map(([k, texto, color]) => (
              <span key={k} className={`rounded-full px-2.5 py-1 text-xs font-medium ${color}`}>{texto}: <b>{e.dias[k]}</b></span>
            ))}
          </div>
          {e.nomina && <NominaPersona n={e.nomina} />}
          <p className="text-xs text-slate-500">
            &quot;Diurnas ordinarias&quot; cuenta todas las horas ordinarias del turno; los recargos marcan cuáles de esas horas llevan recargo y no se suman aparte.
          </p>
          <div className="overflow-auto rounded-lg border border-slate-200">
            <table className="tabla text-xs">
              <thead>
                <tr>
                  <th>Fecha</th><th>Turno</th><th>Tipo de día</th><th>Cuenta como</th>
                  {usados.map(([k, largo, corto]) => <th key={k} className="text-right" title={largo}>{corto}</th>)}
                </tr>
              </thead>
              <tbody>
                {dias.map((d) => {
                  const f = new Date(d.fecha + "T12:00:00");
                  const clase = CLASES.find(([k]) => k === d.clase);
                  return (
                    <tr key={d.fecha}>
                      <td className="whitespace-nowrap">{DIA_SEMANA[f.getDay()]} {f.getDate()}</td>
                      <td title={d.turno}><span className="font-mono font-semibold">{d.codigo}</span> <span className="text-slate-500">{d.turno}</span></td>
                      <td>{TIPO_DIA[d.tipo_dia] ?? d.tipo_dia}</td>
                      <td>{clase && <span className={`rounded-full px-2 py-0.5 ${clase[2]}`}>{clase[4]}</span>}</td>
                      {usados.map(([k]) => <td key={k} className="text-right tabular-nums">{horas(d.horas[k])}</td>)}
                    </tr>
                  );
                })}
              </tbody>
              <tfoot className="bg-slate-100 font-semibold">
                <tr>
                  <td colSpan={4}>Total</td>
                  {usados.map(([k]) => <td key={k} className="text-right tabular-nums">{horas(e.horas[k])}</td>)}
                </tr>
              </tfoot>
            </table>
          </div>
        </div>
      </aside>
    </div>
  );
}

function Cifra({ titulo, valor, fuerte, detalle }: { titulo: string; valor: number; fuerte?: boolean; detalle?: string }) {
  return (
    <div title={detalle}>
      <p className="text-xs text-slate-500">{titulo}</p>
      <p className={`tabular-nums ${fuerte ? "text-lg font-bold text-marca-900" : "font-semibold text-slate-800"}`}>{pesos(valor)}</p>
    </div>
  );
}

function NominaPersona({ n }: { n: Nomina }) {
  const fila = (concepto: React.ReactNode, detalle: React.ReactNode, valor: number, clase = "") => (
    <tr className={clase}><td>{concepto}</td><td className="text-xs text-slate-500">{detalle}</td><td className="whitespace-nowrap text-right tabular-nums">{pesos(valor)}</td></tr>
  );
  const usados = CONCEPTOS_PAGO.filter(([k]) => n.valores[k]);
  return (
    <section className="rounded-lg border border-slate-200">
      <header className="flex flex-wrap items-baseline gap-x-4 gap-y-1 border-b border-slate-200 bg-slate-50 px-4 py-3">
        <h3 className="font-semibold text-slate-900">Nómina del periodo</h3>
        <span className="text-xs text-slate-500">
          Salario {pesos(n.salario)}{n.salario_minimo ? " (mínimo)" : ""} · día {pesos(n.valor_dia)} · hora {pesos(n.valor_hora)} ({n.horas_mes} h/mes)
        </span>
        <span className="ml-auto text-sm">Devengado <b className="tabular-nums">{pesos(n.devengado)}</b> · Neto <b className="tabular-nums text-marca-800">{pesos(n.neto)}</b></span>
      </header>
      <div className="grid md:grid-cols-2 md:divide-x md:divide-slate-200">
        <table className="tabla text-xs">
          <thead><tr><th>Devengado</th><th /><th className="text-right">Valor</th></tr></thead>
          <tbody>
            {fila("Sueldo básico", `${n.dias_salario} días (trabajados, descansos y libres)`, n.basico)}
            {n.dias_incapacidad > 0 && fila("Incapacidad (100 %)", `${n.dias_incapacidad} días · ${n.incapacidad_empresa} empresa, ${n.incapacidad_eps} EPS`, n.incapacidad)}
            {usados.map(([k, largo]) => <Fragment key={k}>{fila(largo, `${horas(n.horas[k])} h`, n.valores[k])}</Fragment>)}
            {fila("Auxilio de transporte", `${n.dias_auxilio} días`, n.auxilio)}
            {fila(<b>Total devengado</b>, "", n.devengado, "bg-slate-50")}
          </tbody>
        </table>
        <table className="tabla text-xs">
          <thead><tr><th>Deducciones</th><th /><th className="text-right">Valor</th></tr></thead>
          <tbody>
            {fila("Salud", `${n.salud_pct} % de ${pesos(n.ibc)}`, n.salud)}
            {fila("Pensión", `${n.pension_pct} % de ${pesos(n.ibc)}`, n.pension)}
            {n.descuentos.map((x) => (
              <Fragment key={x.id}>
                {fila(`${x.tipo === "embargo" ? "Embargo" : "Préstamo"}: ${x.descripcion}`,
                  <>{x.calculo}{x.observacion && <span className="block text-amber-700">{x.observacion}</span>}</>, x.valor)}
              </Fragment>
            ))}
            {fila(<b>Total deducciones</b>, "", n.deducciones, "bg-slate-50")}
            {fila(<b>Neto a pagar</b>, "", n.neto, "bg-marca-50 font-bold text-marca-900")}
          </tbody>
        </table>
      </div>
      {n.dias_sin_pago > 0 && (
        <p className="border-t border-slate-200 px-4 py-2 text-xs text-slate-500">
          {n.dias_sin_pago} días sin pago en esta nómina: ausencias y novedades (vacaciones, licencias…, que se pagan en otro proceso).
        </p>
      )}
    </section>
  );
}
