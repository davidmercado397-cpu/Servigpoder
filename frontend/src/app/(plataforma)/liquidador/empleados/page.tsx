"use client";

import { ChevronRight, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Paginador, metaDe, usePaginacion, type MetaPagina } from "@/components/paginacion";
import { Alerta, Titulo } from "@/components/ui";
import { apiEnvelope, mensajeError } from "@/lib/api";
import { pesos } from "@/lib/formato";
import { CLASES_ARL, DIAS_SEMANA, type Empleado } from "@/lib/liquidador";
import { usePermiso } from "@/lib/sesion";

const habilesTexto = (d: number[]) => {
  const s = [...d].sort();
  const seguidos = s.length > 2 && s.every((x, i) => i === 0 || x === s[i - 1] + 1);
  return seguidos ? `${DIAS_SEMANA[s[0]]} a ${DIAS_SEMANA[s[s.length - 1]].toLowerCase()}` : s.map((x) => DIAS_SEMANA[x].slice(0, 3)).join(", ");
};

export default function Empleados() {
  const verNomina = usePermiso("liquidador.nomina.ver");
  const router = useRouter();
  const [lista, setLista] = useState<Empleado[]>([]);
  const [meta, setMeta] = useState<MetaPagina | null>(null);
  const [q, setQ] = useState("");
  const [error, setError] = useState("");
  const pag = usePaginacion([q]);

  const cargar = useCallback(async () => {
    const r = await apiEnvelope<Empleado[]>(`/liquidador/empleados?q=${encodeURIComponent(q)}&${pag.query}`);
    setLista(r.data ?? []);
    setMeta(metaDe(r));
  }, [q, pag.query]);

  useEffect(() => {
    const t = setTimeout(() => cargar().catch((e) => setError(mensajeError(e))), 250);
    return () => clearTimeout(t);
  }, [cargar]);

  return (
    <div className="space-y-5">
      <Titulo>Empleados</Titulo>
      <p className="-mt-4 text-sm text-slate-500">
        Se crean y actualizan solos al cargar el Excel de cada nómina. Haga clic en una persona para abrir su ficha: salario, ARL, vacaciones,
        préstamos, embargos, auxilios y las nóminas en que aparece.
      </p>
      {error && <Alerta>{error}</Alerta>}
      <div className="tarjeta overflow-hidden">
        <div className="px-4 py-3">
          <div className="relative w-72">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input className="input pl-8" placeholder="Buscar por cédula o nombre…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
        </div>
        <div className="overflow-auto">
          <table className="tabla">
            <thead>
              <tr><th>Documento</th><th>Nombre</th><th>Cargo</th><th>Último periodo</th><th className="text-right">Nóminas</th>
                {verNomina && <th>Salario mensual</th>}<th>ARL</th><th>Vacaciones</th><th /></tr>
            </thead>
            <tbody>
              {lista.map((e) => (
                <tr key={e.id} className="cursor-pointer hover:bg-marca-50" onClick={() => router.push(`/liquidador/empleados/${e.id}`)}>
                  <td className="font-mono">{e.documento}</td>
                  <td>{e.nombre}</td>
                  <td>{e.cargo}</td>
                  <td>{e.ultima ?? "—"}</td>
                  <td className="text-right tabular-nums">{e.quincenas}</td>
                  {verNomina && (
                    <td className="whitespace-nowrap">
                      {e.salario ? <span className="tabular-nums">{pesos(e.salario)}</span> : <span className="text-slate-500">Salario mínimo</span>}
                    </td>
                  )}
                  <td className="whitespace-nowrap text-sm">
                    {e.arl_clase ? `Clase ${CLASES_ARL.find(([n]) => n === e.arl_clase)?.[1]}` : <span className="text-slate-500">Sin definir</span>}
                  </td>
                  <td className="whitespace-nowrap text-sm">
                    <span className="block text-xs text-slate-500">Hábiles: {habilesTexto(e.dias_habiles)}</span>
                    {e.saldo_vacaciones ? (
                      <span className={`tabular-nums ${e.saldo_vacaciones.pendientes < 0 ? "font-semibold text-red-700" : ""}`}>
                        {e.saldo_vacaciones.pendientes.toLocaleString("es-CO")} días pendientes
                      </span>
                    ) : <span className="text-slate-500">Sin fecha de ingreso</span>}
                  </td>
                  <td className="text-right text-slate-400"><ChevronRight className="inline h-4 w-4" aria-label="Abrir ficha" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Paginador meta={meta} onPagina={pag.setPagina} onTamano={pag.setTamano} />
      </div>
    </div>
  );
}
