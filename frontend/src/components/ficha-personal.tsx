"use client";

import { Pencil, Plus, Trash2, X } from "lucide-react";
import { useState } from "react";
import { Alerta, Insignia } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";
import type { Contrato, DatosPersonales, SalidaVacaciones, TramoVacaciones } from "@/lib/liquidador";

const fecha = (iso: string | null | undefined) => (iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : "—");

type Campo = [keyof DatosPersonales | "nombre" | "cargo", string, "texto" | "fecha" | "select" | "check" | "area", [string, string][]?];

const ESTADO_CIVIL: [string, string][] = [["", "—"], ["0", "Ninguno"], ["1", "Soltero(a)"], ["2", "Casado(a)"], ["3", "Viudo(a)"],
  ["4", "Divorciado(a)"], ["5", "Unión libre"]];

const GRUPOS: [string, Campo[]][] = [
  ["Laboral", [["nombre", "Nombre completo", "texto"], ["cargo", "Cargo", "texto"],
    ["tipo_personal", "Tipo", "select", [["", "—"], ["operativo", "Operativo"], ["administrativo", "Administrativo"]]],
    ["puesto", "Puesto", "texto"], ["tipo_contrato", "Tipo de contrato", "texto"], ["ciudad", "Ciudad", "texto"]]],
  ["Identificación", [["sexo", "Sexo", "select", [["", "—"], ["F", "Femenino"], ["M", "Masculino"]]], ["fecha_nacimiento", "Fecha de nacimiento", "fecha"],
    ["rh", "RH", "texto"], ["estado_civil", "Estado civil", "select", ESTADO_CIVIL], ["pais_nacimiento", "País de nacimiento", "texto"],
    ["depto_nacimiento", "Departamento de nacimiento", "texto"], ["ciudad_nacimiento", "Ciudad de nacimiento", "texto"],
    ["fecha_expedicion", "Fecha de expedición del documento", "fecha"], ["pais_expedicion", "País de expedición", "texto"],
    ["depto_expedicion", "Departamento de expedición", "texto"], ["ciudad_expedicion", "Ciudad de expedición", "texto"],
    ["extranjero", "Extranjero", "check"]]],
  ["Contacto", [["celular", "Celular", "texto"], ["correo", "Correo", "texto"], ["direccion", "Dirección", "texto"], ["barrio", "Barrio", "texto"]]],
  ["Seguridad social y pago", [["eps", "EPS", "texto"], ["fondo_pensiones", "Fondo de pensiones", "texto"], ["pensionado", "Pensionado", "check"],
    ["fondo_cesantias", "Fondo de cesantías", "texto"], ["caja_compensacion", "Caja de compensación", "texto"],
    ["plan_exequial", "Plan exequial", "texto"], ["numero_cuenta", "Número de cuenta", "texto"]]],
  ["Formación", [["nivel_educativo", "Nivel educativo", "texto"], ["cursos", "Cursos adicionales", "area"]]],
];

type Valores = Record<string, string | boolean>;

function valoresDe(p: DatosPersonales, nombre: string, cargo: string): Valores {
  const v: Valores = { nombre, cargo };
  for (const [, campos] of GRUPOS) {
    for (const [k, , tipo] of campos) {
      if (k === "nombre" || k === "cargo") continue;
      const x = p[k as keyof DatosPersonales];
      v[k] = tipo === "check" ? Boolean(x) : x === null || x === undefined ? "" : String(x);
    }
  }
  return v;
}

