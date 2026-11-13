"use client";

import { CheckCircle2, KeyRound, Loader2, PlugZap, Save, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Alerta } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";
import { usePermiso } from "@/lib/sesion";

type Config = {
  configurada: boolean; origen_clave: "panel" | "servidor" | ""; clave_final: string; modelo: string; modelo_costeo: string;
  modelo_servidor: string; modelo_vigente: string; modelo_costeo_vigente: string; proveedor: string; retencion_cero: boolean;
};
type Modelo = { id: string; nombre: string; contexto: number | null; precio_entrada: number | null; precio_salida: number | null; imagenes: boolean; archivos: boolean };

const usd = (v: number | null) => (v == null ? "—" : `US$${v.toLocaleString("es-CO", { maximumFractionDigits: 3 })}`);

/** Campo de modelo: se escribe o se elige de la lista de OpenRouter (con precio y si lee imágenes/PDF). */
function CampoModelo({ etiqueta, ayuda, valor, porDefecto, modelos, on }: {
  etiqueta: string; ayuda: string; valor: string; porDefecto: string; modelos: Modelo[]; on: (v: string) => void;
}) {
  const elegido = modelos.find((m) => m.id === (valor || porDefecto));
  return (
    <div>
      <label className="label">{etiqueta}</label>
      <input className="input font-mono" list="modelos-ia" placeholder={porDefecto} value={valor} onChange={(e) => on(e.target.value.trim())} />
      <p className="mt-1 text-xs text-slate-500">
        {ayuda}{!valor && <> Vacío = <span className="font-mono">{porDefecto}</span>.</>}
        {elegido && <> · Entrada {usd(elegido.precio_entrada)} y salida {usd(elegido.precio_salida)} por millón de tokens
          {elegido.imagenes ? " · lee imágenes" : " · no lee imágenes"}{elegido.archivos ? " y PDF" : ""}.</>}
      </p>
    </div>
  );
}

