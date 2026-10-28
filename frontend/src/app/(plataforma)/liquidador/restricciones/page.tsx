"use client";

import { Pencil, Plus, Search, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { BuscarEmpleado } from "@/components/buscar-empleado";
import { BuscarCie, Soportes } from "@/components/gestion-humana";
import { Paginador, metaDe, usePaginacion, type MetaPagina } from "@/components/paginacion";
import { Alerta, Insignia, Titulo } from "@/components/ui";
import { api, apiEnvelope, mensajeError } from "@/lib/api";
import { TIPOS_RESTRICCION, etiqueta, fechaCorta, qInicial, type Restriccion } from "@/lib/gestion";
import { usePermiso } from "@/lib/sesion";

type Formulario = {
  documento: string; nombre: string; puesto: string; tipo: string; desde: string; hasta: string; cie: string; diagnostico: string;
  detalle: string; observacion: string;
};

const ESTADO: Record<Restriccion["estado"], [string, string]> = {
  vigente: ["Vigente", "bg-amber-100 text-amber-900"], vencida: ["Vencida", "bg-slate-100 text-slate-600"],
  programada: ["Programada", "bg-sky-100 text-sky-800"], seguimiento: ["En seguimiento", "bg-violet-100 text-violet-800"],
};

function FormularioRestriccion({ registro, onGuardado, onCancelar }: { registro: Restriccion | null; onGuardado: () => void; onCancelar: () => void }) {
  const [f, setF] = useState<Formulario>(() => ({
    documento: registro?.documento ?? "", nombre: registro && !registro.empleado_id ? registro.nombre : "", puesto: registro?.puesto ?? "",
    tipo: registro?.tipo ?? "restriccion", desde: registro?.desde ?? "", hasta: registro?.hasta ?? "", cie: registro?.cie?.replaceAll(",", ", ") ?? "",
    diagnostico: registro?.diagnostico ?? "", detalle: registro?.detalle ?? "", observacion: registro?.observacion ?? "",
  }));
  const [error, setError] = useState("");
  const cambiar = (c: Partial<Formulario>) => setF({ ...f, ...c });

  async function guardar(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    const datos = Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v === "" ? null : v]));
    try {
      await api(registro ? `/liquidador/restricciones/${registro.id}` : "/liquidador/restricciones", { method: registro ? "PUT" : "POST", json: datos });
      onGuardado();
    } catch (err) {
      setError(mensajeError(err));
    }
  }

  return (
    <form onSubmit={guardar} className="tarjeta space-y-4 p-5">
      <div className="flex items-center">
        <h2 className="font-semibold text-slate-900">{registro ? "Editar registro" : "Nueva restricción o recomendación"}</h2>
        <button type="button" className="ml-auto rounded-md p-1 text-slate-500 hover:bg-slate-100" onClick={onCancelar} aria-label="Cerrar"><X className="h-5 w-5" /></button>
      </div>
      {error && <Alerta>{error}</Alerta>}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <label className="label">Cédula</label>
          <BuscarEmpleado key={registro?.id ?? "nueva"} valor={f.documento} nombreInicial={registro?.nombre} onCambio={(d) => cambiar({ documento: d })} />
        </div>
        <div>
          <label className="label">Nombre <span className="font-normal text-slate-400">(si no está en la base)</span></label>
          <input className="input" maxLength={200} value={f.nombre} onChange={(e) => cambiar({ nombre: e.target.value })} />
        </div>
        <div>
          <label className="label">Tipo</label>
          <select className="input" value={f.tipo} onChange={(e) => cambiar({ tipo: e.target.value })}>
            {TIPOS_RESTRICCION.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
          </select>
        </div>
        <div>
          <label className="label">Puesto <span className="font-normal text-slate-400">(vacío: el de la ficha)</span></label>
          <input className="input" maxLength={200} value={f.puesto} onChange={(e) => cambiar({ puesto: e.target.value })} />
        </div>
        <div>
          <label className="label">Desde</label>
          <input className="input" type="date" value={f.desde} onChange={(e) => cambiar({ desde: e.target.value })} />
        </div>
        <div>
          <label className="label">Hasta</label>
          <input className="input" type="date" value={f.hasta} onChange={(e) => cambiar({ hasta: e.target.value })} />
        </div>
        <div>
          <label className="label">Código CIE-10</label>
          <BuscarCie valor={f.cie} onCambio={(v) => cambiar({ cie: v })} onDiagnostico={(d) => setF((x) => ({ ...x, diagnostico: d }))} />
        </div>
        <div>
          <label className="label">Diagnóstico</label>
          <input className="input" maxLength={300} value={f.diagnostico} onChange={(e) => cambiar({ diagnostico: e.target.value })} />
        </div>
        <div className="sm:col-span-2 lg:col-span-4">
          <label className="label">Restricciones o recomendaciones</label>
          <textarea className="input min-h-20" maxLength={4000} value={f.detalle} placeholder="p. ej. No levantar más de 5 kg, no trabajar en alturas"
            onChange={(e) => cambiar({ detalle: e.target.value })} />
        </div>
        <div className="sm:col-span-2 lg:col-span-4">
          <label className="label">Observación</label>
          <input className="input" maxLength={300} value={f.observacion} onChange={(e) => cambiar({ observacion: e.target.value })} />
        </div>
      </div>
      <div className="flex gap-2">
        <button className="btn-primario">Guardar</button>
        <button type="button" className="btn-secundario" onClick={onCancelar}>Cancelar</button>
      </div>
    </form>
  );
}

