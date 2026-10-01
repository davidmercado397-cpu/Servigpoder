"use client";

import { ArrowRight, Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Paginador, metaDe, usePaginacion, type MetaPagina } from "@/components/paginacion";
import { Alerta, Insignia, Titulo } from "@/components/ui";
import { api, apiEnvelope, mensajeError } from "@/lib/api";
import { MESES } from "@/lib/formato";
import type { Periodo } from "@/lib/nomina";
import { usePermiso } from "@/lib/sesion";

export default function PeriodosNomina() {
  const cargar = usePermiso("nomina.cargar");
  const router = useRouter();
  const hoy = new Date();
  const [nuevo, setNuevo] = useState({ anio: hoy.getFullYear(), mes: hoy.getMonth() + 1, nomina: "quincenal" });
  const [lista, setLista] = useState<Periodo[] | null>(null);
  const [meta, setMeta] = useState<MetaPagina | null>(null);
  const [error, setError] = useState("");
  const pag = usePaginacion();

  const leer = useCallback(async () => {
    const r = await apiEnvelope<Periodo[]>(`/nomina/periodos?${pag.query}`);
    setLista(r.data ?? []);
    setMeta(metaDe(r));
  }, [pag.query]);

  useEffect(() => {
    leer().catch((e) => setError(mensajeError(e)));
  }, [leer]);

  async function crear(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const p = await api<Periodo>("/nomina/periodos", { method: "POST", json: nuevo });
      router.push(`/nomina/periodos/${p.id}`);
    } catch (err) {
      setError(mensajeError(err));
    }
  }

  return (
    <div className="space-y-5">
      <Titulo>Validación de nómina</Titulo>
      <p className="-mt-4 text-sm text-slate-500">
        Cada revisión es de una nómina: quincenal (2.ª quincena, del 16 al 30) o mensual (del 1 al 30). Se exigen todos los archivos del día;
        después puede recargar solo la nómina, las veces que necesite, para ver qué se corrigió. Los grupos de &quot;los 7&quot; quedan por fuera.
      </p>
      {cargar && (
        <form onSubmit={crear} className="tarjeta flex flex-wrap items-end gap-3 p-4">
          <div><label className="label">Año</label><input className="input w-24" type="number" min={2020} max={2100} value={nuevo.anio} onChange={(e) => setNuevo({ ...nuevo, anio: Number(e.target.value) })} /></div>
          <div>
            <label className="label">Mes</label>
            <select className="input w-40" value={nuevo.mes} onChange={(e) => setNuevo({ ...nuevo, mes: Number(e.target.value) })}>
              {MESES.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Nómina</label>
            <select className="input w-56" value={nuevo.nomina} onChange={(e) => setNuevo({ ...nuevo, nomina: e.target.value })}>
              <option value="quincenal">Quincenal (2.ª quincena)</option>
              <option value="mensual">Mensual (mes completo)</option>
            </select>
          </div>
          <button className="btn-primario inline-flex items-center gap-1.5"><Plus className="h-4 w-4" /> Nueva revisión</button>
        </form>
      )}
      {error && <Alerta>{error}</Alerta>}
      <div className="tarjeta overflow-auto">
        <table className="tabla">
          <thead><tr><th>Revisión</th><th>Archivos</th><th className="text-right">Cargas de nómina</th><th className="text-right">Personas</th><th className="text-right">Alertas</th><th className="text-right">Pendientes</th><th>Calculado</th><th /></tr></thead>
          <tbody>
            {lista?.map((p) => {
              const cargados = p.requeridos.filter((t) => p.archivos[t]).length;
              const personas = Object.values(p.personas ?? {}).reduce((s, n) => s + n, 0);
              return (
                <tr key={p.id}>
                  <td className="font-semibold">{p.nombre}</td>
                  <td><Insignia color={cargados === p.requeridos.length ? "bg-green-100 text-green-800" : "bg-amber-100 text-amber-800"}>{cargados} de {p.requeridos.length}</Insignia></td>
                  <td className="text-right tabular-nums">{p.revisiones}</td>
                  <td className="text-right tabular-nums">{personas.toLocaleString("es-CO")}</td>
                  <td className="text-right tabular-nums">{p.alertas.toLocaleString("es-CO")}</td>
                  <td className="text-right tabular-nums">{p.pendientes ? <b className="text-amber-700">{p.pendientes.toLocaleString("es-CO")}</b> : "0"}</td>
                  <td className="text-sm text-slate-500">{p.calculado_en ? new Date(p.calculado_en).toLocaleString("es-CO") : "—"}</td>
                  <td className="text-right">
                    <Link href={`/nomina/periodos/${p.id}`} className="inline-flex items-center gap-1 text-sm font-medium text-marca-600 hover:underline">Abrir <ArrowRight className="h-4 w-4" /></Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {lista?.length === 0 && <p className="p-6 text-center text-sm text-slate-500">Aún no hay revisiones. Cree la primera arriba.</p>}
        <Paginador meta={meta} onPagina={pag.setPagina} onTamano={pag.setTamano} />
      </div>
    </div>
  );
}
