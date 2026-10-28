"use client";

import { ChevronDown, ChevronRight, Pencil, Plus, Search, Trash2, X } from "lucide-react";
import { Fragment, useCallback, useEffect, useState } from "react";
import { BuscarEmpleado } from "@/components/buscar-empleado";
import { Soportes } from "@/components/gestion-humana";
import { Paginador, metaDe, usePaginacion, type MetaPagina } from "@/components/paginacion";
import { Alerta, Insignia, Titulo } from "@/components/ui";
import { api, apiEnvelope, mensajeError } from "@/lib/api";
import { ESTADOS_CASO, TIPOS_CASO, etiqueta, fechaCorta, qInicial, type Caso } from "@/lib/gestion";
import { usePermiso } from "@/lib/sesion";

type Formulario = {
  documento: string; nombre: string; tipo: string; asunto: string; recibido: string; vence: string; estado: string; contacto: string; observacion: string;
};

const COLOR_ESTADO: Record<string, string> = { abierto: "bg-amber-100 text-amber-900", contestado: "bg-green-100 text-green-800", cerrado: "bg-slate-100 text-slate-600" };
const hoy = () => new Date().toISOString().slice(0, 10);

function FormularioCaso({ registro, onGuardado, onCancelar }: { registro: Caso | null; onGuardado: () => void; onCancelar: () => void }) {
  const [f, setF] = useState<Formulario>(() => ({
    documento: registro?.documento ?? "", nombre: registro && !registro.empleado_id ? registro.nombre : "", tipo: registro?.tipo ?? "derecho_peticion",
    asunto: registro?.asunto ?? "", recibido: registro?.recibido ?? hoy(), vence: registro?.vence ?? "", estado: registro?.estado ?? "abierto",
    contacto: registro?.contacto ?? "", observacion: registro?.observacion ?? "",
  }));
  const [error, setError] = useState("");
  const cambiar = (c: Partial<Formulario>) => setF({ ...f, ...c });

  async function guardar(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    const datos = { ...f, nombre: f.nombre || null, vence: f.vence || null, contacto: f.contacto || null, observacion: f.observacion || null };
    try {
      await api(registro ? `/liquidador/casos/${registro.id}` : "/liquidador/casos", { method: registro ? "PUT" : "POST", json: datos });
      onGuardado();
    } catch (err) {
      setError(mensajeError(err));
    }
  }

  return (
    <form onSubmit={guardar} className="tarjeta space-y-4 p-5">
      <div className="flex items-center">
        <h2 className="font-semibold text-slate-900">{registro ? "Editar caso" : "Nuevo caso"}</h2>
        <button type="button" className="ml-auto rounded-md p-1 text-slate-500 hover:bg-slate-100" onClick={onCancelar} aria-label="Cerrar"><X className="h-5 w-5" /></button>
      </div>
      {error && <Alerta>{error}</Alerta>}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <label className="label">Cédula</label>
          <BuscarEmpleado key={registro?.id ?? "nuevo"} valor={f.documento} nombreInicial={registro?.nombre} onCambio={(d) => cambiar({ documento: d })} />
        </div>
        <div>
          <label className="label">Nombre <span className="font-normal text-slate-400">(si no está en la base)</span></label>
          <input className="input" maxLength={200} value={f.nombre} onChange={(e) => cambiar({ nombre: e.target.value })} />
        </div>
        <div>
          <label className="label">Tipo</label>
          <select className="input" value={f.tipo} onChange={(e) => cambiar({ tipo: e.target.value })}>
            {TIPOS_CASO.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
          </select>
        </div>
        <div>
          <label className="label">Estado</label>
          <select className="input" value={f.estado} onChange={(e) => cambiar({ estado: e.target.value })}>
            {ESTADOS_CASO.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
          </select>
        </div>
        <div className="sm:col-span-2">
          <label className="label">Asunto (quién lo envía y de qué se trata)</label>
          <input className="input" required maxLength={300} value={f.asunto} placeholder="p. ej. Juzgado 9 Penal Municipal – tutela por pago de incapacidades"
            onChange={(e) => cambiar({ asunto: e.target.value })} />
        </div>
        <div>
          <label className="label">Recibido</label>
          <input className="input" type="date" required value={f.recibido} onChange={(e) => cambiar({ recibido: e.target.value })} />
        </div>
        <div>
          <label className="label">Vence (plazo para responder)</label>
          <input className="input" type="date" value={f.vence} onChange={(e) => cambiar({ vence: e.target.value })} />
        </div>
        <div className="sm:col-span-2">
          <label className="label">Correo o celular para responder</label>
          <input className="input" maxLength={200} value={f.contacto} onChange={(e) => cambiar({ contacto: e.target.value })} />
        </div>
        <div className="sm:col-span-2">
          <label className="label">Observación</label>
          <textarea className="input min-h-10" maxLength={4000} value={f.observacion} onChange={(e) => cambiar({ observacion: e.target.value })} />
        </div>
      </div>
      <div className="flex gap-2">
        <button className="btn-primario">Guardar</button>
        <button type="button" className="btn-secundario" onClick={onCancelar}>Cancelar</button>
      </div>
    </form>
  );
}

function Seguimiento({ caso, editable, onCambio, onError }: { caso: Caso; editable: boolean; onCambio: () => void; onError: (m: string) => void }) {
  const [f, setF] = useState({ fecha: hoy(), descripcion: "", medio: "", estado: "" });

  async function agregar(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api(`/liquidador/casos/${caso.id}/actuaciones`, { method: "POST", json: { ...f, medio: f.medio || null, estado: f.estado || null } });
      setF({ fecha: hoy(), descripcion: "", medio: "", estado: "" });
      onCambio();
    } catch (err) {
      onError(mensajeError(err));
    }
  }

  async function quitar(id: number) {
    if (!window.confirm("¿Quitar esta actuación del seguimiento?")) return;
    try {
      await api(`/liquidador/casos/actuaciones/${id}`, { method: "DELETE" });
      onCambio();
    } catch (err) {
      onError(mensajeError(err));
    }
  }

  return (
    <div className="space-y-2 bg-slate-50 px-4 py-3 text-sm">
      {caso.observacion && <p className="whitespace-pre-line text-xs text-slate-600">{caso.observacion}</p>}
      {caso.contacto && <p className="text-xs text-slate-500">Responder a: {caso.contacto}</p>}
      <p className="text-xs font-medium text-slate-700">Seguimiento</p>
      {caso.actuaciones.length === 0 && <p className="text-xs text-slate-500">Sin actuaciones registradas.</p>}
      <ul className="space-y-1">
        {caso.actuaciones.map((a) => (
          <li key={a.id} className="flex items-center gap-2 text-xs">
            <span className="w-20 tabular-nums text-slate-500">{fechaCorta(a.fecha)}</span>
            <span>{a.descripcion}{a.medio ? ` · ${a.medio}` : ""}</span>
            {editable && <button className="text-slate-400 hover:text-red-700" onClick={() => quitar(a.id)} aria-label="Quitar actuación"><X className="h-3 w-3" /></button>}
          </li>
        ))}
      </ul>
      {editable && (
        <form onSubmit={agregar} className="flex flex-wrap items-end gap-2">
          <input className="input w-36" type="date" required value={f.fecha} onChange={(e) => setF({ ...f, fecha: e.target.value })} aria-label="Fecha" />
          <input className="input w-72" required maxLength={300} placeholder="Contestación, requerimiento, fallo…" value={f.descripcion}
            onChange={(e) => setF({ ...f, descripcion: e.target.value })} aria-label="Actuación" />
          <input className="input w-32" maxLength={60} placeholder="Medio" value={f.medio} onChange={(e) => setF({ ...f, medio: e.target.value })} aria-label="Medio" />
          <select className="input w-44" value={f.estado} onChange={(e) => setF({ ...f, estado: e.target.value })} aria-label="Cambiar estado">
            <option value="">Sin cambiar el estado</option>
            {ESTADOS_CASO.map(([v, t]) => <option key={v} value={v}>Pasar a {t.toLowerCase()}</option>)}
          </select>
          <button className="btn-secundario">Agregar</button>
        </form>
      )}
    </div>
  );
}

export default function Tutelas() {
  const gestionar = usePermiso("liquidador.juridico.gestionar");
  const [lista, setLista] = useState<Caso[]>([]);
  const [meta, setMeta] = useState<MetaPagina | null>(null);
  const [resumen, setResumen] = useState<{ abiertos: number; vencidos: number } | null>(null);
  const [q, setQ] = useState("");
  useEffect(() => setQ(qInicial()), []);  // desde la ficha llega ?q=documento
  const [tipo, setTipo] = useState("");
  const [estado, setEstado] = useState("");
  const [abierto, setAbierto] = useState<number | null>(null);
  const [edicion, setEdicion] = useState<{ registro: Caso | null } | null>(null);
  const [error, setError] = useState("");
  const [aviso, setAviso] = useState("");
  const pag = usePaginacion([q, tipo, estado]);

  const cargar = useCallback(async () => {
    const r = await apiEnvelope<Caso[]>(`/liquidador/casos?q=${encodeURIComponent(q)}&tipo=${tipo}&estado=${estado}&${pag.query}`);
    setLista(r.data ?? []);
    setMeta(metaDe(r));
    setResumen((r.meta?.extra as { resumen: { abiertos: number; vencidos: number } } | null)?.resumen ?? null);
  }, [q, tipo, estado, pag.query]);

  useEffect(() => {
    const t = setTimeout(() => cargar().catch((e) => setError(mensajeError(e))), 250);
    return () => clearTimeout(t);
  }, [cargar]);

  async function eliminar(x: Caso) {
    if (!window.confirm(`¿Eliminar el caso «${x.asunto}» con su seguimiento${x.documentos.length ? " y sus soportes" : ""}?`)) return;
    try {
      await api(`/liquidador/casos/${x.id}`, { method: "DELETE" });
      await cargar();
    } catch (err) {
      setError(mensajeError(err));
    }
  }

  return (
    <div className="space-y-5">
      <Titulo accion={gestionar && !edicion && (
        <button className="btn-primario inline-flex items-center gap-1.5" onClick={() => { setAviso(""); setEdicion({ registro: null }); }}>
          <Plus className="h-4 w-4" /> Nuevo caso
        </button>
      )}>Tutelas y demandas</Titulo>
      <p className="-mt-4 text-sm text-slate-500">
        Derechos de petición, tutelas, incidentes de desacato, demandas, órdenes judiciales y quejas de acoso laboral, con su seguimiento y los
        soportes. Se puede registrar a personas que ya no trabajan en la empresa. Se importan con el formato de ausentismo desde Registro de incapacidades.
      </p>
      {error && <Alerta>{error}</Alerta>}
      {aviso && <Alerta tipo="ok">{aviso}</Alerta>}
      {resumen && resumen.abiertos > 0 && (
        <Alerta tipo="info">{resumen.abiertos} casos abiertos{resumen.vencidos ? `, ${resumen.vencidos} con el plazo vencido` : ""}.</Alerta>
      )}
      {edicion && (
        <FormularioCaso key={edicion.registro?.id ?? "nuevo"} registro={edicion.registro} onCancelar={() => setEdicion(null)}
          onGuardado={() => { setEdicion(null); setAviso("Caso guardado."); cargar().catch(() => {}); }} />
      )}
      <div className="tarjeta overflow-hidden">
        <div className="flex flex-wrap items-center gap-3 px-4 py-3">
          <div className="relative w-72">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input className="input pl-8" placeholder="Cédula, nombre o asunto…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <select className="input w-52" value={tipo} onChange={(e) => setTipo(e.target.value)} aria-label="Tipo">
            <option value="">Todos los tipos</option>
            {TIPOS_CASO.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
          </select>
          <select className="input w-40" value={estado} onChange={(e) => setEstado(e.target.value)} aria-label="Estado">
            <option value="">Todos</option>
            {ESTADOS_CASO.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
          </select>
        </div>
        <div className="overflow-auto">
          <table className="tabla text-sm">
            <thead><tr><th /><th>Persona</th><th>Tipo y asunto</th><th>Recibido</th><th>Estado</th><th>Soportes</th><th /></tr></thead>
            <tbody>
              {lista.map((x) => (
                <Fragment key={x.id}>
                  <tr className="cursor-pointer align-top hover:bg-marca-50" onClick={() => setAbierto(abierto === x.id ? null : x.id)}>
                    <td className="w-6 text-slate-400">{abierto === x.id ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}</td>
                    <td className="min-w-[170px]"><span className="font-medium">{x.nombre}</span><span className="block font-mono text-xs text-slate-500">{x.documento}</span></td>
                    <td className="min-w-[240px]"><span className="text-xs font-medium text-marca-800">{etiqueta(TIPOS_CASO, x.tipo)}</span><span className="block text-xs">{x.asunto}</span></td>
                    <td className="whitespace-nowrap text-xs">{fechaCorta(x.recibido)}{x.vence && <span className={`block ${x.vencido ? "font-semibold text-red-700" : "text-slate-500"}`}>Vence {fechaCorta(x.vence)}</span>}</td>
                    <td className="whitespace-nowrap text-xs">
                      <Insignia color={COLOR_ESTADO[x.estado]}>{etiqueta(ESTADOS_CASO, x.estado)}</Insignia>
                      {x.dias_abierto !== null && <span className="block text-slate-500">hace {x.dias_abierto} días</span>}
                      <span className="block text-slate-500">{x.actuaciones.length} actuaciones</span>
                    </td>
                    <td className="min-w-[140px]" onClick={(e) => e.stopPropagation()}>
                      <Soportes modulo="caso" registroId={x.id} documentos={x.documentos} editable={gestionar} onCambio={() => cargar().catch(() => {})} onError={setError} />
                    </td>
                    <td className="whitespace-nowrap text-right" onClick={(e) => e.stopPropagation()}>
                      {gestionar && (
                        <>
                          <button className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100" onClick={() => { setAviso(""); setEdicion({ registro: x }); }} aria-label="Editar"><Pencil className="h-4 w-4" /></button>
                          <button className="rounded-md p-1.5 text-slate-500 hover:bg-red-50 hover:text-red-700" onClick={() => eliminar(x)} aria-label="Eliminar"><Trash2 className="h-4 w-4" /></button>
                        </>
                      )}
                    </td>
                  </tr>
                  {abierto === x.id && (
                    <tr><td colSpan={7} className="p-0"><Seguimiento caso={x} editable={gestionar} onCambio={() => cargar().catch(() => {})} onError={setError} /></td></tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
          {lista.length === 0 && <p className="p-6 text-center text-sm text-slate-500">No hay casos con esos filtros.</p>}
        </div>
        <Paginador meta={meta} onPagina={pag.setPagina} onTamano={pag.setTamano} />
      </div>
    </div>
  );
}
