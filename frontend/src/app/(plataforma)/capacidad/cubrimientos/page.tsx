"use client";

import { Paginador, metaDe, usePaginacion, type MetaPagina } from "@/components/paginacion";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useMesAnalizado } from "@/components/selector-mes";
import { Alerta, Insignia, Titulo } from "@/components/ui";
import { api, apiEnvelope, mensajeError, type Cubrimiento } from "@/lib/api";
import { DIAS } from "@/lib/formato";
import { usePermiso } from "@/lib/sesion";

const PESTANAS: [string, string][] = [
  ["pendiente", "Pendientes"],
  ["justificado", "Justificados automáticamente"],
  ["aprobado", "Aprobados"],
  ["rechazado", "Rechazados"],
  ["", "Todos"],
];

const ESTADO_COLOR: Record<string, string> = {
  pendiente: "bg-[#fab219]/20 text-[#8a5a00]",
  justificado: "bg-marca-100 text-marca-900",
  aprobado: "bg-[#0ca30c]/15 text-[#086b08]",
  rechazado: "bg-[#d03b3b]/15 text-[#a32525]",
};
const ESTADO_TEXTO: Record<string, string> = {
  pendiente: "⏳ Pendiente", justificado: "✓ Justificado", aprobado: "✓ Aprobado", rechazado: "✕ Rechazado",
};

function motivoTexto(c: Cubrimiento) {
  const nombres = c.referencia.map((r) => `${r.nombre} (${r.codigo})`).join(", ");
  if (c.motivo === "novedad") return `Cubre novedad de ${nombres}`;
  if (c.motivo === "descanso") return `Relevo del descanso de ${nombres}`;
  return "Sin motivo encontrado";
}

