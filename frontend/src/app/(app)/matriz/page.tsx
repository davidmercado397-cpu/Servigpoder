"use client";

import { useCallback, useEffect, useState } from "react";
import { Alerta, Insignia, Titulo } from "@/components/ui";
import { api, mensajeError, subirArchivo, type DiaRequerido, type Excepcion, type Franja, type MatrizPuesto, type Periodo } from "@/lib/api";
import { DIAS, ESTADO_COLOR, MESES, franjaTexto, hora, nombreMes } from "@/lib/formato";
import { usePermiso } from "@/lib/sesion";

export default function MatrizPage() {
  const puedeEditar = usePermiso("matriz.gestionar");
  const [periodos, setPeriodos] = useState<Periodo[]>([]);
  const [periodoId, setPeriodoId] = useState<number | null>(null);
  const [puestos, setPuestos] = useState<MatrizPuesto[]>([]);
  const [soloRevision, setSoloRevision] = useState(false);
  const [q, setQ] = useState("");
  const [seleccion, setSeleccion] = useState<MatrizPuesto | null>(null);
  const [msg, setMsg] = useState<{ tipo: "ok" | "error"; texto: string } | null>(null);
  const [importando, setImportando] = useState(false);

  const periodo = periodos.find((p) => p.id === periodoId) ?? null;
  const editable = puedeEditar && periodo?.estado !== "cerrado";

  const cargarPeriodos = useCallback(async () => {
    const lista = await api<Periodo[]>("/matriz/periodos");
    setPeriodos(lista);
    setPeriodoId((id) => id ?? lista[0]?.id ?? null);
  }, []);

  const cargarPuestos = useCallback(async () => {
    if (!periodoId) return setPuestos([]);
    const params = new URLSearchParams({ q, solo_revision: String(soloRevision) });
    setPuestos(await api<MatrizPuesto[]>(`/matriz/periodos/${periodoId}/puestos?${params}`));
  }, [periodoId, q, soloRevision]);

  useEffect(() => {
    cargarPeriodos();
  }, [cargarPeriodos]);

  useEffect(() => {
    const t = setTimeout(cargarPuestos, 250);
    return () => clearTimeout(t);
  }, [cargarPuestos]);

  async function accion(fn: () => Promise<unknown>, ok: string) {
    setMsg(null);
    try {
      await fn();
      setMsg({ tipo: "ok", texto: ok });
      await cargarPeriodos();
      await cargarPuestos();
    } catch (e) {
      setMsg({ tipo: "error", texto: mensajeError(e) });
    }
  }

  async function proyectar() {
    if (!periodo) return;
    const copiar = confirm(
      `Se creará la matriz del mes siguiente como borrador, copiando los ${periodo.puestos} puestos activos.\n\n` +
        "¿Copiar también las excepciones de días puntuales?\n\nAceptar = sí · Cancelar = no",
    );
    await accion(async () => {
      const nuevo = await api<Periodo>(`/matriz/periodos/${periodo.id}/proyectar`, { method: "POST", json: { copiar_excepciones: copiar } });
      setPeriodoId(nuevo.id);
    }, "Matriz proyectada al mes siguiente. Corrija solo los puestos que cambian.");
  }

  async function cambiarEstado(estado: string) {
    if (!periodo) return;
    if (estado === "cerrado" && !confirm("Un mes cerrado ya no se puede modificar. ¿Cerrar?")) return;
    await accion(() => api(`/matriz/periodos/${periodo.id}/estado`, { method: "PUT", json: { estado } }), `Matriz en estado ${estado}`);
  }

  return (
    <div className="max-w-7xl space-y-4">
      <Titulo
        accion={puedeEditar && <button className="btn-secundario" onClick={() => setImportando((v) => !v)}>Importar matriz desde Excel</button>}
      >
        Matriz comercial
      </Titulo>

      {importando && <Importar onListo={(id) => { setImportando(false); setPeriodoId(id); cargarPeriodos(); }} />}
      {msg && <Alerta tipo={msg.tipo}>{msg.texto}</Alerta>}

      {periodos.length === 0 ? (
        <Alerta tipo="info">Aún no hay matriz. Importe el Excel de la matriz de programación para crear el primer mes.</Alerta>
      ) : (
        <div className="tarjeta flex flex-wrap items-center gap-3 p-4">
          <select className="input w-56" value={periodoId ?? ""} onChange={(e) => { setSeleccion(null); setPeriodoId(Number(e.target.value)); }}>
            {periodos.map((p) => (
              <option key={p.id} value={p.id}>{nombreMes(p.anio, p.mes)} · {p.estado}</option>
            ))}
          </select>
          {periodo && (
            <>
              <Insignia color={ESTADO_COLOR[periodo.estado]}>{periodo.estado}</Insignia>
              <span className="text-sm text-slate-600">
                {periodo.puestos} puestos · {Number(periodo.hombres).toLocaleString("es-CO")} hombres · {periodo.requieren_revision} por revisar · {periodo.excluidos} excluidos
              </span>
              <div className="ml-auto flex flex-wrap gap-2">
                {puedeEditar && <button className="btn-primario" onClick={proyectar}>Proyectar al mes siguiente</button>}
                {editable && periodo.estado === "borrador" && <button className="btn-secundario" onClick={() => cambiarEstado("aprobado")}>Aprobar</button>}
                {editable && periodo.estado === "aprobado" && <button className="btn-secundario" onClick={() => cambiarEstado("borrador")}>Volver a borrador</button>}
                {editable && <button className="btn-secundario" onClick={() => cambiarEstado("cerrado")}>Cerrar mes</button>}
              </div>
            </>
          )}
        </div>
      )}

      {periodo && (
        <div className="grid gap-4 xl:grid-cols-[1fr_28rem]">
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-3">
              <input className="input max-w-xs" placeholder="Buscar puesto o ubicación…" value={q} onChange={(e) => setQ(e.target.value)} />
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={soloRevision} onChange={(e) => setSoloRevision(e.target.checked)} /> Solo los que requieren revisión
              </label>
              <span className="text-xs text-slate-500">{puestos.length} puestos</span>
            </div>
            <div className="tarjeta max-h-[70vh] overflow-auto">
              <table className="tabla">
                <thead className="sticky top-0">
                  <tr><th>Puesto</th><th>Ubicación</th><th>Hombres</th><th>Secuencia</th><th>Cobertura vendida</th><th>Festivos</th><th /></tr>
                </thead>
                <tbody>
                  {puestos.map((mp) => (
                    <tr key={mp.id} onClick={() => setSeleccion(mp)}
                      className={`cursor-pointer hover:bg-slate-50 ${seleccion?.id === mp.id ? "bg-marca-50" : ""} ${mp.puesto.excluido ? "text-slate-400" : ""}`}>
                      <td className="font-mono font-semibold">{mp.puesto.codigo}</td>
                      <td>
                        <div>{mp.puesto.ubicacion.nombre}</div>
                        <div className="text-xs text-slate-500">{mp.puesto.descripcion}</div>
                      </td>
                      <td>{Number(mp.hombres).toLocaleString("es-CO")}</td>
                      <td className="text-xs">{mp.secuencia}</td>
                      <td className="text-xs">{mp.puesto.excluido ? "Excluido" : mp.franjas.map(franjaTexto).join(" · ") || "—"}</td>
                      <td>{mp.incluye_festivos ? "Sí" : "No"}</td>
                      <td>{mp.requiere_revision && <Insignia color="bg-amber-100 text-amber-800">Revisar</Insignia>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          {seleccion && (
            <Editor
              key={seleccion.id}
              mp={seleccion}
              editable={!!editable}
              onGuardado={(mp) => { setSeleccion(mp); cargarPuestos(); cargarPeriodos(); }}
            />
          )}
        </div>
      )}
    </div>
  );
}

function Importar({ onListo }: { onListo: (periodoId: number) => void }) {
  const hoy = new Date();
  const [anio, setAnio] = useState(hoy.getFullYear());
  const [mes, setMes] = useState(hoy.getMonth() + 1);
  const [archivo, setArchivo] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [cargando, setCargando] = useState(false);

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    if (!archivo) return;
    setError("");
    setCargando(true);
    try {
      const r = await subirArchivo<{ periodo_id: number; avisos: string[] }>("/matriz/importar", archivo, { anio: String(anio), mes: String(mes) });
      if (r.avisos.length) alert("Avisos de la importación:\n\n" + r.avisos.join("\n"));
      onListo(r.periodo_id);
    } catch (err) {
      setError(mensajeError(err));
    } finally {
      setCargando(false);
    }
  }

  return (
    <form onSubmit={enviar} className="tarjeta flex flex-wrap items-end gap-3 p-4">
      <div>
        <label className="label">Mes</label>
        <select className="input" value={mes} onChange={(e) => setMes(Number(e.target.value))}>
          {MESES.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
        </select>
      </div>
      <div>
        <label className="label">Año</label>
        <input className="input w-28" type="number" value={anio} onChange={(e) => setAnio(Number(e.target.value))} />
      </div>
      <div>
        <label className="label">Archivo de la matriz (.xlsx)</label>
        <input type="file" accept=".xlsx" className="text-sm" onChange={(e) => setArchivo(e.target.files?.[0] ?? null)} required />
      </div>
      <button className="btn-primario" disabled={cargando || !archivo}>{cargando ? "Importando…" : "Importar"}</button>
      {error && <div className="w-full"><Alerta>{error}</Alerta></div>}
    </form>
  );
}

function Editor({ mp, editable, onGuardado }: { mp: MatrizPuesto; editable: boolean; onGuardado: (mp: MatrizPuesto) => void }) {
  const [hombres, setHombres] = useState(mp.hombres);
  const [secuencia, setSecuencia] = useState(mp.secuencia);
  const [festivos, setFestivos] = useState(mp.incluye_festivos);
  const [nota, setNota] = useState(mp.nota);
  const [franjas, setFranjas] = useState<Franja[]>(mp.franjas.map((f) => ({ ...f, inicio: hora(f.inicio), fin: hora(f.fin) })));
  const [dias, setDias] = useState<DiaRequerido[]>([]);
  const [error, setError] = useState("");
  const [exc, setExc] = useState({ fecha: "", sin_servicio: true, inicio: "", fin: "", observacion: "" });

  const cargarDias = useCallback(async () => setDias(await api<DiaRequerido[]>(`/matriz/puestos/${mp.id}/requerimiento`)), [mp.id]);
  useEffect(() => {
    cargarDias();
  }, [cargarDias]);

  async function guardar(extra: Record<string, unknown> = {}) {
    setError("");
    try {
      const r = await api<MatrizPuesto>(`/matriz/puestos/${mp.id}`, {
        method: "PATCH",
        json: { hombres, secuencia, incluye_festivos: festivos, nota, franjas, ...extra },
      });
      onGuardado(r);
      cargarDias();
    } catch (e) {
      setError(mensajeError(e));
    }
  }

  async function agregarExcepcion(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const nueva = await api<Excepcion>(`/matriz/puestos/${mp.id}/excepciones`, {
        method: "POST",
        json: { fecha: exc.fecha, sin_servicio: exc.sin_servicio, inicio: exc.sin_servicio ? null : exc.inicio, fin: exc.sin_servicio ? null : exc.fin, observacion: exc.observacion },
      });
      onGuardado({ ...mp, excepciones: [...mp.excepciones, nueva] });
      cargarDias();
      setExc({ ...exc, fecha: "", observacion: "" });
    } catch (err) {
      setError(mensajeError(err));
    }
  }

  function setFranja(i: number, cambios: Partial<Franja>) {
    setFranjas(franjas.map((f, j) => (j === i ? { ...f, ...cambios } : f)));
  }

  const totalHoras = dias.reduce((s, d) => s + d.horas, 0);
  const primerDia = dias.length ? (new Date(dias[0].fecha + "T00:00:00").getDay() + 6) % 7 : 0;

  return (
    <aside className="tarjeta space-y-4 p-4 xl:sticky xl:top-4 xl:max-h-[85vh] xl:overflow-auto">
      <div>
        <h2 className="text-lg font-bold text-marca-900">Puesto {mp.puesto.codigo}</h2>
        <p className="text-sm text-slate-600">{mp.puesto.ubicacion.nombre} · {mp.puesto.descripcion}</p>
        <p className="mt-1 text-xs text-slate-500">Jornada en la matriz original: “{mp.jornada || "—"}”</p>
      </div>
      {mp.nota && <Alerta tipo={mp.requiere_revision ? "error" : "info"}>{mp.nota}</Alerta>}
      {error && <Alerta>{error}</Alerta>}

      <fieldset disabled={!editable} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div><label className="label">Hombres</label><input className="input" value={hombres} onChange={(e) => setHombres(e.target.value)} /></div>
          <div><label className="label">Secuencia</label><input className="input" value={secuencia} onChange={(e) => setSecuencia(e.target.value)} /></div>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={festivos} onChange={(e) => setFestivos(e.target.checked)} /> Incluye festivos (el servicio se presta en festivos)
        </label>

        <div>
          <p className="label">Cobertura vendida (franjas)</p>
          <div className="space-y-2">
            {franjas.map((f, i) => (
              <div key={i} className="rounded-md border border-slate-200 p-2">
                <div className="mb-2 flex gap-1">
                  {DIAS.map((d, b) => (
                    <button type="button" key={d} onClick={() => setFranja(i, { dias: f.dias ^ (1 << b) })}
                      className={`h-7 w-7 rounded text-xs font-semibold ${f.dias & (1 << b) ? "bg-marca-600 text-white" : "bg-slate-100 text-slate-500"}`}>{d}</button>
                  ))}
                </div>
                <div className="flex items-center gap-2 text-sm">
                  <input type="time" className="input w-28" value={f.inicio} onChange={(e) => setFranja(i, { inicio: e.target.value })} />
                  a
                  <input type="time" className="input w-28" value={f.fin} onChange={(e) => setFranja(i, { fin: e.target.value })} />
                  <input type="number" min={1} className="input w-16" title="Personas simultáneas" value={f.cantidad} onChange={(e) => setFranja(i, { cantidad: Number(e.target.value) })} />
                  <button type="button" className="text-red-600" title="Quitar" onClick={() => setFranjas(franjas.filter((_, j) => j !== i))}>✕</button>
                </div>
              </div>
            ))}
          </div>
          <button type="button" className="mt-2 text-sm text-marca-600 hover:underline"
            onClick={() => setFranjas([...franjas, { dias: 127, inicio: "06:00", fin: "18:00", cantidad: 1 }])}>+ Agregar franja</button>
          <p className="mt-1 text-xs text-slate-500">Si el fin es menor o igual al inicio, la franja termina al día siguiente (18:00 a 06:00). Igual inicio y fin = 24 horas.</p>
        </div>

        <div><label className="label">Nota</label><textarea className="input" rows={2} value={nota} onChange={(e) => setNota(e.target.value)} /></div>

        {editable && (
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn-primario" onClick={() => guardar()}>Guardar</button>
            {mp.requiere_revision && <button type="button" className="btn-secundario" onClick={() => guardar({ requiere_revision: false })}>Guardar y marcar revisado</button>}
          </div>
        )}
      </fieldset>

      <div>
        <p className="label">Requerimiento del mes · {totalHoras.toLocaleString("es-CO")} horas</p>
        <div className="grid grid-cols-7 gap-1 text-center text-xs">
          {DIAS.map((d) => <div key={d} className="font-semibold text-slate-500">{d}</div>)}
          {Array.from({ length: primerDia }).map((_, i) => <div key={`v${i}`} />)}
          {dias.map((d) => (
            <div key={d.fecha} title={`${d.fecha}${d.festivo ? ` · ${d.festivo}` : ""}\n${d.franjas.map((f) => `${hora(f.inicio)}–${hora(f.fin)}`).join(", ") || "Sin servicio"}`}
              className={`rounded p-1 ${d.horas === 0 ? "bg-slate-100 text-slate-400" : "bg-marca-50 text-marca-900"} ${d.festivo ? "ring-1 ring-red-300" : ""}`}>
              <div className="font-semibold">{Number(d.fecha.slice(8))}</div>
              <div>{d.horas ? `${d.horas}h` : "—"}</div>
            </div>
          ))}
        </div>
        <p className="mt-1 text-xs text-slate-500">Los festivos tienen borde rojo.</p>
      </div>

      <div>
        <p className="label">Excepciones de días puntuales</p>
        <ul className="space-y-1 text-sm">
          {mp.excepciones.length === 0 && <li className="text-slate-500">Ninguna</li>}
          {mp.excepciones.map((e) => (
            <li key={e.id} className="flex items-center justify-between rounded bg-slate-50 px-2 py-1">
              <span>{e.fecha} · {e.sin_servicio ? "Sin servicio" : `${hora(e.inicio)}–${hora(e.fin)}`} {e.observacion && `· ${e.observacion}`}</span>
              {editable && (
                <button className="text-red-600" onClick={async () => { await api(`/matriz/excepciones/${e.id}`, { method: "DELETE" }); onGuardado({ ...mp, excepciones: mp.excepciones.filter((x) => x.id !== e.id) }); cargarDias(); }}>✕</button>
              )}
            </li>
          ))}
        </ul>
        {editable && (
          <form onSubmit={agregarExcepcion} className="mt-2 space-y-2 rounded-md border border-dashed border-slate-300 p-2 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <input type="date" className="input w-40" value={exc.fecha} onChange={(e) => setExc({ ...exc, fecha: e.target.value })} required />
              <label className="flex items-center gap-1"><input type="checkbox" checked={exc.sin_servicio} onChange={(e) => setExc({ ...exc, sin_servicio: e.target.checked })} /> Sin servicio</label>
            </div>
            {!exc.sin_servicio && (
              <div className="flex items-center gap-2">
                Franja adicional:
                <input type="time" className="input w-28" value={exc.inicio} onChange={(e) => setExc({ ...exc, inicio: e.target.value })} required />
                a
                <input type="time" className="input w-28" value={exc.fin} onChange={(e) => setExc({ ...exc, fin: e.target.value })} required />
              </div>
            )}
            <input className="input" placeholder="Observación" value={exc.observacion} onChange={(e) => setExc({ ...exc, observacion: e.target.value })} />
            <button className="btn-secundario">Agregar excepción</button>
          </form>
        )}
      </div>
    </aside>
  );
}
