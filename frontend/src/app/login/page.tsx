"use client";

import { Copy, KeyRound, Lock, ShieldCheck, Smartphone, User } from "lucide-react";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, mensajeError } from "@/lib/api";

type Paso = "credenciales" | "mfa" | "enrolar_mfa" | "recuperacion";
type RespuestaPaso = { paso: "mfa" | "enrolar_mfa" | "listo"; sesion: { debe_cambiar_password: boolean } | null; codigos_recuperacion: string[] | null };
type ConfigMfa = { secreto: string; uri: string; qr: string };

function Marca() {
  return (
    <div className="mb-6 flex flex-col items-center text-center">
      <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-sky-400 to-marca-600 shadow-lg shadow-sky-900/50 ring-1 ring-white/20">
        <ShieldCheck className="h-7 w-7 text-white" strokeWidth={2.2} />
      </div>
      <h1 className="text-2xl font-bold text-white">Plataforma Servigpoder</h1>
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-sky-300/80">Acceso restringido a personal autorizado</p>
    </div>
  );
}

function Formulario() {
  const expirada = useSearchParams().get("expirada") === "1";
  const [paso, setPaso] = useState<Paso>("credenciales");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [codigo, setCodigo] = useState("");
  const [usarRecuperacion, setUsarRecuperacion] = useState(false);
  const [config, setConfig] = useState<ConfigMfa | null>(null);
  const [codigos, setCodigos] = useState<string[]>([]);
  const [destino, setDestino] = useState("/");
  const [error, setError] = useState("");
  const [cargando, setCargando] = useState(false);

  function terminar(r: RespuestaPaso) {
    const ir = r.sesion?.debe_cambiar_password ? "/cuenta?forzado=1" : "/";
    if (r.codigos_recuperacion?.length) {
      setCodigos(r.codigos_recuperacion);
      setDestino(ir);
      setPaso("recuperacion");
    } else {
      window.location.href = ir;
    }
  }

  async function ejecutar(fn: () => Promise<void>) {
    setError("");
    setCargando(true);
    try {
      await fn();
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setCargando(false);
    }
  }

  const credenciales = (e: React.FormEvent) => {
    e.preventDefault();
    ejecutar(async () => {
      const r = await api<RespuestaPaso>("/auth/login", { method: "POST", json: { username, password } });
      setPassword("");
      if (r.paso === "listo") return terminar(r);
      if (r.paso === "enrolar_mfa") setConfig(await api<ConfigMfa>("/auth/mfa/configurar", { method: "POST" }));
      setPaso(r.paso);
    });
  };

  const verificar = (e: React.FormEvent) => {
    e.preventDefault();
    ejecutar(async () => {
      const ruta = paso === "enrolar_mfa" ? "/auth/mfa/activar" : "/auth/mfa/verificar";
      terminar(await api<RespuestaPaso>(ruta, { method: "POST", json: { codigo } }));
    });
  };

  return (
    <div className="relative w-full max-w-md">
      <Marca />
      <div className="rounded-2xl bg-white p-7 shadow-2xl shadow-black/30">
        {expirada && paso === "credenciales" && (
          <p className="mb-4 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900">Su sesión se cerró por inactividad o expiró. Ingrese de nuevo.</p>
        )}

        {paso === "credenciales" && (
          <form onSubmit={credenciales} className="space-y-4">
            <div>
              <h2 className="font-semibold text-slate-800">Iniciar sesión</h2>
              <p className="text-sm text-slate-500">Paso 1 de 2 · Usuario y contraseña</p>
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
            <button className="btn-primario w-full py-2.5" disabled={cargando}>{cargando ? "Verificando…" : "Continuar"}</button>
          </form>
        )}

        {paso === "mfa" && (
          <form onSubmit={verificar} className="space-y-4">
            <div>
              <h2 className="font-semibold text-slate-800">Verificación en dos pasos</h2>
              <p className="text-sm text-slate-500">Paso 2 de 2 · {usarRecuperacion ? "Escriba uno de sus códigos de recuperación" : "Escriba el código de 6 dígitos de su app Authenticator"}</p>
            </div>
            <div className="relative">
              {usarRecuperacion ? <KeyRound className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" /> : <Smartphone className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />}
              <input className="input pl-9 text-center font-mono text-lg tracking-[0.3em]" autoFocus autoComplete="one-time-code"
                inputMode={usarRecuperacion ? "text" : "numeric"} maxLength={usarRecuperacion ? 20 : 6}
                placeholder={usarRecuperacion ? "xxxxxxxx-xxxxxxxx" : "000000"} value={codigo} onChange={(e) => setCodigo(e.target.value.trim())} required />
            </div>
            {error && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
            <button className="btn-primario w-full py-2.5" disabled={cargando}>{cargando ? "Verificando…" : "Ingresar"}</button>
            <button type="button" className="w-full text-center text-sm text-marca-600 hover:underline" onClick={() => { setUsarRecuperacion(!usarRecuperacion); setCodigo(""); }}>
              {usarRecuperacion ? "Usar el código de la app" : "No tengo mi teléfono: usar un código de recuperación"}
            </button>
          </form>
        )}

        {paso === "enrolar_mfa" && config && (
          <form onSubmit={verificar} className="space-y-4">
            <div>
              <h2 className="font-semibold text-slate-800">Configure la verificación en dos pasos</h2>
              <p className="text-sm text-slate-500">Es obligatoria para proteger la información. Solo se hace una vez.</p>
            </div>
            <ol className="list-decimal space-y-1 pl-5 text-sm text-slate-600">
              <li>Instale <b>Microsoft Authenticator</b> o <b>Google Authenticator</b> en su celular.</li>
              <li>En la app, agregue una cuenta y escanee este código:</li>
            </ol>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={config.qr} alt="Código QR para la app Authenticator" className="mx-auto h-48 w-48 rounded-lg border border-slate-200 p-2" />
            <details className="text-xs text-slate-500">
              <summary className="cursor-pointer">¿No puede escanear? Escriba la clave manualmente</summary>
              <p className="mt-1 break-all rounded bg-slate-100 p-2 font-mono text-slate-700">{config.secreto}</p>
            </details>
            <div>
              <label className="label">3. Escriba el código de 6 dígitos que muestra la app</label>
              <input className="input text-center font-mono text-lg tracking-[0.3em]" inputMode="numeric" maxLength={6} autoComplete="one-time-code"
                placeholder="000000" value={codigo} onChange={(e) => setCodigo(e.target.value.trim())} required />
            </div>
            {error && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
            <button className="btn-primario w-full py-2.5" disabled={cargando}>{cargando ? "Verificando…" : "Activar e ingresar"}</button>
          </form>
        )}

        {paso === "recuperacion" && (
          <div className="space-y-4">
            <div>
              <h2 className="font-semibold text-slate-800">Guarde sus códigos de recuperación</h2>
              <p className="text-sm text-slate-500">
                Si pierde su celular, cada código permite ingresar <b>una sola vez</b>. Guárdelos en un lugar seguro: no se volverán a mostrar.
              </p>
            </div>
            <div className="grid grid-cols-2 gap-2 rounded-lg bg-slate-100 p-3 font-mono text-sm">
              {codigos.map((c) => <span key={c}>{c}</span>)}
            </div>
            <button type="button" className="btn-secundario w-full" onClick={() => navigator.clipboard?.writeText(codigos.join("\n"))}>
              <Copy className="h-4 w-4" /> Copiar códigos
            </button>
            <button type="button" className="btn-primario w-full py-2.5" onClick={() => (window.location.href = destino)}>Ya los guardé, continuar</button>
          </div>
        )}
      </div>
      <p className="mt-6 text-center text-xs text-slate-400">© {new Date().getFullYear()} Servigpoder · Uso exclusivo del personal autorizado · Actividad auditada</p>
    </div>
  );
}

export default function LoginPage() {
  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-gradient-to-br from-[#0f2d5c] via-[#0c2750] to-[#081a38] px-4 py-10">
      <div className="pointer-events-none absolute -left-32 -top-32 h-96 w-96 rounded-full bg-sky-500/20 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-40 -right-24 h-[28rem] w-[28rem] rounded-full bg-indigo-500/20 blur-3xl" />
      <Suspense fallback={null}>
        <Formulario />
      </Suspense>
    </main>
  );
}
