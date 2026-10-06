"use client";

import { Building2, Database, Plus, Users } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiEnvelope, api, mensajeError, type Empresa } from "@/lib/api";
import { usePermiso } from "@/lib/sesion";

type AppInfo = { codigo: string; nombre: string };
type Form = { id?: number; codigo: string; nombre: string; apps: string[]; activa: boolean };
const VACIO: Form = { codigo: "", nombre: "", apps: [], activa: true };

export default function EmpresasPage() {
  const gestionar = usePermiso("empresas.gestionar");
  const [empresas, setEmpresas] = useState<Empresa[]>([]);
  const [apps, setApps] = useState<AppInfo[]>([]);
  const [form, setForm] = useState<Form | null>(null);
  const [error, setError] = useState("");
  const [aviso, setAviso] = useState("");
  const [ocupado, setOcupado] = useState(false);

  const cargar = useCallback(async () => {
    const r = await apiEnvelope<Empresa[]>("/empresas");
    setEmpresas(r.data ?? []);
    setApps((r.meta.extra?.apps as AppInfo[]) ?? []);
  }, []);

  useEffect(() => {
    cargar().catch((e) => setError(mensajeError(e)));
  }, [cargar]);

  const nombreApp = (c: string) => apps.find((a) => a.codigo === c)?.nombre ?? c;

  async function guardar(e: React.FormEvent) {
    e.preventDefault();
    if (!form) return;
    setError("");
    setAviso("");
    setOcupado(true);
    try {
      if (form.id) {
        await api(`/empresas/${form.id}`, { method: "PATCH", json: { nombre: form.nombre, activa: form.activa, apps: form.apps } });
        setAviso("Empresa actualizada.");
      } else {
        await api("/empresas", { method: "POST", json: { codigo: form.codigo.trim().toLowerCase(), nombre: form.nombre, apps: form.apps } });
        setAviso(`Empresa creada con su propia base de datos. Ya tiene acceso a sus desarrollos; asigne los accesos de los demás usuarios en Usuarios.`);
      }
      setForm(null);
      await cargar();
    } catch (err) {
      setError(mensajeError(err));
    } finally {
      setOcupado(false);
    }
  }

  const toggleApp = (c: string) => form && setForm({ ...form, apps: form.apps.includes(c) ? form.apps.filter((x) => x !== c) : [...form.apps, c] });

  return (
    <div className="max-w-5xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-marca-900">Empresas</h1>
          <p className="text-sm text-slate-500">
            Cada empresa tiene sus propios datos (empleados, turnos, nóminas, maestros…), separados de las demás. Los usuarios y roles son
            compartidos; en cada usuario se marca a qué desarrollos entra en cada empresa.
          </p>
        </div>
        {gestionar && !form && (
          <button className="btn-primario inline-flex shrink-0 items-center gap-1.5" onClick={() => { setError(""); setAviso(""); setForm({ ...VACIO }); }}>
            <Plus className="h-4 w-4" /> Nueva empresa
          </button>
        )}
      </div>
      {aviso && <p className="rounded-md bg-green-50 px-3 py-2 text-sm text-green-800">{aviso}</p>}
      {error && !form && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

      {form && (
        <form onSubmit={guardar} className="tarjeta grid gap-4 p-5 md:grid-cols-2">
          <h2 className="font-semibold md:col-span-2">{form.id ? `Editar ${form.nombre}` : "Nueva empresa"}</h2>
          <div>
            <label className="label">Nombre</label>
            <input className="input" required minLength={2} maxLength={120} value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} />
          </div>
          <div>
            <label className="label">Código</label>
            <input className="input font-mono" required pattern="[a-z][a-z0-9]{1,19}" maxLength={20} disabled={!!form.id} placeholder="p. ej. sera"
              value={form.codigo} onChange={(e) => setForm({ ...form, codigo: e.target.value.toLowerCase() })} />
            <p className="mt-1 text-xs text-slate-500">Minúsculas y números, sin espacios. Nombra su base de datos (emp_{form.codigo || "codigo"}); no se puede cambiar.</p>
          </div>
          <div className="md:col-span-2">
            <p className="label">Desarrollos habilitados</p>
            <div className="flex flex-wrap gap-4">
              {apps.map((a) => (
                <label key={a.codigo} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={form.apps.includes(a.codigo)} onChange={() => toggleApp(a.codigo)} /> {a.nombre}
                </label>
              ))}
            </div>
          </div>
          {form.id && (
            <label className="flex items-center gap-2 text-sm md:col-span-2">
              <input type="checkbox" checked={form.activa} onChange={(e) => setForm({ ...form, activa: e.target.checked })} />
              Empresa activa (inactiva: nadie puede entrar a sus desarrollos; sus datos se conservan)
            </label>
          )}
          {error && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 md:col-span-2">{error}</p>}
          <div className="flex gap-2 md:col-span-2">
            <button className="btn-primario" disabled={ocupado}>{ocupado ? "Guardando…" : "Guardar"}</button>
            <button type="button" className="btn-secundario" onClick={() => setForm(null)}>Cancelar</button>
          </div>
        </form>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {empresas.map((e) => (
          <div key={e.id} className={`tarjeta p-5 ${e.activa ? "" : "opacity-60"}`}>
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-marca-50 text-marca-700"><Building2 className="h-5 w-5" /></div>
              <div className="min-w-0 flex-1">
                <h2 className="font-semibold text-slate-900">{e.nombre} {!e.activa && <span className="ml-1 rounded-full bg-slate-200 px-2 py-0.5 text-xs text-slate-600">Inactiva</span>}</h2>
                <p className="flex flex-wrap gap-x-3 text-xs text-slate-500">
                  <span className="inline-flex items-center gap-1"><Database className="h-3.5 w-3.5" /> {e.esquema}</span>
                  <span className="inline-flex items-center gap-1"><Users className="h-3.5 w-3.5" /> {e.usuarios} usuarios con acceso</span>
                </p>
              </div>
              {gestionar && (
                <button className="text-sm text-marca-600 hover:underline"
                  onClick={() => { setError(""); setAviso(""); setForm({ id: e.id, codigo: e.codigo, nombre: e.nombre, apps: [...e.apps], activa: e.activa }); }}>
                  Editar
                </button>
              )}
            </div>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {e.apps.length ? e.apps.map((a) => <span key={a} className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs text-slate-700">{nombreApp(a)}</span>)
                : <span className="text-xs text-slate-400">Sin desarrollos habilitados</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
