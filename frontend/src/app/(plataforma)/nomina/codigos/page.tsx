"use client";

import { Search } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Paginador, metaDe, usePaginacion, type MetaPagina } from "@/components/paginacion";
import { Alerta, Insignia, Titulo } from "@/components/ui";
import { api, apiEnvelope, mensajeError } from "@/lib/api";
import { usePermiso } from "@/lib/sesion";

type Codigo = { codigo: string; descripcion: string; descuenta: boolean; vacaciones: boolean; revisado: boolean };

export default function CodigosNomina() {
  const configurar = usePermiso("nomina.configurar");
  const [lista, setLista] = useState<Codigo[]>([]);
  const [meta, setMeta] = useState<MetaPagina | null>(null);
  const [porRevisar, setPorRevisar] = useState(0);
  const [f, setF] = useState({ q: "", por_revisar: false });
  const [error, setError] = useState("");
  const pag = usePaginacion([f]);

  const leer = useCallback(async () => {
    const r = await apiEnvelope<Codigo[]>(`/nomina/codigos?q=${encodeURIComponent(f.q)}&por_revisar=${f.por_revisar}&${pag.query}`);
    setLista(r.data ?? []);
    setMeta(metaDe(r));
    setPorRevisar(Number(r.meta.extra?.por_revisar ?? 0));
  }, [f, pag.query]);

  useEffect(() => {
    const t = setTimeout(() => leer().catch((e) => setError(mensajeError(e))), 250);
    return () => clearTimeout(t);
  }, [leer]);

  async function guardar(c: Codigo, cambios: Partial<Codigo>) {
    setError("");
    try {
      const nuevo = await api<Codigo>(`/nomina/codigos/${encodeURIComponent(c.codigo)}`, { method: "PUT", json: { ...c, ...cambios } });
      setLista((l) => l.map((x) => (x.codigo === c.codigo ? nuevo : x)));
      if (!c.revisado) setPorRevisar((n) => Math.max(0, n - 1));
    } catch (e) {
      setError(mensajeError(e));
    }
  }

  return (
    <div className="space-y-5">
      <Titulo>Códigos que descuentan</Titulo>
      <p className="-mt-4 text-sm text-slate-500">
        Códigos de la programación de SIESA. Con <b>Descuenta</b> marcado, ese día no se paga la modalidad ni lleva auxilio de transporte
        (vacaciones, licencias, incapacidades…). Sin marcar, el día cuenta como pagable (turnos, Z, L, IND). Los códigos nuevos aparecen solos al
        cargar la programación y quedan por revisar. Después de un cambio, recalcule la revisión.
      </p>
      {porRevisar > 0 && <Alerta tipo="info">{porRevisar} códigos nuevos por revisar: confirme si descuentan o no.</Alerta>}
      {error && <Alerta>{error}</Alerta>}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input className="input w-64 pl-8" placeholder="Buscar código…" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} />
        </div>
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input type="checkbox" className="h-4 w-4" checked={f.por_revisar} onChange={(e) => setF({ ...f, por_revisar: e.target.checked })} /> Solo por revisar
        </label>
      </div>
      <div className="tarjeta overflow-auto">
        <table className="tabla text-sm">
          <thead><tr><th>Código</th><th>Descripción</th><th className="text-center">Descuenta</th><th className="text-center">Es vacaciones</th><th>Estado</th></tr></thead>
          <tbody>
            {lista.map((c) => (
              <tr key={c.codigo}>
                <td className="font-mono font-semibold">{c.codigo}</td>
                <td>
                  <input className="input h-8 w-72" disabled={!configurar} defaultValue={c.descripcion}
                    onBlur={(e) => e.target.value !== c.descripcion && guardar(c, { descripcion: e.target.value })} />
                </td>
                <td className="text-center"><input type="checkbox" className="h-4 w-4" disabled={!configurar} checked={c.descuenta} onChange={(e) => guardar(c, { descuenta: e.target.checked })} /></td>
                <td className="text-center"><input type="checkbox" className="h-4 w-4" disabled={!configurar || !c.descuenta} checked={c.vacaciones} onChange={(e) => guardar(c, { vacaciones: e.target.checked })} /></td>
                <td>{c.revisado ? <Insignia color="bg-green-100 text-green-800">Confirmado</Insignia> : (
                  <button className="text-left" disabled={!configurar} onClick={() => guardar(c, {})}><Insignia color="bg-amber-100 text-amber-800">Nuevo · confirmar</Insignia></button>
                )}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <Paginador meta={meta} onPagina={pag.setPagina} onTamano={pag.setTamano} />
      </div>
    </div>
  );
}
