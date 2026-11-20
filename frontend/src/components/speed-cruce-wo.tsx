"use client";

import { CheckCircle2, Download, Undo2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Modal } from "@/components/costeo";
import { Paginador, usePaginacion } from "@/components/paginacion";
import { Alerta, Insignia, SubirArchivo } from "@/components/ui";
import { api, mensajeError, subirArchivo } from "@/lib/api";
import { pesos, type Nomina } from "@/lib/speed";

const TAMANOS = [20, 50, 100] as const;

type Justificacion = { correcto: "wo" | "nuestro"; motivo: string; usuario: string; fecha: string | null; diferencia: number; vigente: boolean };
type Diferencia = {
  concepto: string; nombre: string; nuestro: number | string; wo: number | string; diferencia: number; detalle?: string; justificacion?: Justificacion;
};
type FilaCruce = {
  cedula: string; nombre: string; area: string; cruce: "ambos" | "solo_wo" | "solo_nuestra"; cedula_wo?: string;
  estado: "pendiente" | "justificada" | "cuadra"; diferencias: Diferencia[];
};
type Cruce = { cargado: false } | {
  cargado: true; tolerancia: number;
  info: { archivo?: string; titulo?: string; desde?: string | null; hasta?: string | null; avisos?: string[]; cargado_por?: string; cargado_en?: string | null };
  resumen: { personas_wo: number; personas_nuestras: number; cuadran: number; pendientes: number; justificadas: number; solo_wo: number;
    solo_nuestra: number; diferencias_pendientes: number; neto_wo: number; neto_nuestro: number };
  filas: FilaCruce[];
};
type Filtro = "pendiente" | "justificada" | "cuadra" | "todas";

const valor = (d: Diferencia, v: number | string) => typeof v === "string" ? v : d.concepto === "dias" ? String(v) : pesos(v);
const conSigno = (d: Diferencia) => d.concepto === "cedula" ? "—" : d.concepto === "dias" ? `${d.diferencia > 0 ? "+" : ""}${d.diferencia}`
  : `${d.diferencia > 0 ? "+" : ""}${pesos(d.diferencia)}`;

