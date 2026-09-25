"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type Rol, type Usuario } from "@/lib/api";
import { usePermiso } from "@/lib/sesion";

type Form = { id?: number; username: string; nombre: string; email: string; password: string; roles: number[]; activo: boolean };
const VACIO: Form = { username: "", nombre: "", email: "", password: "", roles: [], activo: true };

export default function UsuariosPage() {
  const puedeGestionar = usePermiso("usuarios.gestionar");
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [roles, setRoles] = useState<Rol[]>([]);
  const [form, setForm] = useState<Form | null>(null);
  const [error, setError] = useState("");

  const cargar = useCallback(async () => {
    setUsuarios(await api<Usuario[]>("/usuarios"));
    setRoles(await api<Rol[]>("/roles").catch(() => []));
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  function editar(u: Usuario) {
    setError("");
    setForm({ id: u.id, username: u.username, nombre: u.nombre, email: u.email ?? "", password: "", roles: u.roles.map((r) => r.id), activo: u.activo });
  }

  async function guardar(e: React.FormEvent) {
    e.preventDefault();
    if (!form) return;
    setError("");
    try {
      if (form.id) {
        await api(`/usuarios/${form.id}`, {
          method: "PATCH",
          json: { nombre: form.nombre, email: form.email, roles: form.roles, activo: form.activo, ...(form.password ? { password: form.password } : {}) },
        });
      } else {
        await api("/usuarios", {
          method: "POST",
          json: { username: form.username, nombre: form.nombre, email: form.email || null, password: form.password, roles: form.roles },
        });
      }
      setForm(null);
      cargar();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Error al guardar");
    }
  }

  function toggleRol(id: number) {
    if (!form) return;
    setForm({ ...form, roles: form.roles.includes(id) ? form.roles.filter((r) => r !== id) : [...form.roles, id] });
  }

  return (
    <div className="max-w-5xl space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-marca-900">Usuarios</h1>
        {puedeGestionar && (
          <button className="btn-primario" onClick={() => { setError(""); setForm(VACIO); }}>
            Nuevo usuario
          </button>
        )}
      </div>

      {form && (
        <form onSubmit={guardar} className="tarjeta grid gap-4 p-5 md:grid-cols-2">
          <h2 className="font-semibold md:col-span-2">{form.id ? `Editar ${form.username}` : "Nuevo usuario"}</h2>
          <div>
            <label className="label">Usuario</label>
            <input className="input" value={form.username} disabled={!!form.id} onChange={(e) => setForm({ ...form, username: e.target.value })} required minLength={3} />
          </div>
          <div>
            <label className="label">Nombre completo</label>
            <input className="input" value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} required minLength={2} />
          </div>
          <div>
            <label className="label">Correo (opcional)</label>
            <input className="input" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </div>
          <div>
            <label className="label">{form.id ? "Nueva contraseña (dejar vacío para no cambiar)" : "Contraseña"}</label>
            <input className="input" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required={!form.id} minLength={8} autoComplete="new-password" />
          </div>
          <div className="md:col-span-2">
            <p className="label">Roles</p>
            <div className="flex flex-wrap gap-3">
              {roles.map((r) => (
                <label key={r.id} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={form.roles.includes(r.id)} onChange={() => toggleRol(r.id)} />
                  {r.nombre}
                </label>
              ))}
            </div>
          </div>
          {form.id && (
            <label className="flex items-center gap-2 text-sm md:col-span-2">
              <input type="checkbox" checked={form.activo} onChange={(e) => setForm({ ...form, activo: e.target.checked })} />
              Usuario activo
            </label>
          )}
          {error && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 md:col-span-2">{error}</p>}
          <div className="flex gap-2 md:col-span-2">
            <button className="btn-primario">Guardar</button>
            <button type="button" className="btn-secundario" onClick={() => setForm(null)}>Cancelar</button>
          </div>
        </form>
      )}

      <div className="tarjeta overflow-hidden">
        <table className="tabla">
          <thead>
            <tr>
              <th>Usuario</th>
              <th>Nombre</th>
              <th>Roles</th>
              <th>Estado</th>
              {puedeGestionar && <th />}
            </tr>
          </thead>
          <tbody>
            {usuarios.map((u) => (
              <tr key={u.id}>
                <td className="font-mono">{u.username}</td>
                <td>{u.nombre}</td>
                <td>{u.roles.map((r) => r.nombre).join(", ") || <span className="text-slate-400">Sin rol</span>}</td>
                <td>
                  <span className={`rounded-full px-2 py-0.5 text-xs ${u.activo ? "bg-green-100 text-green-800" : "bg-slate-200 text-slate-600"}`}>
                    {u.activo ? "Activo" : "Inactivo"}
                  </span>
                </td>
                {puedeGestionar && (
                  <td className="text-right">
                    <button className="text-sm text-marca-600 hover:underline" onClick={() => editar(u)}>Editar</button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
