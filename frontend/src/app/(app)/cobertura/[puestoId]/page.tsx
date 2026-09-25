"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { ESTADOS, EstadoInsignia, num } from "@/components/estado";
import { Alerta } from "@/components/ui";
import { api, mensajeError, type DetallePuesto } from "@/lib/api";
import { DIAS, franjaTexto } from "@/lib/formato";

const CLASE_CELDA: Record<string, string> = {
  trabajo: "bg-marca-100 text-marca-900",
  descanso: "bg-slate-100 text-slate-500",
  novedad: "bg-[#fab219]/25 text-[#8a5a00] font-semibold",
  desconocido: "bg-red-100 text-red-700",
};

/** Abreviatura legible del código de SIESA: D = 06-18, N = 18-06, resto hora de inicio. */
function corto(codigo: string) {
  const c = codigo.replace(/\*/g, "").trim();
  if (c === "06:00 - 18:00") return "D";
  if (c === "18:00 - 06:00") return "N";
  const m = c.match(/^(\d{1,2}):(\d{2}) - (\d{1,2}):\d{2}/);
  if (m) return `${Number(m[1])}-${Number(m[3])}`;
  return c.length > 5 ? c.slice(0, 5) : c;
}

function Detalle() {
  const { puestoId } = useParams<{ puestoId: string }>();
  const analisisId = useSearchParams().get("analisis");
  const [d, setD] = useState<DetallePuesto | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!analisisId) return;
    api<DetallePuesto>(`/analisis/${analisisId}/puestos/${puestoId}`).then(setD).catch((e) => setError(mensajeError(e)));
  }, [analisisId, puestoId]);

  if (error) return <Alerta>{error}</Alerta>;
  if (!d) return <p className="text-slate-500">Cargando…</p>;

  const r = d.resumen;
  const p = r.puesto;
  const dias = d.dias;
  const semana = (fecha: string) => DIAS[(new Date(fecha + "T00:00:00").getDay() + 6) % 7];

  return (
    <div className="max-w-full space-y-5">
      <div>
        <Link href="/cobertura" className="text-sm text-marca-600 hover:underline">← Volver al tablero</Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold text-marca-900">Puesto {p.codigo}</h1>
          <EstadoInsignia estado={r.estado} />
        </div>
        <p className="text-slate-600">{p.ubicacion.nombre} · {p.descripcion} · {p.ubicacion.ciudad}</p>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-6">
        <Dato t="Vendido" v={d.franjas.length ? d.franjas.map(franjaTexto).join(" · ") : "Sin matriz"} />
        <Dato t="¿Incluye festivos?" v={d.incluye_festivos == null ? "—" : d.incluye_festivos ? "Sí" : "No"} />
        <Dato t="Hombres / titulares" v={`${num(r.hombres, 1)} / ${r.fijos}`} alerta={r.fijos > Number(r.hombres) + 0.5 || r.fijos < Number(r.hombres) - 0.5} />
        <Dato t="Personas programadas" v={String(r.personas)} />
        <Dato t="Horas descubiertas" v={num(r.horas_descubiertas)} />
        <Dato t="Horas en exceso" v={num(r.horas_exceso)} />
      </div>

      <section className="tarjeta overflow-x-auto">
        <table className="w-max border-separate border-spacing-0.5 text-center text-xs">
          <thead>
            <tr>
              <th className="sticky left-0 z-10 bg-white px-2 text-left font-semibold text-slate-600">Persona</th>
              {dias.map((x) => (
                <th key={x.fecha} className={`min-w-10 px-1 font-semibold ${d.festivos[x.fecha] ? "text-[#a32525]" : "text-slate-600"}`} title={d.festivos[x.fecha] ?? ""}>
                  <div>{semana(x.fecha)}</div>
                  <div>{Number(x.fecha.slice(8))}{d.festivos[x.fecha] ? "*" : ""}</div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {d.personas.map((per) => (
              <tr key={per.cedula}>
                <td className="sticky left-0 z-10 max-w-64 truncate bg-white px-2 text-left" title={`${per.nombre} · CC ${per.cedula}`}>
                  <span className="font-medium">{per.nombre}</span>
                  <span className="ml-1 text-slate-400">
                    {per.titular ? "titular" : per.puesto_titular ? `apoyo (titular en ${per.puesto_titular})` : "sin puesto titular"}
                  </span>
                </td>
                {dias.map((x) => {
                  const cod = per.dias[x.fecha];
                  return (
                    <td key={x.fecha} className={`h-7 rounded px-1 ${cod ? CLASE_CELDA[per.clases[x.fecha]] ?? "" : ""}`} title={cod ?? ""}>
                      {cod ? corto(cod) : ""}
                    </td>
                  );
                })}
              </tr>
            ))}
            <tr>
              <td className="sticky left-0 z-10 bg-white px-2 pt-2 text-left font-semibold">Resultado del día</td>
              {dias.map((x) => {
                const e = ESTADOS[x.estado] ?? ESTADOS.ok;
                const tip = x.detalle.map((t) => `${t.tipo === "hueco" ? "Falta" : "Sobra"} ${t.personas} de ${t.inicio} a ${t.fin}`).join("\n") || e.texto;
                return (
                  <td key={x.fecha} className={`h-8 rounded pt-2 font-semibold ${e.celda}`} title={tip}>
                    <span aria-label={e.texto}>{e.icono}</span>
                  </td>
                );
              })}
            </tr>
          </tbody>
        </table>
        <div className="flex flex-wrap gap-4 border-t border-slate-200 px-4 py-2 text-xs text-slate-600">
          <span><b>D</b> 06–18 · <b>N</b> 18–06 · otros: hora de inicio–fin</span>
          <span className="rounded bg-marca-100 px-1">turno</span>
          <span className="rounded bg-slate-100 px-1">descanso</span>
          <span className="rounded bg-[#fab219]/25 px-1">novedad</span>
          {Object.entries(ESTADOS).map(([k, e]) => <span key={k}>{e.icono} {e.texto}</span>)}
          <span className="text-[#a32525]">* festivo</span>
        </div>
      </section>

      <section className="tarjeta overflow-x-auto">
        <h2 className="border-b border-slate-200 px-4 py-3 font-semibold">Hallazgos por día</h2>
        <table className="tabla">
          <thead><tr><th>Fecha</th><th>Estado</th><th className="text-right">Vendidas</th><th className="text-right">Programadas</th><th>Detalle</th></tr></thead>
          <tbody>
            {dias.filter((x) => x.detalle.length).length === 0 && <tr><td colSpan={5} className="text-center text-slate-500">Sin hallazgos: el puesto está cubierto como se vendió</td></tr>}
            {dias.filter((x) => x.detalle.length).map((x) => (
              <tr key={x.fecha}>
                <td className="whitespace-nowrap">{semana(x.fecha)} {x.fecha}{d.festivos[x.fecha] && <span className="ml-1 text-xs text-[#a32525]">({d.festivos[x.fecha]})</span>}</td>
                <td><EstadoInsignia estado={x.estado} /></td>
                <td className="text-right tabular-nums">{num(x.horas_requeridas)} h</td>
                <td className="text-right tabular-nums">{num(x.horas_programadas)} h</td>
                <td>
                  {x.detalle.map((t, i) => (
                    <div key={i}>
                      {t.tipo === "hueco" ? "▼ Falta" : "▲ Sobra"} {t.personas} {t.personas === 1 ? "persona" : "personas"} de {t.inicio} a {t.fin}
                    </div>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function Dato({ t, v, alerta }: { t: string; v: string; alerta?: boolean }) {
  return (
    <div className={`tarjeta p-3 ${alerta ? "border-l-4 border-l-[#ec835a]" : ""}`}>
      <p className="text-xs text-slate-500">{t}</p>
      <p className="text-sm font-semibold text-slate-800">{v}{alerta && " ⚠"}</p>
    </div>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<p className="text-slate-500">Cargando…</p>}>
      <Detalle />
    </Suspense>
  );
}
