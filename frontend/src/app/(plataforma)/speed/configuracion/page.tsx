"use client";

import { Save } from "lucide-react";
import { useEffect, useState } from "react";
import { InputPesos } from "@/components/input-pesos";
import { Alerta, Titulo } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";
import { usePermiso } from "@/lib/sesion";

type Parametro = { clave: string; valor: number; nombre: string; ayuda: string };
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
    </div>
  );
}
