"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Alerta, Insignia, SubirArchivo, Titulo } from "@/components/ui";
import { api, mensajeError, subirArchivo, type Carga } from "@/lib/api";
import { nombreMes } from "@/lib/formato";
import { usePermiso } from "@/lib/sesion";

const CLASES: [string, string, string][] = [
  ["trabajo", "Turnos", "bg-marca-100 text-marca-900"],
  ["descanso", "Descansos", "bg-slate-100 text-slate-700"],
  ["novedad", "Novedades", "bg-amber-100 text-amber-800"],
  ["desconocido", "Sin interpretar", "bg-red-100 text-red-700"],
];

export default function ProgramacionPage() {
  const puedeCargar = usePermiso("programacion.cargar");
  const [cargas, setCargas] = useState<Carga[]>([]);
  const [actual, setActual] = useState<Carga | null>(null);
  const [error, setError] = useState("");

  const cargar = useCallback(async () => {
    const lista = await api<Carga[]>("/programacion/cargas");
    setCargas(lista);
    setActual((a) => a ?? lista[0] ?? null);
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  return (
    <div className="max-w-6xl space-y-6">
      <Titulo
        accion={
          puedeCargar && (
            <SubirArchivo
              texto="Subir Excel de SIESA"
              onArchivo={async (f) => {
                setError("");
                try {
                  const c = await subirArchivo<Carga>("/programacion/cargas", f);
                  setActual(c);
                  cargar();
                } catch (e) {
                  setError(mensajeError(e));
                }
              }}
            />
          )
        }
      >
        Programación SIESA
      </Titulo>
      <Alerta tipo="info">
        Suba el reporte <b>ReporteAsignacionResumido</b> exportado de SIESA. Cada carga es una foto completa: la más reciente de cada mes es la que se analiza.
      </Alerta>
      {error && <Alerta>{error}</Alerta>}

      {actual && <DetalleCarga carga={actual} />}

      <section className="tarjeta overflow-x-auto">
        <h2 className="border-b border-slate-200 px-4 py-3 font-semibold">Historial de cargas</h2>
        <table className="tabla">
          <thead><tr><th>#</th><th>Periodo</th><th>Rango</th><th>Archivo</th><th>Filas</th><th>Cargado</th></tr></thead>
          <tbody>
            {cargas.length === 0 && <tr><td colSpan={6} className="text-center text-slate-500">Aún no hay cargas</td></tr>}
            {cargas.map((c) => (
              <tr key={c.id} onClick={() => setActual(c)} className={`cursor-pointer hover:bg-slate-50 ${actual?.id === c.id ? "bg-marca-50" : ""}`}>
                <td>{c.id}</td>
                <td>{nombreMes(c.anio, c.mes)}</td>
                <td>{c.desde} → {c.hasta}</td>
                <td className="max-w-xs truncate">{c.archivo}</td>
                <td>{c.resumen.filas}</td>
                <td>{new Date(c.cargado_en).toLocaleString("es-CO")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function DetalleCarga({ carga }: { carga: Carga }) {
  const r = carga.resumen;
  return (
    <section className="tarjeta space-y-4 p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-semibold">Carga #{carga.id} · {nombreMes(carga.anio, carga.mes)} ({carga.desde} → {carga.hasta})</h2>
        <span className="text-sm text-slate-500">{carga.compania}</span>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
        <Dato titulo="Filas" valor={r.filas} />
        <Dato titulo="Empleados" valor={r.empleados} />
        <Dato titulo="Puestos" valor={r.puestos} />
      </div>
      <div className="flex flex-wrap gap-2">
        {CLASES.map(([k, t, c]) => (r.dias_por_clase[k] ? <Insignia key={k} color={c}>{t}: {r.dias_por_clase[k].toLocaleString("es-CO")}</Insignia> : null))}
      </div>
      {r.codigos_desconocidos.length > 0 && (
        <Alerta>
          Códigos sin interpretar (no están en el catálogo de horarios ni de novedades):{" "}
          {r.codigos_desconocidos.map((c) => `${c.codigo} (${c.veces})`).join(", ")}. Actualice el catálogo en Maestros.
        </Alerta>
      )}
      {r.puestos_sin_equivalencia.length > 0 ? (
        <Alerta>
          {r.puestos_sin_equivalencia.length} puestos de SIESA no se encontraron en la matriz.{" "}
          <Link href="/maestros" className="font-semibold underline">Aclararlos en Maestros</Link>
        </Alerta>
      ) : (
        <Alerta tipo="ok">Todos los puestos se cruzaron con la matriz.</Alerta>
      )}
    </section>
  );
}

function Dato({ titulo, valor }: { titulo: string; valor: number }) {
  return (
    <div className="rounded-md border border-slate-200 p-3">
      <p className="text-xs uppercase text-slate-500">{titulo}</p>
      <p className="text-2xl font-bold text-marca-900">{valor.toLocaleString("es-CO")}</p>
    </div>
  );
}
