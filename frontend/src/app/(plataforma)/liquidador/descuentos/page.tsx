"use client";

import { Pencil, Plus, Search, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { FormularioDescuento } from "@/components/formulario-descuento";
import { Paginador, metaDe, usePaginacion, type MetaPagina } from "@/components/paginacion";
import { Alerta, Insignia, Titulo } from "@/components/ui";
import { api, apiEnvelope, mensajeError } from "@/lib/api";
import { pesos } from "@/lib/formato";
import { QUINCENAS, type Descuento } from "@/lib/liquidador";
import { usePermiso } from "@/lib/sesion";


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
  const [edicion, setEdicion] = useState<{ registro: Descuento | null } | null>(null);
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
    setEdicion({ registro: d });
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


  return (
    <div className="space-y-5">
      <Titulo accion={gestionar && !edicion && (
        <button className="btn-primario inline-flex items-center gap-1.5" onClick={() => { setAviso(""); setEdicion({ registro: null }); }}>
          <Plus className="h-4 w-4" /> Nuevo préstamo o embargo
        </button>
      )}>Préstamos y embargos</Titulo>
      <p className="-mt-4 text-sm text-slate-500">
        Se descuentan después de salud y pensión: primero los embargos, luego los préstamos. Con un valor mensual y «ambas quincenas», cada
        quincena descuenta la mitad; si es solo de una quincena, la cuota completa va en esa; el periodo mensual descuenta la cuota completa; con un %, se aplica sobre el devengado sin auxilio de transporte. Si tiene monto total, deja de
        descontar al completarlo. Nunca se descuenta más que el neto disponible.
      </p>
      {error && <Alerta>{error}</Alerta>}
      {aviso && <Alerta tipo="ok">{aviso}</Alerta>}

      {edicion && (
        <FormularioDescuento key={edicion.registro?.id ?? "nuevo"} registro={edicion.registro} onCancelar={() => setEdicion(null)}
          onGuardado={() => { setEdicion(null); setAviso("Descuento guardado. Se aplica al calcular o recalcular cada periodo."); cargar().catch(() => {}); }} />
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
                <th>Empleado</th><th>Tipo</th><th>Descripción</th><th className="text-right">Cuota</th><th>Quincena</th><th className="text-right">Monto total</th>
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
                  <td className="whitespace-nowrap text-xs">{QUINCENAS.find(([v]) => v === d.quincena)?.[1] ?? "Ambas quincenas"}</td>
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
