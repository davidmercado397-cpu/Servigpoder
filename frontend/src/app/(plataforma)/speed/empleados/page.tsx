"use client";

import { UserMinus, UserPlus } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Paginador, usePaginacion } from "@/components/paginacion";
import { RetirarEmpleado } from "@/components/speed-retiro";
import { Alerta, SubirArchivo, Titulo } from "@/components/ui";
import { api, mensajeError, subirArchivo } from "@/lib/api";
import { usePermiso } from "@/lib/sesion";
import { pesos, type EmpleadoSpeed } from "@/lib/speed";

const TAMANOS_EMPLEADOS = [20, 50, 100] as const;

type Importacion = { filas: number; nuevos: number; actualizados: number; sin_cambios: number; reactivados: number;
  inactivados: { cedula: string; nombre: string }[]; retirados_en_archivo?: { cedula: string; nombre: string; fecha_retiro: string }[]; cambios: { cedula: string; nombre: string; campo: string; antes: unknown; ahora: unknown }[]; advertencias: string[] };
const CAMPO: Record<string, string> = { salario: "Salario", horas_extras: "Horas extras", ley_2466: "Ley 2466", bonificaciones: "Bonificaciones",
  rodamiento: "Rodamiento", aplica_programacion: "Regla de programación" };

export default function EmpleadosSpeed() {
  const liquidar = usePermiso("speed.liquidar");
  const [lista, setLista] = useState<EmpleadoSpeed[] | null>(null);
  const [inactivos, setInactivos] = useState(false);
  const [buscar, setBuscar] = useState("");
  const [regla, setRegla] = useState("");
  const [res, setRes] = useState<Importacion | null>(null);
  const [retirar, setRetirar] = useState<EmpleadoSpeed | null>(null);
  const [error, setError] = useState("");
  const cargar = useCallback(() => api<EmpleadoSpeed[]>(`/speed/empleados?inactivos=${inactivos}`).then(setLista).catch((e) => setError(mensajeError(e))), [inactivos]);
  useEffect(() => { cargar(); }, [cargar]);

  const visibles = useMemo(() => (lista ?? []).filter((e) => (!regla || String(e.aplica_programacion) === regla)
    && (!buscar || `${e.cedula} ${e.nombre} ${e.cargo} ${e.puesto} ${e.tipo_turno}`.toLowerCase().includes(buscar.toLowerCase()))), [lista, buscar, regla]);
  // Paginación en pantalla (20, 50 o 100 por página); vuelve a la primera al cambiar los filtros
  const pag = usePaginacion([buscar, regla, inactivos], TAMANOS_EMPLEADOS);
  const paginas = Math.max(1, Math.ceil(visibles.length / pag.tamano));
  const pagina = Math.min(pag.pagina, paginas);
  const enPagina = visibles.slice((pagina - 1) * pag.tamano, pagina * pag.tamano);

  return (
    <div className="space-y-4">
      <Titulo accion={liquidar && <SubirArchivo texto="Importar Listado (Excel)" onArchivo={async (f) => {
        setError(""); setRes(null);
        try { setRes(await subirArchivo<Importacion>("/speed/empleados/importar", f)); await cargar(); } catch (e) { setError(mensajeError(e)); }
      }} />}>Empleados</Titulo>
      <p className="text-sm text-slate-600">Se importan desde el Excel de colaboradores (hoja <b>LISTADO</b>). Cada vez que cambien los valores, vuelva a importarlo:
        se actualiza por cédula y quien ya no viene queda inactivo. El archivo se lee y se descarta; la dirección y el teléfono no se guardan.</p>
      {error && <Alerta>{error}</Alerta>}
      {res && (
        <Alerta tipo="ok">
          <p>{res.filas} colaboradores leídos: {res.nuevos} nuevos, {res.actualizados} actualizados, {res.sin_cambios} sin cambios
            {res.reactivados ? `, ${res.reactivados} reactivados` : ""}{res.inactivados.length ? `, ${res.inactivados.length} quedaron inactivos (no vienen en el archivo)` : ""}.</p>
          {res.cambios.length > 0 && <details className="mt-1"><summary className="cursor-pointer">Ver {res.cambios.length} valores que cambiaron</summary>
            <ul className="mt-1 text-xs">{res.cambios.map((c, i) => <li key={i}>{c.nombre} ({c.cedula}) · {CAMPO[c.campo] ?? c.campo}: {formato(c.antes)} → {formato(c.ahora)}</li>)}</ul></details>}
          {res.inactivados.length > 0 && <details className="mt-1"><summary className="cursor-pointer">Ver inactivos</summary>
            <ul className="mt-1 text-xs">{res.inactivados.map((x) => <li key={x.cedula}>{x.nombre} ({x.cedula})</li>)}</ul></details>}
          {(res.retirados_en_archivo?.length ?? 0) > 0 && <p className="mt-1 text-xs text-amber-800">
            {res.retirados_en_archivo!.length} siguen en el Excel pero están retirados en la plataforma (no se reactivaron):{" "}
            {res.retirados_en_archivo!.map((x) => `${x.nombre} (${x.cedula})`).join(", ")}</p>}
          {res.advertencias.length > 0 && <ul className="mt-1 text-xs text-amber-800">{res.advertencias.map((a, i) => <li key={i}>• {a}</li>)}</ul>}
        </Alerta>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <input className="input w-80" placeholder="Buscar por cédula, nombre, cargo, puesto o turno" value={buscar} onChange={(e) => setBuscar(e.target.value)} />
        <select className="input w-56" value={regla} onChange={(e) => setRegla(e.target.value)}>
          <option value="">Regla de programación: todos</option><option value="true">Aplica</option><option value="false">No aplica</option></select>
        <label className="flex items-center gap-2 text-sm text-slate-600"><input type="checkbox" checked={inactivos} onChange={(e) => setInactivos(e.target.checked)} /> Ver inactivos</label>
        <span className="ml-auto text-sm text-slate-500">{visibles.length} colaboradores</span>
      </div>
      <div className="tarjeta overflow-x-auto">
        <table className="tabla">
          <thead><tr><th>Colaborador</th><th>Turno / puesto</th><th className="text-right">Salario</th><th className="text-right">Horas extras</th>
            <th className="text-right">Ley 2466</th><th className="text-right">Bonificaciones</th><th className="text-right">Rodamiento</th><th>Programación</th>{liquidar && <th />}</tr></thead>
          <tbody>
            {lista === null && <tr><td colSpan={9} className="py-6 text-center text-slate-400">Cargando…</td></tr>}
            {lista?.length === 0 && <tr><td colSpan={9} className="py-6 text-center text-slate-400">Aún no se ha importado el Listado.</td></tr>}
            {enPagina.map((e) => (
              <tr key={e.id} className={e.activo ? "" : "opacity-50"}>
                <td><p className="font-medium">{e.nombre}</p><p className="text-xs text-slate-500">{e.cedula} · {e.cargo} · ingreso {e.fecha_ingreso ?? "—"}
                  {e.fecha_retiro ? <span className="text-red-700"> · retirado el {e.fecha_retiro}{e.motivo_retiro ? ` (${e.motivo_retiro})` : ""}</span> : e.activo ? "" : " · inactivo"}</p></td>
                <td><p>{e.tipo_turno}</p><p className="text-xs text-slate-500">{e.puesto} · {e.cliente}</p></td>
                <td className="text-right tabular-nums">{pesos(e.salario)}</td>
                <td className="text-right tabular-nums">{pesos(e.horas_extras)}</td>
                <td className="text-right tabular-nums">{pesos(e.ley_2466)}</td>
                <td className="text-right tabular-nums">{pesos(e.bonificaciones)}{e.nota && <p className="max-w-[12rem] text-xs text-slate-500">{e.nota}</p>}</td>
                <td className="text-right tabular-nums">{pesos(e.rodamiento)}</td>
                <td>{liquidar ? (
                  <select className="input w-32" value={String(e.aplica_programacion)} onChange={async (ev) => {
                    try { await api(`/speed/empleados/${e.id}`, { method: "PATCH", json: { aplica_programacion: ev.target.value === "true" } }); await cargar(); }
                    catch (err) { setError(mensajeError(err)); }
                  }}><option value="true">Aplica</option><option value="false">No aplica</option></select>
                ) : e.aplica_programacion ? "Aplica" : "No aplica"}</td>
                {liquidar && <td>{e.fecha_retiro
                  ? <button className="inline-flex items-center gap-1 text-sm text-marca-700 hover:underline" onClick={async () => {
                    if (!confirm(`¿Reintegrar a ${e.nombre}? Vuelve a liquidarse en las quincenas.`)) return;
                    try { await api(`/speed/empleados/${e.id}/reintegrar`, { method: "POST" }); await cargar(); } catch (err) { setError(mensajeError(err)); }
                  }}><UserPlus className="h-4 w-4" /> Reintegrar</button>
                  : <button className="inline-flex items-center gap-1 text-sm text-red-700 hover:underline" onClick={() => setRetirar(e)}>
                    <UserMinus className="h-4 w-4" /> Retirar</button>}</td>}
              </tr>
            ))}
          </tbody>
        </table>
        <Paginador meta={lista ? { total: visibles.length, pagina, tamano: pag.tamano, paginas } : null} tamanos={TAMANOS_EMPLEADOS}
          onPagina={pag.setPagina} onTamano={pag.setTamano} />
      </div>
      {retirar && <RetirarEmpleado empleadoId={retirar.id} nombre={retirar.nombre} onCerrar={() => setRetirar(null)}
        onListo={async () => { setRetirar(null); await cargar(); }} />}
    </div>
  );
}

function formato(v: unknown) {
  if (typeof v === "boolean") return v ? "aplica" : "no aplica";
  if (typeof v === "number") return pesos(v);
  return String(v ?? "—");
}

