"use client";

import { useSesion } from "@/lib/sesion";

const FASES = [
  { fase: "F0", nombre: "Base: acceso, usuarios, roles y despliegue", estado: "Listo" },
  { fase: "F1", nombre: "Maestros, matriz comercial (con proyección) y carga de programación SIESA", estado: "Listo" },
  { fase: "F2", nombre: "Motor de cobertura, tablero y vista de puesto", estado: "En construcción" },
  { fase: "F3", nombre: "Cubrimientos, bandeja de nómina y bolsas", estado: "Pendiente" },
  { fase: "F4", nombre: "Histórico, comparación de cargas y alertas", estado: "Pendiente" },
];

const COLOR: Record<string, string> = {
  Listo: "bg-green-100 text-green-800",
  "En construcción": "bg-amber-100 text-amber-800",
  Pendiente: "bg-slate-100 text-slate-600",
};

export default function Inicio() {
  const sesion = useSesion();
  return (
    <div className="max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-marca-900">Hola, {sesion.nombre}</h1>
        <p className="text-slate-500">Control de capacidad operativa de la programación de personal.</p>
      </div>
      <section className="tarjeta">
        <h2 className="border-b border-slate-200 px-4 py-3 font-semibold">Avance del proyecto</h2>
        <table className="tabla">
          <tbody>
            {FASES.map((f) => (
              <tr key={f.fase}>
                <td className="w-12 font-semibold text-marca-700">{f.fase}</td>
                <td>{f.nombre}</td>
                <td className="w-40 text-right">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${COLOR[f.estado]}`}>{f.estado}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
