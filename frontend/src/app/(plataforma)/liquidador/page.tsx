"use client";

import { ArrowRight, Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Paginador, metaDe, usePaginacion, type MetaPagina } from "@/components/paginacion";
import { Alerta, Insignia, Titulo } from "@/components/ui";
import { api, apiEnvelope, mensajeError } from "@/lib/api";
import { MESES } from "@/lib/formato";
import { ESTADO_PERIODO, type Periodo } from "@/lib/liquidador";
import { usePermiso } from "@/lib/sesion";

function fecha(iso: string | null) {
  return iso ? new Date(iso).toLocaleDateString("es-CO", { day: "2-digit", month: "2-digit", year: "numeric" }) : "—";
}

export default function Quincenas() {
  const gestionar = usePermiso("liquidador.periodos.gestionar");
  const router = useRouter();
  const hoy = new Date();
  const [nueva, setNueva] = useState({ anio: hoy.getFullYear(), mes: hoy.getMonth() + 1, quincena: hoy.getDate() <= 15 ? 1 : 2 });
  const [lista, setLista] = useState<Periodo[] | null>(null);
  const [meta, setMeta] = useState<MetaPagina | null>(null);
  const [error, setError] = useState("");
  const pag = usePaginacion();

  const cargar = useCallback(async () => {
    const r = await apiEnvelope<Periodo[]>(`/liquidador/periodos?${pag.query}`);
    setLista(r.data ?? []);
    setMeta(metaDe(r));
  }, [pag.query]);

  useEffect(() => {
    cargar().catch((e) => setError(mensajeError(e)));
  }, [cargar]);

  async function crear(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const p = await api<Periodo>("/liquidador/periodos", { method: "POST", json: nueva });
      router.push(`/liquidador/quincenas/${p.id}`);
    } catch (err) {
      setError(mensajeError(err));
    }
  }

  return (
    <div className="space-y-5">
      <Titulo>Quincenas</Titulo>
      <p className="-mt-4 text-sm text-slate-500">Quincena 1: días 1 al 15 · Quincena 2: del 16 al fin de mes. Cada quincena cuenta las horas del Excel de turnos cargado.</p>

      {gestionar && (
        <form onSubmit={crear} className="tarjeta flex flex-wrap items-end gap-3 p-4">
          <div>
            <label className="label">Año</label>
            <input className="input w-24" type="number" min={2020} max={2100} value={nueva.anio} onChange={(e) => setNueva({ ...nueva, anio: Number(e.target.value) })} />
          </div>
          <div>
            <label className="label">Mes</label>
            <select className="input w-40" value={nueva.mes} onChange={(e) => setNueva({ ...nueva, mes: Number(e.target.value) })}>
              {MESES.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Quincena</label>
            <select className="input w-44" value={nueva.quincena} onChange={(e) => setNueva({ ...nueva, quincena: Number(e.target.value) })}>
              <option value={1}>1 (días 1 al 15)</option>
              <option value={2}>2 (16 a fin de mes)</option>
            </select>
          </div>
          <button className="btn-primario inline-flex items-center gap-1.5"><Plus className="h-4 w-4" /> Nueva quincena</button>
        </form>
      )}
      {error && <Alerta>{error}</Alerta>}

      <div className="tarjeta overflow-auto">
        <table className="tabla">
          <thead>
            <tr><th>Quincena</th><th>Rango</th><th>Estado</th><th>Archivo cargado</th><th className="text-right">Personas</th><th>Creada</th><th /></tr>
          </thead>
          <tbody>
            {lista?.map((p) => {
              const [texto, color] = ESTADO_PERIODO[p.estado] ?? [p.estado, ""];
              return (
                <tr key={p.id}>
                  <td className="font-semibold">{MESES[p.mes - 1]} {p.anio} · Q{p.quincena}</td>
                  <td className="whitespace-nowrap text-sm text-slate-600">{fecha(p.desde + "T12:00:00")} → {fecha(p.hasta + "T12:00:00")}</td>
                  <td><Insignia color={color}>{texto}</Insignia></td>
                  <td className="max-w-xs truncate text-sm text-slate-600" title={p.archivo ?? ""}>{p.archivo ?? "—"}</td>
                  <td className="text-right tabular-nums">{p.empleados.toLocaleString("es-CO")}</td>
                  <td className="text-sm text-slate-500">{fecha(p.creado_en)}</td>
                  <td className="text-right">
                    <Link href={`/liquidador/quincenas/${p.id}`} className="inline-flex items-center gap-1 text-sm font-medium text-marca-600 hover:underline">
                      Abrir <ArrowRight className="h-4 w-4" />
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {lista?.length === 0 && <p className="p-6 text-center text-sm text-slate-500">Aún no hay quincenas. Cree la primera arriba.</p>}
        <Paginador meta={meta} onPagina={pag.setPagina} onTamano={pag.setTamano} />
      </div>
    </div>
  );
}
