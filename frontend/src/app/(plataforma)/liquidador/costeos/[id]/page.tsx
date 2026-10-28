"use client";

import { ArrowLeft, Download, Pencil, Search, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { NominaPersona } from "@/components/nomina-persona";
import { ParametrosCosteoForm } from "@/components/parametros-costeo";
import { Alerta, Insignia } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";
import { MESES, pesos } from "@/lib/formato";
import { CLASES_ARL, nombrePeriodo, pct, type Costeo, type CosteoPersona, type ParametrosCosteo, type ParametrosDefecto } from "@/lib/liquidador";

const romano = (n: number) => CLASES_ARL.find(([c]) => c === n)?.[1] ?? String(n);
import { usePermiso } from "@/lib/sesion";

export default function DetalleCosteo() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const gestionar = usePermiso("liquidador.costeo.gestionar");
  const [c, setC] = useState<Costeo | null>(null);
  const [def, setDef] = useState<ParametrosDefecto | null>(null);
  const [par, setPar] = useState<ParametrosCosteo | null>(null);
  const [q, setQ] = useState("");
  const [persona, setPersona] = useState<CosteoPersona | null>(null);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState("");
  const [aviso, setAviso] = useState("");

  useEffect(() => {
    Promise.all([api<Costeo>(`/liquidador/costeos/${id}`), api<ParametrosDefecto>("/liquidador/costeos/parametros")])
      .then(([x, d]) => { setC(x); setPar(x.parametros); setDef(d); })
      .catch((e) => setError(mensajeError(e)));
  }, [id]);

  const filas = useMemo(() => {
    const t = q.trim().toLowerCase();
    return (c?.resultados ?? []).filter((r) => !t || r.documento.toLowerCase().includes(t) || r.nombre.toLowerCase().includes(t));
  }, [c, q]);

  async function guardar(nombre: string, parametros: ParametrosCosteo, texto: string) {
    setError("");
    setGuardando(true);
    try {
      const x = await api<Costeo>(`/liquidador/costeos/${id}`, { method: "PUT", json: { nombre, parametros } });
      setC(x);
      setPar(x.parametros);
      setPersona(null);
      setAviso(texto);
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setGuardando(false);
    }
  }

  async function eliminar() {
    if (!window.confirm("¿Eliminar este costeo? No se puede deshacer.")) return;
    try {
      await api(`/liquidador/costeos/${id}`, { method: "DELETE" });
      router.push("/liquidador/costeos");
    } catch (e) {
      setError(mensajeError(e));
    }
  }

  if (!c || !def || !par) return error ? <Alerta>{error}</Alerta> : <p className="text-slate-500">Cargando…</p>;
  const t = c.totales;
  const cambiados = JSON.stringify(par) !== JSON.stringify(c.parametros);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <Link href="/liquidador/costeos" className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100" aria-label="Volver"><ArrowLeft className="h-5 w-5" /></Link>
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-marca-900">
            {c.nombre}
            {gestionar && (
              <button className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700" aria-label="Cambiar el nombre"
                onClick={() => {
                  const nombre = window.prompt("Nombre del costeo", c.nombre)?.trim();
                  if (nombre && nombre !== c.nombre) guardar(nombre, c.parametros, "Nombre actualizado.");
                }}>
                <Pencil className="h-4 w-4" />
              </button>
            )}
          </h1>
          <p className="text-sm text-slate-500">
            Costeo · {MESES[c.mes - 1]} {c.anio} — {nombrePeriodo(c)} · del {c.desde} al {c.hasta}{c.archivo ? ` · Archivo: ${c.archivo}` : ""}
            {c.umbral_activo ? ` · umbral semanal de ${c.umbral_horas} h` : ""}
            {c.auxilio_mensual > 0 ? ` · auxilio no prestacional ${pesos(c.auxilio_mensual)} mensual por persona` : " · sin auxilio no prestacional"}
          </p>
        </div>
        <Insignia color="bg-violet-100 text-violet-800">No cuenta como pagado</Insignia>
        <div className="ml-auto flex items-center gap-2">
          <a className="btn-secundario inline-flex items-center gap-1.5" href={`/api/liquidador/costeos/${id}/excel`}><Download className="h-4 w-4" /> Excel</a>
          {gestionar && (
            <button onClick={eliminar} className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-sm text-slate-500 hover:bg-red-50 hover:text-red-700">
              <Trash2 className="h-4 w-4" /> Eliminar
            </button>
          )}
        </div>
      </div>

      {error && <Alerta>{error}</Alerta>}
      {aviso && <Alerta tipo="ok">{aviso}</Alerta>}
      {t.no_registradas > 0 && (
        <Alerta tipo="info">
          {t.no_registradas === 1 ? "1 cédula no está registrada" : `${t.no_registradas} cédulas no están registradas`} en el liquidador: se costean con el
          salario mínimo y los días hábiles de lunes a sábado, y no se crean como empleados.
        </Alerta>
      )}
      {t.sin_arl > 0 && (
        <Alerta tipo="info">
          {t.sin_arl === 1 ? "1 persona no trae" : `${t.sin_arl} personas no traen`} clase de ARL en el Excel ni la tienen configurada en Empleados:
          se costean con la clase {romano(c.parametros.arl_clase)}, que se puede cambiar abajo.
        </Alerta>
      )}
      {c.advertencias.length > 0 && (
        <details className="tarjeta p-4 text-sm">
          <summary className="cursor-pointer font-medium text-amber-800">{c.advertencias.length} advertencias del Excel</summary>
          <ul className="mt-2 list-disc space-y-0.5 pl-5 text-slate-600">{c.advertencias.map((a) => <li key={a}>{a}</li>)}</ul>
        </details>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {([["Personas", t.personas.toLocaleString("es-CO")], ["Total devengado", pesos(t.devengado)], ["Aportes del empleador", pesos(t.total_aportes)],
          ["Prestaciones", pesos(t.total_prestaciones)], ["Costo total empresa", pesos(t.costo_total)]] as const).map(([titulo, valor], i) => (
          <div key={titulo} className={`tarjeta p-4 ${i === 4 ? "border-marca-300 bg-marca-50" : ""}`}>
            <p className="text-xs text-slate-500">{titulo}</p>
            <p className={`text-xl font-bold tabular-nums ${i === 4 ? "text-marca-900" : "text-slate-900"}`}>{valor}</p>
          </div>
        ))}
      </div>

      <section className="tarjeta space-y-4 p-5">
        <div className="grid gap-4 lg:grid-cols-2">
          <table className="tabla text-sm">
            <thead><tr><th>Aportes del empleador</th><th className="text-right">Total</th></tr></thead>
            <tbody>{def.aportes.map((k) => (
              <tr key={k}><td>{def.nombres[k]}{k === "arl" ? "" : ` (${pct(c.parametros, k)} %)`}</td><td className="text-right tabular-nums">{pesos(t.aportes[k] ?? 0)}</td></tr>
            ))}</tbody>
          </table>
          <table className="tabla text-sm">
            <thead><tr><th>Prestaciones</th><th className="text-right">Total</th></tr></thead>
            <tbody>{def.prestaciones.map((k) => <tr key={k}><td>{def.nombres[k]} ({pct(c.parametros, k)} %)</td><td className="text-right tabular-nums">{pesos(t.prestaciones[k] ?? 0)}</td></tr>)}</tbody>
          </table>
        </div>
        <details>
          <summary className="cursor-pointer text-sm font-medium text-marca-700">Cambiar los porcentajes y recalcular el costo</summary>
          <div className="mt-3 space-y-3">
            <ParametrosCosteoForm valores={par} def={def} onCambio={setPar} deshabilitado={!gestionar} />
            {gestionar && (
              <div className="flex gap-2">
                <button className="btn-primario" disabled={!cambiados || guardando} onClick={() => guardar(c.nombre, par, "Costo recalculado con los nuevos porcentajes.")}>
                  {guardando ? "Recalculando…" : "Recalcular costo"}
                </button>
                {cambiados && <button className="btn-secundario" onClick={() => setPar(c.parametros)}>Deshacer</button>}
              </div>
            )}
            <p className="text-xs text-slate-500">Solo cambia el costo empresa; la nómina de cada persona se mantiene. Para cambiar turnos, cree otro costeo con el Excel corregido.</p>
          </div>
        </details>
      </section>

      {persona && (
        <section className="tarjeta space-y-3 p-5">
          <div className="flex items-center">
            <h2 className="font-semibold text-slate-900">{persona.nombre} <span className="font-mono text-sm font-normal text-slate-500">{persona.documento}</span></h2>
            <button className="ml-auto rounded-md p-1 text-slate-500 hover:bg-slate-100" onClick={() => setPersona(null)} aria-label="Cerrar"><X className="h-5 w-5" /></button>
          </div>
          <NominaPersona n={persona.nomina} titulo="Nómina costeada" />
          <table className="tabla text-xs">
            <thead><tr><th>Costo empresa</th><th>Base</th><th className="text-right">Valor</th></tr></thead>
            <tbody>
              <tr><td>Total devengado</td><td /><td className="text-right tabular-nums">{pesos(persona.costo.devengado)}</td></tr>
              {def.aportes.map((k) => (
                <tr key={k}>
                  <td>
                    {k === "arl"
                      ? `ARL clase ${romano(persona.costo.arl_clase)} (${persona.costo.arl_tarifa} %, ${persona.arl_origen === "excel" ? "del Excel" : persona.arl_origen === "empleado" ? "configurada en Empleados" : "por defecto"})`
                      : `${def.nombres[k]} (${pct(c.parametros, k)} %)`}
                  </td>
                  <td className="text-slate-500">
                    {persona.costo.exonerado && ["salud", "icbf", "sena"].includes(k) ? "Exonerado (menos de 10 mínimos)" : pesos(k === "arl" ? persona.costo.base_arl : persona.costo.base_aportes)}
                  </td>
                  <td className="text-right tabular-nums">{pesos(persona.costo.aportes[k])}</td>
                </tr>
              ))}
              {def.prestaciones.map((k) => (
                <tr key={k}>
                  <td>{def.nombres[k]} ({pct(c.parametros, k)} %)</td>
                  <td className="text-slate-500">{pesos(k === "vacaciones" ? persona.costo.base_vacaciones : persona.costo.base_prestaciones)}</td>
                  <td className="text-right tabular-nums">{pesos(persona.costo.prestaciones[k])}</td>
                </tr>
              ))}
              <tr className="bg-marca-50 font-bold text-marca-900"><td>Costo total empresa</td><td /><td className="text-right tabular-nums">{pesos(persona.costo.costo_total)}</td></tr>
            </tbody>
          </table>
        </section>
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
            <thead>
              <tr><th>Documento</th><th>Nombre</th><th>ARL</th><th className="text-right">Horas</th><th className="text-right">Devengado</th>
                <th className="text-right">Aportes</th><th className="text-right">Prestaciones</th><th className="text-right">Costo total</th></tr>
            </thead>
            <tbody>
              {filas.map((r) => (
                <tr key={r.documento} className="cursor-pointer hover:bg-marca-50" onClick={() => { setPersona(r); window.scrollTo({ top: 0, behavior: "smooth" }); }}>
                  <td className="font-mono">{r.documento}</td>
                  <td>
                    {r.nombre}
                    {!r.existe && <span className="ml-2 text-xs text-amber-700">sin registrar · salario mínimo</span>}
                  </td>
                  <td className={r.arl_clase ? "" : "text-slate-500"}>{romano(r.costo.arl_clase)}{r.arl_clase ? "" : " (defecto)"}</td>
                  <td className="text-right tabular-nums">{r.total_horas.toLocaleString("es-CO")}</td>
                  <td className="text-right tabular-nums">{pesos(r.costo.devengado)}</td>
                  <td className="text-right tabular-nums">{pesos(r.costo.total_aportes)}</td>
                  <td className="text-right tabular-nums">{pesos(r.costo.total_prestaciones)}</td>
                  <td className="text-right font-semibold tabular-nums">{pesos(r.costo.costo_total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
