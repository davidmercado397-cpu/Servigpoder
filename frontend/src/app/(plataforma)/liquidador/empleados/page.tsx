"use client";

import { ChevronRight, FileDown, FileUp, Search, UserMinus, UserPlus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ImportarPersonal } from "@/components/importar-personal";
import { NuevoEmpleado } from "@/components/nuevo-empleado";
import { RetirarEmpleado } from "@/components/retirar-empleado";
import { Paginador, metaDe, usePaginacion, type MetaPagina } from "@/components/paginacion";
import { Alerta, Insignia, Modal, Titulo } from "@/components/ui";
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
  const gestionarPersonal = usePermiso("liquidador.personal.gestionar");
  const verPersonal = usePermiso("liquidador.personal.ver");
  const router = useRouter();
  const [estado, setEstado] = useState("activo");
  const [tipo, setTipo] = useState("todos");
  const [importar, setImportar] = useState(false);
  const [nuevo, setNuevo] = useState(false);
  const [retirar, setRetirar] = useState<Empleado | null>(null);
  const [lista, setLista] = useState<Empleado[]>([]);
  const [meta, setMeta] = useState<MetaPagina | null>(null);
  const [q, setQ] = useState("");
  const [error, setError] = useState("");
  const pag = usePaginacion([q, estado, tipo]);

  const cargar = useCallback(async () => {
    const r = await apiEnvelope<Empleado[]>(`/liquidador/empleados?q=${encodeURIComponent(q)}&estado=${estado}&tipo=${tipo}&${pag.query}`);
    setLista(r.data ?? []);
    setMeta(metaDe(r));
  }, [q, estado, tipo, pag.query]);

  useEffect(() => {
    const t = setTimeout(() => cargar().catch((e) => setError(mensajeError(e))), 250);
    return () => clearTimeout(t);
  }, [cargar]);

  return (
    <div className="space-y-5">
      <Titulo accion={(verPersonal || gestionarPersonal) && (
        <div className="flex flex-wrap gap-2">
          {verPersonal && (
            <a className="btn-secundario inline-flex items-center gap-1.5" href="/api/liquidador/personal/exportar-base"
              title="Todos los empleados con su ficha, en el mismo formato de la base de personal (se puede corregir y volver a importar)">
              <FileDown className="h-4 w-4" /> Exportar base de personal
            </a>
          )}
          {gestionarPersonal && (
          <button className="btn-secundario inline-flex items-center gap-1.5" onClick={() => setImportar(!importar)}>
            <FileUp className="h-4 w-4" /> Importar base de personal o libro de vacaciones
          </button>
          )}
          {gestionarPersonal && !nuevo && (
            <button className="btn-primario inline-flex items-center gap-1.5" onClick={() => setNuevo(true)}>
              <UserPlus className="h-4 w-4" /> Nuevo empleado
            </button>
          )}
        </div>
      )}>Empleados</Titulo>
      <p className="-mt-4 text-sm text-slate-500">
        Haga clic en una persona para abrir su ficha: datos personales, contratos, salario, ARL, vacaciones, préstamos, embargos, cuotas, auxilios y las
        nóminas en que aparece. También se crean al cargar el Excel de una nómina o al importar la base de personal.
      </p>
      {error && <Alerta>{error}</Alerta>}
      {nuevo && <Modal onCerrar={() => setNuevo(false)}><NuevoEmpleado onCancelar={() => setNuevo(false)} onCreado={(id) => router.push(`/liquidador/empleados/${id}`)} /></Modal>}
      {retirar && (
        <Modal onCerrar={() => setRetirar(null)}>
          <RetirarEmpleado empleado={retirar} onCancelar={() => setRetirar(null)} onRetirado={() => { setRetirar(null); cargar().catch(() => {}); }} />
        </Modal>
      )}
      {importar && <ImportarPersonal onImportado={() => cargar().catch(() => {})} />}
      <div className="tarjeta overflow-hidden">
        <div className="px-4 py-3">
          <div className="relative w-72">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input className="input pl-8" placeholder="Buscar por cédula o nombre…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
        </div>
        <div className="-mt-1 flex flex-wrap gap-2 px-4 pb-3">
          <select className="input w-40" value={estado} onChange={(e) => setEstado(e.target.value)} aria-label="Estado">
            <option value="activo">Activos</option>
            <option value="retirado">Retirados</option>
            <option value="todos">Todos</option>
          </select>
          <select className="input w-48" value={tipo} onChange={(e) => setTipo(e.target.value)} aria-label="Tipo de personal">
            <option value="todos">Operativos y administrativos</option>
            <option value="operativo">Operativos</option>
            <option value="administrativo">Administrativos</option>
          </select>
          {meta && <span className="self-center text-sm text-slate-500">{meta.total.toLocaleString("es-CO")} personas</span>}
        </div>
        <div className="overflow-auto">
          <table className="tabla">
            <thead>
              <tr><th>Documento</th><th>Nombre</th><th>Cargo</th><th>Puesto</th><th>Último periodo</th><th className="text-right">Nóminas</th>
                {verNomina && <th>Salario mensual</th>}<th>ARL</th><th>Vacaciones</th><th /></tr>
            </thead>
            <tbody>
              {lista.map((e) => (
                <tr key={e.id} className="cursor-pointer hover:bg-marca-50" onClick={() => router.push(`/liquidador/empleados/${e.id}`)}>
                  <td className="font-mono">{e.documento}</td>
                  <td>
                    {e.nombre}
                    {e.estado === "retirado" && <Insignia color="ml-2 bg-rose-100 text-rose-800">Retirado</Insignia>}
                  </td>
                  <td>{e.cargo}</td>
                  <td className="max-w-[200px] truncate text-sm" title={e.puesto ?? ""}>{e.puesto ?? "—"}</td>
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
                  <td className="whitespace-nowrap text-right text-slate-400">
                    {gestionarPersonal && e.estado !== "retirado" && (
                      <button className="mr-2 inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-rose-700 hover:bg-rose-50"
                        title="Marcar el retiro: fecha y motivo" onClick={(ev) => { ev.stopPropagation(); setRetirar(e); }}>
                        <UserMinus className="h-3.5 w-3.5" /> Retirar
                      </button>
                    )}
                    <ChevronRight className="inline h-4 w-4" aria-label="Abrir ficha" />
                  </td>
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
