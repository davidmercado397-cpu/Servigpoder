"use client";

import { useState } from "react";
import { CLASES, CONCEPTOS, RECARGOS, TIPOS_DIA, horas, type Dia } from "@/lib/liquidador";

const LETRA = ["D", "L", "M", "X", "J", "V", "S"];
const NOMBRE_DIA = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"];
// Abreviatura de cada concepto que lleva recargo o es extra (las horas ordinarias se muestran como «7 h»)
const CORTO: Record<string, string> = {
  ordinary_night: "RN", holiday_day_surcharge: "RFD", holiday_night_surcharge: "RFN", sunday_surcharge: "RD", sunday_night_surcharge: "RDN",
  overtime_day: "EXD", overtime_night: "EXN", holiday_overtime_day: "EXFD", holiday_overtime_night: "EXFN",
  sunday_overtime_day: "EXDD", sunday_overtime_night: "EXDN",
};
const FESTIVOS = ["holiday", "saturday_holiday", "holiday_double"];
const PAGA_POR_DIA: Record<string, string> = { descanso_pago: "día", incapacidad: "día", novedad: "día" };
const QUE_PAGA: Record<string, string> = {
  descanso_pago: "Paga el día de salario y el auxilio de transporte", libre: "Paga el día de salario (no el auxilio de transporte)",
  ausencia: "No se paga y descuenta los auxilios no prestacionales", incapacidad: "Se paga al 100 % (los 2 primeros días los paga la empresa)",
  novedad: "Se liquida según su código (vacaciones, licencias…)",
};

function fechas(desde: string, hasta: string): string[] {
  const out: string[] = [];
  for (let f = new Date(desde + "T12:00:00"); f <= new Date(hasta + "T12:00:00"); f.setDate(f.getDate() + 1)) {
    out.push(f.toISOString().slice(0, 10));
  }
  return out;
}

/** Programación de la persona como calendario: el turno de cada día con su color y, debajo, las horas que paga
 * (ordinarias, recargos y extras). Al tocar un día se ve su detalle. */
export function ProgramacionDias({ dias, desde, hasta, diasAuxilio }: { dias: Dia[]; desde: string; hasta: string; diasAuxilio?: number }) {
  const porFecha = Object.fromEntries(dias.map((d) => [d.fecha, d]));
  const lista = fechas(desde, hasta);
  const [sel, setSel] = useState<string | null>(dias[0]?.fecha ?? null);
  const elegido = sel ? porFecha[sel] : undefined;

  const total = (filtro: (k: string) => boolean) => dias.reduce((s, d) => s + Object.entries(d.horas).filter(([k]) => filtro(k)).reduce((a, [, h]) => a + h, 0), 0);
  const ordinarias = total((k) => k === "ordinary_day");
  const recargo = total((k) => RECARGOS.includes(k));
  const extras = total((k) => k !== "ordinary_day" && !RECARGOS.includes(k));
  const cifra = (t: string, v: string) => (
    <div className="rounded-lg bg-slate-50 px-3 py-2"><p className="text-xs text-slate-500">{t}</p><p className="text-lg font-semibold tabular-nums">{v}</p></div>
  );

  return (
    <section className="space-y-3 rounded-lg border border-slate-200 p-4">
      <h3 className="font-semibold text-slate-900">Programación y horas que paga cada día</h3>
      <div className="overflow-x-auto pb-1">
        <div className="grid gap-1" style={{ gridTemplateColumns: `repeat(${lista.length}, minmax(44px, 1fr))` }}>
          {lista.map((f) => {
            const fe = new Date(f + "T12:00:00");
            const d = porFecha[f];
            const rojo = fe.getDay() === 0 || (d && FESTIVOS.includes(d.tipo_dia));
            return (
              <div key={`h-${f}`} className={`text-center text-xs ${rojo ? "font-semibold text-red-700" : "text-slate-500"}`}
                title={d ? TIPOS_DIA.find(([k]) => k === d.tipo_dia)?.[1] : undefined}>
                {LETRA[fe.getDay()]}<br />{fe.getDate()}
              </div>
            );
          })}
          {lista.map((f) => {
            const d = porFecha[f];
            if (!d) return <div key={f} className="rounded-md border border-dashed border-slate-200 py-2 text-center text-xs text-slate-300" title="Sin turno">—</div>;
            const color = CLASES.find(([k]) => k === d.clase)?.[2] ?? "bg-slate-100 text-slate-700";
            const ord = d.horas.ordinary_day ?? 0;
            const otros = Object.entries(d.horas).filter(([k, h]) => k !== "ordinary_day" && h);
            return (
              <button key={f} type="button" onClick={() => setSel(f)} title={d.turno}
                className={`rounded-md border-2 px-0.5 py-1 text-center text-xs leading-tight ${color} ${sel === f ? "border-marca-600" : "border-transparent hover:border-slate-300"}`}>
                <span className="block font-mono text-sm font-semibold">{d.codigo}</span>
                <span className="block font-medium">{ord ? `${horas(ord)} h` : PAGA_POR_DIA[d.clase] ?? "—"}</span>
                {otros.map(([k, h]) => <span key={k} className="block text-[10px] opacity-80">{CORTO[k] ?? k} {horas(h)}</span>)}
              </button>
            );
          })}
        </div>
      </div>
      <p className="text-xs text-slate-500">
        Debajo del código, las horas ordinarias que paga el día · RN recargo nocturno · RD/RDN dominical diurno/nocturno · RFD/RFN festivo
        diurno/nocturno · EX… horas extras. Domingos y festivos en rojo. Toque un día para ver su detalle.
      </p>
      {elegido && (
        <div className="rounded-lg bg-slate-50 px-4 py-3 text-sm">
          <p className="mb-1 font-medium text-slate-900">
            {NOMBRE_DIA[new Date(elegido.fecha + "T12:00:00").getDay()]} {Number(elegido.fecha.slice(8, 10))} · <span className="font-mono">{elegido.codigo}</span>{" "}
            {elegido.turno} · {TIPOS_DIA.find(([k]) => k === elegido.tipo_dia)?.[1] ?? elegido.tipo_dia} · {CLASES.find(([k]) => k === elegido.clase)?.[4] ?? elegido.clase}
          </p>
          {Object.values(elegido.horas).some(Boolean) ? (
            <table className="text-sm">
              <tbody>
                {CONCEPTOS.filter(([k]) => elegido.horas[k]).map(([k, largo]) => (
                  <tr key={k}>
                    <td className="pr-6">{k === "ordinary_day" ? "Horas ordinarias" : largo}</td>
                    <td className="pr-6 text-right font-medium tabular-nums">{horas(elegido.horas[k])} h</td>
                    <td className="text-xs text-slate-500">
                      {k === "ordinary_day" ? "van en el sueldo" : RECARGOS.includes(k) ? "recargo sobre horas que ya están en el sueldo" : "hora extra (se paga completa con su %)"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <p className="text-slate-600">{QUE_PAGA[elegido.clase] ?? "Sin horas"}</p>}
        </div>
      )}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {cifra("Horas ordinarias", horas(ordinarias))}
        {cifra("Horas con recargo", horas(recargo))}
        {cifra("Horas extras", horas(extras))}
        {diasAuxilio !== undefined && cifra("Días de auxilio de transporte", String(diasAuxilio))}
      </div>
    </section>
  );
}
