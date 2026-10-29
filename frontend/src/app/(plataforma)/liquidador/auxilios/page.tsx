"use client";

import { Pencil, Plus, Search, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { FormularioAuxilio } from "@/components/formulario-auxilio";
import { Paginador, metaDe, usePaginacion, type MetaPagina } from "@/components/paginacion";
import { Alerta, Insignia, Modal, Titulo } from "@/components/ui";
import { api, apiEnvelope, mensajeError } from "@/lib/api";
import { pesos } from "@/lib/formato";
import { QUINCENAS, type Auxilio } from "@/lib/liquidador";
import { usePermiso } from "@/lib/sesion";



export default function Auxilios() {
  const gestionar = usePermiso("liquidador.nomina.gestionar");
  const [lista, setLista] = useState<Auxilio[]>([]);
  const [meta, setMeta] = useState<MetaPagina | null>(null);
  const [q, setQ] = useState("");
  const [estado, setEstado] = useState("activos");
  const [edicion, setEdicion] = useState<{ registro: Auxilio | null } | null>(null);
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
    setEdicion({ registro: a });
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


  return (
    <div className="space-y-5">
      <Titulo accion={gestionar && !edicion && (
        <button className="btn-primario inline-flex items-center gap-1.5" onClick={() => { setAviso(""); setEdicion({ registro: null }); }}>
          <Plus className="h-4 w-4" /> Nuevo auxilio
        </button>
      )}>Auxilios no prestacionales</Titulo>
      <p className="-mt-4 text-sm text-slate-500">
        Suman al devengado y al neto, pero no hacen base para salud y pensión (salvo lo que pase del 40 % de la remuneración, Ley 1393 de 2010,
        que sí entra en la base). Valor mensual: con «ambas quincenas» cada quincena paga la mitad; si es solo de una quincena, va completo en
        esa. Cada día no laborado (ausencias, incapacidades, vacaciones y demás novedades; no los descansos Z ni L) descuenta 1/30 del valor mensual.
      </p>
      {error && <Alerta>{error}</Alerta>}
      {aviso && <Alerta tipo="ok">{aviso}</Alerta>}

      {edicion && (
        <Modal onCerrar={() => setEdicion(null)}>
          <FormularioAuxilio key={edicion.registro?.id ?? "nuevo"} registro={edicion.registro} onCancelar={() => setEdicion(null)}
            onGuardado={() => { setEdicion(null); setAviso("Auxilio guardado. Se aplica al calcular o recalcular cada periodo."); cargar().catch(() => {}); }} />
        </Modal>
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
