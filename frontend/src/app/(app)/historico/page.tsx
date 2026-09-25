"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { num } from "@/components/estado";
import { Alerta, Insignia, Titulo } from "@/components/ui";
import { api, mensajeError, type Comparacion, type Historico } from "@/lib/api";
import { nombreMes } from "@/lib/formato";

const TIPO: Record<string, [string, string]> = {
  agregado: ["+ Agregado", "bg-[#0ca30c]/15 text-[#086b08]"],
  eliminado: ["− Eliminado", "bg-[#d03b3b]/15 text-[#a32525]"],
  cambiado: ["↻ Cambiado", "bg-[#fab219]/20 text-[#8a5a00]"],
};

export default function HistoricoPage() {
  const [filas, setFilas] = useState<Historico[]>([]);
  const [comp, setComp] = useState<Comparacion | null>(null);
  const [sel, setSel] = useState<{ anterior: number | null; actual: number | null }>({ anterior: null, actual: null });
  const [error, setError] = useState("");
  const [q, setQ] = useState("");

  useEffect(() => {
    api<Historico[]>("/historico").then(setFilas);
  }, []);

  const porMes = useMemo(() => {
    const m = new Map<string, Historico[]>();
    filas.forEach((f) => m.set(`${f.anio}-${f.mes}`, [...(m.get(`${f.anio}-${f.mes}`) ?? []), f]));
    return [...m.values()];
  }, [filas]);

  async function comparar(anterior: number, actual: number) {
    setError("");
    setSel({ anterior, actual });
    try {
      setComp(await api<Comparacion>(`/programacion/comparar?anterior=${anterior}&actual=${actual}`));
    } catch (e) {
      setComp(null);
      setError(mensajeError(e));
    }
  }

  const cambios = (comp?.cambios ?? []).filter((c) => !q || `${c.nombre} ${c.cedula} ${c.puesto}`.toLowerCase().includes(q.toLowerCase()));

  return (
    <div className="max-w-7xl space-y-5">
      <Titulo>Histórico y novedades de programación</Titulo>
      <Alerta tipo="info">
        Cada carga del Excel de SIESA queda guardada. Compare una carga con la anterior del mismo mes para ver las <b>novedades de
        programación</b>: turnos agregados, eliminados o cambiados, y cómo cambió la cobertura de cada puesto.
      </Alerta>
      {error && <Alerta>{error}</Alerta>}

      {porMes.map((cargas) => (
        <section key={`${cargas[0].anio}-${cargas[0].mes}`} className="tarjeta overflow-x-auto">
          <h2 className="border-b border-slate-200 px-4 py-3 font-semibold">{nombreMes(cargas[0].anio, cargas[0].mes)}</h2>
          <table className="tabla">
            <thead>
              <tr>
                <th>Carga</th><th>Rango</th><th>Cargada</th><th className="w-56">Cobertura</th>
                <th className="text-right">H. descubiertas</th><th className="text-right">H. exceso</th>
                <th className="text-right">Cubrimientos pend.</th><th />
              </tr>
            </thead>
            <tbody>
              {cargas.map((c, i) => {
                const previa = cargas[i + 1];
                return (
                  <tr key={c.carga_id} className={sel.actual === c.carga_id ? "bg-marca-50" : ""}>
                    <td>#{c.carga_id}</td>
                    <td className="whitespace-nowrap">{c.desde} → {c.hasta}</td>
                    <td className="whitespace-nowrap">{new Date(c.cargado_en).toLocaleString("es-CO")}</td>
                    <td>
                      {c.cobertura_pct == null ? <span className="text-xs text-slate-400">sin análisis</span> : (
                        <div className="flex items-center gap-2">
                          <div className="h-2 flex-1 rounded-full bg-marca-100"><div className="h-2 rounded-full bg-marca-600" style={{ width: `${c.cobertura_pct}%` }} /></div>
                          <span className="w-14 text-right text-xs tabular-nums">{num(c.cobertura_pct, 1)} %</span>
                        </div>
                      )}
                    </td>
                    <td className="text-right tabular-nums">{c.descubiertas == null ? "—" : num(c.descubiertas)}</td>
                    <td className="text-right tabular-nums">{c.exceso == null ? "—" : num(c.exceso)}</td>
                    <td className="text-right tabular-nums">{c.cubrimientos_pendiente ?? "—"}</td>
                    <td className="whitespace-nowrap text-right text-sm">
                      {c.analisis_id && <Link className="mr-3 text-marca-600 hover:underline" href="/cobertura">Ver</Link>}
                      {previa && <button className="text-marca-600 hover:underline" onClick={() => comparar(previa.carga_id, c.carga_id)}>Comparar con #{previa.carga_id}</button>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      ))}
      {filas.length === 0 && <Alerta tipo="info">Aún no hay cargas de programación.</Alerta>}

      {comp && (
        <section className="space-y-3">
          <h2 className="text-lg font-semibold text-marca-900">Cambios de la carga #{comp.actual} frente a #{comp.anterior} ({comp.desde} → {comp.hasta})</h2>
          <div className="flex flex-wrap gap-2 text-sm">
            <Insignia>{comp.total} cambios</Insignia>
            {Object.entries(comp.por_tipo).map(([t, n]) => <Insignia key={t} color={TIPO[t]?.[1]}>{TIPO[t]?.[0]}: {n}</Insignia>)}
            <Insignia>{comp.personas} personas</Insignia>
            <Insignia>{comp.puestos} puestos</Insignia>
          </div>

          {comp.impacto.length > 0 && (
            <div className="tarjeta overflow-x-auto">
              <h3 className="border-b border-slate-200 px-4 py-2 text-sm font-semibold">Impacto en la cobertura</h3>
              <table className="tabla">
                <thead><tr><th>Puesto</th><th className="text-right">H. descubiertas antes → después</th><th className="text-right">H. exceso antes → después</th></tr></thead>
                <tbody>
                  {comp.impacto.slice(0, 50).map((i) => (
                    <tr key={i.puesto_id}>
                      <td className="font-mono font-semibold">{i.puesto}</td>
                      <td className="text-right tabular-nums">
                        {num(i.descubiertas_antes)} → <b className={i.descubiertas_despues > i.descubiertas_antes ? "text-[#a32525]" : "text-[#086b08]"}>{num(i.descubiertas_despues)}</b>
                        {i.descubiertas_despues > i.descubiertas_antes ? " ▲" : i.descubiertas_despues < i.descubiertas_antes ? " ▼" : ""}
                      </td>
                      <td className="text-right tabular-nums">{num(i.exceso_antes)} → <b>{num(i.exceso_despues)}</b></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <input className="input w-72" placeholder="Filtrar por persona o puesto…" value={q} onChange={(e) => setQ(e.target.value)} />
          <div className="tarjeta max-h-[60vh] overflow-auto">
            <table className="tabla">
              <thead className="sticky top-0"><tr><th>Fecha</th><th>Puesto</th><th>Persona</th><th>Cambio</th><th>Antes</th><th>Después</th></tr></thead>
              <tbody>
                {cambios.length === 0 && <tr><td colSpan={6} className="text-center text-slate-500">Sin cambios</td></tr>}
                {cambios.map((c, i) => (
                  <tr key={i}>
                    <td className="whitespace-nowrap">{c.fecha}</td>
                    <td className="font-mono">{c.puesto}</td>
                    <td>{c.nombre}<div className="text-xs text-slate-500">CC {c.cedula}</div></td>
                    <td><Insignia color={TIPO[c.tipo]?.[1]}>{TIPO[c.tipo]?.[0]}</Insignia></td>
                    <td className="text-slate-500">{c.antes ?? "—"}</td>
                    <td className="font-medium">{c.despues ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {comp.truncado && <p className="text-xs text-slate-500">Se muestran los primeros 3.000 cambios.</p>}
        </section>
      )}
    </div>
  );
}
