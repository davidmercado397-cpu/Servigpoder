"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useMesAnalizado } from "@/components/selector-mes";
import { Alerta, Titulo } from "@/components/ui";
import { apiEnvelope, type PersonaBolsa } from "@/lib/api";

export default function BolsasPage() {
  const { analisisId, selector, cargado } = useMesAnalizado();
  const [todas, setTodas] = useState(false);
  const [lista, setLista] = useState<PersonaBolsa[]>([]);
  const [horas, setHoras] = useState(0);
  const [q, setQ] = useState("");

  useEffect(() => {
    if (!analisisId) return;
    apiEnvelope<PersonaBolsa[]>(`/cubrimientos/${analisisId}/bolsas?todas=${todas}`).then((r) => {
      setLista(r.data ?? []);
      setHoras(Number(r.meta.extra?.horas ?? 0));
    });
  }, [analisisId, todas]);

  const filtrada = lista.filter((p) => !q || `${p.nombre} ${p.cedula}`.toLowerCase().includes(q.toLowerCase()));

  return (
    <div className="max-w-6xl space-y-4">
      <Titulo accion={selector}>Personas en bolsa sin puesto</Titulo>
      <Alerta tipo="info">
        Personas con turnos en las bolsas de <b>disponibles (05)</b> y <b>relevantes (06)</b> los días en que no cubren ningún puesto.
        Es capacidad programada que no está cubriendo un servicio vendido.
      </Alerta>
      {cargado && !analisisId && <Alerta>Este mes no tiene análisis. Calcúlelo en <Link className="underline" href="/cobertura">Cobertura</Link>.</Alerta>}
      {analisisId && (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <input className="input w-72" placeholder="Buscar persona o cédula…" value={q} onChange={(e) => setQ(e.target.value)} />
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={todas} onChange={(e) => setTodas(e.target.checked)} /> Incluir todas las bolsas (07 incapacitados, 08 vacaciones)
            </label>
            <span className="text-sm text-slate-500">{filtrada.length} personas · {horas.toLocaleString("es-CO")} horas sin puesto</span>
          </div>
          <div className="tarjeta max-h-[70vh] overflow-auto">
            <table className="tabla">
              <thead className="sticky top-0">
                <tr><th>Persona</th><th>Bolsa</th><th className="text-right">Días sin puesto</th><th className="text-right">Horas</th><th className="text-right">Días cubriendo puestos</th><th>Fechas sin puesto</th></tr>
              </thead>
              <tbody>
                {filtrada.length === 0 && <tr><td colSpan={6} className="text-center text-slate-500">Nadie en bolsa sin puesto</td></tr>}
                {filtrada.map((p) => (
                  <tr key={p.cedula}>
                    <td><div>{p.nombre}</div><div className="text-xs text-slate-500">CC {p.cedula}</div></td>
                    <td className="text-sm">{p.bolsas.join(", ")}</td>
                    <td className="text-right tabular-nums">{p.dias_sin_puesto.length}</td>
                    <td className="text-right tabular-nums">{p.horas_sin_puesto.toLocaleString("es-CO")}</td>
                    <td className="text-right tabular-nums">{p.dias_en_puesto}</td>
                    <td className="max-w-md text-xs text-slate-600">{p.dias_sin_puesto.map((d) => Number(d.slice(8))).join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
