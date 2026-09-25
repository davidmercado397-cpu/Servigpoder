"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, mensajeError, type Permiso, type Rol } from "@/lib/api";
import { usePermiso } from "@/lib/sesion";

type Form = { id?: number; nombre: string; descripcion: string; permisos: string[] };

export default function RolesPage() {
  const puedeGestionar = usePermiso("roles.gestionar");
  const [roles, setRoles] = useState<Rol[]>([]);
  const [permisos, setPermisos] = useState<Permiso[]>([]);
  const [form, setForm] = useState<Form | null>(null);
  const [error, setError] = useState("");

  const cargar = useCallback(async () => {
    const [r, p] = await Promise.all([api<Rol[]>("/roles"), api<Permiso[]>("/permisos")]);
    setRoles(r);
    setPermisos(p);
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const porModulo = useMemo(() => {
    const m = new Map<string, Permiso[]>();
    permisos.forEach((p) => m.set(p.modulo, [...(m.get(p.modulo) ?? []), p]));
    return [...m.entries()];
  }, [permisos]);

  const descripcion = useMemo(() => Object.fromEntries(permisos.map((p) => [p.codigo, p.descripcion])), [permisos]);

  function toggle(codigo: string) {
    if (!form) return;
    setForm({ ...form, permisos: form.permisos.includes(codigo) ? form.permisos.filter((c) => c !== codigo) : [...form.permisos, codigo] });
  }

  async function guardar(e: React.FormEvent) {
    e.preventDefault();
    if (!form) return;
    setError("");
    try {
      const body = { nombre: form.nombre, descripcion: form.descripcion, permisos: form.permisos };
      if (form.id) await api(`/roles/${form.id}`, { method: "PUT", json: body });
      else await api("/roles", { method: "POST", json: body });
      setForm(null);
      cargar();
    } catch (err) {
      setError(mensajeError(err));
    }
  }

  async function eliminar(rol: Rol) {
    if (!confirm(`¿Eliminar el rol "${rol.nombre}"? Los usuarios que lo tengan perderán sus permisos.`)) return;
    try {
      await api(`/roles/${rol.id}`, { method: "DELETE" });
      cargar();
    } catch (err) {
      alert(mensajeError(err));
    }
  }

  return (
    <div className="max-w-5xl space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-marca-900">Roles y permisos</h1>
        {puedeGestionar && (
          <button className="btn-primario" onClick={() => { setError(""); setForm({ nombre: "", descripcion: "", permisos: [] }); }}>
            Nuevo rol
          </button>
        )}
      </div>

      {form && (
        <form onSubmit={guardar} className="tarjeta space-y-4 p-5">
          <h2 className="font-semibold">{form.id ? `Editar rol ${form.nombre}` : "Nuevo rol"}</h2>
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label className="label">Nombre</label>
              <input className="input" value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} required minLength={2} />
            </div>
            <div>
              <label className="label">Descripción</label>
              <input className="input" value={form.descripcion} onChange={(e) => setForm({ ...form, descripcion: e.target.value })} />
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            {porModulo.map(([modulo, lista]) => (
              <fieldset key={modulo} className="rounded-md border border-slate-200 p-3">
                <legend className="px-1 text-sm font-semibold text-slate-600">{modulo}</legend>
                {lista.map((p) => (
                  <label key={p.codigo} className="flex items-start gap-2 py-1 text-sm">
                    <input type="checkbox" className="mt-0.5" checked={form.permisos.includes(p.codigo)} onChange={() => toggle(p.codigo)} />
                    {p.descripcion}
                  </label>
                ))}
              </fieldset>
            ))}
          </div>
          {error && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
          <div className="flex gap-2">
            <button className="btn-primario">Guardar</button>
            <button type="button" className="btn-secundario" onClick={() => setForm(null)}>Cancelar</button>
          </div>
        </form>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {roles.map((r) => (
          <div key={r.id} className="tarjeta p-4">
            <div className="flex items-start justify-between gap-2">
              <div>
                <h3 className="font-semibold text-marca-900">{r.nombre}</h3>
                <p className="text-sm text-slate-500">{r.descripcion}</p>
              </div>
              {puedeGestionar && (
                <div className="flex gap-3 text-sm">
                  <button className="text-marca-600 hover:underline" onClick={() => { setError(""); setForm({ id: r.id, nombre: r.nombre, descripcion: r.descripcion, permisos: r.permisos }); }}>
                    Editar
                  </button>
                  {r.nombre !== "Administrador" && (
                    <button className="text-red-600 hover:underline" onClick={() => eliminar(r)}>Eliminar</button>
                  )}
                </div>
              )}
            </div>
            <ul className="mt-3 space-y-0.5 text-sm text-slate-600">
              {r.permisos.map((c) => (
                <li key={c}>• {descripcion[c] ?? c}</li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}
