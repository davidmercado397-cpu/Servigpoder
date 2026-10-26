"use client";

import { ArrowLeft, ChevronDown, ChevronRight, Paperclip, Pencil, Plus, ShieldAlert, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { ACEPTA_SOPORTE, MAX_SOPORTES, Modal, ModalMovimiento, subirSoportes } from "@/components/costeo";
import { Alerta } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";
import { ESTADO_MFP, SEVERIDAD, UNIDAD, fecha, hoyISO, pct, pesos, valorItem, type ItemMfp, type Mfp, type TipoItem } from "@/lib/costeo";
import { usePermiso } from "@/lib/sesion";

export default function DetalleMfp() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const gestionar = usePermiso("costeo.mfp");
  const registrar = usePermiso("costeo.movimientos");
  const [m, setM] = useState<Mfp | null>(null);
  const [fechaReembolso, setFechaReembolso] = useState("");
  const [abierto, setAbierto] = useState<number | null>(null);
  const [movItem, setMovItem] = useState<ItemMfp | null>(null);
  const [editarItem, setEditarItem] = useState<ItemMfp | null>(null);
  const [nuevoItem, setNuevoItem] = useState(false);
  const [terminar, setTerminar] = useState(false);
  const [error, setError] = useState("");

  const cargar = useCallback(() => {
    api<Mfp>(`/costeo/mfp/${id}${fechaReembolso ? `?fecha_reembolso=${fechaReembolso}` : ""}`).then(setM).catch((e) => setError(mensajeError(e)));
  }, [id, fechaReembolso]);
  useEffect(() => {
    cargar();
  }, [cargar]);

  async function accion(fn: () => Promise<Mfp>) {
    setError("");
    try {
      setM(await fn());
    } catch (e) {
      setError(mensajeError(e));
    }
  }

  if (!m) return error ? <Alerta>{error}</Alerta> : <p className="text-sm text-slate-500">Cargando…</p>;
  const reembolsoRef = fechaReembolso || (m.terminada ? m.fecha_terminacion : null);
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start gap-3">
        <Link href="/costeo/mfp" className="mt-1 text-slate-400 hover:text-slate-600"><ArrowLeft className="h-5 w-5" /></Link>
        <div>
          <h1 className="text-2xl font-bold text-marca-900">MFP {m.numero} · {m.cliente.nombre}</h1>
          <p className="text-sm text-slate-500">NIT {m.cliente.nit || "—"} · Contrato {m.contrato || "—"} · {fecha(m.fecha_inicio)} a {fecha(m.fecha_fin)} ({m.duracion_meses ?? "—"} meses)
            {m.costeo_id && <> · <Link className="text-marca-700 hover:underline" href={`/costeo/costeos/${m.costeo_id}`}>ver costeo</Link></>}</p>
        </div>
        <span className={`mt-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${ESTADO_MFP[m.estado]}`}>{m.estado}{m.terminada ? ` el ${fecha(m.fecha_terminacion)}` : ""}</span>
        <div className="ml-auto flex gap-2">
          {gestionar && !m.terminada && <button className="btn-secundario" onClick={() => setTerminar(true)}>Terminación anticipada</button>}
          {gestionar && m.terminada && <button className="btn-secundario" onClick={() => accion(() => api(`/costeo/mfp/${m.id}/reactivar`, { method: "POST" }))}>Quitar terminación</button>}
          {gestionar && m.items.every((i) => !i.ejecutado) && (
            <button className="btn-secundario" onClick={async () => {
              if (!confirm("¿Eliminar esta MFP?")) return;
              try { await api(`/costeo/mfp/${m.id}`, { method: "DELETE" }); router.push("/costeo/mfp"); } catch (e) { setError(mensajeError(e)); }
            }}><Trash2 className="h-4 w-4" /></button>
          )}
        </div>
      </div>
      {error && <Alerta>{error}</Alerta>}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Dato titulo="Facturación del contrato" valor={pesos(m.facturacion_total)} nota={`${pesos(m.valor_mensual)} al mes`} />
        <Dato titulo="MFP pactada" valor={pesos(m.pactado)} nota={`${pct(m.pct_mfp)} · comercial ${pct(m.pct_comercial)}`} rojo={m.diferencia_pct !== null && m.diferencia_pct > 0.0005} />
        <Dato titulo="Ejecutado" valor={pesos(m.ejecutado)} nota={`${pct(m.pct_ejecucion)} de lo pactado`} />
        <Dato titulo="Pendiente por ejecutar" valor={pesos(m.pendiente)} nota={m.meses_pendientes !== null ? `${m.meses_pendientes.toFixed(1)} meses de contrato por delante` : ""} />
        <Dato titulo="Reembolso si termina" valor={pesos(m.reembolso)} nota={reembolsoRef ? `a ${fecha(reembolsoRef)}` : "a hoy"} />
      </div>

      {m.alertas.length > 0 && (
        <div className="tarjeta p-4">
          <ul className="space-y-1 text-sm">{m.alertas.map((a, i) => <li key={i} className={SEVERIDAD[a.severidad]}>• {a.mensaje}</li>)}</ul>
        </div>
      )}

      <div className="tarjeta overflow-hidden">
        <div className="flex flex-wrap items-center gap-3 border-b border-slate-100 p-4">
          <h2 className="font-semibold text-slate-700">Ítems pactados</h2>
          <label className="ml-auto flex items-center gap-2 text-sm text-slate-600">
            Simular reembolso a la fecha <input type="date" className="input w-40" value={fechaReembolso} onChange={(e) => setFechaReembolso(e.target.value)} />
          </label>
          {gestionar && <button className="btn-secundario" onClick={() => setNuevoItem(true)}><Plus className="h-4 w-4" /> Ítem</button>}
        </div>
        <div className="overflow-x-auto">
          <table className="tabla">
            <thead><tr><th /><th>Ítem</th><th className="text-right">Pactado</th><th className="text-right">Ejecutado</th><th className="w-40">Avance</th>
              <th className="text-right">Pendiente</th><th className="text-right">Reembolso</th><th /></tr></thead>
            <tbody>
              {m.items.map((it) => {
                const avance = it.pactado_total ? Math.min(1.5, it.ejecutado / it.pactado_total) : 0;
                const horasAnio = it.unidad === "horas" ? it.anios.find((a) => a.actual) : null;
                return (
                  <Fragment key={it.id}>
                    <tr className="hover:bg-slate-50">
                      <td><button onClick={() => setAbierto(abierto === it.id ? null : it.id)}>{abierto === it.id ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}</button></td>
                      <td>
                        <p className="font-medium">{it.tipo}{!it.cuenta_en_mfp && <span className="ml-1 text-xs text-slate-400">(bolsa interna)</span>}</p>
                        <p className="text-xs text-slate-500">{it.descripcion} · {UNIDAD[it.unidad]}{it.unidad === "pesos_mes" ? ` de ${pesos(it.pactado)}` : ""}</p>
                      </td>
                      <td className="text-right tabular-nums">{valorItem(it.pactado_total, it.unidad)}{it.unidad === "horas" && <p className="text-xs text-slate-500">{it.pactado} h por año</p>}</td>
                      <td className="text-right tabular-nums">{valorItem(it.ejecutado, it.unidad)}{it.causado !== null && <p className="text-xs text-slate-500">causado {pesos(it.causado)}</p>}</td>
                      <td>
                        <div className="h-2 rounded-full bg-slate-100"><div className={`h-2 rounded-full ${it.excede ? "bg-red-500" : "bg-marca-600"}`} style={{ width: `${Math.min(100, avance * 100)}%` }} /></div>
                        <p className="mt-0.5 text-xs text-slate-500">{pct(it.pactado_total ? it.ejecutado / it.pactado_total : null, 0)}</p>
                      </td>
                      <td className={`text-right tabular-nums ${it.pendiente < 0 ? "font-semibold text-red-700" : ""}`}>
                        {valorItem(it.pendiente, it.unidad)}{horasAnio && <p className="text-xs text-slate-500">año {horasAnio.anio}: {fecha(horasAnio.desde)}–{fecha(horasAnio.hasta)}</p>}
                      </td>
                      <td className="text-right tabular-nums">{it.reembolsable && it.unidad !== "horas" ? pesos(it.reembolso) : "—"}</td>
                      <td className="whitespace-nowrap text-right">
                        {registrar && !(m.terminada && it.unidad === "horas") && (
                          <button className="btn-primario px-2 py-1 text-xs" onClick={() => setMovItem(it)}>{it.unidad === "horas" ? "Solicitud" : "Registrar"}</button>
                        )}
                        {gestionar && <button className="ml-2" title="Editar lo pactado" onClick={() => setEditarItem(it)}><Pencil className="h-4 w-4 text-slate-400 hover:text-marca-700" /></button>}
                      </td>
                    </tr>
                    {abierto === it.id && (
                      <tr><td /><td colSpan={7} className="bg-slate-50">
                        {it.unidad === "horas" && (
                          <div className="mb-3 flex flex-wrap gap-2">
                            {it.anios.map((a) => (
                              <span key={a.anio} className={`rounded-md border px-2 py-1 text-xs ${a.actual ? "border-marca-600 bg-white" : "border-slate-200 text-slate-500"}`}>
                                Año {a.anio} ({fecha(a.desde)}–{fecha(a.hasta)}): {a.usado} de {a.pactado} h{a.vencido && a.saldo > 0 ? ` · ${a.saldo} h perdidas` : ""}
                              </span>
                            ))}
                          </div>
                        )}
                        {(it.movimientos ?? []).length === 0 ? <p className="text-sm text-slate-500">Sin movimientos.</p> : (
                          <table className="w-full text-sm">
                            <thead><tr className="text-left text-xs text-slate-500"><th className="py-1">Fecha</th><th>Valor</th><th>Descripción</th><th>Documento</th><th>Soportes</th><th>Autorización</th><th /></tr></thead>
                            <tbody>
                              {it.movimientos!.map((x) => (
                                <tr key={x.id} className="border-t border-slate-200">
                                  <td className="py-1">{fecha(x.fecha)}</td>
                                  <td className="tabular-nums">{valorItem(x.valor, it.unidad)}</td>
                                  <td>{x.descripcion}{x.soporte && <p className="text-xs text-slate-500">{x.soporte}</p>}</td>
                                  <td className="whitespace-nowrap">{x.tipo_documento || x.numero_documento ? `${x.tipo_documento} ${x.numero_documento}`.trim() : <span className="text-slate-400">—</span>}</td>
                                  <td>
                                    <div className="flex flex-wrap items-center gap-1.5">
                                      {x.soportes.map((s) => (
                                        <span key={s.id} className="inline-flex items-center gap-1 rounded border border-slate-200 bg-white px-1.5 py-0.5 text-xs">
                                          <a className="inline-flex items-center gap-1 text-marca-700 hover:underline" href={`/api/costeo/soportes/${s.id}`} target="_blank" rel="noopener noreferrer" title={s.nombre}>
                                            <Paperclip className="h-3 w-3" /><span className="max-w-[9rem] truncate">{s.nombre}</span>
                                          </a>
                                          {gestionar && (
                                            <button aria-label="Quitar soporte" className="text-slate-400 hover:text-red-600"
                                              onClick={async () => { if (!confirm(`¿Quitar el soporte «${s.nombre}»?`)) return; try { await api(`/costeo/soportes/${s.id}`, { method: "DELETE" }); cargar(); } catch (e) { setError(mensajeError(e)); } }}>
                                              <X className="h-3 w-3" />
                                            </button>
                                          )}
                                        </span>
                                      ))}
                                      {registrar && x.soportes.length < MAX_SOPORTES && <Adjuntar movimientoId={x.id} onListo={cargar} onError={setError} />}
                                    </div>
                                  </td>
                                  <td>{x.excede && <span className="inline-flex items-center gap-1 text-xs text-red-700"><ShieldAlert className="h-3.5 w-3.5" />{x.autorizacion}</span>}</td>
                                  <td className="text-right">{gestionar && (
                                    <button title="Eliminar movimiento" onClick={() => confirm("¿Eliminar este movimiento?") && accion(() => api(`/costeo/movimientos/${x.id}`, { method: "DELETE" }))}>
                                      <Trash2 className="h-4 w-4 text-slate-400 hover:text-red-600" />
                                    </button>
                                  )}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        )}
                      </td></tr>
                    )}
                  </Fragment>
                );
              })}
              {m.items.length === 0 && <tr><td colSpan={8} className="py-8 text-center text-slate-400">Sin ítems pactados.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {gestionar && <FichaMfp m={m} onGuardado={setM} />}

      {movItem && <ModalMovimiento item={movItem} onCerrar={() => setMovItem(null)} onGuardado={(x) => { setM(x); setMovItem(null); }} />}
      {editarItem && (
        <Modal titulo={`Editar ${editarItem.tipo}`} onCerrar={() => setEditarItem(null)}>
          <EditarItem item={editarItem} onGuardado={(x) => { setM(x); setEditarItem(null); }} />
        </Modal>
      )}
      {nuevoItem && (
        <Modal titulo="Agregar ítem pactado" onCerrar={() => setNuevoItem(false)}>
          <NuevoItem mfpId={m.id} onGuardado={(x) => { setM(x); setNuevoItem(false); }} />
        </Modal>
      )}
      {terminar && (
        <Modal titulo="Terminación anticipada" onCerrar={() => setTerminar(false)}>
          <Terminar m={m} onGuardado={(x) => { setM(x); setTerminar(false); }} />
        </Modal>
      )}
    </div>
  );
}

function Adjuntar({ movimientoId, onListo, onError }: { movimientoId: number; onListo: () => void; onError: (e: string) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [subiendo, setSubiendo] = useState(false);
  return (
    <>
      <input ref={input} type="file" multiple accept={ACEPTA_SOPORTE} className="hidden" onChange={async (e) => {
        const lista = Array.from(e.target.files ?? []);
        e.target.value = "";
        if (!lista.length) return;
        setSubiendo(true);
        const fallas = await subirSoportes(movimientoId, lista);
        setSubiendo(false);
        if (fallas.length) onError(`No se pudieron subir: ${fallas.join(" · ")}`);
        onListo();
      }} />
      <button className="inline-flex items-center gap-1 rounded px-1 text-xs text-slate-500 hover:bg-slate-100 hover:text-marca-700" disabled={subiendo} onClick={() => input.current?.click()}>
        <Paperclip className="h-3 w-3" />{subiendo ? "Subiendo…" : "Adjuntar"}
      </button>
    </>
  );
}

function Dato({ titulo, valor, nota, rojo }: { titulo: string; valor: string; nota?: string; rojo?: boolean }) {
  return (
    <div className="tarjeta p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{titulo}</p>
      <p className={`mt-1 text-lg font-bold ${rojo ? "text-red-700" : "text-marca-900"}`}>{valor}</p>
      {nota && <p className={`text-xs ${rojo ? "text-red-600" : "text-slate-500"}`}>{nota}</p>}
    </div>
  );
}

function EditarItem({ item, onGuardado }: { item: ItemMfp; onGuardado: (m: Mfp) => void }) {
  const [pactado, setPactado] = useState(String(item.pactado));
  const [descripcion, setDescripcion] = useState(item.descripcion);
  const [error, setError] = useState("");
  return (
    <div className="space-y-3">
      <div><label className="label">Pactado ({UNIDAD[item.unidad]})</label><input type="number" className="input" value={pactado} onChange={(e) => setPactado(e.target.value)} /></div>
      <div><label className="label">Descripción</label><input className="input" value={descripcion} onChange={(e) => setDescripcion(e.target.value)} /></div>
      {error && <Alerta>{error}</Alerta>}
      <div className="flex justify-between">
        {!item.ejecutado ? (
          <button className="btn-secundario text-red-700" onClick={async () => {
            try { onGuardado(await api<Mfp>(`/costeo/items/${item.id}`, { method: "DELETE" })); } catch (e) { setError(mensajeError(e)); }
          }}>Eliminar ítem</button>
        ) : <span />}
        <button className="btn-primario" onClick={async () => {
          try { onGuardado(await api<Mfp>(`/costeo/items/${item.id}`, { method: "PUT", json: { pactado: Number(pactado), descripcion } })); } catch (e) { setError(mensajeError(e)); }
        }}>Guardar</button>
      </div>
    </div>
  );
}

function NuevoItem({ mfpId, onGuardado }: { mfpId: number; onGuardado: (m: Mfp) => void }) {
  const [tipos, setTipos] = useState<TipoItem[]>([]);
  const [f, setF] = useState({ tipo_id: "", pactado: "", descripcion: "" });
  const [error, setError] = useState("");
  useEffect(() => {
    api<TipoItem[]>("/costeo/tipos-item").then((t) => setTipos(t.filter((x) => x.activo))).catch(() => {});
  }, []);
  const unidad = tipos.find((t) => String(t.id) === f.tipo_id)?.unidad;
  return (
    <div className="space-y-3">
      <div><label className="label">Ítem</label>
        <select className="input" value={f.tipo_id} onChange={(e) => setF({ ...f, tipo_id: e.target.value })}>
          <option value="">Seleccione…</option>{tipos.map((t) => <option key={t.id} value={t.id}>{t.nombre} ({UNIDAD[t.unidad]})</option>)}
        </select></div>
      <div><label className="label">{unidad === "horas" ? "Horas por año" : unidad === "pesos_mes" ? "Valor mensual" : "Valor total pactado"}</label>
        <input type="number" className="input" value={f.pactado} onChange={(e) => setF({ ...f, pactado: e.target.value })} /></div>
      <div><label className="label">Descripción</label><input className="input" value={f.descripcion} onChange={(e) => setF({ ...f, descripcion: e.target.value })} /></div>
      {error && <Alerta>{error}</Alerta>}
      <div className="flex justify-end">
        <button className="btn-primario" disabled={!f.tipo_id || !f.pactado} onClick={async () => {
          try {
            onGuardado(await api<Mfp>(`/costeo/mfp/${mfpId}/items`, { method: "POST", json: { tipo_id: Number(f.tipo_id), pactado: Number(f.pactado), descripcion: f.descripcion } }));
          } catch (e) { setError(mensajeError(e)); }
        }}>Agregar</button>
      </div>
    </div>
  );
}

function Terminar({ m, onGuardado }: { m: Mfp; onGuardado: (m: Mfp) => void }) {
  const [f, setF] = useState(hoyISO());
  const [error, setError] = useState("");
  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-600">
        Con la fecha de terminación se calcula lo que el cliente debe reembolsar: lo ejecutado de cada ítem reembolsable × los meses que
        faltaban ÷ la duración del contrato. Lo pactado que no se ejecutó queda cancelado y la bolsa de horas deja de estar disponible.
      </p>
      <div><label className="label">Fecha de terminación</label><input type="date" className="input" value={f} onChange={(e) => setF(e.target.value)} /></div>
      {error && <Alerta>{error}</Alerta>}
      <div className="flex justify-end">
        <button className="btn-primario" onClick={async () => {
          try { onGuardado(await api<Mfp>(`/costeo/mfp/${m.id}/terminar`, { method: "POST", json: { fecha: f } })); } catch (e) { setError(mensajeError(e)); }
        }}>Terminar MFP</button>
      </div>
    </div>
  );
}

function FichaMfp({ m, onGuardado }: { m: Mfp; onGuardado: (m: Mfp) => void }) {
  const [f, setF] = useState({
    numero: m.numero, contrato: m.contrato, fecha_inicio: m.fecha_inicio ?? "", duracion_meses: String(m.duracion_meses ?? ""),
    valor_mensual: String(m.valor_mensual), pct_comercial: m.pct_comercial !== null ? String(+(m.pct_comercial * 100).toFixed(4)) : "", notas: m.notas,
  });
  const [abierta, setAbierta] = useState(false);
  const [error, setError] = useState("");
  const campo = (k: keyof typeof f, etiqueta: string, tipo = "text") => (
    <div><label className="label">{etiqueta}</label><input className="input" type={tipo} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></div>
  );
  return (
    <div className="tarjeta p-4">
      <button className="flex items-center gap-1 font-semibold text-slate-700" onClick={() => setAbierta(!abierta)}>
        {abierta ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />} Datos del contrato
      </button>
      {abierta && (
        <div className="mt-3 space-y-3">
          <div className="grid gap-3 sm:grid-cols-4">
            {campo("numero", "Número de MFP")}{campo("contrato", "Contrato")}{campo("fecha_inicio", "Fecha de inicio", "date")}{campo("duracion_meses", "Duración (meses)", "number")}
            {campo("valor_mensual", "Facturación mensual", "number")}{campo("pct_comercial", "% de la MFP física")}
            <div className="sm:col-span-2"><label className="label">Notas / otrosí</label><input className="input" value={f.notas} onChange={(e) => setF({ ...f, notas: e.target.value })} /></div>
          </div>
          {error && <Alerta>{error}</Alerta>}
          <div className="flex justify-end">
            <button className="btn-primario" onClick={async () => {
              setError("");
              try {
                onGuardado(await api<Mfp>(`/costeo/mfp/${m.id}`, {
                  method: "PUT", json: {
                    numero: f.numero, cliente_id: m.cliente.id, contrato: f.contrato, fecha_inicio: f.fecha_inicio || null,
                    duracion_meses: f.duracion_meses ? Number(f.duracion_meses) : null, valor_mensual: Number(f.valor_mensual || 0),
                    pct_comercial: f.pct_comercial ? Number(f.pct_comercial.replace(",", ".")) / 100 : null, notas: f.notas,
                  },
                }));
              } catch (e) { setError(mensajeError(e)); }
            }}>Guardar datos</button>
          </div>
        </div>
      )}
    </div>
  );
}
