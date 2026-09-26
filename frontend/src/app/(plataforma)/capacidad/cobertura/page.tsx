"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { EstadoInsignia, num } from "@/components/estado";
import { Alerta, Titulo } from "@/components/ui";
import { api, mensajeError, type Analisis, type MesDisponible, type PuestoAnalisis } from "@/lib/api";
import { nombreMes } from "@/lib/formato";

const FILTROS: [string, string][] = [
  ["con_hallazgo", "Con hallazgos"],
  ["hueco", "Solo huecos"],
  ["exceso", "Solo exceso"],
  ["mixto", "Hueco y exceso"],
  ["fijos", "Titulares ≠ hombres"],
  ["sin_programacion", "Vendidos sin programar"],
  ["", "Todos"],
];

export default function CoberturaPage() {
  const [meses, setMeses] = useState<MesDisponible[]>([]);
  const [mes, setMes] = useState<MesDisponible | null>(null);
  const [analisis, setAnalisis] = useState<Analisis | null>(null);
  const [puestos, setPuestos] = useState<PuestoAnalisis[]>([]);
  const [filtro, setFiltro] = useState("con_hallazgo");
  const [ciudad, setCiudad] = useState("");
  const [q, setQ] = useState("");
  const [orden, setOrden] = useState("descubiertas");
  const [calculando, setCalculando] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api<MesDisponible[]>("/capacidad/analisis/meses").then((m) => {
      setMeses(m);
      setMes(m[0] ?? null);
    });
  }, []);

  useEffect(() => {
    setAnalisis(null);
    if (mes?.analisis_id) api<Analisis>(`/capacidad/analisis/${mes.analisis_id}`).then(setAnalisis);
  }, [mes]);

  const cargarPuestos = useCallback(async () => {
    if (!analisis) return setPuestos([]);
    const p = new URLSearchParams({ estado: filtro, ciudad, q, orden });
    setPuestos(await api<PuestoAnalisis[]>(`/capacidad/analisis/${analisis.id}/puestos?${p}`));
  }, [analisis, filtro, ciudad, q, orden]);

  useEffect(() => {
    const t = setTimeout(cargarPuestos, 250);
    return () => clearTimeout(t);
  }, [cargarPuestos]);

  async function calcular() {
    if (!mes) return;
    setError("");
    setCalculando(true);
    try {
      const a = await api<Analisis>("/capacidad/analisis", { method: "POST", json: { anio: mes.anio, mes: mes.mes } });
      setAnalisis(a);
      setMeses((lista) => lista.map((m) => (m.carga_id === mes.carga_id ? { ...m, analisis_id: a.id } : m)));
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setCalculando(false);
    }
  }

  const r = analisis?.resumen;

  return (
    <div className="max-w-7xl space-y-5">
      <Titulo
        accion={
          <div className="flex flex-wrap items-center gap-2">
            {meses.length > 0 && (
              <select className="input w-52" value={mes?.carga_id ?? ""} onChange={(e) => setMes(meses.find((m) => m.carga_id === Number(e.target.value)) ?? null)}>
                {meses.map((m) => <option key={m.carga_id} value={m.carga_id}>{nombreMes(m.anio, m.mes)}</option>)}
              </select>
            )}
            {mes && <button className="btn-primario" onClick={calcular} disabled={calculando}>{calculando ? "Calculando…" : analisis ? "Recalcular" : "Calcular cobertura"}</button>}
            {analisis && <a className="btn-secundario" href={`/api/capacidad/analisis/${analisis.id}/exportar`}>Exportar a Excel</a>}
          </div>
        }
      >
        Cobertura: vendido vs programado
      </Titulo>

      {error && <Alerta>{error}</Alerta>}
      {meses.length === 0 && <Alerta tipo="info">Aún no hay programación cargada. Súbala en <Link className="underline" href="/capacidad/programacion">Programación SIESA</Link>.</Alerta>}
      {mes && !mes.tiene_matriz && <Alerta>No existe matriz comercial para {nombreMes(mes.anio, mes.mes)}. Proyéctela o impórtela en <Link className="underline" href="/capacidad/matriz">Matriz comercial</Link>.</Alerta>}
      {mes && mes.tiene_matriz && !analisis && !calculando && <Alerta tipo="info">Este mes aún no tiene análisis. Pulse “Calcular cobertura”.</Alerta>}
      {analisis?.desactualizado && (
        <Alerta>⚠ {analisis.motivo_desactualizado}. Los resultados pueden no reflejar la situación actual: pulse “Recalcular”.</Alerta>
      )}

      {r && (
        <>
          <p className="text-sm text-slate-500">
            Programación del {r.desde} al {r.hasta} · calculado {new Date(analisis!.generado_en).toLocaleString("es-CO")}
          </p>

          <section className="grid gap-4 lg:grid-cols-[18rem_1fr]">
            <div className="tarjeta flex flex-col justify-center p-5">
              <p className="text-sm text-slate-500">Cobertura de horas vendidas</p>
              <p className="text-5xl font-semibold text-marca-900">{r.cobertura_pct == null ? "—" : `${num(r.cobertura_pct, 1)} %`}</p>
              <div className="mt-3 h-2 rounded-full bg-marca-100">
                <div className="h-2 rounded-full bg-marca-600" style={{ width: `${Math.max(0, Math.min(100, r.cobertura_pct ?? 0))}%` }} />
              </div>
              <p className="mt-2 text-xs text-slate-500">{num(r.requeridas)} h vendidas · {num(r.programadas)} h programadas</p>
            </div>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Tile label="Horas descubiertas" valor={num(r.descubiertas)} nota="vendidas sin nadie programado" estado="hueco" />
              <Tile label="Horas en exceso" valor={num(r.exceso)} nota="programadas de más" estado="exceso" />
              <Tile label="Puestos con hueco" valor={num((r.puestos_hueco ?? 0) + (r.puestos_mixto ?? 0))} nota={`de ${num(r.puestos)} analizados`} onClick={() => setFiltro("hueco")} />
              <Tile label="Puestos con exceso" valor={num((r.puestos_exceso ?? 0) + (r.puestos_mixto ?? 0))} nota={`${num(r.puestos_mixto)} con hueco y exceso`} onClick={() => setFiltro("exceso")} />
              <Tile label="Hombres presupuestados" valor={num(r.hombres, 1)} nota={`${num(r.fijos)} titulares programados`} />
              <Tile label="Titulares ≠ hombres" valor={num((r.puestos_fijos_de_mas ?? 0) + (r.puestos_fijos_de_menos ?? 0))} nota={`${num(r.puestos_fijos_de_mas)} de más · ${num(r.puestos_fijos_de_menos)} de menos`} onClick={() => setFiltro("fijos")} />
              <Tile label="Vendidos sin programar" valor={num(r.puestos_sin_programacion)} nota="nadie programado en el mes" onClick={() => setFiltro("sin_programacion")} />
              <Tile label="Filas sin puesto" valor={num(r.filas_sin_puesto)} nota="códigos SIESA por aclarar" href="/capacidad/maestros" />
            </div>
          </section>

          <section className="tarjeta overflow-x-auto">
            <h2 className="border-b border-slate-200 px-4 py-3 font-semibold">Por ciudad</h2>
            <table className="tabla">
              <thead>
                <tr><th>Ciudad</th><th className="text-right">Puestos</th><th className="text-right">Horas vendidas</th><th className="text-right">Descubiertas</th><th className="text-right">Exceso</th><th className="w-64">Cobertura</th></tr>
              </thead>
              <tbody>
                {Object.entries(r.por_ciudad)
                  .sort((a, b) => (b[1].descubiertas ?? 0) - (a[1].descubiertas ?? 0))
                  .map(([c, v]) => (
                    <tr key={c} className={`cursor-pointer hover:bg-slate-50 ${ciudad === c ? "bg-marca-50" : ""}`} onClick={() => setCiudad(ciudad === c ? "" : c)}>
                      <td className="font-medium">{c}</td>
                      <td className="text-right tabular-nums">{num(v.puestos)}</td>
                      <td className="text-right tabular-nums">{num(v.requeridas)}</td>
                      <td className="text-right tabular-nums">{num(v.descubiertas)}</td>
                      <td className="text-right tabular-nums">{num(v.exceso)}</td>
                      <td>
                        <div className="flex items-center gap-2" title={`${num(v.cobertura_pct, 1)} % de las horas vendidas están programadas`}>
                          <div className="h-2 flex-1 rounded-full bg-marca-100">
                            <div className="h-2 rounded-full bg-marca-600" style={{ width: `${v.cobertura_pct ?? 0}%` }} />
                          </div>
                          <span className="w-14 text-right text-xs tabular-nums">{v.cobertura_pct == null ? "—" : `${num(v.cobertura_pct, 1)} %`}</span>
                        </div>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
            <p className="px-4 py-2 text-xs text-slate-500">Haga clic en una ciudad para filtrar los puestos.</p>
          </section>

          <section className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              {FILTROS.map(([v, t]) => (
                <button key={v} onClick={() => setFiltro(v)} className={`rounded-full px-3 py-1 text-sm ${filtro === v ? "bg-marca-600 text-white" : "bg-white text-slate-600 ring-1 ring-slate-300 hover:bg-slate-50"}`}>{t}</button>
              ))}
              {ciudad && <button className="rounded-full bg-marca-100 px-3 py-1 text-sm text-marca-900" onClick={() => setCiudad("")}>{ciudad} ✕</button>}
              <input className="input ml-auto w-64" placeholder="Buscar puesto o ubicación…" value={q} onChange={(e) => setQ(e.target.value)} />
              <select className="input w-44" value={orden} onChange={(e) => setOrden(e.target.value)}>
                <option value="descubiertas">Más horas descubiertas</option>
                <option value="exceso">Más horas en exceso</option>
                <option value="puesto">Código de puesto</option>
              </select>
            </div>
            <div className="tarjeta max-h-[65vh] overflow-auto">
              <table className="tabla">
                <thead className="sticky top-0">
                  <tr>
                    <th>Puesto</th><th>Ubicación</th><th>Estado</th>
                    <th className="text-right">Hombres</th><th className="text-right">Titulares</th><th className="text-right">Personas</th>
                    <th className="text-right">H. descubiertas</th><th className="text-right">H. exceso</th><th className="text-right">Días hueco / exceso</th>
                  </tr>
                </thead>
                <tbody>
                  {puestos.length === 0 && <tr><td colSpan={9} className="text-center text-slate-500">Sin puestos para este filtro</td></tr>}
                  {puestos.map((p) => {
                    const h = Number(p.hombres);
                    const difFijos = p.fijos > h + 0.5 || p.fijos < h - 0.5;
                    return (
                      <tr key={p.puesto.id} className="hover:bg-slate-50">
                        <td className="font-mono font-semibold">
                          <Link className="text-marca-700 hover:underline" href={`/capacidad/cobertura/${p.puesto.id}?analisis=${analisis!.id}`}>{p.puesto.codigo}</Link>
                        </td>
                        <td>
                          <div>{p.puesto.ubicacion.nombre}</div>
                          <div className="text-xs text-slate-500">{p.puesto.descripcion} · {p.puesto.ubicacion.ciudad}</div>
                        </td>
                        <td><EstadoInsignia estado={p.estado} /></td>
                        <td className="text-right tabular-nums">{num(p.hombres, 1)}</td>
                        <td className={`text-right tabular-nums ${difFijos ? "font-semibold text-[#9a3f1a]" : ""}`} title={difFijos ? "Los titulares no coinciden con los hombres presupuestados" : ""}>
                          {p.fijos}{difFijos && " ⚠"}
                        </td>
                        <td className="text-right tabular-nums">{p.personas}</td>
                        <td className="text-right tabular-nums">{num(p.horas_descubiertas)}</td>
                        <td className="text-right tabular-nums">{num(p.horas_exceso)}</td>
                        <td className="text-right tabular-nums">{p.dias_hueco} / {p.dias_exceso}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-slate-500">{puestos.length} puestos. Titulares: personas cuyo puesto principal del mes es este (donde más turnos tienen).</p>
          </section>
        </>
      )}
    </div>
  );
}

function Tile({ label, valor, nota, estado, onClick, href }: {
  label: string; valor: string; nota?: string; estado?: "hueco" | "exceso"; onClick?: () => void; href?: string;
}) {
  const marca = estado === "hueco" ? "border-l-[#d03b3b]" : estado === "exceso" ? "border-l-[#fab219]" : "border-l-transparent";
  const contenido = (
    <>
      <p className="text-xs text-slate-500">{label}</p>
      <p className="text-2xl font-semibold text-slate-800">{valor}</p>
      {nota && <p className="text-xs text-slate-500">{nota}</p>}
    </>
  );
  const clase = `tarjeta border-l-4 ${marca} p-3 text-left ${onClick || href ? "hover:bg-slate-50" : ""}`;
  if (href) return <Link href={href} className={clase}>{contenido}</Link>;
  if (onClick) return <button onClick={onClick} className={clase}>{contenido}</button>;
  return <div className={clase}>{contenido}</div>;
}
