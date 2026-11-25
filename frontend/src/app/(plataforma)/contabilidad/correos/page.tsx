"use client";

import { useEffect, useState } from "react";
import { Paginador, metaDe, usePaginacion, type MetaPagina } from "@/components/paginacion";
import { Alerta, Titulo } from "@/components/ui";
import { apiEnvelope, mensajeError } from "@/lib/api";
import { TAMANOS, fechaHora } from "@/lib/contabilidad";

type Correo = { id: number; de: string; asunto: string; fecha: string | null; resultado: string; facturas: number; leido_en: string | null };

export default function CorreosLeidos() {
  const [lista, setLista] = useState<Correo[] | null>(null);
  const [error, setError] = useState("");
  const [meta, setMeta] = useState<MetaPagina | null>(null);
  const pag = usePaginacion([], TAMANOS);
  useEffect(() => {
    apiEnvelope<Correo[]>(`/contabilidad/correos?${pag.query}`).then((r) => { setLista(r.data ?? []); setMeta(metaDe(r)); })
      .catch((e) => setError(mensajeError(e)));
  }, [pag.query]);
  return (
    <div className="space-y-4">
      <Titulo>Correos leídos</Titulo>
      <p className="-mt-4 text-sm text-slate-500">Qué pasó con cada correo del buzón. No se guardan los correos ni sus adjuntos: solo el remitente, el asunto y el resultado.</p>
      {error && <Alerta>{error}</Alerta>}
      <div className="tarjeta overflow-x-auto">
        <table className="tabla text-sm">
          <thead><tr><th>Leído</th><th>De</th><th>Asunto</th><th className="text-right">Facturas</th><th>Resultado</th></tr></thead>
          <tbody>
            {lista?.length === 0 && <tr><td colSpan={5} className="py-6 text-center text-slate-400">Aún no se ha leído ningún correo.</td></tr>}
            {lista?.map((c) => (
              <tr key={c.id}>
                <td className="whitespace-nowrap">{fechaHora(c.leido_en)}</td><td className="max-w-[14rem] truncate">{c.de}</td>
                <td className="max-w-xs truncate" title={c.asunto}>{c.asunto}</td><td className="text-right">{c.facturas}</td>
                <td className={`text-xs ${c.facturas ? "text-green-700" : "text-slate-500"}`}>{c.resultado}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <Paginador meta={meta} onPagina={pag.setPagina} onTamano={pag.setTamano} tamanos={TAMANOS} />
      </div>
    </div>
  );
}
