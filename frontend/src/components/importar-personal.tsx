"use client";

import { Upload, X } from "lucide-react";
import { useState } from "react";
import { Alerta } from "@/components/ui";
import { mensajeError, subirArchivo } from "@/lib/api";
import type { Hallazgo } from "@/lib/liquidador";

type Resultado = { tipo: "base" | "vacaciones"; datos: Record<string, unknown> & { hallazgos: Hallazgo[] } };

const RESUMEN: Record<Resultado["tipo"], [string, string][]> = {
  base: [["empleados", "Personas en la base"], ["creados", "Creadas"], ["actualizados", "Actualizadas"], ["activos", "Activas"],
    ["retirados", "Retiradas"], ["contratos_retirados", "Contratos con retiro"]],
  vacaciones: [["saldos", "Saldos cargados"], ["salidas", "Salidas en el historial"], ["programadas", "Programadas"],
    ["compensadas", "Compensadas"], ["creados", "Personas creadas"]],
};

/** Importación de la base de personal y del libro de vacaciones: el archivo se procesa y se descarta. */
export function ImportarPersonal({ onImportado }: { onImportado: () => void }) {
  const [archivos, setArchivos] = useState<{ base: File | null; vacaciones: File | null }>({ base: null, vacaciones: null });
  const [cargando, setCargando] = useState<Resultado["tipo"] | null>(null);
  const [resultado, setResultado] = useState<Resultado | null>(null);
  const [error, setError] = useState("");

  async function importar(tipo: Resultado["tipo"]) {
    const archivo = archivos[tipo];
    if (!archivo) return;
    setError("");
    setResultado(null);
    setCargando(tipo);
    try {
      const datos = await subirArchivo<Resultado["datos"]>(tipo === "base" ? "/liquidador/personal/importar-base" : "/liquidador/personal/importar-vacaciones", archivo);
      setResultado({ tipo, datos });
      onImportado();
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setCargando(null);
    }
  }

  const fila = (tipo: Resultado["tipo"], titulo: string, ayuda: string) => (
    <div className="rounded-lg border border-slate-200 p-3">
      <p className="text-sm font-medium text-slate-800">{titulo}</p>
      <p className="mb-2 text-xs text-slate-500">{ayuda}</p>
      <div className="flex flex-wrap items-center gap-2">
        <input className="input max-w-xs" type="file" accept=".xlsx" onChange={(e) => setArchivos({ ...archivos, [tipo]: e.target.files?.[0] ?? null })} />
        <button className="btn-primario inline-flex items-center gap-1.5" disabled={!archivos[tipo] || cargando !== null} onClick={() => importar(tipo)}>
          <Upload className="h-4 w-4" /> {cargando === tipo ? "Importando…" : "Importar"}
        </button>
      </div>
    </div>
  );

  return (
    <section className="tarjeta space-y-3 p-5">
      <h2 className="font-semibold text-slate-900">Importar desde Excel</h2>
      <p className="-mt-2 text-xs text-slate-500">
        Se puede repetir para actualizar: busca a cada persona por su documento. Los archivos se procesan y no se guardan. Importe primero la base de
        personal y después el libro de vacaciones.
      </p>
      <div className="grid gap-3 lg:grid-cols-2">
        {fila("base", "1. Base de personal", "Hojas OPERATIVOS, ADMINISTRATIVOS, RETIROS OP y RETIROS ADMIN. Si alguien está en operativos y administrativos, manda administrativos.")}
        {fila("vacaciones", "2. Libro de vacaciones", "Hojas PERSONAL (saldo a la fecha de corte) y FECHAS VACACIONES (historial; las posteriores al corte quedan programadas).")}
      </div>
      {error && <Alerta>{error}</Alerta>}
      {resultado && (
        <div className="space-y-3 rounded-lg border border-green-200 bg-green-50/60 p-3">
          <div className="flex items-center">
            <p className="text-sm font-semibold text-green-900">{resultado.tipo === "base" ? "Base de personal importada" : "Libro de vacaciones importado"}</p>
            <button className="ml-auto rounded-md p-1 text-slate-500 hover:bg-white" onClick={() => setResultado(null)} aria-label="Cerrar"><X className="h-4 w-4" /></button>
          </div>
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
            {RESUMEN[resultado.tipo].map(([k, t]) => (
              <span key={k}>{t}: <b className="tabular-nums">{String(resultado.datos[k] ?? 0)}</b></span>
            ))}
            {resultado.tipo === "vacaciones" && resultado.datos.corte ? <span>Corte: <b>{String(resultado.datos.corte).split("-").reverse().join("/")}</b></span> : null}
          </div>
          {resultado.datos.hallazgos.length > 0 && (
            <div className="overflow-auto rounded-md border border-amber-200 bg-white">
              <p className="border-b border-amber-200 bg-amber-50 px-3 py-2 text-sm font-medium text-amber-900">
                {resultado.datos.hallazgos.length} casos para revisar en el Excel o en la ficha
              </p>
              <table className="tabla text-xs">
                <thead><tr><th>Hoja</th><th className="text-right">Fila</th><th>Documento</th><th>Detalle</th></tr></thead>
                <tbody>
                  {resultado.datos.hallazgos.map((h, i) => (
                    <tr key={i}><td className="whitespace-nowrap">{h.hoja}</td><td className="text-right tabular-nums">{h.fila}</td>
                      <td className="whitespace-nowrap font-mono">{h.documento ?? "—"}</td><td>{h.detalle}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
