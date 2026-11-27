"use client";

import { AlertTriangle, FileUp, Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Paginador, metaDe, usePaginacion, type MetaPagina } from "@/components/paginacion";
import { Alerta, Titulo } from "@/components/ui";
import { api, apiEnvelope, mensajeError } from "@/lib/api";
import { ESTADOS_LEG, TAMANOS, fecha, plata, type EstadoLeg, type Legalizacion, type LegalizacionCompleta, type Persona } from "@/lib/contabilidad";
import { usePermiso } from "@/lib/sesion";

export default function Legalizaciones() {
  const revisar = usePermiso("contabilidad.revisar");
  const router = useRouter();
  const [estado, setEstado] = useState<EstadoLeg>("pendiente");
  const [lista, setLista] = useState<Legalizacion[] | null>(null);
  const [meta, setMeta] = useState<MetaPagina | null>(null);
  const [conteos, setConteos] = useState<Record<string, number>>({});
  const pag = usePaginacion([estado], TAMANOS);
  const [formato, setFormato] = useState<File | null>(null);
  const [soportes, setSoportes] = useState<File | null>(null);
  const [elabora, setElabora] = useState("");
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [leyendo, setLeyendo] = useState(false);
  const [error, setError] = useState("");

  const cargar = useCallback(() => {
    setLista(null);
    apiEnvelope<Legalizacion[]>(`/contabilidad/legalizaciones?estado=${estado}&${pag.query}`).then((r) => {
      setLista(r.data ?? []);
      setMeta(metaDe(r));
      setConteos(((r.meta.extra ?? {}) as { conteos?: Record<string, number> }).conteos ?? {});
    }).catch((e) => setError(mensajeError(e)));
  }, [estado, pag.query]);
  useEffect(() => { cargar(); }, [cargar]);
  useEffect(() => {
    api<Persona[]>("/contabilidad/legalizaciones/personas/lista?tipo=elabora").then((p) => setPersonas(p.filter((x) => x.activo))).catch(() => {});
  }, []);

  async function leer() {
    if (!formato) return;
    setError("");
    setLeyendo(true);
    try {
      const form = new FormData();
      form.append("formato", formato);
      if (soportes) form.append("soportes", soportes);
      form.append("elabora_documento", elabora);
      const r = await api<LegalizacionCompleta>("/contabilidad/legalizaciones", { method: "POST", body: form });
      router.push(`/contabilidad/legalizaciones/${r.id}`);
    } catch (e) { setError(mensajeError(e)); } finally { setLeyendo(false); }
  }

  return (
    <div className="space-y-4">
      <Titulo>Legalizaciones</Titulo>
      <p className="-mt-4 text-sm text-slate-500">Legalización de anticipos y reembolsos de los colaboradores: el formato y sus soportes se leen con IA y se arma la nota
        contable para World Office. Los archivos no se guardan.</p>

      {revisar && (
        <section className="tarjeta space-y-3 p-4">
          <h2 className="font-semibold text-slate-800">Cargar una legalización</h2>
          <div className="grid gap-3 md:grid-cols-3">
            <div><label className="label">Formato de legalización (Excel o PDF)</label>
              <input type="file" accept=".xlsx,.xlsm,.pdf" className="input" onChange={(e) => setFormato(e.target.files?.[0] ?? null)} /></div>
            <div><label className="label">Soportes (PDF con fotos y transferencias)</label>
              <input type="file" accept=".pdf" className="input" onChange={(e) => setSoportes(e.target.files?.[0] ?? null)} />
              <p className="mt-1 text-xs text-slate-500">Opcional: la IA revisa que cada gasto tenga su soporte.</p></div>
            <div><label className="label">Elabora el documento (tercero interno)</label>
              <select className="input" value={elabora} onChange={(e) => setElabora(e.target.value)}>
                <option value="">— Elegir después —</option>{personas.map((p) => <option key={p.id} value={p.documento}>{p.nombre} · {p.documento}</option>)}
              </select>
              {!personas.length && <p className="mt-1 text-xs text-slate-500">Cargue el listado en <Link className="text-marca-700 underline" href="/contabilidad/legalizaciones/configuracion">Cuentas y personas</Link>.</p>}</div>
          </div>
          <button className="btn-primario" disabled={!formato || leyendo} onClick={leer}>
            {leyendo ? <><Loader2 className="h-4 w-4 animate-spin" /> Leyendo el formato y los soportes…</> : <><FileUp className="h-4 w-4" /> Leer legalización</>}
          </button>
          {leyendo && <p className="text-xs text-slate-500">Puede tardar uno o dos minutos.</p>}
        </section>
      )}
      {error && <Alerta>{error}</Alerta>}

      <div className="flex flex-wrap gap-1 border-b border-slate-200">
        {ESTADOS_LEG.map(([k, t]) => (
          <button key={k} onClick={() => setEstado(k)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${estado === k ? "border-marca-600 font-semibold text-marca-700" : "border-transparent text-slate-500 hover:text-slate-700"}`}>
            {t} <span className="ml-1 rounded-full bg-slate-100 px-1.5 text-xs text-slate-600">{conteos[k] ?? 0}</span>
          </button>
        ))}
      </div>
      <div className="tarjeta overflow-x-auto">
        <table className="tabla text-sm">
          <thead><tr><th>Formato</th><th>Colaborador</th><th>Legalización</th><th>Tipo</th><th className="text-right">Gastos</th><th className="text-right">Total</th><th>Revisión</th></tr></thead>
          <tbody>
            {lista === null && <tr><td colSpan={7} className="py-6 text-center text-slate-400">Cargando…</td></tr>}
            {lista?.length === 0 && <tr><td colSpan={7} className="py-6 text-center text-slate-400">No hay legalizaciones en esta bandeja.</td></tr>}
            {lista?.map((x) => (
              <tr key={x.id} className="hover:bg-slate-50">
                <td><Link className="font-medium text-marca-700 hover:underline" href={`/contabilidad/legalizaciones/${x.id}`}>#{x.numero_formato || x.id}</Link></td>
                <td><p>{x.colaborador_nombre}</p><p className="text-xs text-slate-500">{x.colaborador_documento}</p></td>
                <td>{fecha(x.fecha_legalizacion)}</td>
                <td className="text-xs">{x.anticipo_valor ? `Anticipo ${plata(x.anticipo_valor)}` : "Reembolso"}</td>
                <td className="text-right">{x.gastos}</td>
                <td className="text-right tabular-nums">{plata(x.total)}</td>
                <td className="text-xs">
                  {estado === "contabilizada" ? <>LG {x.documento_numero} · {fecha(x.fecha_contable)}</>
                    : x.faltantes.length ? <span className="text-amber-800">{x.faltantes.length} dato(s) por completar</span> : <span className="text-green-700">Completa</span>}
                  {x.sin_soporte > 0 && <span className="ml-1 text-amber-700">· {x.sin_soporte} sin soporte</span>}
                  {x.avisos.length > 0 && estado !== "contabilizada" && <AlertTriangle className="ml-1 inline h-3.5 w-3.5 text-amber-600" />}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <Paginador meta={meta} onPagina={pag.setPagina} onTamano={pag.setTamano} tamanos={TAMANOS} />
      </div>
    </div>
  );
}
