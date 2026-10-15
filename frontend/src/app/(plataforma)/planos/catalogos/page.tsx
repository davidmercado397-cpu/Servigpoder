"use client";

import { Pencil, Plus, Search, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Alerta, Pestanas, Titulo } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";
import { usePermiso } from "@/lib/sesion";

type Entidad = { catalogo: string; codigo: string; descripcion: string; observacion: string };
type Salario = { anio: number; valor: number };
type Catalogo = "BANCOS" | "AFP" | "EPS" | "CESANTIAS" | "CAJAS" | "CARGOS" | "SALARIO";
const PESTANAS: [Catalogo, string][] = [
  ["CARGOS", "Cargos"], ["BANCOS", "Bancos"], ["AFP", "Pensiones"], ["EPS", "EPS"], ["CESANTIAS", "Cesantías"], ["CAJAS", "Cajas"],
  ["SALARIO", "Salario mínimo"],
];
const peso = (n: number) => `$ ${n.toLocaleString("es-CO")}`;

export default function Catalogos() {
  const configurar = usePermiso("planos.configurar");
  const [pestana, setPestana] = useState<Catalogo>("CARGOS");
  const [entidades, setEntidades] = useState<Entidad[]>([]);
  const [salarios, setSalarios] = useState<Salario[]>([]);
  const [edicion, setEdicion] = useState<Entidad | null>(null);
  const [existente, setExistente] = useState(false); // al editar no se cambia el código
  const [nuevoSalario, setNuevoSalario] = useState({ anio: String(new Date().getFullYear() + 1), valor: "" });
  const [q, setQ] = useState("");
  const [error, setError] = useState("");

  const cargar = useCallback(() => Promise.all([
    api<Entidad[]>("/planos/entidades").then(setEntidades),
    api<Salario[]>("/planos/salarios").then(setSalarios),
  ]).catch((e) => setError(mensajeError(e))), []);
  useEffect(() => {
    cargar();
  }, [cargar]);

  const visibles = useMemo(() => {
    const t = q.trim().toUpperCase();
    return entidades.filter((e) => e.catalogo === pestana && (!t || e.codigo.includes(t) || e.descripcion.toUpperCase().includes(t)));
  }, [entidades, pestana, q]);

  async function guardar() {
    if (!edicion) return;
    setError("");
    try {
      await api("/planos/entidades", { method: "PUT", json: edicion });
      setEdicion(null);
      cargar();
    } catch (e) {
      setError(mensajeError(e));
    }
  }

  async function eliminar(e: Entidad) {
    if (!window.confirm(`¿Eliminar ${e.codigo} · ${e.descripcion}? También se quitan sus alias.`)) return;
    try {
      await api(`/planos/entidades/${e.catalogo}/${encodeURIComponent(e.codigo)}`, { method: "DELETE" });
      cargar();
    } catch (err) {
      setError(mensajeError(err));
    }
  }

  async function guardarSalario(anio: string, valor: string) {
    setError("");
    try {
      await api(`/planos/salarios/${anio}`, { method: "PUT", json: { valor: Number(valor.replace(/\D/g, "")) } });
      setNuevoSalario({ anio: String(Number(anio) + 1), valor: "" });
      cargar();
    } catch (e) {
      setError(mensajeError(e));
    }
  }

  return (
    <>
      <Titulo>Catálogos y salario mínimo</Titulo>
      <Pestanas opciones={PESTANAS} valor={pestana} onChange={(v) => { setPestana(v); setEdicion(null); setQ(""); }} />
      {error && <div className="mb-4"><Alerta>{error}</Alerta></div>}

      {pestana === "SALARIO" ? (
        <div className="tarjeta max-w-xl p-5">
          <p className="mb-4 text-sm text-slate-500">
            Se usa en el plano de contratos: salario de los vigilantes, salarios menores al mínimo y el indicador de auxilio de transporte
            (hasta 2 salarios mínimos). Se toma el del año en curso.
          </p>
          <table className="tabla mb-4">
            <thead><tr><th>Año</th><th>Salario mínimo</th><th>2 salarios mínimos</th></tr></thead>
            <tbody>
              {salarios.map((s) => <tr key={s.anio}><td>{s.anio}</td><td>{peso(s.valor)}</td><td className="text-slate-500">{peso(s.valor * 2)}</td></tr>)}
            </tbody>
          </table>
          {configurar && (
            <div className="flex items-end gap-2">
              <div className="w-24"><label className="label">Año</label><input className="input" value={nuevoSalario.anio} onChange={(e) => setNuevoSalario({ ...nuevoSalario, anio: e.target.value.replace(/\D/g, "") })} /></div>
              <div className="flex-1"><label className="label">Valor</label><input className="input" inputMode="numeric" value={nuevoSalario.valor} onChange={(e) => setNuevoSalario({ ...nuevoSalario, valor: e.target.value })} /></div>
              <button className="btn-primario" disabled={!nuevoSalario.anio || !nuevoSalario.valor} onClick={() => guardarSalario(nuevoSalario.anio, nuevoSalario.valor)}>Guardar</button>
            </div>
          )}
        </div>
      ) : (
        <div className="tarjeta overflow-hidden">
          <div className="flex flex-wrap items-center gap-3 border-b border-slate-100 p-4">
            <div className="relative w-72">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-slate-400" />
              <input className="input pl-8" placeholder="Código o nombre" value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
            <span className="text-sm text-slate-500">{visibles.length} registros</span>
            {configurar && !edicion && (
              <button className="btn-primario ml-auto" onClick={() => { setEdicion({ catalogo: pestana, codigo: "", descripcion: "", observacion: "" }); setExistente(false); }}>
                <Plus className="h-4 w-4" /> Agregar
              </button>
            )}
          </div>
          {edicion && (
            <div className="grid gap-3 border-b border-slate-100 bg-slate-50 p-4 sm:grid-cols-4">
              <div><label className="label">Código</label><input className="input" disabled={existente} value={edicion.codigo} onChange={(e) => setEdicion({ ...edicion, codigo: e.target.value })} /></div>
              <div className="sm:col-span-2"><label className="label">Descripción</label><input className="input" value={edicion.descripcion} onChange={(e) => setEdicion({ ...edicion, descripcion: e.target.value })} /></div>
              <div><label className="label">Observación</label><input className="input" value={edicion.observacion} onChange={(e) => setEdicion({ ...edicion, observacion: e.target.value })} /></div>
              <div className="flex justify-end gap-2 sm:col-span-4">
                <button className="btn-secundario" onClick={() => setEdicion(null)}>Cancelar</button>
                <button className="btn-primario" disabled={!edicion.codigo.trim() || edicion.descripcion.trim().length < 2} onClick={guardar}>Guardar</button>
              </div>
            </div>
          )}
          <div className="overflow-x-auto">
            <table className="tabla">
              <thead><tr><th>Código</th><th>Descripción</th><th>Observación</th>{configurar && <th />}</tr></thead>
              <tbody>
                {visibles.map((e) => (
                  <tr key={e.codigo}>
                    <td className="font-mono text-xs">{e.codigo}</td>
                    <td>{e.descripcion}</td>
                    <td className="text-slate-500">{e.observacion}</td>
                    {configurar && (
                      <td className="whitespace-nowrap text-right">
                        <button title="Editar" className="mr-3" onClick={() => { setEdicion(e); setExistente(true); }}><Pencil className="h-4 w-4 text-slate-400 hover:text-marca-700" /></button>
                        <button title="Eliminar" onClick={() => eliminar(e)}><Trash2 className="h-4 w-4 text-slate-400 hover:text-red-600" /></button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}
