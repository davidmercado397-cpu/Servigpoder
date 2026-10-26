"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Alerta, Titulo } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";
import { fecha, pct, pesos, valorItem } from "@/lib/costeo";

type PorTipo = { tipo: string; unidad: string; mfp: number; pactado: number; ejecutado: number; pendiente: number; reembolso: number; excedidos: number };
type Resumen = {
  mfp: number; estados: Record<string, number>; alertas: Record<string, number>; facturacion_total: number; pactado: number; ejecutado: number;
  pendiente_vigentes: number; reembolso_vigentes: number; por_tipo: PorTipo[];
  por_vencer: { id: number; numero: string; cliente: string; fecha_fin: string | null; pendiente: number }[];
};

const ALERTAS: Record<string, string> = {
  excede: "Ejecutado mayor que lo pactado", supera_comercial: "MFP mayor que el % comercial", por_vencer: "Por vencer con saldo",
  bolsa_agotada: "Bolsa de horas agotada", datos_incompletos: "Datos del contrato incompletos",
};

export default function ResumenCosteo() {
  const [r, setR] = useState<Resumen | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api<Resumen>("/costeo/resumen").then(setR).catch((e) => setError(mensajeError(e)));
  }, []);

  if (error) return <Alerta>{error}</Alerta>;
  if (!r) return <p className="text-sm text-slate-500">Cargando…</p>;
  const tile = (titulo: string, valor: string, nota?: string) => (
    <div className="tarjeta p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{titulo}</p>
      <p className="mt-1 text-xl font-bold text-marca-900">{valor}</p>
      {nota && <p className="text-xs text-slate-500">{nota}</p>}
    </div>
  );
  return (
    <>
      <Titulo>Resumen de MFP</Titulo>
      <div className="mb-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {tile("MFP", String(r.mfp), `${r.estados.vigente ?? 0} vigentes · ${r.estados.vencida ?? 0} vencidas · ${r.estados.terminada ?? 0} terminadas`)}
        {tile("MFP pactada", pesos(r.pactado), `${pct(r.facturacion_total ? r.pactado / r.facturacion_total : null)} de ${pesos(r.facturacion_total)} facturados`)}
        {tile("Ejecutado", pesos(r.ejecutado), `${pct(r.pactado ? r.ejecutado / r.pactado : null)} de lo pactado`)}
        {tile("Pendiente (vigentes)", pesos(r.pendiente_vigentes), `Reembolso si terminaran hoy: ${pesos(r.reembolso_vigentes)}`)}
      </div>

      <div className="grid gap-5 xl:grid-cols-[2fr_1fr]">
        <div className="tarjeta overflow-x-auto">
          <h2 className="border-b border-slate-100 px-4 py-3 font-semibold text-slate-700">Por ítem</h2>
          <table className="tabla">
            <thead><tr><th>Ítem</th><th className="text-right">MFP</th><th className="text-right">Pactado</th><th className="text-right">Ejecutado</th>
              <th className="text-right">Pendiente</th><th className="text-right">Reembolso a hoy</th><th className="text-right">Excedidos</th></tr></thead>
            <tbody>
              {r.por_tipo.map((t) => (
                <tr key={t.tipo}>
                  <td className="font-medium">{t.tipo}</td>
                  <td className="text-right tabular-nums">{t.mfp}</td>
                  <td className="text-right tabular-nums">{valorItem(t.pactado, t.unidad)}</td>
                  <td className="text-right tabular-nums">{valorItem(t.ejecutado, t.unidad)}</td>
                  <td className="text-right tabular-nums">{valorItem(t.pendiente, t.unidad)}</td>
                  <td className="text-right tabular-nums">{t.unidad === "horas" ? "—" : pesos(t.reembolso)}</td>
                  <td className={`text-right tabular-nums ${t.excedidos ? "font-semibold text-red-700" : ""}`}>{t.excedidos}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="space-y-5">
          <div className="tarjeta p-4">
            <h2 className="mb-2 font-semibold text-slate-700">Alertas</h2>
            {Object.keys(r.alertas).length === 0 ? <p className="text-sm text-slate-500">Sin alertas.</p> : (
              <ul className="space-y-1 text-sm">
                {Object.entries(r.alertas).map(([k, n]) => (
                  <li key={k} className="flex justify-between"><Link className="text-marca-700 hover:underline" href={`/costeo/mfp?alertas=1`}>{ALERTAS[k] ?? k}</Link><span className="tabular-nums">{n}</span></li>
                ))}
              </ul>
            )}
          </div>
          <div className="tarjeta p-4">
            <h2 className="mb-2 font-semibold text-slate-700">Vencen en los próximos 60 días con saldo</h2>
            {r.por_vencer.length === 0 ? <p className="text-sm text-slate-500">Ninguna.</p> : (
              <ul className="space-y-1 text-sm">
                {r.por_vencer.map((m) => (
                  <li key={m.id} className="flex justify-between gap-2">
                    <Link className="truncate text-marca-700 hover:underline" href={`/costeo/mfp/${m.id}`}>{m.numero} · {m.cliente}</Link>
                    <span className="whitespace-nowrap text-slate-500">{fecha(m.fecha_fin)} · {pesos(m.pendiente)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
