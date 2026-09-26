"use client";

import { Paginador, metaDe, usePaginacion, type MetaPagina } from "@/components/paginacion";
import { useCallback, useEffect, useState } from "react";
import { Titulo } from "@/components/ui";
import { apiEnvelope } from "@/lib/api";

type Registro = { id: number; fecha: string; usuario: string | null; accion: string; detalle: Record<string, unknown>; ip: string; request_id: string };

const COLOR: Record<string, string> = {
  login_fallido: "text-[#a32525]", mfa_fallido: "text-[#a32525]", login_bloqueado: "text-[#a32525] font-semibold",
  login_exitoso: "text-[#086b08]", mfa_restablecida: "text-[#9a3f1a]", password_cambiada: "text-marca-700",
};

export default function AuditoriaPage() {
  const [filtros, setFiltros] = useState({ accion: "", usuario: "", desde: "", hasta: "" });
  const [lista, setLista] = useState<Registro[]>([]);
  const [meta, setMeta] = useState<MetaPagina | null>(null);
  const pag = usePaginacion([filtros]);

  const cargar = useCallback(async () => {
    const p = new URLSearchParams(Object.entries(filtros).filter(([, v]) => v));
    const r = await apiEnvelope<Registro[]>(`/plataforma/auditoria?${p}&${pag.query}`);
    setLista(r.data ?? []);
    setMeta(metaDe(r));
  }, [filtros, pag.query]);

  useEffect(() => {
    const t = setTimeout(cargar, 300);
    return () => clearTimeout(t);
  }, [cargar]);

  return (
    <div className="space-y-4">
      <Titulo>Auditoría</Titulo>
      <div className="flex flex-wrap items-end gap-3">
        <div><label className="label">Acción</label><input className="input w-48" placeholder="login, matriz, usuario…" value={filtros.accion} onChange={(e) => setFiltros({ ...filtros, accion: e.target.value })} /></div>
        <div><label className="label">Usuario</label><input className="input w-40" value={filtros.usuario} onChange={(e) => setFiltros({ ...filtros, usuario: e.target.value })} /></div>
        <div><label className="label">Desde</label><input className="input" type="date" value={filtros.desde} onChange={(e) => setFiltros({ ...filtros, desde: e.target.value })} /></div>
        <div><label className="label">Hasta</label><input className="input" type="date" value={filtros.hasta} onChange={(e) => setFiltros({ ...filtros, hasta: e.target.value })} /></div>
        <span className="text-sm text-slate-500">{(meta?.total ?? 0).toLocaleString("es-CO")} registros</span>
      </div>
      <div className="tarjeta max-h-[70vh] overflow-auto">
        <table className="tabla">
          <thead className="sticky top-0"><tr><th>Fecha</th><th>Usuario</th><th>Acción</th><th>Detalle</th><th>IP</th></tr></thead>
          <tbody>
            {lista.map((r) => (
              <tr key={r.id}>
                <td className="whitespace-nowrap text-xs">{new Date(r.fecha).toLocaleString("es-CO")}</td>
                <td>{r.usuario ?? "—"}</td>
                <td className={`font-mono text-xs ${COLOR[r.accion] ?? ""}`}>{r.accion}</td>
                <td className="max-w-md truncate text-xs text-slate-600" title={JSON.stringify(r.detalle)}>
                  {Object.entries(r.detalle).map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`).join(" · ")}
                </td>
                <td className="font-mono text-xs">{r.ip}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <Paginador className="sticky bottom-0" meta={meta} onPagina={pag.setPagina} onTamano={pag.setTamano} />
      </div>
    </div>
  );
}
