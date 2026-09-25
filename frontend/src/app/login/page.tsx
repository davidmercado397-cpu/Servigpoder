"use client";

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
    <main className="flex min-h-screen items-center justify-center bg-marca-900 px-4">
      <form onSubmit={entrar} className="tarjeta w-full max-w-sm space-y-4 p-8">
        <div>
          <h1 className="text-xl font-bold text-marca-900">Capacidad Operativa</h1>
          <p className="text-sm text-slate-500">Servigpoder · Programación de personal</p>
        </div>
        <div>
          <label className="label" htmlFor="username">Usuario</label>
          <input id="username" className="input" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
        </div>
        <div>
          <label className="label" htmlFor="password">Contraseña</label>
          <input id="password" type="password" className="input" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </div>
        {error && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
        <button className="btn-primario w-full" disabled={cargando}>
          {cargando ? "Ingresando…" : "Ingresar"}
        </button>
      </form>
    </main>
  );
}
