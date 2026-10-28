"use client";

import { ArrowRight, Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Paginador, metaDe, usePaginacion, type MetaPagina } from "@/components/paginacion";
import { Alerta, Insignia, Titulo } from "@/components/ui";
import { api, apiEnvelope, mensajeError } from "@/lib/api";
import { MESES } from "@/lib/formato";
import { ESTADO_PERIODO, nombrePeriodo, type Periodo } from "@/lib/liquidador";
import { usePermiso } from "@/lib/sesion";

function fecha(iso: string | null) {
  return iso ? new Date(iso).toLocaleDateString("es-CO", { day: "2-digit", month: "2-digit", year: "numeric" }) : "—";
}

type Grupo = { clave: string; anio: number; mes: number; quincena: number; desde: string; hasta: string; nominas: Periodo[] };

/** Las nóminas llegan ordenadas por periodo: se agrupan por año, mes y quincena. */
function agrupar(lista: Periodo[]): Grupo[] {
  const grupos: Grupo[] = [];
  for (const p of lista) {
    const clave = `${p.anio}-${p.mes}-${p.quincena}`;
    const g = grupos.find((x) => x.clave === clave);
    if (g) g.nominas.push(p);
    else grupos.push({ clave, anio: p.anio, mes: p.mes, quincena: p.quincena, desde: p.desde, hasta: p.hasta, nominas: [p] });
  }
  return grupos;
}

export default function Quincenas() {
  const gestionar = usePermiso("liquidador.periodos.gestionar");
  const router = useRouter();
  const hoy = new Date();
  const [nueva, setNueva] = useState({ anio: hoy.getFullYear(), mes: hoy.getMonth() + 1, quincena: hoy.getDate() <= 15 ? 1 : 2, nombre: "General" });
  const [lista, setLista] = useState<Periodo[] | null>(null);
  const [meta, setMeta] = useState<MetaPagina | null>(null);
  const [error, setError] = useState("");
  const pag = usePaginacion();
  const campoNombre = useRef<HTMLInputElement>(null);

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

  function agregarA(g: Grupo) {
    setNueva({ anio: g.anio, mes: g.mes, quincena: g.quincena, nombre: "" });
    window.scrollTo({ top: 0, behavior: "smooth" });
    setTimeout(() => campoNombre.current?.focus(), 300);
  }

  return (
    <div className="space-y-5">
      <Titulo>Periodos</Titulo>
      <p className="-mt-4 text-sm text-slate-500">
        Quincena 1: días 1 al 15 · Quincena 2: del 16 al fin de mes · Mensual: el mes completo. Cada periodo agrupa sus nóminas (por cliente,
        administrativa…), cada una con su Excel de turnos, su cálculo y su cierre.
      </p>

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
            <label className="label">Tipo de periodo</label>
            <select className="input w-56" value={nueva.quincena} onChange={(e) => setNueva({ ...nueva, quincena: Number(e.target.value) })}>
              <option value={1}>Quincena 1 (días 1 al 15)</option>
              <option value={2}>Quincena 2 (16 a fin de mes)</option>
              <option value={0}>Mensual (mes completo)</option>
            </select>
          </div>
          <div>
            <label className="label">Nombre de la nómina</label>
            <input ref={campoNombre} className="input w-56" required maxLength={80} placeholder="Cliente 1, Administrativa…" value={nueva.nombre}
              onChange={(e) => setNueva({ ...nueva, nombre: e.target.value })} />
          </div>
          <button className="btn-primario inline-flex items-center gap-1.5"><Plus className="h-4 w-4" /> Crear nómina</button>
        </form>
      )}
      {error && <Alerta>{error}</Alerta>}

      <div className="tarjeta overflow-auto">
        <table className="tabla">
          <thead>
            <tr><th>Nómina</th><th>Estado</th><th>Archivo cargado</th><th className="text-right">Personas</th><th>Creada</th><th /></tr>
          </thead>
          <tbody>
            {lista && agrupar(lista).map((g) => (
              <PeriodoFilas key={g.clave} g={g} gestionar={gestionar} onAgregar={() => agregarA(g)} />
            ))}
          </tbody>
        </table>
        {lista?.length === 0 && <p className="p-6 text-center text-sm text-slate-500">Aún no hay periodos. Cree la primera nómina arriba.</p>}
        <Paginador meta={meta} onPagina={pag.setPagina} onTamano={pag.setTamano} />
      </div>
    </div>
  );
}

function PeriodoFilas({ g, gestionar, onAgregar }: { g: Grupo; gestionar: boolean; onAgregar: () => void }) {
  const personas = g.nominas.reduce((s, p) => s + p.empleados, 0);
  return (
    <>
      <tr className="bg-slate-50">
        <td colSpan={3} className="font-semibold text-slate-900">
          {MESES[g.mes - 1]} {g.anio} · {nombrePeriodo(g)}
          {g.quincena === 0 && <Insignia color="ml-2 bg-indigo-100 text-indigo-800">Mes completo</Insignia>}
          <span className="ml-2 text-sm font-normal text-slate-500">{fecha(g.desde + "T12:00:00")} → {fecha(g.hasta + "T12:00:00")}</span>
        </td>
        <td className="text-right text-sm tabular-nums text-slate-600">{personas.toLocaleString("es-CO")}</td>
        <td className="text-sm text-slate-500">{g.nominas.length} {g.nominas.length === 1 ? "nómina" : "nóminas"}</td>
        <td className="text-right">
          {gestionar && (
            <button onClick={onAgregar} className="inline-flex items-center gap-1 text-sm font-medium text-marca-600 hover:underline">
              <Plus className="h-4 w-4" /> Agregar nómina
            </button>
          )}
        </td>
      </tr>
      {g.nominas.map((p) => {
        const [texto, color] = ESTADO_PERIODO[p.estado] ?? [p.estado, ""];
        return (
          <tr key={p.id}>
            <td className="pl-8 font-medium">{p.nombre}</td>
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
    </>
  );
}
