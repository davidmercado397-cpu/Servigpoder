"use client";

import { ImageUp, Loader2, RotateCcw, Save, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Alerta } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";
import { LogoMarca, estiloFondo, useMarca, variables, type Marca } from "@/lib/marca";
import { usePermiso, useSesion } from "@/lib/sesion";

type Tipo = "logo" | "favicon" | "fondo";
const CAMPOS = ["nombre", "subtitulo", "color_primario", "color_acento", "color_barra", "color_barra_fin", "login_fondo", "login_color", "login_oscurecer"] as const;

export default function MarcaPage() {
  const puede = usePermiso("marca.gestionar");
  const { recargar } = useMarca();
  const { empresas, empresa_actual } = useSesion();
  // Marca que se edita: "" = la general (pantalla de ingreso y empresas sin marca propia) o el código de una empresa
  const [destino, setDestino] = useState<string>(empresa_actual ?? "");
  const [marca, setMarca] = useState<Marca | null>(null); // como está guardada
  const [f, setF] = useState<Marca | null>(null);
  const [guardando, setGuardando] = useState(false);
  const [subiendo, setSubiendo] = useState<Tipo | null>(null);
  const [msg, setMsg] = useState<{ tipo: "ok" | "error"; texto: string } | null>(null);
  const q = `?empresa=${encodeURIComponent(destino)}`;
  const nombreDestino = destino ? empresas.find((e) => e.codigo === destino)?.nombre ?? destino : "General";

  useEffect(() => {
    setMarca(null);
    setMsg(null);
    api<Marca>(`/marca?empresa=${encodeURIComponent(destino)}`).then((m) => { setMarca(m); setF(m); })
      .catch((e) => setMsg({ tipo: "error", texto: mensajeError(e) }));
  }, [destino]);

  if (!puede) return <Alerta>No tiene permiso para editar la marca.</Alerta>;
  if (!f || !marca) {
    return msg ? <Alerta>{msg.texto}</Alerta>
      : <div className="flex items-center gap-2 text-sm text-slate-500"><Loader2 className="h-4 w-4 animate-spin" /> Cargando marca…</div>;
  }
  const cambios = CAMPOS.some((k) => f[k] !== marca[k]);
  const cambiar = <K extends keyof Marca>(k: K, v: Marca[K]) => setF({ ...f, [k]: v });

  /** Tras un cambio: el formulario toma lo guardado y la plataforma se repinta (si es la marca que se está viendo). */
  async function aplicar(m: Marca, soloImagenes = false) {
    setMarca(m);
    setF((actual) => (soloImagenes && actual
      ? { ...actual, logo: m.logo, favicon: m.favicon, fondo: m.fondo, version: m.version, propia: m.propia, login_fondo: m.login_fondo }
      : m));
    await recargar();
  }

  async function guardar() {
    setMsg(null);
    setGuardando(true);
    try {
      const formulario = f as Marca; // ya cargado: la página no llega aquí sin él
      const datos = Object.fromEntries(CAMPOS.map((k) => [k, formulario[k]]));
      const m = await api<Marca>(`/marca${q}`, { method: "PUT", json: datos });
      await aplicar(m);
      setMsg({ tipo: "ok", texto: `Marca de ${nombreDestino} guardada (los demás usuarios la verán al recargar).` });
    } catch (e) {
      setMsg({ tipo: "error", texto: mensajeError(e) });
    } finally {
      setGuardando(false);
    }
  }

  async function subir(tipo: Tipo, archivo: File) {
    setMsg(null);
    setSubiendo(tipo);
    try {
      const form = new FormData();
      form.append("archivo", archivo);
      const m = await api<Marca>(`/marca/imagen/${tipo}${q}`, { method: "POST", body: form });
      // Solo cambian las imágenes (y el tipo de fondo si fue el fondo); lo demás sigue como se está editando
      await aplicar(m, true);
    } catch (e) {
      setMsg({ tipo: "error", texto: mensajeError(e) });
    } finally {
      setSubiendo(null);
    }
  }

  async function quitar(tipo: Tipo) {
    if (!confirm(`¿Quitar ${tipo === "logo" ? "el logo" : tipo === "favicon" ? "el favicon" : "la imagen de fondo"}?`)) return;
    try {
      const m = await api<Marca>(`/marca/imagen/${tipo}${q}`, { method: "DELETE" });
      await aplicar(m, true);
    } catch (e) {
      setMsg({ tipo: "error", texto: mensajeError(e) });
    }
  }

  async function restablecer() {
    const pregunta = destino
      ? `¿Quitar la marca propia de ${nombreDestino}? Volverá a verse con la marca general.`
      : "¿Volver a la marca de fábrica? Se quitan el logo, el favicon y el fondo generales, y los colores vuelven a los originales.";
    if (!confirm(pregunta)) return;
    try {
      const m = await api<Marca>(`/marca/restablecer${q}`, { method: "POST" });
      await aplicar(m);
      setMsg({ tipo: "ok", texto: destino ? `${nombreDestino} vuelve a usar la marca general.` : "Marca general restablecida a los valores de fábrica." });
    } catch (e) {
      setMsg({ tipo: "error", texto: mensajeError(e) });
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <h1 className="text-2xl font-bold text-marca-900">Marca</h1>
          <p className="text-sm text-slate-500">Nombre, colores, logo, favicon y fondo de la pantalla de ingreso, en general o por empresa.</p>
        </div>
        <div className="ml-auto flex flex-wrap gap-2">
          {(!destino || marca.propia) && (
            <button className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-sm text-slate-500 hover:bg-slate-100" onClick={restablecer}>
              <RotateCcw className="h-4 w-4" /> {destino ? "Usar la marca general" : "Valores de fábrica"}
            </button>
          )}
          {cambios && <button className="btn-secundario" onClick={() => setF(marca)}>Descartar cambios</button>}
          <button className="btn-primario inline-flex items-center gap-1.5" disabled={!cambios || guardando} onClick={guardar}>
            <Save className="h-4 w-4" /> {guardando ? "Guardando…" : "Guardar"}
          </button>
        </div>
      </div>

      <div className="tarjeta flex flex-wrap items-center gap-3 p-4">
        <span className="text-sm font-medium text-slate-700">Marca de</span>
        <div className="flex flex-wrap gap-1.5">
          {[{ codigo: "", nombre: "General" }, ...empresas].map((e) => (
            <button key={e.codigo} disabled={cambios && destino !== e.codigo}
              title={cambios && destino !== e.codigo ? "Guarde o descarte los cambios antes de cambiar de marca" : undefined}
              onClick={() => setDestino(e.codigo)}
              className={`rounded-full border px-3 py-1 text-sm disabled:opacity-40 ${destino === e.codigo ? "border-marca-600 bg-marca-50 font-medium text-marca-800" : "border-slate-300 text-slate-600 hover:bg-slate-50"}`}>
              {e.nombre}
            </button>
          ))}
        </div>
        <p className="w-full text-xs text-slate-500">
          {!destino
            ? "La general se ve en la pantalla de ingreso de quien aún no ha elegido empresa y en las empresas sin marca propia."
            : marca.propia
              ? `${nombreDestino} tiene marca propia: se ve al trabajar con esta empresa y en la pantalla de ingreso de quien la usó por última vez. Lo que no cargue (logo, favicon o fondo) se toma de la general.`
              : `${nombreDestino} usa la marca general. Al guardar o subir una imagen aquí, se crea su marca propia.`}
        </p>
      </div>
      {msg && <Alerta tipo={msg.tipo}>{msg.texto}</Alerta>}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <div className="space-y-5">
          <Seccion titulo="Identidad">
            <div className="grid gap-4 sm:grid-cols-2">
              <Campo etiqueta="Nombre de la plataforma">
                <input className="input" maxLength={80} value={f.nombre} onChange={(e) => cambiar("nombre", e.target.value)} />
              </Campo>
              <Campo etiqueta="Subtítulo">
                <input className="input" maxLength={80} placeholder="Opcional" value={f.subtitulo} onChange={(e) => cambiar("subtitulo", e.target.value)} />
              </Campo>
            </div>
          </Seccion>

          <Seccion titulo="Logo y favicon">
            <div className="grid gap-4 sm:grid-cols-2">
              <Imagen titulo="Logo" ayuda="PNG con fondo transparente, horizontal o cuadrado. Se ajusta a 800×400 px máximo."
                imagen={f.logo} subiendo={subiendo === "logo"} onSubir={(a) => subir("logo", a)} onQuitar={() => quitar("logo")}
                vista={<div className="flex h-16 items-center justify-center rounded-md bg-gradient-to-r from-(--barra-desde) to-(--barra-hasta) px-3"><LogoMarca alto={40} marca={f} /></div>} />
              <Imagen titulo="Favicon" ayuda="Ícono de la pestaña del navegador. Imagen cuadrada (PNG, JPG o ICO); se ajusta a 64×64 px."
                imagen={f.favicon} subiendo={subiendo === "favicon"} onSubir={(a) => subir("favicon", a)} onQuitar={() => quitar("favicon")}
                vista={
                  <div className="flex h-16 items-center justify-center gap-2 rounded-md bg-slate-100 px-3 text-xs text-slate-600">
                    <span className="flex items-center gap-1.5 rounded-t-md border border-b-0 border-slate-300 bg-white px-2 py-1.5">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      {f.favicon ? <img src={f.favicon.url} alt="" className="h-4 w-4" /> : <span className="h-4 w-4 rounded bg-slate-300" />}
                      <span className="max-w-[9rem] truncate">{f.nombre}</span>
                    </span>
                  </div>
                } />
            </div>
          </Seccion>

          <Seccion titulo="Colores">
            <div className="grid gap-4 sm:grid-cols-2">
              <Color etiqueta="Color principal" ayuda="Botones, enlaces y resaltados" valor={f.color_primario} onChange={(v) => cambiar("color_primario", v)} />
              <Color etiqueta="Color de acento" ayuda="Subtítulos y detalles sobre la barra" valor={f.color_acento} onChange={(v) => cambiar("color_acento", v)} />
              <Color etiqueta="Barra y menú: inicio" ayuda="Degradado de la barra superior y del menú lateral" valor={f.color_barra} onChange={(v) => cambiar("color_barra", v)} />
              <Color etiqueta="Barra y menú: final" valor={f.color_barra_fin} onChange={(v) => cambiar("color_barra_fin", v)} />
            </div>
          </Seccion>

          <Seccion titulo="Fondo de la pantalla de ingreso">
            <div className="flex flex-wrap gap-2">
              {([["degradado", "Degradado de la barra"], ["color", "Color sólido"], ["imagen", "Imagen"]] as const).map(([v, t]) => (
                <label key={v} className={`cursor-pointer rounded-lg border px-3 py-1.5 text-sm ${f.login_fondo === v ? "border-marca-600 bg-marca-50 font-medium text-marca-800" : "border-slate-300"}`}>
                  <input type="radio" className="sr-only" checked={f.login_fondo === v} onChange={() => cambiar("login_fondo", v)} /> {t}
                </label>
              ))}
            </div>
            {f.login_fondo === "color" && (
              <div className="mt-4 max-w-xs"><Color etiqueta="Color de fondo" valor={f.login_color} onChange={(v) => cambiar("login_color", v)} /></div>
            )}
            {f.login_fondo === "imagen" && (
              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <Imagen titulo="Imagen de fondo" ayuda="Foto horizontal (JPG o PNG). Se ajusta a 2560 px de ancho máximo."
                  imagen={f.fondo} subiendo={subiendo === "fondo"} onSubir={(a) => subir("fondo", a)} onQuitar={() => quitar("fondo")}
                  vista={f.fondo ? <div className="h-16 rounded-md bg-cover bg-center" style={{ backgroundImage: `url(${f.fondo.url})` }} /> : null} />
                <Campo etiqueta={`Oscurecer la imagen: ${f.login_oscurecer} %`}>
                  <input type="range" min={0} max={85} step={5} className="w-full accent-marca-600" value={f.login_oscurecer}
                    onChange={(e) => cambiar("login_oscurecer", Number(e.target.value))} />
                  <p className="mt-1 text-xs text-slate-500">Más oscuro = el formulario y el nombre se leen mejor sobre la foto.</p>
                </Campo>
              </div>
            )}
          </Seccion>
        </div>

        <VistaPrevia m={f} />
      </div>
    </div>
  );
}

function VistaPrevia({ m }: { m: Marca }) {
  // Las variables de la marca se aplican solo dentro de la vista previa hasta guardar
  const vars = variables(m) as React.CSSProperties;
  return (
    <div className="space-y-3 xl:sticky xl:top-4 xl:self-start" style={vars}>
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Vista previa</p>
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-slate-50 shadow-sm">
        <div className="flex items-center gap-3 bg-gradient-to-r from-(--barra-desde) via-(--barra-medio) to-(--barra-hasta) px-4 py-3 text-white">
          <LogoMarca alto={32} marca={m} />
          <div className="leading-tight">
            <p className="text-sm font-bold">{m.nombre || "—"}</p>
            {m.subtitulo && <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-acento-300/80">{m.subtitulo}</p>}
          </div>
          <span className="ml-auto flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-acento-400 to-marca-600 text-[10px] font-bold">AB</span>
        </div>
        <div className="flex">
          <div className="w-28 shrink-0 space-y-1 bg-gradient-to-b from-(--barra-desde) to-(--barra-hasta) p-2 text-[11px] text-slate-300">
            <p className="relative rounded bg-white/10 px-2 py-1 text-white"><span className="absolute left-0 top-1 h-4 w-0.5 rounded bg-acento-400" />Inicio</p>
            <p className="px-2 py-1">Reportes</p>
            <p className="px-2 py-1">Configuración</p>
          </div>
          <div className="flex-1 space-y-2 p-4">
            <p className="text-lg font-bold text-marca-900">Título de una página</p>
            <p className="text-xs text-slate-600">Texto con un <span className="font-medium text-marca-600 underline">enlace</span> y una etiqueta <span className="rounded-full bg-marca-50 px-2 py-0.5 text-marca-700">activa</span>.</p>
            <div className="flex gap-2">
              <span className="btn-primario px-3 py-1.5 text-xs">Botón principal</span>
              <span className="btn-secundario px-3 py-1.5 text-xs">Secundario</span>
            </div>
          </div>
        </div>
      </div>
      <div className="relative flex h-64 items-center justify-center overflow-hidden rounded-xl shadow-sm" style={estiloFondo(m)}>
        <div className="w-56 rounded-xl bg-white/95 p-4 text-center shadow-xl">
          <div className="mb-2 flex justify-center"><LogoMarca alto={36} marca={m} /></div>
          <p className="text-sm font-bold text-slate-800">{m.nombre || "—"}</p>
          <div className="mt-3 space-y-1.5">
            <div className="h-6 rounded border border-slate-200 bg-white" />
            <div className="h-6 rounded border border-slate-200 bg-white" />
            <div className="h-6 rounded bg-marca-600" />
          </div>
        </div>
        <span className="absolute bottom-2 right-3 text-[10px] text-white/70">Pantalla de ingreso</span>
      </div>
    </div>
  );
}

function Seccion({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <section className="tarjeta p-5">
      <h2 className="mb-4 font-semibold text-slate-900">{titulo}</h2>
      {children}
    </section>
  );
}

function Campo({ etiqueta, children }: { etiqueta: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="label">{etiqueta}</label>
      {children}
    </div>
  );
}

function Color({ etiqueta, ayuda, valor, onChange }: { etiqueta: string; ayuda?: string; valor: string; onChange: (v: string) => void }) {
  const [texto, setTexto] = useState(valor);
  useEffect(() => setTexto(valor), [valor]);
  return (
    <div>
      <label className="label">{etiqueta}</label>
      <div className="flex items-center gap-2">
        <input type="color" aria-label={etiqueta} className="h-9 w-12 cursor-pointer rounded border border-slate-300 bg-white p-0.5" value={valor}
          onChange={(e) => onChange(e.target.value)} />
        <input className="input w-28 font-mono uppercase" maxLength={7} value={texto}
          onChange={(e) => { setTexto(e.target.value); if (/^#[0-9a-fA-F]{6}$/.test(e.target.value)) onChange(e.target.value.toLowerCase()); }} />
      </div>
      {ayuda && <p className="mt-1 text-xs text-slate-500">{ayuda}</p>}
    </div>
  );
}

function Imagen({ titulo, ayuda, imagen, subiendo, onSubir, onQuitar, vista }: {
  titulo: string; ayuda: string; imagen: Marca["logo"]; subiendo: boolean; onSubir: (a: File) => void; onQuitar: () => void; vista: React.ReactNode;
}) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <div className="space-y-2">
      <p className="label mb-0">{titulo}</p>
      {vista}
      <div className="flex flex-wrap items-center gap-2">
        <button className="btn-secundario inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs" disabled={subiendo} onClick={() => input.current?.click()}>
          {subiendo ? <Loader2 className="h-4 w-4 animate-spin" /> : <ImageUp className="h-4 w-4" />} {imagen && !imagen.heredada ? "Cambiar" : "Subir imagen"}
        </button>
        {imagen?.heredada && <span className="text-xs text-slate-400">De la marca general</span>}
        {imagen && !imagen.heredada && (
          <>
            <button className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-slate-500 hover:bg-red-50 hover:text-red-700" onClick={onQuitar}>
              <Trash2 className="h-3.5 w-3.5" /> Quitar
            </button>
            <span className="text-xs text-slate-400">{imagen.ancho}×{imagen.alto} · {Math.round(imagen.bytes / 1024)} KB</span>
          </>
        )}
        <input ref={input} type="file" hidden accept="image/png,image/jpeg,image/webp,image/x-icon,image/vnd.microsoft.icon,.ico"
          onChange={(e) => { const a = e.target.files?.[0]; e.target.value = ""; if (a) onSubir(a); }} />
      </div>
      <p className="text-xs text-slate-500">{ayuda}</p>
    </div>
  );
}
