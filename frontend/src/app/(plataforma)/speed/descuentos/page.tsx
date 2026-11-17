"use client";

import { Plus, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { InputPesos } from "@/components/input-pesos";
import { Alerta, Insignia, Titulo } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";
import { usePermiso } from "@/lib/sesion";
import { TIPOS_DESCUENTO, pesos, type DescuentoSpeed, type EmpleadoSpeed } from "@/lib/speed";

const VACIO = { empleado_id: "", tipo: "prestamo" as DescuentoSpeed["tipo"], descripcion: "", valor_total: null as number | null, cuota: null as number | null, salarial: true };

export default function DescuentosSpeed() {
  const puede = usePermiso("speed.descuentos");
  const [lista, setLista] = useState<DescuentoSpeed[] | null>(null);
  const [empleados, setEmpleados] = useState<EmpleadoSpeed[]>([]);
  const [f, setF] = useState(VACIO);
  const [buscarEmp, setBuscarEmp] = useState("");
  const [msg, setMsg] = useState<{ tipo: "ok" | "error"; texto: string } | null>(null);
  const cargar = useCallback(() => api<DescuentoSpeed[]>("/speed/descuentos").then(setLista).catch((e) => setMsg({ tipo: "error", texto: mensajeError(e) })), []);
  useEffect(() => {
    cargar();
    api<EmpleadoSpeed[]>("/speed/empleados").then(setEmpleados).catch(() => {});
  }, [cargar]);
  const opciones = useMemo(() => empleados.filter((e) => !buscarEmp || `${e.cedula} ${e.nombre}`.toLowerCase().includes(buscarEmp.toLowerCase())).slice(0, 200),
    [empleados, buscarEmp]);

  async function crear(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    try {
      await api("/speed/descuentos", { method: "POST", json: { ...f, empleado_id: Number(f.empleado_id) } });
      setF(VACIO);
      setBuscarEmp("");
      await cargar();
      setMsg({ tipo: "ok", texto: "Registrado: se aplica en la próxima quincena que se liquide." });
    } catch (err) { setMsg({ tipo: "error", texto: mensajeError(err) }); }
  }

  return (
    <div className="space-y-4">
      <Titulo>Descuentos y pagos adicionales</Titulo>
      <p className="text-sm text-slate-600">Préstamos, embargos y cuotas por mayores valores pagados se descuentan una cuota por quincena hasta completar el total
        (en ese orden: embargos, préstamos y cuotas, sin dejar el neto en negativo). Los pagos adicionales por menores valores pagados se suman al devengado.</p>
      {puede && (
        <form onSubmit={crear} className="tarjeta grid gap-3 p-4 md:grid-cols-6">
          <div className="md:col-span-2"><label className="label">Colaborador</label>
            <input className="input mb-1" placeholder="Buscar por cédula o nombre" value={buscarEmp} onChange={(e) => setBuscarEmp(e.target.value)} />
            <select className="input" required value={f.empleado_id} onChange={(e) => setF({ ...f, empleado_id: e.target.value })}>
              <option value="">Seleccione…</option>{opciones.map((e) => <option key={e.id} value={e.id}>{e.nombre} · {e.cedula}</option>)}</select></div>
          <div><label className="label">Tipo</label>
            <select className="input" value={f.tipo} onChange={(e) => setF({ ...f, tipo: e.target.value as DescuentoSpeed["tipo"] })}>
              {TIPOS_DESCUENTO.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select>
            {f.tipo === "adicional" && <label className="mt-1 flex items-center gap-2 text-xs text-slate-600">
              <input type="checkbox" checked={f.salarial} onChange={(e) => setF({ ...f, salarial: e.target.checked })} /> Salarial (entra a salud y pensión)</label>}</div>
          <div><label className="label">Valor total{f.tipo === "embargo" ? " (opcional)" : ""}</label>
            <InputPesos vacio valor={f.valor_total} onValor={(v) => setF({ ...f, valor_total: v })} placeholder={f.tipo === "embargo" ? "Sin tope" : ""} /></div>
          <div><label className="label">Cuota por quincena</label><InputPesos vacio valor={f.cuota} onValor={(v) => setF({ ...f, cuota: v })} /></div>
          <div><label className="label">Descripción</label><input className="input" maxLength={300} value={f.descripcion} placeholder="Ej. Préstamo de libre inversión"
            onChange={(e) => setF({ ...f, descripcion: e.target.value })} /></div>
          <div className="md:col-span-6 flex justify-end"><button className="btn-primario" disabled={!f.empleado_id || !f.cuota}><Plus className="h-4 w-4" /> Registrar</button></div>
        </form>
      )}
      {msg && <Alerta tipo={msg.tipo}>{msg.texto}</Alerta>}
      <div className="tarjeta overflow-x-auto">
        <table className="tabla">
          <thead><tr><th>Colaborador</th><th>Tipo</th><th className="text-right">Total</th><th className="text-right">Cuota</th><th className="text-right">Aplicado</th>
            <th className="text-right">Saldo</th><th>Estado</th><th /></tr></thead>
          <tbody>
            {lista?.length === 0 && <tr><td colSpan={8} className="py-6 text-center text-slate-400">Sin descuentos registrados.</td></tr>}
            {lista?.map((d) => (
              <tr key={d.id} className={d.activo ? "" : "opacity-50"}>
                <td><p className="font-medium">{d.nombre}</p><p className="text-xs text-slate-500">{d.cedula}</p></td>
                <td><p>{d.tipo_nombre}</p><p className="text-xs text-slate-500">{d.descripcion}{d.tipo === "adicional" ? (d.salarial ? " · salarial" : " · no salarial") : ""}</p></td>
                <td className="text-right tabular-nums">{d.valor_total === null ? "Sin tope" : pesos(d.valor_total)}</td>
                <td className="text-right tabular-nums">{pesos(d.cuota)}</td>
                <td className="text-right tabular-nums">{pesos(d.aplicado)}</td>
                <td className="text-right tabular-nums">{d.saldo === null ? "—" : pesos(d.saldo)}</td>
                <td>{d.saldo === 0 ? <Insignia color="bg-slate-200 text-slate-700">pagado</Insignia>
                  : puede ? <button className="text-sm text-marca-700 hover:underline" onClick={async () => {
                    try { await api(`/speed/descuentos/${d.id}`, { method: "PATCH", json: { activo: !d.activo } }); await cargar(); } catch (e) { setMsg({ tipo: "error", texto: mensajeError(e) }); }
                  }}>{d.activo ? "Activo · suspender" : "Suspendido · activar"}</button> : d.activo ? "Activo" : "Suspendido"}</td>
                <td>{puede && <button title="Eliminar" onClick={async () => {
                  if (!confirm("¿Eliminar este registro?")) return;
                  try { await api(`/speed/descuentos/${d.id}`, { method: "DELETE" }); await cargar(); } catch (e) { setMsg({ tipo: "error", texto: mensajeError(e) }); }
                }}><Trash2 className="h-4 w-4 text-slate-400 hover:text-red-600" /></button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
