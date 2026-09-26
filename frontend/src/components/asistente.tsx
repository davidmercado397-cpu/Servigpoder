"use client";

import { Bot, Loader2, RotateCcw, Send, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api, mensajeError } from "@/lib/api";

type Mensaje = { rol: "usuario" | "asistente"; texto: string; error?: boolean };
type Estado = { configurado: boolean; modelo: string; datos_personales: boolean; usadas_hoy: number; limite_diario: number };
type Respuesta = { texto: string; herramientas: string[]; usadas_hoy: number; limite_diario: number };

const CLAVE = "asistente-conversacion";
const SUGERENCIAS = [
  "¿De dónde sale el porcentaje de cobertura del mes?",
  "¿Cuáles son los 5 puestos con más horas descubiertas y por qué?",
  "¿Qué cubrimientos están pendientes para nómina?",
  "Explícame cómo se calculan los hombres esperados de un 4x2",
];

export function Asistente() {
  const pathname = usePathname();
  const search = useSearchParams();
  const [abierto, setAbierto] = useState(false);
  const [mensajes, setMensajes] = useState<Mensaje[]>([]);
  const [texto, setTexto] = useState("");
  const [cargando, setCargando] = useState(false);
  const [estado, setEstado] = useState<Estado | null>(null);
  const fin = useRef<HTMLDivElement>(null);

  // La conversación vive solo en esta pestaña del navegador (se borra al cerrarla)
  useEffect(() => {
    try {
      const guardada = sessionStorage.getItem(CLAVE);
      if (guardada) setMensajes(JSON.parse(guardada));
    } catch {}
  }, []);

  useEffect(() => {
    try {
      sessionStorage.setItem(CLAVE, JSON.stringify(mensajes.slice(-20)));
    } catch {}
    fin.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensajes]);

  useEffect(() => {
    if (abierto && !estado) api<Estado>("/capacidad/asistente/estado").then(setEstado).catch(() => {});
  }, [abierto, estado]);

  async function enviar(pregunta: string) {
    const q = pregunta.trim();
    if (!q || cargando) return;
    const historial: Mensaje[] = [...mensajes.filter((m) => !m.error), { rol: "usuario", texto: q }];
    setMensajes([...mensajes, { rol: "usuario", texto: q }]);
    setTexto("");
    setCargando(true);
    try {
      const qs = search.toString();
      const r = await api<Respuesta>("/capacidad/asistente", {
        method: "POST",
        json: { mensajes: historial.slice(-12).map(({ rol, texto }) => ({ rol, texto })), pantalla: pathname + (qs ? `?${qs}` : "") },
      });
      setMensajes((m) => [...m, { rol: "asistente", texto: r.texto }]);
      setEstado((e) => (e ? { ...e, usadas_hoy: r.usadas_hoy, limite_diario: r.limite_diario } : e));
    } catch (e) {
      setMensajes((m) => [...m, { rol: "asistente", texto: mensajeError(e), error: true }]);
    } finally {
      setCargando(false);
    }
  }

  return (
    <>
      {!abierto && (
        <button
          onClick={() => setAbierto(true)}
          className="fixed bottom-5 right-5 z-40 flex items-center gap-2 rounded-full bg-gradient-to-r from-marca-600 to-indigo-600 px-4 py-3 text-sm font-medium text-white shadow-lg shadow-marca-900/30 transition hover:scale-105"
          aria-label="Abrir asistente"
        >
          <Sparkles className="h-4 w-4" /> Pregúntale al asistente
        </button>
      )}

      {abierto && (
        <section className="fixed bottom-5 right-5 z-40 flex h-[min(640px,calc(100vh-2.5rem))] w-[min(420px,calc(100vw-2.5rem))] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
          <header className="flex items-center gap-3 bg-gradient-to-r from-[#0f2d5c] to-[#174c99] px-4 py-3 text-white">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/15"><Bot className="h-5 w-5" /></div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold">Asistente de análisis</p>
              <p className="truncate text-[11px] text-sky-200">Explica de dónde salen los datos · uso interno y confidencial</p>
            </div>
            {mensajes.length > 0 && (
              <button onClick={() => setMensajes([])} className="rounded p-1 text-sky-200 hover:bg-white/10 hover:text-white" title="Nueva conversación" aria-label="Nueva conversación">
                <RotateCcw className="h-4 w-4" />
              </button>
            )}
            <button onClick={() => setAbierto(false)} className="rounded p-1 text-sky-200 hover:bg-white/10 hover:text-white" aria-label="Cerrar asistente">
              <X className="h-4 w-4" />
            </button>
          </header>

          <div className="flex-1 space-y-3 overflow-y-auto bg-slate-50 p-4 text-sm">
            {estado && !estado.configurado && (
              <div className="rounded-lg bg-amber-50 p-3 text-amber-900">
                El asistente aún no está activado: el administrador debe configurar la clave <b>ANTHROPIC_API_KEY</b> en el servidor.
              </div>
            )}
            {mensajes.length === 0 && (
              <div className="space-y-2">
                <p className="text-slate-600">Pregúntame sobre la cobertura, la matriz, los cubrimientos o cualquier cifra de los tableros. Consulto los datos reales antes de responder.</p>
                {SUGERENCIAS.map((s) => (
                  <button key={s} onClick={() => enviar(s)} className="block w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-left text-slate-700 transition hover:border-marca-600 hover:text-marca-700">
                    {s}
                  </button>
                ))}
              </div>
            )}
            {mensajes.map((m, i) =>
              m.rol === "usuario" ? (
                <div key={i} className="ml-8 rounded-2xl rounded-br-sm bg-marca-600 px-3 py-2 text-white">{m.texto}</div>
              ) : (
                <div key={i} className={`mr-4 rounded-2xl rounded-bl-sm px-3 py-2 shadow-sm ${m.error ? "bg-red-50 text-red-700" : "bg-white text-slate-800"}`}>
                  <div className="prose-asistente">
                    <ReactMarkdown
                      components={{
                        a: ({ href, children }) =>
                          href?.startsWith("/") ? (
                            <Link href={href} className="font-medium text-marca-600 underline">{children}</Link>
                          ) : (
                            <span>{children}</span>
                          ),
                      }}
                    >
                      {m.texto}
                    </ReactMarkdown>
                  </div>
                </div>
              ),
            )}
            {cargando && (
              <div className="mr-4 flex items-center gap-2 rounded-2xl bg-white px-3 py-2 text-slate-500 shadow-sm">
                <Loader2 className="h-4 w-4 animate-spin" /> Consultando los datos…
              </div>
            )}
            <div ref={fin} />
          </div>

          <form onSubmit={(e) => { e.preventDefault(); enviar(texto); }} className="border-t border-slate-200 bg-white p-3">
            <div className="flex items-end gap-2">
              <textarea
                className="input max-h-32 min-h-[42px] flex-1 resize-none"
                rows={1}
                maxLength={4000}
                placeholder="Escriba su pregunta…"
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enviar(texto); } }}
              />
              <button className="btn-primario h-[42px] px-3" disabled={cargando || !texto.trim()} aria-label="Enviar">
                <Send className="h-4 w-4" />
              </button>
            </div>
            {estado && (
              <p className="mt-1.5 text-[11px] text-slate-400">
                {estado.usadas_hoy}/{estado.limite_diario} preguntas hoy · Las respuestas pueden contener errores: verifique en la pantalla enlazada.
              </p>
            )}
          </form>
        </section>
      )}
    </>
  );
}
