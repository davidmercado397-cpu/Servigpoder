"use client";

import { BookOpen, FileText, Loader2, RotateCcw, SearchX, Send } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api, mensajeError } from "@/lib/api";
import { usePermiso } from "@/lib/sesion";

type Fuente = { n: number; documento: string; archivo: string; pagina: number; seccion: string; modulo: string; fecha: string | null; extracto: string };
type Mensaje = { rol: "usuario" | "asistente"; texto: string; fuentes?: Fuente[]; encontrado?: boolean; error?: boolean };
type Estado = { configurado: boolean; documentos: number; paginas: number; usadas_hoy: number; limite_diario: number };
type Respuesta = { texto: string; encontrado: boolean; fuentes: Fuente[]; usadas_hoy: number; limite_diario: number };

const CLAVE = "siesa-chat";

export default function ChatSiesa() {
  const gestionar = usePermiso("siesa.gestionar");
  const [mensajes, setMensajes] = useState<Mensaje[]>([]);
  const [texto, setTexto] = useState("");
  const [cargando, setCargando] = useState(false);
  const [estado, setEstado] = useState<Estado | null>(null);
  const [modulos, setModulos] = useState<string[]>([]);
  const [modulo, setModulo] = useState("");
  const fin = useRef<HTMLDivElement>(null);
  const entrada = useRef<HTMLTextAreaElement>(null);

  // La conversación vive solo en esta pestaña del navegador
  useEffect(() => {
    try {
      const guardada = sessionStorage.getItem(CLAVE);
      if (guardada) setMensajes(JSON.parse(guardada));
    } catch {}
    api<Estado>("/siesa/estado").then(setEstado).catch(() => {});
    api<string[]>("/siesa/modulos").then(setModulos).catch(() => {});
    try {
      setModulo(sessionStorage.getItem(`${CLAVE}-modulo`) ?? "");
    } catch {}
  }, []);

  useEffect(() => {
    try {
      sessionStorage.setItem(CLAVE, JSON.stringify(mensajes.slice(-30)));
    } catch {}
    fin.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensajes]);

  async function enviar() {
    const q = texto.trim();
    if (!q || cargando) return;
    const historial = [...mensajes.filter((m) => !m.error), { rol: "usuario" as const, texto: q }];
    setMensajes([...mensajes, { rol: "usuario", texto: q }]);
    setTexto("");
    setCargando(true);
    try {
      const r = await api<Respuesta>("/siesa/chat", {
        method: "POST",
        json: { mensajes: historial.slice(-10).map(({ rol, texto }) => ({ rol, texto })), modulo: modulo || null },
      });
      setMensajes((m) => [...m, { rol: "asistente", texto: r.texto, fuentes: r.fuentes, encontrado: r.encontrado }]);
      setEstado((e) => (e ? { ...e, usadas_hoy: r.usadas_hoy } : e));
    } catch (e) {
      setMensajes((m) => [...m, { rol: "asistente", texto: mensajeError(e), error: true }]);
    } finally {
      setCargando(false);
      entrada.current?.focus();
    }
  }

  const vacia = estado && estado.documentos === 0;

  return (
    <div className="mx-auto flex h-[calc(100vh-7.5rem)] max-w-4xl flex-col">
      <div className="flex-1 space-y-4 overflow-y-auto pb-4">
        {estado && !estado.configurado && (
          <div className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
            El chat aún no está activado: el administrador debe configurar la clave <b>IA_API_KEY</b> en el servidor.
          </div>
        )}
        {mensajes.length === 0 && (
          <div className="flex flex-col items-center px-4 pt-10 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-amber-100 text-amber-700"><BookOpen className="h-7 w-7" /></div>
            <h1 className="mt-4 text-2xl font-bold text-marca-900">Instructivos de SIESA</h1>
            <p className="mt-2 max-w-xl text-slate-600">
              Pregunte cómo hacer un proceso en SIESA. Respondo <b>solo</b> con lo que dicen los instructivos cargados y le indico el
              documento y la página de donde sale cada dato. Si algo no está en los instructivos, se lo digo.
            </p>
            {estado && (
              <p className="mt-3 text-sm text-slate-500">
                {vacia ? "Aún no hay instructivos cargados." : `Base de conocimiento: ${estado.documentos} instructivos, ${estado.paginas.toLocaleString("es-CO")} páginas.`}{" "}
                {(vacia || gestionar) && <Link href="/siesa/documentos" className="font-medium text-marca-600 hover:underline">{gestionar ? "Administrar instructivos" : "Ver instructivos"}</Link>}
              </p>
            )}
          </div>
        )}

        {mensajes.map((m, i) =>
          m.rol === "usuario" ? (
            <div key={i} className="ml-auto max-w-[80%] rounded-2xl rounded-br-sm bg-marca-600 px-4 py-2.5 text-white">{m.texto}</div>
          ) : (
            <div key={i} className="mr-auto max-w-[90%]">
              <div className={`rounded-2xl rounded-bl-sm px-4 py-3 shadow-sm ${m.error ? "bg-red-50 text-red-700" : m.encontrado === false ? "bg-slate-100 text-slate-700" : "bg-white text-slate-800"}`}>
                {m.encontrado === false && <SearchX className="mb-1 h-4 w-4 text-slate-500" />}
                <div className="prose-asistente text-sm"><ReactMarkdown>{m.texto}</ReactMarkdown></div>
              </div>
              {m.fuentes && m.fuentes.length > 0 && (
                <div className="mt-2 space-y-1.5">
                  <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Fuentes</p>
                  {m.fuentes.map((f) => (
                    <details key={f.n} className="rounded-lg border border-slate-200 bg-white text-sm">
                      <summary className="flex cursor-pointer items-center gap-2 px-3 py-1.5 text-slate-700">
                        <span className="rounded bg-amber-100 px-1.5 text-xs font-semibold text-amber-800">[{f.n}]</span>
                        <FileText className="h-4 w-4 shrink-0 text-slate-400" />
                        <span className="min-w-0 truncate">
                          {f.modulo && <span className="text-slate-500">{f.modulo} · </span>}{f.documento}
                          {f.seccion && <span className="text-slate-500"> › {f.seccion}</span>}
                        </span>
                        <span className="shrink-0 text-xs text-slate-500">
                          · pág. {f.pagina}{f.fecha ? ` · ${new Date(f.fecha + "T12:00:00").toLocaleDateString("es-CO")}` : ""}
                        </span>
                      </summary>
                      <p className="whitespace-pre-line border-t border-slate-100 px-3 py-2 text-xs text-slate-600">{f.extracto}</p>
                    </details>
                  ))}
                </div>
              )}
            </div>
          ),
        )}
        {cargando && (
          <div className="mr-auto flex items-center gap-2 rounded-2xl bg-white px-4 py-2.5 text-sm text-slate-500 shadow-sm">
            <Loader2 className="h-4 w-4 animate-spin" /> Buscando en los instructivos…
          </div>
        )}
        <div ref={fin} />
      </div>

      {modulos.length > 0 && (
        <div className="mb-2 flex items-center gap-2 text-sm text-slate-600">
          <label htmlFor="modulo-chat">Buscar en:</label>
          <select id="modulo-chat" className="input w-56 py-1" value={modulo}
            onChange={(e) => { setModulo(e.target.value); try { sessionStorage.setItem(`${CLAVE}-modulo`, e.target.value); } catch {} }}>
            <option value="">Todos los módulos</option>
            {modulos.map((m) => <option key={m} value={m}>Solo {m}</option>)}
          </select>
        </div>
      )}
      <form onSubmit={(e) => { e.preventDefault(); enviar(); }} className="tarjeta flex items-end gap-2 p-2">
        <textarea ref={entrada} rows={1} value={texto} maxLength={2000} disabled={!!vacia}
          placeholder={vacia ? "Primero hay que cargar los instructivos" : "Escriba su pregunta sobre SIESA…"}
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enviar(); } }}
          className="max-h-40 min-h-[2.5rem] flex-1 resize-none bg-transparent px-2 py-2 text-sm focus:outline-none" />
        {mensajes.length > 0 && (
          <button type="button" title="Nueva conversación" onClick={() => setMensajes([])} className="rounded-lg p-2 text-slate-500 hover:bg-slate-100">
            <RotateCcw className="h-5 w-5" />
          </button>
        )}
        <button className="btn-primario inline-flex items-center gap-1.5" disabled={cargando || !texto.trim()}>
          <Send className="h-4 w-4" /> Enviar
        </button>
      </form>
      <p className="mt-1.5 text-center text-xs text-slate-400">
        Respuestas basadas solo en los instructivos cargados{estado ? ` · ${estado.usadas_hoy} de ${estado.limite_diario} preguntas hoy` : ""}.
      </p>
    </div>
  );
}