/** Datos personales de la ficha (solo con el permiso de la ficha del personal). */
export function DatosPersonalesForm({ empleadoId, personal, nombre, cargo, editable, onGuardado }: {
  empleadoId: number; personal: DatosPersonales; nombre: string; cargo: string; editable: boolean; onGuardado: (texto: string) => void;
}) {
  const inicial = valoresDe(personal, nombre, cargo);
  const [v, setV] = useState<Valores>(inicial);
  const [error, setError] = useState("");
  const [guardando, setGuardando] = useState(false);
  const cambios = JSON.stringify(v) !== JSON.stringify(inicial);

  async function guardar() {
    setError("");
    setGuardando(true);
    const datos: Record<string, unknown> = {};
    for (const [k, x] of Object.entries(v)) datos[k] = typeof x === "boolean" ? x : x.trim() === "" ? null : x.trim();
    datos.estado_civil = datos.estado_civil === null ? null : Number(datos.estado_civil);
    try {
      const r = await api<{ cambios: string[] }>(`/liquidador/empleados/${empleadoId}/datos`, { method: "PUT", json: datos });
      onGuardado(r.cambios.length ? `Datos personales guardados (${r.cambios.length} campo(s)).` : "No había cambios.");
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setGuardando(false);
    }
  }

  return (
    <section className="tarjeta space-y-5 p-5">
      <div className="flex flex-wrap items-baseline gap-3">
        <h2 className="font-semibold text-slate-900">Datos del personal</h2>
        {personal.edad !== undefined && <span className="text-sm text-slate-500">{personal.edad} años</span>}
        {personal.antiguedad_anios !== undefined && <span className="text-sm text-slate-500">· {personal.antiguedad_anios} años de antigüedad</span>}
      </div>
      {error && <Alerta>{error}</Alerta>}
      {GRUPOS.map(([titulo, campos]) => (
        <div key={titulo}>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{titulo}</p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {campos.map(([k, etiqueta, tipo, opciones]) => (
              <div key={k} className={tipo === "area" ? "sm:col-span-2 lg:col-span-3" : ""}>
                {tipo === "check" ? (
                  <label className="mt-6 flex items-center gap-2 text-sm text-slate-700">
                    <input type="checkbox" className="h-4 w-4" disabled={!editable} checked={Boolean(v[k])} onChange={(e) => setV({ ...v, [k]: e.target.checked })} />
                    {etiqueta}
                  </label>
                ) : (
                  <>
                    <label className="label">{etiqueta}</label>
                    {tipo === "select" ? (
                      <select className="input" disabled={!editable} value={String(v[k])} onChange={(e) => setV({ ...v, [k]: e.target.value })}>
                        {opciones?.map(([val, t]) => <option key={val} value={val}>{t}</option>)}
                      </select>
                    ) : tipo === "area" ? (
                      <textarea className="input min-h-[60px]" disabled={!editable} maxLength={2000} value={String(v[k])} onChange={(e) => setV({ ...v, [k]: e.target.value })} />
                    ) : (
                      <input className="input" type={tipo === "fecha" ? "date" : "text"} disabled={!editable} value={String(v[k])}
                        onChange={(e) => setV({ ...v, [k]: e.target.value })} />
                    )}
                  </>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
      {editable && (
        <div className="flex gap-2">
          <button className="btn-primario" disabled={!cambios || guardando} onClick={guardar}>{guardando ? "Guardando…" : "Guardar datos del personal"}</button>
          {cambios && <button className="btn-secundario" onClick={() => setV(inicial)}>Deshacer</button>}
        </div>
      )}
    </section>
  );
}

type FormContrato = { id: number | null; fecha_inicio: string; fecha_retiro: string; tipo_contrato: string; cargo: string; puesto: string; motivo_retiro: string; observacion: string };

/** Historial laboral: contratos con su retiro (registrar retiros y reintegros). */
export function HistorialLaboral({ empleadoId, contratos, editable, onCambio }: {
  empleadoId: number; contratos: Contrato[]; editable: boolean; onCambio: (texto: string) => void;
}) {
  const [f, setF] = useState<FormContrato | null>(null);
  const [error, setError] = useState("");

  async function guardar(e: React.FormEvent) {
    e.preventDefault();
    if (!f) return;
    setError("");
    const datos = { fecha_inicio: f.fecha_inicio, fecha_retiro: f.fecha_retiro || null, tipo_contrato: f.tipo_contrato || null, cargo: f.cargo || null,
      puesto: f.puesto || null, motivo_retiro: f.motivo_retiro || null, observacion: f.observacion || null };
    try {
      await api(f.id ? `/liquidador/contratos/${f.id}` : `/liquidador/empleados/${empleadoId}/contratos`, { method: f.id ? "PUT" : "POST", json: datos });
      setF(null);
      onCambio("Contrato guardado: el estado del empleado se actualizó.");
    } catch (err) {
      setError(mensajeError(err));
    }
  }

  async function eliminar(c: Contrato) {
    if (!window.confirm(`¿Eliminar el contrato que inició el ${fecha(c.fecha_inicio)}?`)) return;
    try {
      await api(`/liquidador/contratos/${c.id}`, { method: "DELETE" });
      onCambio("Contrato eliminado.");
    } catch (err) {
      setError(mensajeError(err));
    }
  }

  const campo = (k: keyof FormContrato, etiqueta: string, tipo = "text") => f && (
    <div>
      <label className="label">{etiqueta}</label>
      <input className="input" type={tipo} required={k === "fecha_inicio"} value={String(f[k] ?? "")} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
    </div>
  );

  return (
    <section className="space-y-3">
      <div className="flex items-center">
        <h2 className="font-semibold text-slate-900">Historial laboral</h2>
        {editable && !f && (
          <button className="btn-secundario ml-auto inline-flex items-center gap-1.5"
            onClick={() => setF({ id: null, fecha_inicio: "", fecha_retiro: "", tipo_contrato: "", cargo: "", puesto: "", motivo_retiro: "", observacion: "" })}>
            <Plus className="h-4 w-4" /> Nuevo contrato o reintegro
          </button>
        )}
      </div>
      {error && <Alerta>{error}</Alerta>}
      {f && (
        <form onSubmit={guardar} className="tarjeta space-y-4 p-5">
          <div className="flex items-center">
            <h3 className="font-semibold text-slate-900">{f.id ? "Editar contrato" : "Nuevo contrato"}</h3>
            <button type="button" className="ml-auto rounded-md p-1 text-slate-500 hover:bg-slate-100" onClick={() => setF(null)} aria-label="Cerrar"><X className="h-5 w-5" /></button>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {campo("fecha_inicio", "Fecha de inicio", "date")}
            {campo("fecha_retiro", "Fecha de retiro (si se retiró)", "date")}
            {campo("tipo_contrato", "Tipo de contrato")}
            {campo("cargo", "Cargo")}
            {campo("puesto", "Puesto")}
            {campo("motivo_retiro", "Motivo de retiro")}
            <div className="sm:col-span-2">{campo("observacion", "Observación")}</div>
          </div>
          <p className="text-xs text-slate-500">Con fecha de retiro el contrato queda cerrado; si no queda ningún contrato abierto, el empleado pasa a retirado.</p>
          <div className="flex gap-2">
            <button className="btn-primario">Guardar</button>
            <button type="button" className="btn-secundario" onClick={() => setF(null)}>Cancelar</button>
          </div>
        </form>
      )}
      <div className="tarjeta overflow-auto">
        <table className="tabla text-sm">
          <thead><tr><th>Inicio</th><th>Retiro</th><th>Contrato</th><th>Cargo</th><th>Puesto</th><th>Motivo de retiro</th><th /></tr></thead>
          <tbody>
            {contratos.map((c) => (
              <tr key={c.id}>
                <td className="whitespace-nowrap">{fecha(c.fecha_inicio)}</td>
                <td className="whitespace-nowrap">{c.fecha_retiro ? fecha(c.fecha_retiro) : <Insignia color="bg-green-100 text-green-800">Vigente</Insignia>}</td>
                <td>{c.tipo_contrato ?? "—"}</td>
                <td>{c.cargo ?? "—"}</td>
                <td className="max-w-[220px] truncate" title={c.puesto ?? ""}>{c.puesto ?? "—"}</td>
                <td>{c.motivo_retiro ?? "—"}{c.observacion && <span className="block text-xs text-slate-500">{c.observacion}</span>}</td>
                <td className="whitespace-nowrap text-right">
                  {editable && (
                    <>
                      <button className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100" aria-label="Editar"
                        onClick={() => setF({ id: c.id, fecha_inicio: c.fecha_inicio, fecha_retiro: c.fecha_retiro ?? "", tipo_contrato: c.tipo_contrato ?? "",
                          cargo: c.cargo ?? "", puesto: c.puesto ?? "", motivo_retiro: c.motivo_retiro ?? "", observacion: c.observacion ?? "" })}>
                        <Pencil className="h-4 w-4" />
                      </button>
                      <button className="rounded-md p-1.5 text-slate-500 hover:bg-red-50 hover:text-red-700" aria-label="Eliminar" onClick={() => eliminar(c)}><Trash2 className="h-4 w-4" /></button>
                    </>
                  )}
                </td>
              </tr>
            ))}
            {contratos.length === 0 && <tr><td colSpan={7} className="py-4 text-center text-sm text-slate-500">Sin contratos registrados.</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
}

const ESTADO_SALIDA: Record<string, [string, string]> = {
  historico: ["Tomadas", "bg-slate-100 text-slate-700"],
  programada: ["Programadas", "bg-sky-100 text-sky-800"],
  cancelada: ["Canceladas", "bg-rose-100 text-rose-800"],
};

type FormSalida = { tipo: "disfrutadas" | "compensadas"; desde: string; hasta: string; retorno: string; dias_habiles: string; estado: string; observacion: string };

/** Historial de vacaciones: salidas registradas (libro o manual) y los días V liquidados en las nóminas. */
export function HistorialVacaciones({ empleadoId, salidas, liquidadas, editable, onCambio }: {
  empleadoId: number; salidas: SalidaVacaciones[]; liquidadas: TramoVacaciones[]; editable: boolean; onCambio: (texto: string) => void;
}) {
  const [f, setF] = useState<FormSalida | null>(null);
  const [error, setError] = useState("");

  async function guardar(e: React.FormEvent) {
    e.preventDefault();
    if (!f) return;
    setError("");
    try {
      await api(`/liquidador/empleados/${empleadoId}/salidas`, {
        method: "POST",
        json: { tipo: f.tipo, desde: f.desde || null, hasta: f.hasta || null, retorno: f.retorno || null,
          dias_habiles: f.dias_habiles ? Number(f.dias_habiles) : null, estado: f.estado, observacion: f.observacion || null },
      });
      setF(null);
      onCambio("Vacaciones registradas en el historial.");
    } catch (err) {
      setError(mensajeError(err));
    }
  }

  async function eliminar(x: SalidaVacaciones) {
    if (!window.confirm("¿Eliminar este registro de vacaciones del historial?")) return;
    try {
      await api(`/liquidador/salidas/${x.id}`, { method: "DELETE" });
      onCambio("Registro eliminado.");
    } catch (err) {
      setError(mensajeError(err));
    }
  }

  return (
    <section className="space-y-3">
      <div className="flex items-center">
        <h2 className="font-semibold text-slate-900">Historial de vacaciones</h2>
        {editable && !f && (
          <button className="btn-secundario ml-auto inline-flex items-center gap-1.5"
            onClick={() => setF({ tipo: "disfrutadas", desde: "", hasta: "", retorno: "", dias_habiles: "", estado: "programada", observacion: "" })}>
            <Plus className="h-4 w-4" /> Registrar vacaciones
          </button>
        )}
      </div>
      <p className="-mt-2 text-xs text-slate-500">
        El historial es informativo: el saldo descuenta los días disfrutados hasta el corte del libro y, después, los días con código de vacaciones (V)
        liquidados en las nóminas.
      </p>
      {error && <Alerta>{error}</Alerta>}
      {f && (
        <form onSubmit={guardar} className="tarjeta space-y-4 p-5">
          <div className="flex items-center">
            <h3 className="font-semibold text-slate-900">Registrar vacaciones</h3>
            <button type="button" className="ml-auto rounded-md p-1 text-slate-500 hover:bg-slate-100" onClick={() => setF(null)} aria-label="Cerrar"><X className="h-5 w-5" /></button>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <label className="label">Tipo</label>
              <select className="input" value={f.tipo} onChange={(e) => setF({ ...f, tipo: e.target.value as FormSalida["tipo"] })}>
                <option value="disfrutadas">Disfrutadas</option>
                <option value="compensadas">Compensadas en dinero</option>
              </select>
            </div>
            <div>
              <label className="label">Estado</label>
              <select className="input" value={f.estado} onChange={(e) => setF({ ...f, estado: e.target.value })}>
                <option value="programada">Programadas</option>
                <option value="historico">Ya tomadas</option>
                <option value="cancelada">Canceladas</option>
              </select>
            </div>
            <div>
              <label className="label">Desde</label>
              <input className="input" type="date" required={f.tipo === "disfrutadas"} value={f.desde} onChange={(e) => setF({ ...f, desde: e.target.value })} />
            </div>
            <div>
              <label className="label">Hasta</label>
              <input className="input" type="date" required={f.tipo === "disfrutadas"} value={f.hasta} onChange={(e) => setF({ ...f, hasta: e.target.value })} />
            </div>
            <div>
              <label className="label">Retoma labores</label>
              <input className="input" type="date" value={f.retorno} onChange={(e) => setF({ ...f, retorno: e.target.value })} />
            </div>
            <div>
              <label className="label">Días hábiles</label>
              <input className="input" type="number" min={0} value={f.dias_habiles} onChange={(e) => setF({ ...f, dias_habiles: e.target.value })} />
            </div>
            <div className="sm:col-span-2">
              <label className="label">Observación</label>
              <input className="input" maxLength={300} value={f.observacion} onChange={(e) => setF({ ...f, observacion: e.target.value })} />
            </div>
          </div>
          <div className="flex gap-2">
            <button className="btn-primario">Guardar</button>
            <button type="button" className="btn-secundario" onClick={() => setF(null)}>Cancelar</button>
          </div>
        </form>
      )}
      <div className="tarjeta overflow-auto">
        <table className="tabla text-sm">
          <thead><tr><th>Periodo</th><th>Retoma</th><th>Tipo</th><th className="text-right">Días hábiles</th><th>Estado</th><th>Origen</th><th /></tr></thead>
          <tbody>
            {liquidadas.map((t) => (
              <tr key={`v-${t.desde}`}>
                <td className="whitespace-nowrap">{fecha(t.desde)} → {fecha(t.hasta)}</td>
                <td>—</td>
                <td>Disfrutadas</td>
                <td className="text-right tabular-nums">{t.dias_habiles}<span className="text-xs text-slate-500"> de {t.dias}</span></td>
                <td><Insignia color="bg-green-100 text-green-800">Liquidadas en nómina</Insignia></td>
                <td className="text-xs text-slate-500">{t.antes_del_corte ? "Código V (ya incluidas en el libro)" : "Código V"}</td>
                <td />
              </tr>
            ))}
            {salidas.map((x) => {
              const [texto, color] = ESTADO_SALIDA[x.estado] ?? [x.estado, ""];
              return (
                <tr key={x.id}>
                  <td className="whitespace-nowrap">{x.desde ? `${fecha(x.desde)} → ${fecha(x.hasta)}` : "—"}</td>
                  <td className="whitespace-nowrap">{fecha(x.retorno)}</td>
                  <td>{x.tipo === "compensadas" ? "Compensadas" : "Disfrutadas"}</td>
                  <td className="text-right tabular-nums">{x.dias_habiles ?? "—"}</td>
                  <td><Insignia color={color}>{texto}</Insignia></td>
                  <td className="text-xs text-slate-500">{x.origen === "libro" ? "Libro de vacaciones" : "Registro manual"}{x.observacion ? ` · ${x.observacion}` : ""}</td>
                  <td className="text-right">
                    {editable && (
                      <button className="rounded-md p-1.5 text-slate-500 hover:bg-red-50 hover:text-red-700" aria-label="Eliminar" onClick={() => eliminar(x)}><Trash2 className="h-4 w-4" /></button>
                    )}
                  </td>
                </tr>
              );
            })}
            {salidas.length + liquidadas.length === 0 && <tr><td colSpan={7} className="py-4 text-center text-sm text-slate-500">Sin vacaciones registradas.</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
}
