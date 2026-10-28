"use client";

import { Pencil, Plus, Search, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { BuscarEmpleado } from "@/components/buscar-empleado";
import { Paginador, metaDe, usePaginacion, type MetaPagina } from "@/components/paginacion";
import { Alerta, Insignia, Titulo } from "@/components/ui";
import { api, apiEnvelope, mensajeError } from "@/lib/api";
import { pesos } from "@/lib/formato";
import { QUINCENAS, type Auxilio, type Quincena } from "@/lib/liquidador";
import { usePermiso } from "@/lib/sesion";

type Formulario = { documento: string; descripcion: string; valor_mensual: string; desde: string; hasta: string; quincena: Quincena; activo: boolean };

const hoy = () => new Date().toISOString().slice(0, 10);
const VACIO: Formulario = { documento: "", descripcion: "", valor_mensual: "", desde: hoy(), hasta: "", quincena: "ambas", activo: true };

export default function Auxilios() {
  const gestionar = usePermiso("liquidador.nomina.gestionar");
  const [lista, setLista] = useState<Auxilio[]>([]);
  const [meta, setMeta] = useState<MetaPagina | null>(null);
  const [q, setQ] = useState("");
  const [estado, setEstado] = useState("activos");
  const [edicion, setEdicion] = useState<{ id: number | null; nombre?: string; f: Formulario } | null>(null);
  const [error, setError] = useState("");
  const [aviso, setAviso] = useState("");
  const pag = usePaginacion([q, estado]);

  const cargar = useCallback(async () => {
    const r = await apiEnvelope<Auxilio[]>(`/liquidador/auxilios?q=${encodeURIComponent(q)}&estado=${estado}&${pag.query}`);
    setLista(r.data ?? []);
    setMeta(metaDe(r));
  }, [q, estado, pag.query]);

  useEffect(() => {
    const t = setTimeout(() => cargar().catch((e) => setError(mensajeError(e))), 250);
    return () => clearTimeout(t);
  }, [cargar]);

  function editar(a: Auxilio) {
    setAviso("");
    setEdicion({ id: a.id, nombre: a.nombre, f: { documento: a.documento, descripcion: a.descripcion, valor_mensual: String(a.valor_mensual), desde: a.desde,
      hasta: a.hasta ?? "", quincena: a.quincena, activo: a.activo } });
  }

  async function guardar(e: React.FormEvent) {
    e.preventDefault();
    if (!edicion) return;
    const { f, id } = edicion;
    setError("");
    const datos = { documento: f.documento.trim(), descripcion: f.descripcion.trim(), valor_mensual: Number(f.valor_mensual), desde: f.desde,
      hasta: f.hasta || null, quincena: f.quincena, activo: f.activo };
    try {
      await api(id ? `/liquidador/auxilios/${id}` : "/liquidador/auxilios", { method: id ? "PUT" : "POST", json: datos });
      setEdicion(null);
      setAviso("Auxilio guardado. Se aplica al calcular o recalcular cada periodo.");
      await cargar();
    } catch (err) {
      setError(mensajeError(err));
    }
  }

  async function eliminar(a: Auxilio) {
    if (!window.confirm(`¿Eliminar "${a.descripcion}" de ${a.nombre}?`)) return;
    try {
      await api(`/liquidador/auxilios/${a.id}`, { method: "DELETE" });
      await cargar();
    } catch (err) {
      setError(mensajeError(err));
    }
  }

  const f = edicion?.f;
  const cambiar = (c: Partial<Formulario>) => edicion && setEdicion({ ...edicion, f: { ...edicion.f, ...c } });

  return (
    <div className="space-y-5">
      <Titulo accion={gestionar && !edicion && (
        <button className="btn-primario inline-flex items-center gap-1.5" onClick={() => { setAviso(""); setEdicion({ id: null, f: { ...VACIO, desde: hoy() } }); }}>
          <Plus className="h-4 w-4" /> Nuevo auxilio
        </button>
      )}>Auxilios no prestacionales</Titulo>
      <p className="-mt-4 text-sm text-slate-500">
        Suman al devengado y al neto, pero no hacen base para salud y pensión (salvo lo que pase del 40 % de la remuneración, Ley 1393 de 2010,
        que sí entra en la base). Valor mensual: con «ambas quincenas» cada quincena paga la mitad; si es solo de una quincena, va completo en
        esa. Cada día de ausencia descuenta 1/30 del valor mensual.
      </p>
      {error && <Alerta>{error}</Alerta>}
      {aviso && <Alerta tipo="ok">{aviso}</Alerta>}

      {f && (
        <form onSubmit={guardar} className="tarjeta space-y-4 p-5">
          <div className="flex items-center">
            <h2 className="font-semibold text-slate-900">{edicion?.id ? "Editar auxilio" : "Nuevo auxilio"}</h2>
            <button type="button" className="ml-auto rounded-md p-1 text-slate-500 hover:bg-slate-100" onClick={() => setEdicion(null)} aria-label="Cerrar"><X className="h-5 w-5" /></button>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <label className="label">Cédula del empleado</label>
              <BuscarEmpleado key={edicion.id ?? "nuevo"} valor={f.documento} nombreInicial={edicion.nombre} onCambio={(documento) => cambiar({ documento })} />
            </div>
            <div className="sm:col-span-2">
              <label className="label">Descripción</label>
              <input className="input" required maxLength={200} placeholder="p. ej. Auxilio de rodamiento · Alimentación" value={f.descripcion}
                onChange={(e) => cambiar({ descripcion: e.target.value })} />
            </div>
            <div>
              <label className="label">Valor mensual</label>
              <input className="input" type="number" min={1} required value={f.valor_mensual} onChange={(e) => cambiar({ valor_mensual: e.target.value })} />
              {f.valor_mensual && <p className="mt-1 text-xs text-slate-500">
                {f.quincena === "ambas" ? `Por quincena: ${pesos(Number(f.valor_mensual) / 2)}` : `Completo en la ${f.quincena === "primera" ? "1.ª" : "2.ª"} quincena`}
                {` · ${pesos(Number(f.valor_mensual) / 30)} menos por día de ausencia`}</p>}
            </div>
            <div>
              <label className="label">Quincena en que se paga</label>
              <select className="input" value={f.quincena} onChange={(e) => cambiar({ quincena: e.target.value as Quincena })}>
                {QUINCENAS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-2 sm:col-span-2">
              <div>
                <label className="label">Desde</label>
                <input className="input" type="date" required value={f.desde} onChange={(e) => cambiar({ desde: e.target.value })} />
              </div>
              <div>
                <label className="label">Hasta</label>
                <input className="input" type="date" value={f.hasta} onChange={(e) => cambiar({ hasta: e.target.value })} />
              </div>
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={f.activo} onChange={(e) => cambiar({ activo: e.target.checked })} /> Activo
          </label>
          <div className="flex gap-2">
            <button className="btn-primario">Guardar</button>
            <button type="button" className="btn-secundario" onClick={() => setEdicion(null)}>Cancelar</button>
          </div>
        </form>
      )}

      <div className="tarjeta overflow-hidden">
        <div className="flex flex-wrap items-center gap-3 px-4 py-3">
          <div className="relative w-72">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input className="input pl-8" placeholder="Buscar por cédula, nombre o descripción…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <select className="input w-40" value={estado} onChange={(e) => setEstado(e.target.value)}>
            <option value="activos">Activos</option>
            <option value="inactivos">Inactivos</option>
            <option value="todos">Todos</option>
          </select>
        </div>
        <div className="overflow-auto">
          <table className="tabla text-sm">
            <thead>
              <tr><th>Empleado</th><th>Descripción</th><th className="text-right">Valor mensual</th><th>Quincena</th><th className="text-right">Pagado</th><th>Vigencia</th><th /></tr>
            </thead>
            <tbody>
              {lista.map((a) => (
                <tr key={a.id} className={a.activo ? "" : "text-slate-400"}>
                  <td><span className="font-medium">{a.nombre}</span><span className="block font-mono text-xs text-slate-500">{a.documento}</span></td>
                  <td>{a.descripcion}{!a.activo && <Insignia color="ml-1">Inactivo</Insignia>}</td>
                  <td className="text-right tabular-nums">{pesos(a.valor_mensual)}</td>
                  <td className="whitespace-nowrap text-xs">{QUINCENAS.find(([v]) => v === a.quincena)?.[1]}</td>
                  <td className="text-right tabular-nums">{pesos(a.pagado)}</td>
                  <td className="whitespace-nowrap text-xs">{a.desde}{a.hasta ? ` → ${a.hasta}` : " en adelante"}</td>
                  <td className="whitespace-nowrap text-right">
                    {gestionar && (
                      <>
                        <button className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100" onClick={() => editar(a)} aria-label="Editar"><Pencil className="h-4 w-4" /></button>
                        {a.pagado === 0 && (
                          <button className="rounded-md p-1.5 text-slate-500 hover:bg-red-50 hover:text-red-700" onClick={() => eliminar(a)} aria-label="Eliminar"><Trash2 className="h-4 w-4" /></button>
                        )}
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {lista.length === 0 && <p className="p-6 text-center text-sm text-slate-500">No hay auxilios {estado === "todos" ? "" : estado}.</p>}
        </div>
        <Paginador meta={meta} onPagina={pag.setPagina} onTamano={pag.setTamano} />
      </div>
    </div>
  );
}
