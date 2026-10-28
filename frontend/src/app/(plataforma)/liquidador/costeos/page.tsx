"use client";

import { ArrowRight, ChevronDown, ChevronRight, FileDown, Plus, Search } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Paginador, metaDe, usePaginacion, type MetaPagina } from "@/components/paginacion";
import { ParametrosCosteoForm } from "@/components/parametros-costeo";
import { Alerta, Titulo } from "@/components/ui";
import { api, apiEnvelope, mensajeError, subirArchivo } from "@/lib/api";
import { MESES, pesos } from "@/lib/formato";
import { nombrePeriodo, type Costeo, type CosteoResumen, type ParametrosCosteo, type ParametrosDefecto } from "@/lib/liquidador";
import { usePermiso } from "@/lib/sesion";

export default function Costeos() {
  const gestionar = usePermiso("liquidador.costeo.gestionar");
  const router = useRouter();
  const hoy = new Date();
  const [f, setF] = useState({ nombre: "", anio: hoy.getFullYear(), mes: hoy.getMonth() + 1, quincena: hoy.getDate() <= 15 ? 1 : 2,
    umbral_activo: false, umbral_horas: 42, umbral_horas_novedad: 7, auxilio_mensual: "" });
  const [def, setDef] = useState<ParametrosDefecto | null>(null);
  const [par, setPar] = useState<ParametrosCosteo | null>(null);
  const [verPar, setVerPar] = useState(false);
  const [archivo, setArchivo] = useState<File | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [lista, setLista] = useState<CosteoResumen[]>([]);
  const [meta, setMeta] = useState<MetaPagina | null>(null);
  const [q, setQ] = useState("");
  const [error, setError] = useState("");
  const pag = usePaginacion([q]);

  useEffect(() => {
    api<ParametrosDefecto>("/liquidador/costeos/parametros").then((d) => { setDef(d); setPar(d.valores); }).catch((e) => setError(mensajeError(e)));
  }, []);

  const cargar = useCallback(async () => {
    const r = await apiEnvelope<CosteoResumen[]>(`/liquidador/costeos?q=${encodeURIComponent(q)}&${pag.query}`);
    setLista(r.data ?? []);
    setMeta(metaDe(r));
  }, [q, pag.query]);

  useEffect(() => {
    const t = setTimeout(() => cargar().catch((e) => setError(mensajeError(e))), 250);
    return () => clearTimeout(t);
  }, [cargar]);

  async function crear(e: React.FormEvent) {
    e.preventDefault();
    if (!archivo || !par) return;
    setError("");
    setEnviando(true);
    try {
      const c = await subirArchivo<Costeo>("/liquidador/costeos", archivo, {
        nombre: f.nombre, anio: String(f.anio), mes: String(f.mes), quincena: String(f.quincena), umbral_activo: String(f.umbral_activo),
        umbral_horas: String(f.umbral_horas), umbral_horas_novedad: String(f.umbral_horas_novedad), parametros: JSON.stringify(par),
        auxilio_mensual: f.auxilio_mensual.trim() || "0",
      });
      router.push(`/liquidador/costeos/${c.id}`);
    } catch (err) {
      setError(mensajeError(err));
      setEnviando(false);
    }
  }

  return (
    <div className="space-y-5">
      <Titulo>Costeo de nómina</Titulo>
      <p className="-mt-4 text-sm text-slate-500">
        Cuánto le costaría a la empresa un Excel de turnos (mismo formato que una nómina), con aportes del empleador y prestaciones. No queda como
        pagado: no descuenta préstamos, embargos ni cuotas, no gasta vacaciones y no crea empleados (las cédulas nuevas se costean con el salario mínimo).
      </p>
      {error && <Alerta>{error}</Alerta>}

      {gestionar && (
        <form onSubmit={crear} className="tarjeta space-y-4 p-5">
          <h2 className="font-semibold text-slate-900">Nuevo costeo</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="lg:col-span-2">
              <label className="label">Nombre del costeo</label>
              <input className="input" required maxLength={120} placeholder="p. ej. Cliente nuevo · propuesta noviembre" value={f.nombre}
                onChange={(e) => setF({ ...f, nombre: e.target.value })} />
            </div>
            <div>
              <label className="label">Año</label>
              <input className="input" type="number" min={2020} max={2100} value={f.anio} onChange={(e) => setF({ ...f, anio: Number(e.target.value) })} />
            </div>
            <div>
              <label className="label">Mes</label>
              <select className="input" value={f.mes} onChange={(e) => setF({ ...f, mes: Number(e.target.value) })}>
                {MESES.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
              </select>
            </div>
            <div>
              <label className="label">Tipo de periodo</label>
              <select className="input" value={f.quincena} onChange={(e) => setF({ ...f, quincena: Number(e.target.value) })}>
                <option value={1}>Quincena 1 (días 1 al 15)</option>
                <option value={2}>Quincena 2 (16 a fin de mes)</option>
                <option value={0}>Mensual (mes completo)</option>
              </select>
            </div>
            <div className="lg:col-span-2">
              <label className="label">Excel de turnos</label>
              <input className="input" type="file" required accept=".xlsx" onChange={(e) => setArchivo(e.target.files?.[0] ?? null)} />
              <a className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-marca-700 hover:underline"
                href={`/api/liquidador/costeos/plantilla?anio=${f.anio}&mes=${f.mes}&quincena=${f.quincena}`}>
                <FileDown className="h-3.5 w-3.5" /> Descargar plantilla (con la columna «arl»: clase de riesgo 1 a 5 de cada persona)
              </a>
            </div>
            <div>
              <label className="label">Auxilio no prestacional mensual</label>
              <input className="input" type="number" min={0} placeholder="Solo si aplica" value={f.auxilio_mensual}
                onChange={(e) => setF({ ...f, auxilio_mensual: e.target.value })} />
              <p className="mt-1 text-xs text-slate-500">Por persona; se descuenta por ausencias, incapacidades y demás tiempo no laborado.</p>
            </div>
          </div>
          <label className="flex flex-wrap items-center gap-2 text-sm text-slate-700">
            <input type="checkbox" className="h-4 w-4" checked={f.umbral_activo} onChange={(e) => setF({ ...f, umbral_activo: e.target.checked })} />
            Aplicar umbral semanal de
            <input className="input w-20" type="number" min={1} max={168} step="0.5" disabled={!f.umbral_activo} value={f.umbral_horas}
              onChange={(e) => setF({ ...f, umbral_horas: Number(e.target.value) })} /> h
          </label>
          <div>
            <button type="button" className="inline-flex items-center gap-1 text-sm font-medium text-marca-700" onClick={() => setVerPar(!verPar)}>
              {verPar ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />} Porcentajes de aportes y prestaciones
            </button>
            {verPar && def && par && <div className="mt-3"><ParametrosCosteoForm valores={par} def={def} onCambio={setPar} /></div>}
          </div>
          <button className="btn-primario inline-flex items-center gap-1.5" disabled={enviando || !archivo || !par}>
            <Plus className="h-4 w-4" /> {enviando ? "Costeando…" : "Costear"}
          </button>
          <p className="text-xs text-slate-500">El Excel se procesa y se descarta; solo se guarda el resultado del costeo para consultarlo después.</p>
        </form>
      )}

      <div className="tarjeta overflow-hidden">
        <div className="px-4 py-3">
          <div className="relative w-72">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input className="input pl-8" placeholder="Buscar por nombre…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
        </div>
        <div className="overflow-auto">
          <table className="tabla">
            <thead>
              <tr><th>Costeo</th><th>Periodo</th><th className="text-right">Personas</th><th className="text-right">Devengado</th>
                <th className="text-right">Costo total empresa</th><th>Creado</th><th /></tr>
            </thead>
            <tbody>
              {lista.map((c) => (
                <tr key={c.id}>
                  <td className="font-medium">{c.nombre}</td>
                  <td className="whitespace-nowrap">{MESES[c.mes - 1]} {c.anio} · {nombrePeriodo(c)}</td>
                  <td className="text-right tabular-nums">
                    {c.personas}{c.no_registradas > 0 && <span className="block text-xs text-slate-500">{c.no_registradas} sin registrar</span>}
                  </td>
                  <td className="text-right tabular-nums">{pesos(c.devengado)}</td>
                  <td className="text-right font-semibold tabular-nums">{pesos(c.costo_total)}</td>
                  <td className="text-sm text-slate-500">{c.creado_en ? new Date(c.creado_en).toLocaleDateString("es-CO") : "—"}</td>
                  <td className="text-right">
                    <Link href={`/liquidador/costeos/${c.id}`} className="inline-flex items-center gap-1 text-sm font-medium text-marca-600 hover:underline">
                      Abrir <ArrowRight className="h-4 w-4" />
                    </Link>
                  </td>
                </tr>
              ))}
              {lista.length === 0 && <tr><td colSpan={7} className="py-6 text-center text-sm text-slate-500">Aún no hay costeos.</td></tr>}
            </tbody>
          </table>
        </div>
        <Paginador meta={meta} onPagina={pag.setPagina} onTamano={pag.setTamano} />
      </div>
    </div>
  );
}
