"use client";

import { Fragment } from "react";
import { pesos } from "@/lib/formato";
import { CONCEPTOS_PAGO, TIPOS_DESCUENTO, horas, type Nomina } from "@/lib/liquidador";

/** Devengado, deducciones, neto y alertas de una persona (nómina de un periodo o de un costeo). */
export function NominaPersona({ n, titulo = "Nómina del periodo" }: { n: Nomina; titulo?: string }) {
  const fila = (concepto: React.ReactNode, detalle: React.ReactNode, valor: number, clase = "") => (
    <tr className={clase}><td>{concepto}</td><td className="text-xs text-slate-500">{detalle}</td><td className="whitespace-nowrap text-right tabular-nums">{pesos(valor)}</td></tr>
  );
  const usados = CONCEPTOS_PAGO.filter(([k]) => n.valores[k]);
  return (
    <section className="rounded-lg border border-slate-200">
      <header className="flex flex-wrap items-baseline gap-x-4 gap-y-1 border-b border-slate-200 bg-slate-50 px-4 py-3">
        <h3 className="font-semibold text-slate-900">{titulo}</h3>
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
            {n.vacaciones && (
              <>
                {fila("Vacaciones días hábiles", `${n.vacaciones.dias_habiles} días × ${pesos(n.vacaciones.valor_dia)} (hábiles: ${n.vacaciones.dias_habiles_empleado})`, n.vacaciones.valor_habiles)}
                {n.vacaciones.dias_no_habiles > 0 && fila("Vacaciones días no hábiles", `${n.vacaciones.dias_no_habiles} días × ${pesos(n.vacaciones.valor_dia)}`, n.vacaciones.valor_no_habiles)}
              </>
            )}
            {usados.map(([k, largo]) => <Fragment key={k}>{fila(largo, `${horas(n.horas[k])} h`, n.valores[k])}</Fragment>)}
            {(n.auxilios ?? []).map((x) => (
              <Fragment key={`aux-${x.id}`}>{fila(`Auxilio no prestacional: ${x.descripcion}`, x.calculo, x.valor)}</Fragment>
            ))}
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
                {fila(`${TIPOS_DESCUENTO[x.tipo]?.[0] ?? x.tipo}: ${x.descripcion}`,
                  <>{x.calculo}{x.observacion && <span className="block text-amber-700">{x.observacion}</span>}</>, x.valor)}
              </Fragment>
            ))}
            {fila(<b>Total deducciones</b>, "", n.deducciones, "bg-slate-50")}
            {fila(<b>Neto a pagar</b>, "", n.neto, "bg-marca-50 font-bold text-marca-900")}
          </tbody>
        </table>
      </div>
      {n.vacaciones && (
        <p className="border-t border-slate-200 px-4 py-2 text-xs text-slate-500">
          Base de vacaciones {pesos(n.vacaciones.base)}: salario {pesos(n.vacaciones.salario)} + promedio variable {pesos(n.vacaciones.promedio)}{" "}
          ({n.vacaciones.promedio_manual ? "fijado por nómina" : `sugerido con ${n.vacaciones.meses_promedio} meses de recargo nocturno`}).
          {n.vacaciones.saldo ? ` Saldo pendiente: ${n.vacaciones.saldo.pendientes.toLocaleString("es-CO")} días hábiles.` : " Sin fecha de ingreso: no se controla el saldo."}
        </p>
      )}
      {(n.alertas ?? []).map((a) => <p key={a} className="border-t border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-900">{a}</p>)}
      {n.dias_sin_pago > 0 && (
        <p className="border-t border-slate-200 px-4 py-2 text-xs text-slate-500">
          {n.dias_sin_pago} días sin pago en esta nómina: ausencias y novedades (licencias…, que se pagan en otro proceso).
        </p>
      )}
    </section>
  );
}