export default function Restricciones() {
  const gestionar = usePermiso("liquidador.salud.gestionar");
  const [lista, setLista] = useState<Restriccion[]>([]);
  const [meta, setMeta] = useState<MetaPagina | null>(null);
  const [q, setQ] = useState("");
  useEffect(() => setQ(qInicial()), []);  // desde la ficha llega ?q=documento
  const [tipo, setTipo] = useState("");
  const [estado, setEstado] = useState("todas");
  const [edicion, setEdicion] = useState<{ registro: Restriccion | null } | null>(null);
  const [error, setError] = useState("");
  const [aviso, setAviso] = useState("");
  const pag = usePaginacion([q, tipo, estado]);

  const cargar = useCallback(async () => {
    const r = await apiEnvelope<Restriccion[]>(`/liquidador/restricciones?q=${encodeURIComponent(q)}&tipo=${tipo}&estado=${estado}&${pag.query}`);
    setLista(r.data ?? []);
    setMeta(metaDe(r));
  }, [q, tipo, estado, pag.query]);

  useEffect(() => {
    const t = setTimeout(() => cargar().catch((e) => setError(mensajeError(e))), 250);
    return () => clearTimeout(t);
  }, [cargar]);

  async function eliminar(x: Restriccion) {
    if (!window.confirm(`¿Eliminar este registro de ${x.nombre}${x.documentos.length ? " y sus soportes" : ""}?`)) return;
    try {
      await api(`/liquidador/restricciones/${x.id}`, { method: "DELETE" });
      await cargar();
    } catch (err) {
      setError(mensajeError(err));
    }
  }

  return (
    <div className="space-y-5">
      <Titulo accion={gestionar && !edicion && (
        <button className="btn-primario inline-flex items-center gap-1.5" onClick={() => { setAviso(""); setEdicion({ registro: null }); }}>
          <Plus className="h-4 w-4" /> Nuevo registro
        </button>
      )}>Restricciones médicas</Titulo>
      <p className="-mt-4 text-sm text-slate-500">
        Restricciones y recomendaciones médicas con su vigencia, y casos en seguimiento (p. ej. oncológicos). Repositorio de consulta: no afecta
        la nómina. Se importan con el formato de ausentismo desde Registro de incapacidades.
      </p>
      {error && <Alerta>{error}</Alerta>}
      {aviso && <Alerta tipo="ok">{aviso}</Alerta>}
      {edicion && (
        <FormularioRestriccion key={edicion.registro?.id ?? "nueva"} registro={edicion.registro} onCancelar={() => setEdicion(null)}
          onGuardado={() => { setEdicion(null); setAviso("Registro guardado."); cargar().catch(() => {}); }} />
      )}
      <div className="tarjeta overflow-hidden">
        <div className="flex flex-wrap items-center gap-3 px-4 py-3">
          <div className="relative w-72">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input className="input pl-8" placeholder="Cédula, nombre o diagnóstico…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <select className="input w-48" value={tipo} onChange={(e) => setTipo(e.target.value)} aria-label="Tipo">
            <option value="">Todos los tipos</option>
            {TIPOS_RESTRICCION.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
          </select>
          <select className="input w-40" value={estado} onChange={(e) => setEstado(e.target.value)} aria-label="Estado">
            <option value="todas">Todos</option>
            <option value="vigente">Vigentes</option>
            <option value="programada">Programadas</option>
            <option value="vencida">Vencidas</option>
            <option value="seguimiento">En seguimiento</option>
          </select>
        </div>
        <div className="overflow-auto">
          <table className="tabla text-sm">
            <thead><tr><th>Persona</th><th>Tipo</th><th>Vigencia</th><th>Diagnóstico y detalle</th><th>Soportes</th><th /></tr></thead>
            <tbody>
              {lista.map((x) => (
                <tr key={x.id} className="align-top">
                  <td className="min-w-[180px]"><span className="font-medium">{x.nombre}</span>
                    <span className="block text-xs text-slate-500"><span className="font-mono">{x.documento}</span>{x.puesto ? ` · ${x.puesto}` : ""}</span></td>
                  <td className="whitespace-nowrap text-xs">{etiqueta(TIPOS_RESTRICCION, x.tipo)}<br /><Insignia color={`mt-1 ${ESTADO[x.estado][1]}`}>{ESTADO[x.estado][0]}</Insignia></td>
                  <td className="whitespace-nowrap text-xs">{x.desde || x.hasta ? <>{fechaCorta(x.desde)}<br />{fechaCorta(x.hasta)}</> : "—"}</td>
                  <td className="min-w-[260px] text-xs">
                    {x.cie && <span className="mr-1 font-mono text-marca-700">{x.cie.replaceAll(",", ", ")}</span>}{x.diagnostico}
                    {x.detalle && <span className="block whitespace-pre-line text-slate-700">{x.detalle}</span>}
                    {x.observacion && <span className="block text-slate-500">{x.observacion}</span>}
                  </td>
                  <td className="min-w-[140px]"><Soportes modulo="restriccion" registroId={x.id} documentos={x.documentos} editable={gestionar}
                    onCambio={() => cargar().catch(() => {})} onError={setError} /></td>
                  <td className="whitespace-nowrap text-right">
                    {gestionar && (
                      <>
                        <button className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100" onClick={() => { setAviso(""); setEdicion({ registro: x }); }} aria-label="Editar"><Pencil className="h-4 w-4" /></button>
                        <button className="rounded-md p-1.5 text-slate-500 hover:bg-red-50 hover:text-red-700" onClick={() => eliminar(x)} aria-label="Eliminar"><Trash2 className="h-4 w-4" /></button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {lista.length === 0 && <p className="p-6 text-center text-sm text-slate-500">No hay registros con esos filtros.</p>}
        </div>
        <Paginador meta={meta} onPagina={pag.setPagina} onTamano={pag.setTamano} />
      </div>
    </div>
  );
}
