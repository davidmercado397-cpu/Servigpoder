"use client";

import { Loader2, PlugZap, Plus, Save, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Alerta, Titulo } from "@/components/ui";
import { api, mensajeError, subirArchivo } from "@/lib/api";
import { fechaHora, type Centro } from "@/lib/contabilidad";
import { usePermiso } from "@/lib/sesion";

type Modelo = { id: string; nombre: string; precio_entrada: number | null; precio_salida: number | null; imagenes: boolean; archivos: boolean };
type Config = {
  correo: string; clave_guardada: boolean; carpeta: string; ultima_lectura: string | null; ultimo_error: string;
  modelo: string; modelo_general: string; ia: boolean;
  empresa_nombre: string; empresa_nit: string; tipo_documento: string; prefijo: string; bodega: string; unidad: string;
  tipo_documento_ds: string; prefijo_ds: string; ultimo_fc: number | null; ultimo_ds: number | null;
};

export default function ConfiguracionContabilidad() {
  const puede = usePermiso("contabilidad.configurar");
  const [c, setC] = useState<Config | null>(null);
  const [clave, setClave] = useState("");
  const [centros, setCentros] = useState<Centro[]>([]);
  const [nuevoCentro, setNuevoCentro] = useState("");
  const [conteo, setConteo] = useState({ productos: 0, terceros: 0 });
  const [ocupado, setOcupado] = useState("");
  const [modelos, setModelos] = useState<Modelo[]>([]);
  const [msg, setMsg] = useState<{ tipo: "ok" | "error"; texto: string } | null>(null);
  const cuentas = useRef<HTMLInputElement>(null);
  const terceros = useRef<HTMLInputElement>(null);

  function recargar() {
    api<Config>("/contabilidad/config").then(setC).catch((e) => setMsg({ tipo: "error", texto: mensajeError(e) }));
    api<Centro[]>("/contabilidad/centros").then(setCentros).catch(() => {});
    api<{ productos: number; terceros: number }>("/contabilidad/resumen").then((r) => setConteo({ productos: r.productos, terceros: r.terceros })).catch(() => {});
  }
  useEffect(recargar, []);
  useEffect(() => { if (puede) api<Modelo[]>("/contabilidad/modelos").then(setModelos).catch(() => {}); }, [puede]);

  if (!c) return msg ? <Alerta>{msg.texto}</Alerta> : <p className="text-sm text-slate-500">Cargando…</p>;
  const set = (x: Partial<Config>) => setC({ ...c, ...x });
  const elegido = modelos.find((m) => m.id === (c.modelo || c.modelo_general));

  async function hacer(clave_: string, fn: () => Promise<string>) {
    setMsg(null);
    setOcupado(clave_);
    try { setMsg({ tipo: "ok", texto: await fn() }); } catch (e) { setMsg({ tipo: "error", texto: mensajeError(e) }); } finally { setOcupado(""); }
  }
  const guardar = () => hacer("guardar", async () => {
    setC(await api<Config>("/contabilidad/config", { method: "PUT", json: { ...c, clave } }));
    setClave("");
    return "Configuración guardada.";
  });
  const probar = () => hacer("probar", async () => {
    const r = await api<{ sin_leer: number }>("/contabilidad/config/probar", { method: "POST" });
    return `Conexión correcta con Gmail: hay ${r.sin_leer} correo(s) sin leer en «${c.carpeta}».`;
  });
  const importar = (ruta: string, f: File | undefined) => f && hacer(ruta, async () => {
    const r = await subirArchivo<{ cuentas?: number; terceros?: number }>(`/contabilidad/${ruta}/importar`, f);
    recargar();
    return r.cuentas != null ? `Se cargaron ${r.cuentas} cuentas.` : `Se cargaron ${r.terceros} terceros.`;
  });
  const agregarCentro = (nombre: string, activo = true, codigo = "") => hacer("centro", async () => {
    await api("/contabilidad/centros", { method: "PUT", json: { nombre, codigo, activo } });
    setNuevoCentro("");
    recargar();
    return `Centro de costos «${nombre}» guardado.`;
  });

  return (
    <div className="max-w-4xl space-y-5">
      <Titulo>Buzón y catálogos</Titulo>
      {msg && <Alerta tipo={msg.tipo}>{msg.texto}</Alerta>}

      <section className="tarjeta space-y-3 p-4">
        <h2 className="font-semibold text-slate-800">Buzón de Gmail</h2>
        <p className="text-sm text-slate-500">Las facturas que lleguen a este correo se registran cuando se da <b>«Revisar correo»</b> en Facturas recibidas. En la cuenta de Gmail: active la verificación en dos pasos y cree una
          <b> contraseña de aplicación</b> (Cuenta de Google → Seguridad → Contraseñas de aplicaciones); esa es la que va aquí, no la clave normal.
          Los correos y sus adjuntos no se guardan: se leen y quedan marcados como leídos.</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <div><label className="label">Correo</label><input className="input" disabled={!puede} value={c.correo} onChange={(e) => set({ correo: e.target.value.trim() })} placeholder="facturas.speed@gmail.com" /></div>
          <div><label className="label">Contraseña de aplicación {c.clave_guardada && <span className="text-xs text-green-700">(guardada)</span>}</label>
            <input className="input" type="password" autoComplete="new-password" disabled={!puede} value={clave} onChange={(e) => setClave(e.target.value)}
              placeholder={c.clave_guardada ? "Vacía = se conserva" : "16 letras"} /></div>
          <div><label className="label">Carpeta</label><input className="input" disabled={!puede} value={c.carpeta} onChange={(e) => set({ carpeta: e.target.value })} /></div>
        </div>
        <p className="text-xs text-slate-500">Última revisión: {fechaHora(c.ultima_lectura)}{c.ultimo_error ? ` · error: ${c.ultimo_error}` : ""}</p>
      </section>

      <section className="tarjeta space-y-3 p-4">
        <h2 className="font-semibold text-slate-800">Modelo de IA para las facturas</h2>
        <p className="text-sm text-slate-500">Usa la misma cuenta de OpenRouter de la plataforma (la clave está en Administración → Inteligencia artificial).
          Este modelo solo aplica a Contabilidad: lee las facturas que llegan solo en PDF y propone la cuenta, el centro de costos y las notas.</p>
        {!c.ia && <Alerta tipo="info">La IA no está configurada en la plataforma: sin ella, las cuentas se proponen solo con lo usado antes con cada proveedor.</Alerta>}
        <div className="max-w-xl">
          <label className="label">Modelo</label>
          <input className="input font-mono" list="modelos-contabilidad" disabled={!puede} placeholder={c.modelo_general} value={c.modelo}
            onChange={(e) => set({ modelo: e.target.value.trim() })} />
          <datalist id="modelos-contabilidad">{modelos.map((m) => <option key={m.id} value={m.id}>{m.nombre}</option>)}</datalist>
          <p className="mt-1 text-xs text-slate-500">
            {!c.modelo && <>Vacío = el modelo general de la plataforma (<span className="font-mono">{c.modelo_general}</span>). </>}
            {elegido && <>Entrada US${elegido.precio_entrada ?? "—"} y salida US${elegido.precio_salida ?? "—"} por millón de tokens · {elegido.archivos || elegido.imagenes
              ? "lee PDF e imágenes" : "no lee PDF: las facturas que lleguen sin XML no se podrán leer"}.</>}
          </p>
        </div>
      </section>

      <section className="tarjeta space-y-3 p-4">
        <h2 className="font-semibold text-slate-800">Datos del plano de World Office</h2>
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="sm:col-span-2"><label className="label">Empresa (como en World Office)</label><input className="input" disabled={!puede} value={c.empresa_nombre} onChange={(e) => set({ empresa_nombre: e.target.value })} /></div>
          <div><label className="label">NIT de la empresa</label><input className="input" disabled={!puede} value={c.empresa_nit} onChange={(e) => set({ empresa_nit: e.target.value })} />
            <p className="mt-1 text-xs text-slate-500">Las facturas a otro NIT quedan aparte para confirmar.</p></div>
          <div><label className="label">Facturas: tipo de documento</label><input className="input" disabled={!puede} value={c.tipo_documento} onChange={(e) => set({ tipo_documento: e.target.value })} /></div>
          <div><label className="label">Facturas: prefijo</label><input className="input" disabled={!puede} value={c.prefijo} onChange={(e) => set({ prefijo: e.target.value })} /></div>
          <div><label className="label">Facturas: último número usado en World Office</label>
            <input className="input" inputMode="numeric" disabled={!puede} value={c.ultimo_fc ?? ""} placeholder="Ej. 2608008"
              onChange={(e) => set({ ultimo_fc: e.target.value.replace(/\D/g, "") ? Number(e.target.value.replace(/\D/g, "")) : null })} /></div>
          <div><label className="label">Cuentas de cobro: tipo de documento</label><input className="input" disabled={!puede} value={c.tipo_documento_ds} onChange={(e) => set({ tipo_documento_ds: e.target.value })} /></div>
          <div><label className="label">Cuentas de cobro: prefijo</label><input className="input" disabled={!puede} value={c.prefijo_ds} onChange={(e) => set({ prefijo_ds: e.target.value })} /></div>
          <div><label className="label">Cuentas de cobro: último número usado en World Office</label>
            <input className="input" inputMode="numeric" disabled={!puede} value={c.ultimo_ds ?? ""} placeholder="Vacío = empieza en 001"
              onChange={(e) => set({ ultimo_ds: e.target.value.replace(/\D/g, "") ? Number(e.target.value.replace(/\D/g, "")) : null })} /></div>
          <p className="text-xs text-slate-500 sm:col-span-3">El número de documento es AAMM + consecutivo (2608009). El plano sigue desde el último número usado en el mismo
            mes de la fecha de cargue; en un mes nuevo empieza en 001.</p>
          <div><label className="label">Bodega</label><input className="input" disabled={!puede} value={c.bodega} onChange={(e) => set({ bodega: e.target.value })} /></div>
          <div><label className="label">Unidad de medida</label><input className="input" disabled={!puede} value={c.unidad} onChange={(e) => set({ unidad: e.target.value })} /></div>
        </div>
      </section>

      {puede && (
        <div className="flex flex-wrap gap-2">
          <button className="btn-primario" disabled={!!ocupado} onClick={guardar}>{ocupado === "guardar" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Guardar</button>
          <button className="btn-secundario" disabled={!!ocupado || !c.clave_guardada} onClick={probar} title={c.clave_guardada ? "" : "Guarde primero la contraseña"}>
            {ocupado === "probar" ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlugZap className="h-4 w-4" />} Probar conexión con Gmail</button>
        </div>
      )}

      <section className="tarjeta space-y-3 p-4">
        <h2 className="font-semibold text-slate-800">Catálogos de World Office</h2>
        <p className="text-sm text-slate-500">Los archivos se leen y se descartan; solo quedan los códigos y nombres.</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-lg border border-slate-200 p-3">
            <p className="font-medium">Cuentas / productos <span className="text-sm font-normal text-slate-500">({conteo.productos})</span></p>
            <p className="text-xs text-slate-500">Libro auxiliar o listado con filas «515515 PASAJES AEREOS». La IA propone la cuenta de cada producto de la factura.</p>
            {puede && <button className="btn-secundario mt-2" disabled={!!ocupado} onClick={() => cuentas.current?.click()}><Upload className="h-4 w-4" /> Cargar Excel</button>}
            <input ref={cuentas} type="file" accept=".xlsx" className="hidden" onChange={(e) => { importar("productos", e.target.files?.[0]); e.target.value = ""; }} />
          </div>
          <div className="rounded-lg border border-slate-200 p-3">
            <p className="font-medium">Proveedores (terceros) <span className="text-sm font-normal text-slate-500">({conteo.terceros})</span></p>
            <p className="text-xs text-slate-500">Listado de terceros de World Office. Avisa si llega una factura de un proveedor que no está creado.</p>
            {puede && <button className="btn-secundario mt-2" disabled={!!ocupado} onClick={() => terceros.current?.click()}><Upload className="h-4 w-4" /> Cargar Excel</button>}
            <input ref={terceros} type="file" accept=".xlsx" className="hidden" onChange={(e) => { importar("terceros", e.target.files?.[0]); e.target.value = ""; }} />
          </div>
        </div>
        <div>
          <p className="font-medium">Centros de costos</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {centros.map((x) => (
              <span key={x.id} className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm ring-1 ${x.activo ? "ring-slate-300" : "text-slate-400 ring-slate-200 line-through"}`}>
                {x.nombre}
                {puede && <button className="text-xs text-marca-700 hover:underline" onClick={() => agregarCentro(x.nombre, !x.activo, x.codigo)}>{x.activo ? "quitar" : "activar"}</button>}
              </span>
            ))}
          </div>
          {puede && (
            <div className="mt-2 flex gap-2">
              <input className="input w-64" placeholder="Nombre exacto en World Office" value={nuevoCentro} onChange={(e) => setNuevoCentro(e.target.value)} />
              <button className="btn-secundario" disabled={!nuevoCentro.trim() || !!ocupado} onClick={() => agregarCentro(nuevoCentro.trim())}><Plus className="h-4 w-4" /> Agregar</button>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
