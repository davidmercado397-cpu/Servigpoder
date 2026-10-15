"use client";

import { useEffect, useState } from "react";
import { Alerta } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";

export type SugerenciaAlias = { catalogo: string; pais: string; departamento: string; texto: string; codigo: string };
type Opcion = { codigo: string; nombre: string };
type Depto = Opcion & { pais: string };
type Entidad = { catalogo: string; codigo: string; descripcion: string };

export const CATALOGOS_ALIAS: [string, string][] = [
  ["CIUDAD", "Ciudad"], ["DEPARTAMENTO", "Departamento"], ["BANCOS", "Banco"], ["AFP", "Fondo de pensiones"],
  ["EPS", "EPS"], ["CESANTIAS", "Cesantías"], ["CAJAS", "Caja de compensación"], ["CARGOS", "Cargo"],
];

const VACIO: SugerenciaAlias = { catalogo: "CIUDAD", pais: "169", departamento: "", texto: "", codigo: "" };

/** Crea un alias: el texto que llega en el plano se convierte siempre a este código. */
export function FormularioAlias({ inicial, onGuardado, onCancelar }: {
  inicial?: SugerenciaAlias | null; onGuardado: () => void; onCancelar?: () => void;
}) {
  const [f, setF] = useState<SugerenciaAlias>({ ...VACIO, ...(inicial ?? {}), pais: inicial?.pais || "169" });
  const [paises, setPaises] = useState<Opcion[]>([]);
  const [deptos, setDeptos] = useState<Depto[]>([]);
  const [ciudades, setCiudades] = useState<Opcion[]>([]);
  const [entidades, setEntidades] = useState<Entidad[]>([]);
  const [error, setError] = useState("");
  const [guardando, setGuardando] = useState(false);
  const dane = f.catalogo === "CIUDAD" || f.catalogo === "DEPARTAMENTO";

  useEffect(() => {
    api<{ paises: Opcion[]; departamentos: Depto[] }>("/planos/dane").then((d) => {
      setPaises(d.paises);
      setDeptos(d.departamentos);
    }).catch((e) => setError(mensajeError(e)));
  }, []);
  useEffect(() => {
    if (f.catalogo !== "CIUDAD" || !f.departamento) return setCiudades([]);
    api<Opcion[]>(`/planos/dane/ciudades?pais=${f.pais}&departamento=${f.departamento}`).then(setCiudades).catch((e) => setError(mensajeError(e)));
  }, [f.catalogo, f.pais, f.departamento]);
  useEffect(() => {
    if (dane) return;
    api<Entidad[]>(`/planos/entidades?catalogo=${f.catalogo}`).then(setEntidades).catch((e) => setError(mensajeError(e)));
  }, [f.catalogo, dane]);

  const cambiar = (c: Partial<SugerenciaAlias>) => setF((a) => ({ ...a, ...c }));
  const deptosPais = deptos.filter((d) => d.pais === f.pais);

  async function guardar() {
    setError("");
    setGuardando(true);
    try {
      await api("/planos/alias", { method: "POST", json: f });
      onGuardado();
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className="label">Tipo</label>
          <select className="input" value={f.catalogo} onChange={(e) => cambiar({ catalogo: e.target.value, codigo: "" })}>
            {CATALOGOS_ALIAS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
          </select>
        </div>
        <div>
          <label className="label">Texto que llega en el plano</label>
          <input className="input" value={f.texto} onChange={(e) => cambiar({ texto: e.target.value })} placeholder="Ej. EL BORDO" />
        </div>
        {dane && (
          <div>
            <label className="label">País</label>
            <select className="input" value={f.pais} onChange={(e) => cambiar({ pais: e.target.value, departamento: "", codigo: "" })}>
              {paises.map((p) => <option key={p.codigo} value={p.codigo}>{p.nombre}</option>)}
            </select>
          </div>
        )}
        {f.catalogo === "CIUDAD" && (
          <div>
            <label className="label">Departamento</label>
            <select className="input" value={f.departamento} onChange={(e) => cambiar({ departamento: e.target.value, codigo: "" })}>
              <option value="">Seleccione…</option>
              {deptosPais.map((d) => <option key={d.codigo} value={d.codigo}>{d.nombre} ({d.codigo})</option>)}
            </select>
          </div>
        )}
        <div className="sm:col-span-2">
          <label className="label">Se convierte en</label>
          <select className="input" value={f.codigo} onChange={(e) => cambiar({ codigo: e.target.value })}
            disabled={f.catalogo === "CIUDAD" && !f.departamento}>
            <option value="">Seleccione…</option>
            {f.catalogo === "DEPARTAMENTO" && deptosPais.map((d) => <option key={d.codigo} value={d.codigo}>{d.codigo} · {d.nombre}</option>)}
            {f.catalogo === "CIUDAD" && ciudades.map((c) => <option key={c.codigo} value={c.codigo}>{c.codigo} · {c.nombre}</option>)}
            {!dane && entidades.map((e) => <option key={e.codigo} value={e.codigo}>{e.codigo} · {e.descripcion}</option>)}
          </select>
        </div>
      </div>
      {error && <Alerta>{error}</Alerta>}
      <div className="flex justify-end gap-2">
        {onCancelar && <button className="btn-secundario" onClick={onCancelar}>Cancelar</button>}
        <button className="btn-primario" disabled={guardando || !f.texto.trim() || !f.codigo} onClick={guardar}>
          {guardando ? "Guardando…" : "Guardar alias"}
        </button>
      </div>
    </div>
  );
}
