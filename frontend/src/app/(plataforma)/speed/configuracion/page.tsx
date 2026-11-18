"use client";

import { Save } from "lucide-react";
import { useEffect, useState } from "react";
import { InputPesos } from "@/components/input-pesos";
import { Alerta, Titulo } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";
import { usePermiso } from "@/lib/sesion";

type Parametro = { clave: string; valor: number; nombre: string; ayuda: string };
type ConceptoWO = { codigo: string; concepto: string; incluir: boolean; descripcion: string };
const EN_PESOS = new Set(["salario_minimo", "auxilio_transporte", "valor_tad", "valor_tan"]);

export default function ParametrosSpeed() {
  const puede = usePermiso("speed.configurar");
  const [lista, setLista] = useState<Parametro[] | null>(null);
  const [valores, setValores] = useState<Record<string, number>>({});
  const [msg, setMsg] = useState<{ tipo: "ok" | "error"; texto: string } | null>(null);
  useEffect(() => {
    api<Parametro[]>("/speed/parametros").then((l) => { setLista(l); setValores(Object.fromEntries(l.map((p) => [p.clave, p.valor]))); })
      .catch((e) => setMsg({ tipo: "error", texto: mensajeError(e) }));
  }, []);
  if (!lista) return msg ? <Alerta>{msg.texto}</Alerta> : <p className="text-sm text-slate-500">Cargando…</p>;
  const cambios = lista.some((p) => valores[p.clave] !== p.valor);
  return (
    <div className="max-w-3xl space-y-4">
      <Titulo accion={puede && <button className="btn-primario" disabled={!cambios} onClick={async () => {
        setMsg(null);
        try {
          await api("/speed/parametros", { method: "PUT", json: valores });
          setLista(lista.map((p) => ({ ...p, valor: valores[p.clave] })));
          setMsg({ tipo: "ok", texto: "Parámetros guardados: se usan en las próximas liquidaciones (las quincenas cerradas no cambian)." });
        } catch (e) { setMsg({ tipo: "error", texto: mensajeError(e) }); }
      }}><Save className="h-4 w-4" /> Guardar</button>}>Parámetros</Titulo>
      {msg && <Alerta tipo={msg.tipo}>{msg.texto}</Alerta>}
      <div className="tarjeta grid gap-4 p-5 sm:grid-cols-2">
        {lista.map((p) => (
          <div key={p.clave}>
            <label className="label">{p.nombre}</label>
            {EN_PESOS.has(p.clave)
              ? <InputPesos disabled={!puede} valor={valores[p.clave]} onValor={(v) => setValores({ ...valores, [p.clave]: v ?? 0 })} />
              : <input className="input" type="number" step="any" disabled={!puede} value={valores[p.clave] ?? ""} onChange={(e) => setValores({ ...valores, [p.clave]: Number(e.target.value) })} />}
            {p.ayuda && <p className="mt-0.5 text-xs text-slate-500">{p.ayuda}</p>}
          </div>
        ))}
      </div>
      <ConceptosWO puede={puede} />
    </div>
  );
}

/** Con qué concepto de World Office va cada código de la programación en el archivo plano de novedades. */
function ConceptosWO({ puede }: { puede: boolean }) {
  const [lista, setLista] = useState<ConceptoWO[] | null>(null);
  const [editados, setEditados] = useState<Record<string, ConceptoWO>>({});
  const [msg, setMsg] = useState<{ tipo: "ok" | "error"; texto: string } | null>(null);
  useEffect(() => { api<ConceptoWO[]>("/speed/conceptos-wo").then(setLista).catch((e) => setMsg({ tipo: "error", texto: mensajeError(e) })); }, []);
  if (!lista) return null;
  const filas = lista.map((c) => editados[c.codigo] ?? c);
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3">
        <h2 className="text-lg font-semibold text-marca-900">Conceptos del plano de World Office</h2>
        {puede && <button className="btn-primario ml-auto" disabled={!Object.keys(editados).length} onClick={async () => {
          setMsg(null);
          try {
            await api("/speed/conceptos-wo", { method: "PUT", json: filas.map(({ codigo, concepto, incluir }) => ({ codigo, concepto, incluir })) });
            setLista(filas);
            setEditados({});
            setMsg({ tipo: "ok", texto: "Conceptos guardados." });
          } catch (e) { setMsg({ tipo: "error", texto: mensajeError(e) }); }
        }}><Save className="h-4 w-4" /> Guardar conceptos</button>}
      </div>
      <p className="text-sm text-slate-600">Cada novedad de la programación va en el plano con el nombre del concepto tal como está en World Office.
        Desmarque las que no deben ir (por ejemplo, si las vacaciones se liquidan directamente en World Office).</p>
      {msg && <Alerta tipo={msg.tipo}>{msg.texto}</Alerta>}
      <div className="tarjeta overflow-x-auto">
        <table className="tabla">
          <thead><tr><th>Código</th><th>Qué es</th><th>Concepto en World Office</th><th>Va en el plano</th></tr></thead>
          <tbody>
            {filas.map((c) => (
              <tr key={c.codigo}>
                <td className="font-mono text-sm">{c.codigo}</td>
                <td className="text-sm text-slate-600">{c.descripcion}</td>
                <td><input className="input w-80" disabled={!puede} maxLength={120} value={c.concepto}
                  onChange={(e) => setEditados({ ...editados, [c.codigo]: { ...c, concepto: e.target.value } })} /></td>
                <td><input type="checkbox" disabled={!puede} checked={c.incluir}
                  onChange={(e) => setEditados({ ...editados, [c.codigo]: { ...c, incluir: e.target.checked } })} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
