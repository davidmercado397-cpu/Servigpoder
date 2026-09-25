"use client";

import { useEffect, useState } from "react";
import { Alerta, Titulo } from "@/components/ui";
import { api, mensajeError, type Parametro } from "@/lib/api";
import { usePermiso } from "@/lib/sesion";

const NOMBRES: Record<string, string> = {
  umbral_cobertura: "Cobertura mínima (%)",
  dias_alerta_hueco: "Días a futuro para alertar huecos",
  dias_aviso_proyeccion: "Días antes de fin de mes para avisar la proyección",
  horas_programacion_vieja: "Horas sin carga nueva antes de avisar",
};

export default function ParametrosPage() {
  const puedeEditar = usePermiso("parametros.gestionar");
  const [lista, setLista] = useState<Parametro[]>([]);
  const [valores, setValores] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<{ tipo: "ok" | "error"; texto: string } | null>(null);

  useEffect(() => {
    api<Parametro[]>("/parametros").then((l) => {
      setLista(l);
      setValores(Object.fromEntries(l.map((p) => [p.clave, p.valor])));
    });
  }, []);

  async function guardar(clave: string) {
    setMsg(null);
    try {
      await api(`/parametros/${clave}`, { method: "PUT", json: { valor: valores[clave] } });
      setMsg({ tipo: "ok", texto: `${NOMBRES[clave] ?? clave} actualizado` });
    } catch (e) {
      setMsg({ tipo: "error", texto: mensajeError(e) });
    }
  }

  return (
    <div className="max-w-3xl space-y-4">
      <Titulo>Parámetros de alertas</Titulo>
      {msg && <Alerta tipo={msg.tipo}>{msg.texto}</Alerta>}
      <div className="tarjeta divide-y divide-slate-100">
        {lista.map((p) => (
          <div key={p.clave} className="flex flex-wrap items-center gap-3 p-4">
            <div className="min-w-64 flex-1">
              <p className="font-medium">{NOMBRES[p.clave] ?? p.clave}</p>
              <p className="text-xs text-slate-500">{p.descripcion}</p>
            </div>
            <input className="input w-24" inputMode="decimal" value={valores[p.clave] ?? ""} disabled={!puedeEditar}
              onChange={(e) => setValores({ ...valores, [p.clave]: e.target.value })} />
            {puedeEditar && <button className="btn-secundario" onClick={() => guardar(p.clave)}>Guardar</button>}
          </div>
        ))}
      </div>
    </div>
  );
}