/** Cruce de la nómina que liquidó World Office contra la de la plataforma, con la justificación de cada diferencia. */
export function CruceWorldOffice({ periodoId, nomina, editable }: { periodoId: number; nomina: Nomina; editable: boolean }) {
  const [datos, setDatos] = useState<Cruce | null>(null);
  const [error, setError] = useState("");
  const [filtro, setFiltro] = useState<Filtro>("pendiente");
  const [buscar, setBuscar] = useState("");
  const [justificar, setJustificar] = useState<{ fila: FilaCruce; dif: Diferencia } | null>(null);
  const cargar = useCallback(async () => {
    try { setDatos(await api<Cruce>(`/speed/periodos/${periodoId}/cruce-wo?grupo=${nomina}`)); } catch (e) { setError(mensajeError(e)); }
  }, [periodoId, nomina]);
  useEffect(() => { cargar(); }, [cargar]);

  const filas = useMemo(() => !datos?.cargado ? [] : datos.filas.filter((f) => (filtro === "todas" || f.estado === filtro)
    && (!buscar || `${f.cedula} ${f.cedula_wo ?? ""} ${f.nombre}`.toLowerCase().includes(buscar.toLowerCase()))), [datos, filtro, buscar]);
  const pag = usePaginacion([filtro, buscar, nomina], TAMANOS);
  const paginas = Math.max(1, Math.ceil(filas.length / pag.tamano));
  const actual = Math.min(pag.pagina, paginas);
  const visibles = filas.slice((actual - 1) * pag.tamano, actual * pag.tamano);

  async function quitar(f: FilaCruce, d: Diferencia) {
    if (!confirm(`¿Quitar la justificación de «${d.nombre}» de ${f.nombre}?`)) return;
    try {
      setDatos(await api<Cruce>(`/speed/periodos/${periodoId}/cruce-wo/justificar?grupo=${nomina}&cedula=${encodeURIComponent(f.cedula)}&concepto=${d.concepto}`,
        { method: "DELETE" }));
    } catch (e) { setError(mensajeError(e)); }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <p className="flex-1 text-sm text-slate-600">Suba el Excel de la nómina que liquidó World Office («Exportar a Excel»). Se compara persona por persona y
          concepto por concepto con la liquidación de la plataforma: una diferencia cuenta desde <b>$1.000</b>, hacia arriba o hacia abajo.
          El archivo no se guarda; solo los valores por persona.</p>
        {editable && <SubirArchivo texto={datos?.cargado ? "Subir otra vez" : "Subir nómina de World Office"} onArchivo={async (f) => {
          setError("");
          try { setDatos(await subirArchivo<Cruce>(`/speed/periodos/${periodoId}/cruce-wo/importar?grupo=${nomina}`, f)); setFiltro("pendiente"); }
          catch (e) { setError(mensajeError(e)); }
        }} />}
        {datos?.cargado && <a className="btn-secundario" href={`/api/speed/periodos/${periodoId}/cruce-wo/excel?grupo=${nomina}`}><Download className="h-4 w-4" /> Excel</a>}
      </div>
      {error && <Alerta>{error}</Alerta>}
      {!datos ? <p className="text-sm text-slate-500">Cargando…</p> : !datos.cargado ? (
        <p className="tarjeta p-6 text-center text-sm text-slate-500">Aún no se ha subido la nómina de World Office de esta quincena.</p>
      ) : (
        <>
          <p className="text-xs text-slate-500">{datos.info.titulo || datos.info.archivo} · subida por {datos.info.cargado_por}
            {datos.info.cargado_en ? ` el ${new Date(datos.info.cargado_en).toLocaleString("es-CO")}` : ""}{datos.info.archivo ? ` · ${datos.info.archivo}` : ""}</p>
          {(datos.info.avisos ?? []).map((a) => <Alerta key={a} tipo="info">{a}</Alerta>)}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            <Cifra titulo="Personas" valor={`${datos.resumen.personas_wo} WO · ${datos.resumen.personas_nuestras} plataforma`} />
            <Cifra titulo="Cuadran" valor={String(datos.resumen.cuadran)} color="text-green-700" />
            <Cifra titulo="Diferencias pendientes" valor={`${datos.resumen.pendientes} personas`} color={datos.resumen.pendientes ? "text-red-700" : "text-green-700"}
              nota={`${datos.resumen.diferencias_pendientes} diferencias`} />
            <Cifra titulo="Justificadas" valor={`${datos.resumen.justificadas} personas`} />
            <Cifra titulo="Neto WO − plataforma" valor={pesos(datos.resumen.neto_wo - datos.resumen.neto_nuestro)}
              nota={`WO ${pesos(datos.resumen.neto_wo)} · plataforma ${pesos(datos.resumen.neto_nuestro)}`} />
          </div>
          <div className="tarjeta overflow-hidden">
            <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 p-3">
              {([["pendiente", `Pendientes (${datos.resumen.pendientes})`], ["justificada", `Justificadas (${datos.resumen.justificadas})`],
                ["cuadra", `Cuadran (${datos.resumen.cuadran})`], ["todas", "Todas"]] as [Filtro, string][]).map(([v, t]) => (
                <button key={v} className={`rounded-full px-3 py-1 text-sm ${filtro === v ? "bg-marca-600 text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200"}`}
                  onClick={() => setFiltro(v)}>{t}</button>
              ))}
              <input className="input ml-auto w-72" placeholder="Buscar por cédula o nombre" value={buscar} onChange={(e) => setBuscar(e.target.value)} />
            </div>
            {!visibles.length && <p className="p-6 text-center text-sm text-slate-400">
              {filtro === "pendiente" ? "No hay diferencias pendientes." : "No hay personas con este filtro."}</p>}
            {visibles.map((f) => (
              <div key={`${f.cruce}-${f.cedula}`} className="border-b border-slate-100 p-3 last:border-0">
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <p className="font-medium">{f.nombre}</p>
                  <span className="text-xs text-slate-500">{f.cedula}{f.area ? ` · ${f.area}` : ""}</span>
                  {f.cruce === "solo_wo" && <Insignia color="bg-amber-100 text-amber-800">Solo en World Office</Insignia>}
                  {f.cruce === "solo_nuestra" && <Insignia color="bg-amber-100 text-amber-800">Solo en la plataforma</Insignia>}
                  <Insignia color={f.estado === "pendiente" ? "bg-red-100 text-red-700" : f.estado === "justificada" ? "bg-sky-100 text-sky-800" : "bg-green-100 text-green-800"}>
                    {f.estado === "pendiente" ? "Pendiente" : f.estado === "justificada" ? "Justificada" : "Cuadra"}</Insignia>
                </div>
                {f.diferencias.length > 0 && (
                  <div className="overflow-x-auto">
                    <table className="tabla">
                      <thead><tr><th>Concepto</th><th className="text-right">Plataforma</th><th className="text-right">World Office</th>
                        <th className="text-right">Diferencia</th><th>Justificación</th></tr></thead>
                      <tbody>
                        {f.diferencias.map((d) => {
                          const j = d.justificacion;
                          return (
                            <tr key={d.concepto}>
                              <td><p>{d.nombre}</p>{d.detalle && <p className="text-xs text-slate-500">{d.detalle}</p>}</td>
                              <td className="text-right tabular-nums">{valor(d, d.nuestro)}</td>
                              <td className="text-right tabular-nums">{valor(d, d.wo)}</td>
                              <td className={`text-right font-medium tabular-nums ${d.diferencia > 0 ? "text-amber-700" : d.diferencia < 0 ? "text-red-700" : ""}`}>{conSigno(d)}</td>
                              <td className="text-sm">
                                {j && (
                                  <div className={j.vigente ? "" : "text-slate-400 line-through"}>
                                    <p><CheckCircle2 className="mr-1 inline h-4 w-4 text-sky-600" />
                                      <b>{j.correcto === "wo" ? "World Office" : "La plataforma"} está bien:</b> {j.motivo}</p>
                                    <p className="text-xs text-slate-500">{j.usuario}{j.fecha ? ` · ${new Date(j.fecha).toLocaleDateString("es-CO")}` : ""}</p>
                                  </div>
                                )}
                                {j && !j.vigente && <p className="text-xs text-red-700">La diferencia cambió (era {pesos(j.diferencia)}): justifíquela de nuevo.</p>}
                                {editable && (
                                  <div className="mt-1 flex gap-3">
                                    {(!j || !j.vigente) && <button className="text-sm font-medium text-marca-700 hover:underline" onClick={() => setJustificar({ fila: f, dif: d })}>
                                      Justificar</button>}
                                    {j && <button className="inline-flex items-center gap-1 text-xs text-slate-500 hover:underline" onClick={() => quitar(f, d)}>
                                      <Undo2 className="h-3 w-3" /> Quitar</button>}
                                  </div>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            ))}
            <Paginador meta={{ total: filas.length, pagina: actual, tamano: pag.tamano, paginas }} tamanos={TAMANOS}
              onPagina={pag.setPagina} onTamano={pag.setTamano} />
          </div>
        </>
      )}
      {justificar && <Justificar periodoId={periodoId} nomina={nomina} fila={justificar.fila} dif={justificar.dif}
        onCerrar={() => setJustificar(null)} onListo={(d) => { setDatos(d); setJustificar(null); }} />}
    </div>
  );
}

function Cifra({ titulo, valor: v, nota, color = "" }: { titulo: string; valor: string; nota?: string; color?: string }) {
  return (
    <div className="tarjeta p-3">
      <p className="text-xs text-slate-500">{titulo}</p>
      <p className={`text-lg font-semibold ${color}`}>{v}</p>
      {nota && <p className="text-xs text-slate-500">{nota}</p>}
    </div>
  );
}

function Justificar({ periodoId, nomina, fila, dif, onCerrar, onListo }: {
  periodoId: number; nomina: Nomina; fila: FilaCruce; dif: Diferencia; onCerrar: () => void; onListo: (d: Cruce) => void;
}) {
  const otras = fila.diferencias.filter((d) => d.concepto !== dif.concepto && !d.justificacion?.vigente);
  const [correcto, setCorrecto] = useState<"wo" | "nuestro">("wo");
  const [motivo, setMotivo] = useState("");
  const [todas, setTodas] = useState(otras.length > 0);
  const [error, setError] = useState("");
  const [guardando, setGuardando] = useState(false);
  return (
    <Modal titulo={`Justificar diferencia · ${fila.nombre}`} onCerrar={onCerrar}>
      <form className="space-y-3" onSubmit={async (e) => {
        e.preventDefault();
        setGuardando(true);
        setError("");
        try {
          let r: Cruce | null = null;
          for (const d of [dif, ...(todas ? otras : [])]) {
            r = await api<Cruce>(`/speed/periodos/${periodoId}/cruce-wo/justificar?grupo=${nomina}`,
              { method: "POST", json: { cedula: fila.cedula, concepto: d.concepto, correcto, motivo } });
          }
          if (r) onListo(r);
        } catch (err) { setError(mensajeError(err)); } finally { setGuardando(false); }
      }}>
        <p className="text-sm text-slate-600"><b>{dif.nombre}</b>: plataforma {valor(dif, dif.nuestro)}, World Office {valor(dif, dif.wo)} (diferencia {conSigno(dif)}).</p>
        <div className="space-y-1">
          <label className="label">¿Cuál valor está bien?</label>
          <label className="flex items-center gap-2 text-sm"><input type="radio" checked={correcto === "wo"} onChange={() => setCorrecto("wo")} /> World Office está bien</label>
          <label className="flex items-center gap-2 text-sm"><input type="radio" checked={correcto === "nuestro"} onChange={() => setCorrecto("nuestro")} /> La plataforma está bien</label>
        </div>
        <div><label className="label">Motivo</label>
          <textarea className="input" rows={3} required minLength={3} maxLength={300} value={motivo} onChange={(e) => setMotivo(e.target.value)}
            placeholder="Ej. Menor valor pagado en la 2da quincena de octubre" /></div>
        {otras.length > 0 && <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={todas} onChange={(e) => setTodas(e.target.checked)} />
          <span>Aplicar también a las otras {otras.length} diferencias pendientes de esta persona ({otras.map((d) => d.nombre.split(" (")[0]).join(", ")})</span></label>}
        {error && <Alerta>{error}</Alerta>}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-secundario" onClick={onCerrar}>Cancelar</button>
          <button className="btn-primario" disabled={guardando}>{guardando ? "Guardando…" : "Justificar"}</button>
        </div>
      </form>
    </Modal>
  );
}
