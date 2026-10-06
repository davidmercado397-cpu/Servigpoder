"use client";

import { Paginador, metaDe, usePaginacion, type MetaPagina } from "@/components/paginacion";
import { useCallback, useEffect, useState } from "react";
import { api, apiEnvelope, mensajeError, type Empresa, type Rol, type Usuario } from "@/lib/api";
import { usePermiso } from "@/lib/sesion";

type Form = {
  id?: number; username: string; nombre: string; email: string; password: string; roles: number[]; activo: boolean;
  accesos: Record<string, string[]>;
};
type AppInfo = { codigo: string; nombre: string };
const VACIO: Form = { username: "", nombre: "", email: "", password: "", roles: [], activo: true, accesos: {} };

export default function UsuariosPage() {
  const puedeGestionar = usePermiso("usuarios.gestionar");
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [roles, setRoles] = useState<Rol[]>([]);
  const [empresas, setEmpresas] = useState<Empresa[]>([]);
  const [apps, setApps] = useState<AppInfo[]>([]);
  const [form, setForm] = useState<Form | null>(null);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [meta, setMeta] = useState<MetaPagina | null>(null);
  const pag = usePaginacion([q]);

  const cargar = useCallback(async () => {
    const r = await apiEnvelope<Usuario[]>(`/usuarios?q=${encodeURIComponent(q)}&${pag.query}`);
    setUsuarios(r.data ?? []);
    setMeta(metaDe(r));
    setRoles(await api<Rol[]>("/roles").catch(() => []));
    const e = await apiEnvelope<Empresa[]>("/empresas").catch(() => null);
    setEmpresas(e?.data ?? []);
    setApps((e?.meta.extra?.apps as AppInfo[]) ?? []);
  }, [q, pag.query]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  function editar(u: Usuario) {
    setError("");
    setForm({
      id: u.id, username: u.username, nombre: u.nombre, email: u.email ?? "", password: "", roles: u.roles.map((r) => r.id), activo: u.activo,
      accesos: Object.fromEntries(Object.entries(u.accesos ?? {}).map(([k, v]) => [k, [...v]])),
    });
  }

  async function guardar(e: React.FormEvent) {
    e.preventDefault();
    if (!form) return;
    setError("");
    try {
      if (form.id) {
        await api(`/usuarios/${form.id}`, {
          method: "PATCH",
          json: {
            nombre: form.nombre, email: form.email, roles: form.roles, activo: form.activo, accesos: limpiar(form.accesos),
            ...(form.password ? { password: form.password } : {}),
          },
        });
      } else {
        await api("/usuarios", {
          method: "POST",
          json: { username: form.username, nombre: form.nombre, email: form.email || null, password: form.password, roles: form.roles, accesos: limpiar(form.accesos) },
        });
      }
      setForm(null);
      cargar();
    } catch (err) {
      setError(mensajeError(err));
    }
  }

  async function restablecerMfa(u: Usuario) {
    if (!confirm(`¿Restablecer la verificación en dos pasos de ${u.nombre}? Deberá configurarla de nuevo en su próximo ingreso y se cerrarán sus sesiones abiertas.`)) return;
    try {
      await api(`/usuarios/${u.id}/restablecer-mfa`, { method: "POST" });
      cargar();
    } catch (err) {
      alert(mensajeError(err));
    }
  }

  const limpiar = (a: Record<string, string[]>) => Object.fromEntries(Object.entries(a).filter(([, v]) => v.length));
  const nombreApp = (c: string) => apps.find((a) => a.codigo === c)?.nombre ?? c;
  const nombreEmpresa = (c: string) => empresas.find((e) => e.codigo === c)?.nombre ?? c;

  function toggleAcceso(empresa: string, app: string) {
    if (!form) return;
    const actuales = form.accesos[empresa] ?? [];
    const nuevos = actuales.includes(app) ? actuales.filter((x) => x !== app) : [...actuales, app];
    setForm({ ...form, accesos: { ...form.accesos, [empresa]: nuevos } });
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
            <label className="label">{form.id ? "Nueva contraseña temporal (vacío = no cambiar)" : "Contraseña temporal"}</label>
            <input className="input" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required={!form.id} minLength={10} autoComplete="new-password" />
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
          <div className="md:col-span-2">
            <p className="label">Acceso por empresa</p>
            <p className="mb-2 text-xs text-slate-500">
              Marque a qué desarrollos entra en cada empresa. Lo que puede hacer dentro lo definen sus roles (los mismos en todas las empresas).
            </p>
            <div className="overflow-hidden rounded-lg border border-slate-200">
              <table className="tabla text-sm">
                <tbody>
                  {empresas.filter((e) => e.activa).map((e) => (
                    <tr key={e.codigo}>
                      <td className="w-48 font-medium">{e.nombre}</td>
                      <td>
                        <div className="flex flex-wrap gap-4">
                          {e.apps.length ? e.apps.map((a) => (
                            <label key={a} className="flex items-center gap-2">
                              <input type="checkbox" checked={(form.accesos[e.codigo] ?? []).includes(a)} onChange={() => toggleAcceso(e.codigo, a)} />
                              {nombreApp(a)}
                            </label>
                          )) : <span className="text-xs text-slate-400">Sin desarrollos habilitados</span>}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          {form.id && (
            <label className="flex items-center gap-2 text-sm md:col-span-2">
              <input type="checkbox" checked={form.activo} onChange={(e) => setForm({ ...form, activo: e.target.checked })} />
              Usuario activo
            </label>
          )}
          <p className="text-xs text-slate-500 md:col-span-2">
            La contraseña que asigne es temporal: el usuario deberá cambiarla y configurar su verificación en dos pasos al ingresar.
          </p>
          {error && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 md:col-span-2">{error}</p>}
          <div className="flex gap-2 md:col-span-2">
            <button className="btn-primario">Guardar</button>
            <button type="button" className="btn-secundario" onClick={() => setForm(null)}>Cancelar</button>
          </div>
        </form>
      )}

      <input className="input max-w-sm" placeholder="Buscar por usuario o nombre…" value={q} onChange={(e) => setQ(e.target.value)} />
      <div className="tarjeta overflow-hidden">
        <table className="tabla">
          <thead>
            <tr>
              <th>Usuario</th>
              <th>Nombre</th>
              <th>Roles</th>
              <th>Empresas</th>
              <th>Estado</th>
              <th>Verificación en dos pasos</th>
              {puedeGestionar && <th />}
            </tr>
          </thead>
          <tbody>
            {usuarios.map((u) => (
              <tr key={u.id}>
                <td className="font-mono">{u.username}</td>
                <td>{u.nombre}</td>
                <td>{u.roles.map((r) => r.nombre).join(", ") || <span className="text-slate-400">Sin rol</span>}</td>
                <td className="text-sm">
                  {Object.keys(u.accesos ?? {}).length
                    ? Object.entries(u.accesos).map(([emp, aps]) => (
                      <span key={emp} className="block" title={aps.map(nombreApp).join(", ")}>{nombreEmpresa(emp)} <span className="text-xs text-slate-500">({aps.length})</span></span>
                    ))
                    : <span className="text-slate-400">Sin acceso</span>}
                </td>
                <td>
                  <span className={`rounded-full px-2 py-0.5 text-xs ${u.activo ? "bg-green-100 text-green-800" : "bg-slate-200 text-slate-600"}`}>
                    {u.activo ? "Activo" : "Inactivo"}
                  </span>
                  {u.debe_cambiar_password && <span className="ml-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-800">Contraseña temporal</span>}
                </td>
                <td className="text-sm">
                  {u.mfa_activo ? <span className="text-[#086b08]">✓ Configurada</span> : <span className="text-slate-500">Pendiente (al primer ingreso)</span>}
                </td>
                {puedeGestionar && (
                  <td className="whitespace-nowrap text-right">
                    <button className="text-sm text-marca-600 hover:underline" onClick={() => editar(u)}>Editar</button>
                    {u.mfa_activo && (
                      <button className="ml-3 text-sm text-[#9a3f1a] hover:underline" onClick={() => restablecerMfa(u)}>Restablecer MFA</button>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        <Paginador meta={meta} onPagina={pag.setPagina} onTamano={pag.setTamano} />
      </div>
    </div>
  );
}