export default function CubrimientosPage() {
  const puedeAprobar = usePermiso("capacidad.cubrimientos.aprobar");
  const { mes, analisisId, selector, cargado } = useMesAnalizado();
  const [estado, setEstado] = useState("pendiente");
  const [q, setQ] = useState("");
  const [soloDoble, setSoloDoble] = useState(false);
  const [soloExceso, setSoloExceso] = useState(false);
  const [lista, setLista] = useState<Cubrimiento[]>([]);
  const [conteo, setConteo] = useState<Record<string, number>>({});
  const [horas, setHoras] = useState(0);
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [msg, setMsg] = useState<{ tipo: "ok" | "error"; texto: string } | null>(null);

  const [meta, setMeta] = useState<MetaPagina | null>(null);
  const pag = usePaginacion([analisisId, estado, q, soloDoble, soloExceso]);

  const cargar = useCallback(async () => {
    if (!analisisId) return;
    const p = new URLSearchParams({ estado, q, solo_doble: String(soloDoble), solo_exceso: String(soloExceso) });
    const r = await apiEnvelope<Cubrimiento[]>(`/capacidad/cubrimientos/${analisisId}?${p}&${pag.query}`);
    setLista(r.data ?? []);
    setMeta(metaDe(r));
    setConteo((r.meta.extra?.por_estado as Record<string, number>) ?? {});
    setHoras(Number(r.meta.extra?.horas ?? 0));
    setSel(new Set());
  }, [analisisId, estado, q, soloDoble, soloExceso, pag.query]);

  useEffect(() => {
    const t = setTimeout(cargar, 250);
    return () => clearTimeout(t);
  }, [cargar]);

  async function decidir(nuevo: "aprobado" | "rechazado" | "pendiente", ids: number[]) {
    if (!ids.length) return;
    let comentario = "";
    if (nuevo === "rechazado") {
      comentario = prompt(`Motivo del rechazo (${ids.length} turnos):`) ?? "";
      if (!comentario.trim()) return;
    } else if (nuevo === "aprobado") {
      comentario = prompt(`Comentario de aprobación (opcional) para ${ids.length} turnos:`) ?? "";
    }
    setMsg(null);
    try {
      await api(`/capacidad/cubrimientos/${analisisId}/decidir`, { method: "POST", json: { ids, estado: nuevo, comentario } });
      setMsg({ tipo: "ok", texto: `${ids.length} turnos ${nuevo === "pendiente" ? "devueltos a revisión" : nuevo + "s"}` });
      cargar();
    } catch (e) {
      setMsg({ tipo: "error", texto: mensajeError(e) });
    }
  }

  const todos = lista.length > 0 && lista.every((c) => sel.has(c.id));

  return (
    <div className="max-w-7xl space-y-4">
      <Titulo accion={selector}>Cubrimientos y turnos adicionales</Titulo>
      <Alerta tipo="info">
        Turnos de personas en puestos donde <b>no son titulares</b>. Se justifican solos cuando un titular del puesto tiene una novedad o
        está de descanso ese día y no sobra gente en esas horas. Los demás quedan <b>pendientes</b> para que nómina los apruebe o rechace;
        la decisión se conserva aunque se recalcule la cobertura.
      </Alerta>
      {cargado && !analisisId && <Alerta>Este mes no tiene análisis de cobertura. Calcúlelo en <Link className="underline" href="/capacidad/cobertura">Cobertura</Link>.</Alerta>}
      {msg && <Alerta tipo={msg.tipo}>{msg.texto}</Alerta>}

      {analisisId && (
        <>
          <div className="flex flex-wrap gap-1 border-b border-slate-200">
            {PESTANAS.map(([v, t]) => (
              <button key={v} onClick={() => setEstado(v)}
                className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium ${estado === v ? "border-marca-600 text-marca-700" : "border-transparent text-slate-500 hover:text-slate-700"}`}>
                {t}{v && conteo[v] !== undefined && <span className="ml-1 rounded-full bg-slate-100 px-1.5 text-xs">{conteo[v]}</span>}
              </button>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <input className="input w-72" placeholder="Buscar persona, cédula, puesto…" value={q} onChange={(e) => setQ(e.target.value)} />
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={soloExceso} onChange={(e) => setSoloExceso(e.target.checked)} /> Solo los que generan exceso</label>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={soloDoble} onChange={(e) => setSoloDoble(e.target.checked)} /> Solo doble turno</label>
            <span className="text-sm text-slate-500">{(meta?.total ?? 0).toLocaleString("es-CO")} turnos · {horas.toLocaleString("es-CO")} horas</span>
            {puedeAprobar && sel.size > 0 && (
              <div className="ml-auto flex gap-2">
                <button className="btn-primario" onClick={() => decidir("aprobado", [...sel])}>Aprobar {sel.size}</button>
                <button className="btn-secundario" onClick={() => decidir("rechazado", [...sel])}>Rechazar {sel.size}</button>
                <button className="btn-secundario" onClick={() => decidir("pendiente", [...sel])}>Deshacer</button>
              </div>
            )}
          </div>

          <div className="tarjeta max-h-[65vh] overflow-auto">
            <table className="tabla">
              <thead className="sticky top-0">
                <tr>
                  {puedeAprobar && (
                    <th className="w-8">
                      <input type="checkbox" checked={todos} onChange={() => setSel(todos ? new Set() : new Set(lista.map((c) => c.id)))} aria-label="Seleccionar todos los de esta página" title="Seleccionar todos los de esta página" />
                    </th>
                  )}
                  <th>Fecha</th><th>Puesto</th><th>Persona</th><th>Turno</th><th>Motivo</th><th>Estado</th>{puedeAprobar && <th />}
                </tr>
              </thead>
              <tbody>
                {lista.length === 0 && <tr><td colSpan={8} className="text-center text-slate-500">Sin turnos en esta vista</td></tr>}
                {lista.map((c) => (
                  <tr key={c.id} className={sel.has(c.id) ? "bg-marca-50" : ""}>
                    {puedeAprobar && (
                      <td><input type="checkbox" checked={sel.has(c.id)} onChange={() => { const s = new Set(sel); if (s.has(c.id)) s.delete(c.id); else s.add(c.id); setSel(s); }} aria-label={`Seleccionar ${c.nombre}`} /></td>
                    )}
                    <td className="whitespace-nowrap">{DIAS[(new Date(c.fecha + "T00:00:00").getDay() + 6) % 7]} {c.fecha}</td>
                    <td>
                      <Link className="font-mono font-semibold text-marca-700 hover:underline" href={`/capacidad/cobertura/${c.puesto.id}?analisis=${analisisId}`}>{c.puesto.codigo}</Link>
                      <div className="text-xs text-slate-500">{c.puesto.ubicacion.nombre}</div>
                    </td>
                    <td>
                      <div>{c.nombre}</div>
                      <div className="text-xs text-slate-500">CC {c.cedula} · {c.puesto_titular ? `titular en ${c.puesto_titular}` : "sin puesto titular"}</div>
                    </td>
                    <td className="whitespace-nowrap">{c.codigo_turno}<div className="text-xs text-slate-500">{Number(c.horas)} h</div></td>
                    <td>
                      <div className={c.motivo === "sin_motivo" ? "font-medium text-[#9a3f1a]" : ""}>{motivoTexto(c)}</div>
                      <div className="mt-1 flex flex-wrap gap-1">
                        {c.genera_exceso && <Insignia color="bg-[#fab219]/20 text-[#8a5a00]">▲ Genera exceso</Insignia>}
                        {c.doble_turno && <Insignia color="bg-[#ec835a]/20 text-[#9a3f1a]">◆ Doble turno ese día</Insignia>}
                      </div>
                    </td>
                    <td>
                      <Insignia color={ESTADO_COLOR[c.estado]}>{ESTADO_TEXTO[c.estado] ?? c.estado}</Insignia>
                      {c.comentario && <div className="mt-1 max-w-xs text-xs text-slate-600">“{c.comentario}”</div>}
                      {c.decidido_por && <div className="text-xs text-slate-400">{c.decidido_por}</div>}
                    </td>
                    {puedeAprobar && (
                      <td className="whitespace-nowrap text-right text-sm">
                        {c.estado !== "aprobado" && <button className="mr-2 text-[#086b08] hover:underline" onClick={() => decidir("aprobado", [c.id])}>Aprobar</button>}
                        {c.estado !== "rechazado" && <button className="text-[#a32525] hover:underline" onClick={() => decidir("rechazado", [c.id])}>Rechazar</button>}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
            <Paginador className="sticky bottom-0" meta={meta} onPagina={pag.setPagina} onTamano={pag.setTamano} />
          </div>
          {mes && <p className="text-xs text-slate-500">Programación del {mes.desde} al {mes.hasta}.</p>}
        </>
      )}
    </div>
  );
}
