"use client";

import { Lock, ShieldCheck, User } from "lucide-react";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [cargando, setCargando] = useState(false);

  async function entrar(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setCargando(true);
    try {
      await api("/auth/login", { method: "POST", json: { username, password } });
      window.location.href = "/";
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No fue posible conectar con el servidor");
      setCargando(false);
    }
  }

  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-gradient-to-br from-[#0f2d5c] via-[#0c2750] to-[#081a38] px-4">
      <div className="pointer-events-none absolute -left-32 -top-32 h-96 w-96 rounded-full bg-sky-500/20 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-40 -right-24 h-[28rem] w-[28rem] rounded-full bg-indigo-500/20 blur-3xl" />

      <div className="relative w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center text-center">
          <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-sky-400 to-marca-600 shadow-lg shadow-sky-900/50 ring-1 ring-white/20">
            <ShieldCheck className="h-7 w-7 text-white" strokeWidth={2.2} />
          </div>
          <h1 className="text-2xl font-bold text-white">Capacidad Operativa</h1>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-sky-300/80">Servigpoder</p>
        </div>

        <form onSubmit={entrar} className="space-y-4 rounded-2xl bg-white p-7 shadow-2xl shadow-black/30">
          <div>
            <h2 className="font-semibold text-slate-800">Iniciar sesión</h2>
            <p className="text-sm text-slate-500">Control de programación de personal</p>
          </div>
          <div>
            <label className="label" htmlFor="username">Usuario</label>
            <div className="relative">
              <User className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input id="username" className="input pl-9" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
            </div>
          </div>
          <div>
            <label className="label" htmlFor="password">Contraseña</label>
            <div className="relative">
              <Lock className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input id="password" type="password" className="input pl-9" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            </div>
          </div>
          {error && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
          <button className="btn-primario w-full py-2.5" disabled={cargando}>
            {cargando ? "Ingresando…" : "Ingresar"}
          </button>
        </form>
        <p className="mt-6 text-center text-xs text-slate-400">© {new Date().getFullYear()} Servigpoder · Acceso restringido</p>
      </div>
    </main>
  );
}
