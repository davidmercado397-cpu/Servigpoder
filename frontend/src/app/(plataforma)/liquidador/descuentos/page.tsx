"use client";

import { Pencil, Plus, Search, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Paginador, metaDe, usePaginacion, type MetaPagina } from "@/components/paginacion";
import { Alerta, Insignia, Titulo } from "@/components/ui";
import { api, apiEnvelope, mensajeError } from "@/lib/api";
import { pesos } from "@/lib/formato";
import type { Descuento } from "@/lib/liquidador";
import { usePermiso } from "@/lib/sesion";

type Formulario = {
  documento: string; tipo: "prestamo" | "embargo"; descripcion: string; forma: "valor" | "porcentaje";
  valor_mensual: string; porcentaje: string; monto_total: string; desde: string; hasta: string; activo: boolean;
};

const hoy = () => new Date().toISOString().slice(0, 10);
const VACIO: Formulario = {
  documento: "", tipo: "prestamo", descripcion: "", forma: "valor", valor_mensual: "", porcentaje: "", monto_total: "",
  desde: hoy(), hasta: "", activo: true,
};
const TIPO: Record<string, [string, string]> = {
  prestamo: ["Préstamo", "bg-sky-100 text-sky-800"],
  embargo: ["Embargo", "bg-rose-100 text-rose-800"],
};