export default function IAPage() {
  const puede = usePermiso("ia.gestionar");
  const [c, setC] = useState<Config | null>(null);
  const [clave, setClave] = useState("");
  const [modelo, setModelo] = useState("");
  const [modeloCosteo, setModeloCosteo] = useState("");
  const [modelos, setModelos] = useState<Modelo[]>([]);
  const [ocupado, setOcupado] = useState<"" | "guardar" | "probar" | "borrar">("");
  const [msg, setMsg] = useState<{ tipo: "ok" | "error" | "info"; texto: string } | null>(null);

  function tomar(x: Config) { setC(x); setModelo(x.modelo); setModeloCosteo(x.modelo_costeo); setClave(""); }
  useEffect(() => {
    if (!puede) return;
    api<Config>("/ia/config").then(tomar).catch((e) => setMsg({ tipo: "error", texto: mensajeError(e) }));
    api<Modelo[]>("/ia/modelos").then(setModelos).catch(() => {});
  }, [puede]);
  const opciones = useMemo(() => modelos.map((m) => <option key={m.id} value={m.id}>{m.nombre}</option>), [modelos]);

  if (!puede) return <Alerta>No tiene permiso para configurar la inteligencia artificial.</Alerta>;
  if (!c) return msg ? <Alerta>{msg.texto}</Alerta> : <div className="flex items-center gap-2 text-sm text-slate-500"><Loader2 className="h-4 w-4 animate-spin" /> Cargando…</div>;
  const cambios = !!clave || modelo !== c.modelo || modeloCosteo !== c.modelo_costeo;

  async function guardar(borrar = false) {
    setMsg(null);
    setOcupado(borrar ? "borrar" : "guardar");
    try {
      tomar(await api<Config>("/ia/config", { method: "PUT", json: { api_key: borrar ? "" : clave, borrar_clave: borrar, modelo, modelo_costeo: modeloCosteo } }));
      setMsg({ tipo: "ok", texto: borrar ? "Clave borrada del panel." : "Configuración guardada." });
    } catch (e) { setMsg({ tipo: "error", texto: mensajeError(e) }); } finally { setOcupado(""); }
  }
  async function probar(cual: string) {
    setMsg(null);
    setOcupado("probar");
    try {
      const r = await api<{ modelo: string; respuesta: string; segundos: number }>("/ia/probar", { method: "POST", json: { modelo: cual } });
      setMsg({ tipo: "ok", texto: `Conexión correcta con ${r.modelo} (${r.segundos} s). Respondió: «${r.respuesta}»` });
    } catch (e) { setMsg({ tipo: "error", texto: mensajeError(e) }); } finally { setOcupado(""); }
  }

  return (
    <div className="max-w-3xl space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-marca-900">Inteligencia artificial</h1>
        <p className="text-sm text-slate-500">Agente de IA de la plataforma (OpenRouter): asistentes, chat de instructivos SIESA y costeos llenados desde archivos.</p>
      </div>
      {msg && <Alerta tipo={msg.tipo}>{msg.texto}</Alerta>}

      <section className="tarjeta space-y-4 p-5">
        <h2 className="flex items-center gap-2 font-semibold text-slate-800"><KeyRound className="h-4 w-4" /> Clave de la API</h2>
        <div className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm ${c.configurada ? "bg-green-50 text-green-800" : "bg-amber-50 text-amber-800"}`}>
          {c.configurada ? <CheckCircle2 className="h-4 w-4" /> : <PlugZap className="h-4 w-4" />}
          {c.origen_clave === "panel" && <>Clave guardada en el panel, termina en <b className="font-mono">…{c.clave_final}</b>.</>}
          {c.origen_clave === "servidor" && <>Se usa la clave del servidor (IA_API_KEY), termina en <b className="font-mono">…{c.clave_final}</b>. Si escribe una aquí, esta manda.</>}
          {!c.configurada && <>No hay clave: la IA está apagada en toda la plataforma.</>}
        </div>
        <div>
          <label className="label">{c.origen_clave === "panel" ? "Cambiar la clave" : "Clave de OpenRouter"}</label>
          <input className="input font-mono" type="password" autoComplete="new-password" placeholder="sk-or-v1-…" value={clave}
            onChange={(e) => setClave(e.target.value.trim())} />
          <p className="mt-1 text-xs text-slate-500">Se crea en openrouter.ai → Keys. Se guarda cifrada y no se vuelve a mostrar (solo los últimos 4 caracteres).
            Vacía = se conserva la actual.</p>
        </div>
        {c.origen_clave === "panel" && (
          <button className="btn-secundario text-red-700" disabled={!!ocupado} onClick={() => { if (confirm("¿Borrar la clave del panel?")) guardar(true); }}>
            <Trash2 className="h-4 w-4" /> Borrar la clave del panel
          </button>
        )}
      </section>

      <section className="tarjeta space-y-4 p-5">
        <h2 className="font-semibold text-slate-800">Modelos</h2>
        <datalist id="modelos-ia">{opciones}</datalist>
        <CampoModelo etiqueta="Modelo general" ayuda="Asistentes de Capacidad operativa, SERA 360 y chat de SIESA." valor={modelo}
          porDefecto={c.modelo_servidor} modelos={modelos} on={setModelo} />
        <CampoModelo etiqueta="Modelo para llenar costeos desde archivos" ayuda="Lee solicitudes, pliegos, Excel y fotos: conviene uno que lea imágenes y PDF."
          valor={modeloCosteo} porDefecto={modelo || c.modelo_servidor} modelos={modelos} on={setModeloCosteo} />
        <p className="text-xs text-slate-500">
          {modelos.length ? `${modelos.length} modelos disponibles en el proveedor: escriba para buscar.` : "Escriba el identificador del modelo, p. ej. anthropic/claude-opus-5."}
          {c.retencion_cero && " Solo se usan proveedores que no guardan los datos ni entrenan con ellos (retención cero): algunos modelos pueden no estar disponibles."}
        </p>
      </section>

      <div className="flex flex-wrap gap-2">
        <button className="btn-primario" disabled={!cambios || !!ocupado} onClick={() => guardar()}>
          {ocupado === "guardar" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Guardar
        </button>
        <button className="btn-secundario" disabled={!c.configurada || cambios || !!ocupado} onClick={() => probar("")}
          title={cambios ? "Guarde primero" : ""}>
          {ocupado === "probar" ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlugZap className="h-4 w-4" />} Probar el modelo general
        </button>
        {c.modelo_costeo_vigente !== c.modelo_vigente && (
          <button className="btn-secundario" disabled={!c.configurada || cambios || !!ocupado} onClick={() => probar(c.modelo_costeo_vigente)}>
            <PlugZap className="h-4 w-4" /> Probar el de costeos
          </button>
        )}
      </div>
    </div>
  );
}
