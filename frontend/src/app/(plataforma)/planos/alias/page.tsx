"use client";

import { Plus, Search, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { CATALOGOS_ALIAS, FormularioAlias } from "@/components/formulario-alias";
import { Alerta, Titulo } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";
import { usePermiso } from "@/lib/sesion";

type Alias = { id: number; catalogo: string; texto: string; codigo: string; pais: string; departamento: string; nota: string; destino: string };
const NOMBRE = Object.fromEntries(CATALOGOS_ALIAS);

export default function AliasPlanos() {
  const configurar = usePermiso("planos.configurar");
  const [lista, setLista] = useState<Alias[] | null>(null);
  const [catalogo, setCatalogo] = useState("");
  const [q, setQ] = useState("");
  const [nuevo, setNuevo] = useState(false);
  const [error, setError] = useState("");

  const cargar = useCallback(() => api<Alias[]>("/planos/alias").then(setLista).catch((e) => setError(mensajeError(e))), []);
  useEffect(() => {
    cargar();
  }, [cargar]);

  const visibles = useMemo(() => {
    const t = q.trim().toUpperCase();
    return (lista ?? []).filter((a) => (!catalogo || a.catalogo === catalogo) && (!t || a.texto.includes(t) || a.destino.toUpperCase().includes(t)));
  }, [lista, catalogo, q]);

  async function eliminar(a: Alias) {
    if (!window.confirm(`¿Eliminar el alias «${a.texto}»?`)) return;
    try {
      await api(`/planos/alias/${a.id}`, { method: "DELETE" });
      cargar();
    } catch (e) {
      setError(mensajeError(e));
    }
  }

  return (
    <>
      <Titulo accion={configurar && !nuevo && <button className="btn-primario" onClick={() => setNuevo(true)}><Plus className="h-4 w-4" /> Nuevo alias</button>}>
        Alias
      </Titulo>
      <p className="-mt-4 mb-5 text-sm text-slate-500">
        Un alias convierte siempre un texto en un código: abreviaturas (VALLE), errores frecuentes (COMANDI) o nombres que el catálogo
        escribe distinto. Se comparan sin tildes ni mayúsculas. Una ciudad solo aplica dentro de su departamento.
      </p>
      {error && <div className="mb-4"><Alerta>{error}</Alerta></div>}
      {nuevo && (
        <div className="tarjeta mb-5 p-5">
          <FormularioAlias onCancelar={() => setNuevo(false)} onGuardado={() => { setNuevo(false); cargar(); }} />
        </div>
      )}
      <div className="tarjeta overflow-hidden">
        <div className="flex flex-wrap items-center gap-3 border-b border-slate-100 p-4">
          <select className="input w-56" value={catalogo} onChange={(e) => setCatalogo(e.target.value)}>
            <option value="">Todos los tipos</option>
            {CATALOGOS_ALIAS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
          </select>
          <div className="relative w-72">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-slate-400" />
            <input className="input pl-8" placeholder="Buscar" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <span className="ml-auto text-sm text-slate-500">{visibles.length} alias</span>
        </div>
        <div className="overflow-x-auto">
          <table className="tabla">
            <thead><tr><th>Tipo</th><th>Texto</th><th>Código</th><th>Corresponde a</th><th>Nota</th>{configurar && <th />}</tr></thead>
            <tbody>
              {visibles.map((a) => (
                <tr key={a.id}>
                  <td className="text-slate-500">{NOMBRE[a.catalogo] ?? a.catalogo}</td>
                  <td className="font-medium">{a.texto}</td>
                  <td className="font-mono text-xs">{a.catalogo === "CIUDAD" ? `${a.departamento}-${a.codigo}` : a.codigo}</td>
                  <td>{a.destino}</td>
                  <td className="text-slate-500">{a.nota}</td>
                  {configurar && (
                    <td className="text-right">
                      <button title="Eliminar" onClick={() => eliminar(a)}><Trash2 className="h-4 w-4 text-slate-400 hover:text-red-600" /></button>
                    </td>
                  )}
                </tr>
              ))}
              {lista && !visibles.length && <tr><td colSpan={6} className="py-8 text-center text-slate-400">Sin alias</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