export default function Descuentos() {
  const gestionar = usePermiso("liquidador.nomina.gestionar");
  const [lista, setLista] = useState<Descuento[]>([]);
  const [meta, setMeta] = useState<MetaPagina | null>(null);
  const [q, setQ] = useState("");
  const [estado, setEstado] = useState("activos");
  const [edicion, setEdicion] = useState<{ id: number | null; f: Formulario } | null>(null);
  const [error, setError] = useState("");
  const [aviso, setAviso] = useState("");
  const pag = usePaginacion([q, estado]);

  const cargar = useCallback(async () => {
    const r = await apiEnvelope<Descuento[]>(`/liquidador/descuentos?q=${encodeURIComponent(q)}&estado=${estado}&${pag.query}`);
    setLista(r.data ?? []);
    setMeta(metaDe(r));
  }, [q, estado, pag.query]);

  useEffect(() => {
    const t = setTimeout(() => cargar().catch((e) => setError(mensajeError(e))), 250);
    return () => clearTimeout(t);
  }, [cargar]);

  function editar(d: Descuento) {
    setAviso("");
    setEdicion({
      id: d.id,
      f: {
        documento: d.documento, tipo: d.tipo, descripcion: d.descripcion, forma: d.porcentaje !== null ? "porcentaje" : "valor",
        valor_mensual: d.valor_mensual?.toString() ?? "", porcentaje: d.porcentaje?.toString() ?? "", monto_total: d.monto_total?.toString() ?? "",
        desde: d.desde, hasta: d.hasta ?? "", activo: d.activo,
      },
    });
  }

  async function guardar(e: React.FormEvent) {
    e.preventDefault();
    if (!edicion) return;
    const { f, id } = edicion;
    setError("");
    const datos = {
      documento: f.documento.trim(), tipo: f.tipo, descripcion: f.descripcion.trim(),
      valor_mensual: f.forma === "valor" ? Number(f.valor_mensual) : null,
      porcentaje: f.forma === "porcentaje" ? Number(f.porcentaje) : null,
      monto_total: f.monto_total ? Number(f.monto_total) : null, desde: f.desde, hasta: f.hasta || null, activo: f.activo,
    };
    try {
      await api(id ? `/liquidador/descuentos/${id}` : "/liquidador/descuentos", { method: id ? "PUT" : "POST", json: datos });
      setEdicion(null);
      setAviso("Descuento guardado. Se aplica al calcular o recalcular cada periodo.");
      await cargar();
    } catch (err) {
      setError(mensajeError(err));
    }
  }

  async function eliminar(d: Descuento) {
    if (!window.confirm(`¿Eliminar "${d.descripcion}" de ${d.nombre}?`)) return;
    try {
      await api(`/liquidador/descuentos/${d.id}`, { method: "DELETE" });
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
          <Plus className="h-4 w-4" /> Nuevo préstamo o embargo
        </button>
      )}>Préstamos y embargos</Titulo>
      <p className="-mt-4 text-sm text-slate-500">
        Se descuentan después de salud y pensión: primero los embargos, luego los préstamos. Con un valor mensual, la quincena descuenta la mitad
        y el periodo mensual la cuota completa; con un %, se aplica sobre el devengado sin auxilio de transporte. Si tiene monto total, deja de
        descontar al completarlo. Nunca se descuenta más que el neto disponible.
      </p>
      {error && <Alerta>{error}</Alerta>}
      {aviso && <Alerta tipo="ok">{aviso}</Alerta>}

      {f && (
        <form onSubmit={guardar} className="tarjeta space-y-4 p-5">
          <div className="flex items-center">
            <h2 className="font-semibold text-slate-900">{edicion?.id ? "Editar descuento" : "Nuevo descuento"}</h2>
            <button type="button" className="ml-auto rounded-md p-1 text-slate-500 hover:bg-slate-100" onClick={() => setEdicion(null)} aria-label="Cerrar"><X className="h-5 w-5" /></button>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <label className="label">Cédula del empleado</label>
              <input className="input font-mono" required value={f.documento} onChange={(e) => cambiar({ documento: e.target.value })} />
            </div>
            <div>
              <label className="label">Tipo</label>
              <select className="input" value={f.tipo} onChange={(e) => cambiar({ tipo: e.target.value as Formulario["tipo"] })}>
                <option value="prestamo">Préstamo</option>
                <option value="embargo">Embargo</option>
              </select>
            </div>
            <div className="sm:col-span-2">
              <label className="label">Descripción</label>
              <input className="input" required maxLength={200} placeholder="p. ej. Préstamo de calamidad · Juzgado 3 de Cali" value={f.descripcion}
                onChange={(e) => cambiar({ descripcion: e.target.value })} />
            </div>
            <div>
              <label className="label">Se descuenta</label>
              <select className="input" value={f.forma} onChange={(e) => cambiar({ forma: e.target.value as Formulario["forma"] })}>
                <option value="valor">Valor fijo mensual</option>
                <option value="porcentaje">% del devengado</option>
              </select>
            </div>
            {f.forma === "valor" ? (
              <div>
                <label className="label">Cuota mensual</label>
                <input className="input" type="number" min={1} required value={f.valor_mensual} onChange={(e) => cambiar({ valor_mensual: e.target.value })} />
                {f.valor_mensual && <p className="mt-1 text-xs text-slate-500">Por quincena: {pesos(Number(f.valor_mensual) / 2)}</p>}
              </div>
            ) : (
              <div>
                <label className="label">Porcentaje</label>
                <input className="input" type="number" min={0.01} max={100} step="0.01" required value={f.porcentaje} onChange={(e) => cambiar({ porcentaje: e.target.value })} />
              </div>
            )}
            <div>
              <label className="label">Monto total (opcional)</label>
              <input className="input" type="number" min={1} value={f.monto_total} onChange={(e) => cambiar({ monto_total: e.target.value })} />
              <p className="mt-1 text-xs text-slate-500">Vacío: descuenta hasta desactivarlo</p>
            </div>
            <div className="grid grid-cols-2 gap-2">
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
              <tr>
                <th>Empleado</th><th>Tipo</th><th>Descripción</th><th className="text-right">Cuota</th><th className="text-right">Monto total</th>
                <th className="text-right">Descontado</th><th className="text-right">Saldo</th><th>Vigencia</th><th />
              </tr>
            </thead>
            <tbody>
              {lista.map((d) => (
                <tr key={d.id} className={d.activo ? "" : "text-slate-400"}>
                  <td><span className="font-medium">{d.nombre}</span><span className="block font-mono text-xs text-slate-500">{d.documento}</span></td>
                  <td><Insignia color={TIPO[d.tipo][1]}>{TIPO[d.tipo][0]}</Insignia>{!d.activo && <Insignia color="ml-1">Inactivo</Insignia>}</td>
                  <td>{d.descripcion}</td>
                  <td className="whitespace-nowrap text-right tabular-nums">{d.porcentaje !== null ? `${d.porcentaje} %` : `${pesos(d.valor_mensual)}/mes`}</td>
                  <td className="text-right tabular-nums">{pesos(d.monto_total)}</td>
                  <td className="text-right tabular-nums">{pesos(d.descontado)}</td>
                  <td className="text-right tabular-nums">{d.saldo === null ? "—" : pesos(d.saldo)}</td>
                  <td className="whitespace-nowrap text-xs">{d.desde}{d.hasta ? ` → ${d.hasta}` : " en adelante"}</td>
                  <td className="whitespace-nowrap text-right">
                    {gestionar && (
                      <>
                        <button className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100" onClick={() => editar(d)} aria-label="Editar"><Pencil className="h-4 w-4" /></button>
                        {d.descontado === 0 && (
                          <button className="rounded-md p-1.5 text-slate-500 hover:bg-red-50 hover:text-red-700" onClick={() => eliminar(d)} aria-label="Eliminar"><Trash2 className="h-4 w-4" /></button>
                        )}
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {lista.length === 0 && <p className="p-6 text-center text-sm text-slate-500">No hay préstamos ni embargos {estado === "todos" ? "" : estado}.</p>}
        </div>
        <Paginador meta={meta} onPagina={pag.setPagina} onTamano={pag.setTamano} />
      </div>
    </div>
  );
}
