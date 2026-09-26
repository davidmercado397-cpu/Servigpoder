"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { num } from "@/components/estado";
import { Alerta } from "@/components/ui";
import { api, apiEnvelope, type AlertaT, type Analisis, type MesDisponible } from "@/lib/api";
import { nombreMes } from "@/lib/formato";
import { useSesion } from "@/lib/sesion";

const NIVEL: Record<string, { icono: string; texto: string; clase: string }> = {
  critica: { icono: "⛔", texto: "Crítica", clase: "border-l-[#d03b3b]" },
  advertencia: { icono: "⚠", texto: "Advertencia", clase: "border-l-[#fab219]" },
  info: { icono: "ℹ", texto: "Información", clase: "border-l-marca-600" },
};

export default function Inicio() {
  const sesion = useSesion();
  const puedeAnalisis = sesion.permisos.includes("capacidad.analisis.ver");
  const [alertas, setAlertas] = useState<AlertaT[] | null>(null);
  const [fecha, setFecha] = useState("");
  const [analisis, setAnalisis] = useState<Analisis | null>(null);
  const [abierta, setAbierta] = useState<number | null>(null);

  useEffect(() => {
    if (!puedeAnalisis) return;
    apiEnvelope<AlertaT[]>("/capacidad/alertas").then((r) => {
      setAlertas(r.data ?? []);
      setFecha(String(r.meta.extra?.fecha ?? ""));
    });
    api<MesDisponible[]>("/capacidad/analisis/meses").then((m) => {
      const conAnalisis = m.find((x) => x.analisis_id);
      if (conAnalisis?.analisis_id) api<Analisis>(`/capacidad/analisis/${conAnalisis.analisis_id}`).then(setAnalisis);
    });
  }, [puedeAnalisis]);

  const r = analisis?.resumen as (Analisis["resumen"] & { cubrimientos_pendiente?: number }) | undefined;

  return (
    <div className="max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-marca-900">Hola, {sesion.nombre}</h1>
        <p className="text-slate-500">Control de capacidad operativa de la programación de personal{fecha && ` · ${fecha}`}</p>
      </div>

      {!puedeAnalisis && <Alerta tipo="info">Use el menú de la izquierda para acceder a sus opciones.</Alerta>}

      {r && (
        <section className="grid gap-3 md:grid-cols-4">
          <Link href="/capacidad/cobertura" className="tarjeta p-4 hover:bg-slate-50">
            <p className="text-xs text-slate-500">Cobertura · {nombreMes(r.anio, r.mes)}</p>
            <p className="text-4xl font-semibold text-marca-900">{r.cobertura_pct == null ? "—" : `${num(r.cobertura_pct, 1)} %`}</p>
          </Link>
          <Link href="/capacidad/cobertura" className="tarjeta p-4 hover:bg-slate-50">
            <p className="text-xs text-slate-500">Horas descubiertas</p>
            <p className="text-2xl font-semibold">{num(r.descubiertas)}</p>
          </Link>
          <Link href="/capacidad/cobertura" className="tarjeta p-4 hover:bg-slate-50">
            <p className="text-xs text-slate-500">Horas en exceso</p>
            <p className="text-2xl font-semibold">{num(r.exceso)}</p>
          </Link>
          <Link href="/capacidad/cubrimientos" className="tarjeta p-4 hover:bg-slate-50">
            <p className="text-xs text-slate-500">Cubrimientos sin justificación automática</p>
            <p className="text-2xl font-semibold">{num(r.cubrimientos_pendiente)}</p>
          </Link>
        </section>
      )}

      {puedeAnalisis && (
        <section className="space-y-2">
          <h2 className="font-semibold text-slate-700">Alertas</h2>
          {alertas === null && <p className="text-sm text-slate-500">Evaluando…</p>}
          {alertas?.length === 0 && <Alerta tipo="ok">✓ Sin alertas: todo está al día.</Alerta>}
          {alertas?.map((a, i) => {
            const n = NIVEL[a.nivel];
            return (
              <div key={i} className={`tarjeta border-l-4 ${n.clase} p-4`}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="font-semibold">
                      <span aria-hidden>{n.icono}</span> {a.titulo} <span className="ml-1 text-xs font-normal text-slate-500">{n.texto}</span>
                    </p>
                    <p className="text-sm text-slate-600">{a.detalle}</p>
                  </div>
                  <div className="flex gap-3 text-sm">
                    {a.items.length > 0 && (
                      <button className="text-marca-600 hover:underline" onClick={() => setAbierta(abierta === i ? null : i)}>
                        {abierta === i ? "Ocultar" : `Ver ${a.items.length}`}
                      </button>
                    )}
                    {a.enlace && <Link className="text-marca-600 hover:underline" href={a.enlace}>Ir →</Link>}
                  </div>
                </div>
                {abierta === i && (
                  <table className="tabla mt-3">
                    <thead><tr><th>Fecha</th><th>Puesto</th><th>Horas</th><th>Franjas sin cubrir</th></tr></thead>
                    <tbody>
                      {a.items.map((it, j) => (
                        <tr key={j}>
                          <td>{String(it.fecha)}</td>
                          <td>
                            {analisis ? (
                              <Link className="font-mono text-marca-700 hover:underline" href={`/capacidad/cobertura/${it.puesto_id}?analisis=${analisis.id}`}>{String(it.puesto)}</Link>
                            ) : String(it.puesto)}
                          </td>
                          <td>{String(it.horas)}</td>
                          <td>{String(it.franjas)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            );
          })}
        </section>
      )}
    </div>
  );
}
