"use client";

import { useEffect, useState } from "react";
import { Alerta, Insignia, Titulo } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";
import { usePermiso } from "@/lib/sesion";

type Grupo = { nombre: string; tratamiento: string; revisado: boolean };
type Parametros = {
  tolerancia: number; smlmv: number; auxilio_transporte: number; horas_dia: number;
  solo_primera_quincena: string; excluidos_base_embargo: string; embargos_sin_minimo: string;
};

const TRATAMIENTOS: [string, string, string][] = [
  ["validar", "Se valida", "Se revisa todo: días, salario, auxilio, modalidad y cuotas"],
  ["administrativo", "Administrativo", "Solo contrato y cuotas (no necesita programación)"],
  ["excluido", "Excluido (los 7)", "No se revisa"],
];

const CAMPOS: [keyof Parametros, string, string, "numero" | "texto"][] = [
  ["tolerancia", "Margen de tolerancia ($)", "Diferencias menores no generan alerta", "numero"],
  ["smlmv", "Salario mínimo mensual ($)", "Para el auxilio de transporte (hasta 2 SMLMV) y los embargos", "numero"],
  ["auxilio_transporte", "Auxilio de transporte mensual ($)", "Se divide entre 30 para el valor por día", "numero"],
  ["horas_dia", "Horas de salario por día", "Días de salario = horas del concepto 100 ÷ este valor", "numero"],
  ["solo_primera_quincena", "Cuotas que solo se descuentan en la 1.ª quincena", "Conceptos separados por coma", "texto"],
  ["excluidos_base_embargo", "Conceptos fuera de la base del embargo", "Además del auxilio de transporte (103)", "texto"],
  ["embargos_sin_minimo", "Embargos sobre la base completa", "Sin restar el salario mínimo (p. ej. cooperativas)", "texto"],
];

export default function ConfiguracionNomina() {
  const configurar = usePermiso("nomina.configurar");
  const [grupos, setGrupos] = useState<Grupo[]>([]);
  const [par, setPar] = useState<Parametros | null>(null);
  const [error, setError] = useState("");
  const [aviso, setAviso] = useState("");

  useEffect(() => {
    api<Grupo[]>("/nomina/grupos").then(setGrupos).catch((e) => setError(mensajeError(e)));
    api<Parametros>("/nomina/parametros").then(setPar).catch(() => {});
  }, []);

  async function guardarGrupo(g: Grupo, tratamiento: string) {
    setError("");
    try {
      const n = await api<Grupo>(`/nomina/grupos/${encodeURIComponent(g.nombre)}`, { method: "PUT", json: { tratamiento } });
      setGrupos((l) => l.map((x) => (x.nombre === g.nombre ? n : x)));
      setAviso("Grupo actualizado. Recalcule las revisiones abiertas para aplicar el cambio.");
    } catch (e) {
      setError(mensajeError(e));
    }
  }

  async function guardarParametros(e: React.FormEvent) {
    e.preventDefault();
    if (!par) return;
    setError("");
    try {
      setPar(await api<Parametros>("/nomina/parametros", { method: "PUT", json: par }));
      setAviso("Parámetros guardados. Recalcule las revisiones abiertas para aplicarlos.");
    } catch (err) {
      setError(mensajeError(err));
    }
  }

  return (
    <div className="max-w-5xl space-y-5">
      <Titulo>Grupos y parámetros</Titulo>
      {error && <Alerta>{error}</Alerta>}
      {aviso && <Alerta tipo="ok">{aviso}</Alerta>}

      <section className="tarjeta overflow-hidden">
        <h2 className="border-b border-slate-200 bg-slate-50 px-4 py-2 font-semibold text-slate-800">Grupos de empleados (del listado de contratos)</h2>
        <table className="tabla text-sm">
          <thead><tr><th>Grupo</th><th>Tratamiento</th><th /></tr></thead>
          <tbody>
            {grupos.map((g) => (
              <tr key={g.nombre}>
                <td className="font-medium">{g.nombre} {!g.revisado && <Insignia color="bg-amber-100 text-amber-800">nuevo</Insignia>}</td>
                <td>
                  <select className="input w-56" disabled={!configurar} value={g.tratamiento} onChange={(e) => guardarGrupo(g, e.target.value)}>
                    {TRATAMIENTOS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
                  </select>
                </td>
                <td className="text-xs text-slate-500">{TRATAMIENTOS.find(([v]) => v === g.tratamiento)?.[2]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {par && (
        <form onSubmit={guardarParametros} className="tarjeta space-y-4 p-5">
          <h2 className="font-semibold text-slate-800">Parámetros del cálculo</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {CAMPOS.map(([k, t, ayuda, tipo]) => (
              <div key={k}>
                <label className="label">{t}</label>
                <input className="input" disabled={!configurar} type={tipo === "numero" ? "number" : "text"} step="any"
                  value={par[k]} onChange={(e) => setPar({ ...par, [k]: tipo === "numero" ? Number(e.target.value) : e.target.value })} />
                <p className="mt-1 text-xs text-slate-500">{ayuda}</p>
              </div>
            ))}
          </div>
          {configurar && <div className="flex justify-end"><button className="btn-primario">Guardar parámetros</button></div>}
        </form>
      )}
    </div>
  );
}
