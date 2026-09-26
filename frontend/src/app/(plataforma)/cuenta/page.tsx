"use client";

import { CheckCircle2, KeyRound, ShieldAlert, ShieldCheck } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { BarraPlataforma } from "@/components/barra-plataforma";
import { Alerta } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";
import { useSesion } from "@/lib/sesion";

function Cuenta() {
  const sesion = useSesion();
  const forzado = useSearchParams().get("forzado") === "1" || sesion.debe_cambiar_password;
  const [actual, setActual] = useState("");
  const [nueva, setNueva] = useState("");
  const [confirmar, setConfirmar] = useState("");
  const [msg, setMsg] = useState<{ tipo: "ok" | "error"; texto: string } | null>(null);
  const [pwdCodigos, setPwdCodigos] = useState("");
  const [codigos, setCodigos] = useState<string[]>([]);
  const [msgCodigos, setMsgCodigos] = useState("");

  async function cambiar(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    if (nueva !== confirmar) return setMsg({ tipo: "error", texto: "La confirmación no coincide con la nueva contraseña" });
    try {
      await api("/auth/cambiar-password", { method: "POST", json: { actual, nueva } });
      setActual(""); setNueva(""); setConfirmar("");
      if (forzado) {
        window.location.href = "/";
        return;
      }
      setMsg({ tipo: "ok", texto: "Contraseña actualizada. Sus otras sesiones abiertas se cerraron." });
    } catch (err) {
      setMsg({ tipo: "error", texto: mensajeError(err) });
    }
  }

  async function regenerar(e: React.FormEvent) {
    e.preventDefault();
    setMsgCodigos("");
    try {
      setCodigos(await api<string[]>("/auth/mfa/codigos-recuperacion", { method: "POST", json: { password: pwdCodigos } }));
      setPwdCodigos("");
    } catch (err) {
      setMsgCodigos(mensajeError(err));
    }
  }

  const contenido = (
    <main className="mx-auto max-w-3xl space-y-6 px-4 py-8 lg:px-8">
      <h1 className="text-2xl font-bold text-marca-900">Seguridad de mi cuenta</h1>
      {forzado && (
        <Alerta>
          <span className="inline-flex items-center gap-2"><ShieldAlert className="h-4 w-4" /> Su contraseña es temporal (la asignó un administrador). Debe cambiarla para continuar.</span>
        </Alerta>
      )}

      <section className="tarjeta p-5">
        <h2 className="mb-4 flex items-center gap-2 font-semibold"><KeyRound className="h-5 w-5 text-marca-600" /> Cambiar contraseña</h2>
        <form onSubmit={cambiar} className="grid gap-4 md:grid-cols-3">
          <div><label className="label">Contraseña actual</label><input className="input" type="password" autoComplete="current-password" value={actual} onChange={(e) => setActual(e.target.value)} required /></div>
          <div><label className="label">Nueva contraseña</label><input className="input" type="password" autoComplete="new-password" minLength={10} value={nueva} onChange={(e) => setNueva(e.target.value)} required /></div>
          <div><label className="label">Confirmar nueva</label><input className="input" type="password" autoComplete="new-password" minLength={10} value={confirmar} onChange={(e) => setConfirmar(e.target.value)} required /></div>
          <p className="text-xs text-slate-500 md:col-span-3">Mínimo 10 caracteres, combinando letras y números. No reutilice contraseñas de otros sistemas.</p>
          {msg && <div className="md:col-span-3"><Alerta tipo={msg.tipo}>{msg.texto}</Alerta></div>}
          <div className="md:col-span-3"><button className="btn-primario">Cambiar contraseña</button></div>
        </form>
      </section>

      {!forzado && (
        <section className="tarjeta p-5">
          <h2 className="mb-2 flex items-center gap-2 font-semibold"><ShieldCheck className="h-5 w-5 text-marca-600" /> Verificación en dos pasos</h2>
          <p className="flex items-center gap-2 text-sm text-slate-600">
            <CheckCircle2 className="h-4 w-4 text-[#0ca30c]" /> Activa con su app Authenticator.
          </p>
          <p className="mt-2 text-sm text-slate-600">
            Si cambió de celular o perdió sus códigos de recuperación, genere unos nuevos (los anteriores dejan de funcionar).
            Si ya no tiene acceso a la app, pida al administrador que restablezca su verificación.
          </p>
          <form onSubmit={regenerar} className="mt-4 flex flex-wrap items-end gap-3">
            <div><label className="label">Confirme su contraseña</label><input className="input w-64" type="password" autoComplete="current-password" value={pwdCodigos} onChange={(e) => setPwdCodigos(e.target.value)} required /></div>
            <button className="btn-secundario">Generar códigos de recuperación nuevos</button>
          </form>
          {msgCodigos && <div className="mt-3"><Alerta>{msgCodigos}</Alerta></div>}
          {codigos.length > 0 && (
            <div className="mt-4 space-y-2">
              <Alerta tipo="info">Guárdelos en un lugar seguro: no se volverán a mostrar. Cada uno sirve una sola vez.</Alerta>
              <div className="grid grid-cols-2 gap-2 rounded-lg bg-slate-100 p-3 font-mono text-sm md:grid-cols-5">
                {codigos.map((c) => <span key={c}>{c}</span>)}
              </div>
            </div>
          )}
        </section>
      )}
    </main>
  );

  return (
    <div className="min-h-screen bg-slate-50">
      {forzado ? (
        <header className="bg-gradient-to-r from-[#0f2d5c] to-[#081a38] px-6 py-4 font-bold text-white">Plataforma Servigpoder</header>
      ) : (
        <BarraPlataforma />
      )}
      {contenido}
    </div>
  );
}

export default function CuentaPage() {
  return (
    <Suspense fallback={null}>
      <Cuenta />
    </Suspense>
  );
}
