"use client";

import { AlertTriangle, Loader2, MailCheck, Upload } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Alerta, Titulo } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";
import { ESTADOS, fecha, fechaHora, plata, type Estado, type Factura } from "@/lib/contabilidad";
import { usePermiso } from "@/lib/sesion";

type Resumen = {
  conteos: Partial<Record<Estado, number>>; ia: boolean; productos: number; terceros: number;
  buzon: { correo: string; activo: boolean; minutos: number; ultima_lectura: string | null; ultimo_error: string };
};

export default function FacturasRecibidas() {
  const revisar = usePermiso("contabilidad.revisar");
  const [estado, setEstado] = useState<Estado>("pendiente");
  const [resumen, setResumen] = useState<Resumen | null>(null);
  const [lista, setLista] = useState<Factura[] | null>(null);
  const [ocupado, setOcupado] = useState<"" | "buzon" | "cargar">("");
  const [msg, setMsg] = useState<{ tipo: "ok" | "error" | "info"; texto: string } | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const cargar = useCallback(() => {
    api<Resumen>("/contabilidad/resumen").then(setResumen).catch((e) => setMsg({ tipo: "error", texto: mensajeError(e) }));
    setLista(null);
    api<Factura[]>(`/contabilidad/facturas?estado=${estado}`).then(setLista).catch((e) => setMsg({ tipo: "error", texto: mensajeError(e) }));
  }, [estado]);
  useEffect(() => { cargar(); }, [cargar]);

  async function leerBuzon() {
    setMsg(null);
    setOcupado("buzon");
    try {
      const r = await api<{ correos: number; facturas: number }>("/contabilidad/buzon/leer", { method: "POST" });
      setMsg({ tipo: "ok", texto: r.correos ? `Se leyeron ${r.correos} correo(s) y llegaron ${r.facturas} factura(s) nueva(s).` : "No hay correos nuevos." });
      cargar();
    } catch (e) { setMsg({ tipo: "error", texto: mensajeError(e) }); } finally { setOcupado(""); }
  }
  async function subir(archivos: File[]) {
    if (!archivos.length) return;
    setMsg(null);
    setOcupado("cargar");
    try {
      const form = new FormData();
      archivos.slice(0, 10).forEach((a) => form.append("archivos", a));
      const r = await api<{ resultado: string; errores: string[] }>("/contabilidad/cargar", { method: "POST", body: form });
      setMsg({ tipo: r.errores.length ? "info" : "ok", texto: r.resultado });
      cargar();
    } catch (e) { setMsg({ tipo: "error", texto: mensajeError(e) }); } finally { setOcupado(""); }
  }

  const b = resumen?.buzon;
  return (
    <div className="space-y-4">
      <Titulo accion={revisar && (
        <div className="flex flex-wrap gap-2">
          <button className="btn-secundario" disabled={!!ocupado || !b?.correo} onClick={leerBuzon} title={b?.correo ? "" : "Configure el buzón primero"}>
            {ocupado === "buzon" ? <Loader2 className="h-4 w-4 animate-spin" /> : <MailCheck className="h-4 w-4" />} Leer el buzón ahora
          </button>
          <button className="btn-secundario" disabled={!!ocupado} onClick={() => input.current?.click()}>
            {ocupado === "cargar" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} Cargar facturas
          </button>
          <input ref={input} type="file" multiple accept=".zip,.xml,.pdf" className="hidden" onChange={(e) => { subir(Array.from(e.target.files ?? [])); e.target.value = ""; }} />
        </div>
      )}>Facturas recibidas</Titulo>

      {b && (
        <p className="-mt-4 text-sm text-slate-500">
          {b.correo ? <>Buzón <b>{b.correo}</b> · {b.activo ? `se lee cada ${b.minutos} min` : "lectura automática apagada"} · última lectura {fechaHora(b.ultima_lectura)}</>
            : <>El buzón de Gmail no está configurado: <Link className="text-marca-700 underline" href="/contabilidad/configuracion">configúrelo aquí</Link>. Mientras tanto puede cargar las facturas a mano.</>}
          {!resumen?.ia && " · La IA no está configurada: las cuentas se proponen solo con lo usado antes con cada proveedor."}
        </p>
      )}
      {b?.ultimo_error && <Alerta>Última lectura del buzón: {b.ultimo_error}</Alerta>}
      {resumen && !resumen.productos && <Alerta tipo="info">Cargue el catálogo de cuentas de World Office en Configuración para que la IA proponga la cuenta de cada producto.</Alerta>}
      {msg && <Alerta tipo={msg.tipo}>{msg.texto}</Alerta>}

      <div className="flex flex-wrap gap-1 border-b border-slate-200">
        {ESTADOS.map(([k, t]) => (
          <button key={k} onClick={() => setEstado(k)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${estado === k ? "border-marca-600 font-semibold text-marca-700" : "border-transparent text-slate-500 hover:text-slate-700"}`}>
            {t} <span className="ml-1 rounded-full bg-slate-100 px-1.5 text-xs text-slate-600">{resumen?.conteos[k] ?? 0}</span>
          </button>
        ))}
      </div>
      {estado === "aparte" && <p className="text-sm text-slate-500">Facturas a nombre de otra empresa o notas crédito/débito: confirme si se contabilizan («Incluir») o descártelas.</p>}
      {estado === "lista" && <p className="text-sm text-slate-500">Salen en el próximo plano. <Link className="text-marca-700 underline" href="/contabilidad/plano">Ir al plano</Link></p>}

      <div className="tarjeta overflow-x-auto">
        <table className="tabla text-sm">
          <thead><tr><th>Factura</th><th>Proveedor</th><th>Emisión</th><th className="text-right">Subtotal</th><th className="text-right">Total</th>
            <th>{estado === "contabilizada" ? "Documento WO" : "Revisión"}</th></tr></thead>
          <tbody>
            {lista === null && <tr><td colSpan={6} className="py-6 text-center text-slate-400">Cargando…</td></tr>}
            {lista?.length === 0 && <tr><td colSpan={6} className="py-6 text-center text-slate-400">No hay facturas en esta bandeja.</td></tr>}
            {lista?.map((f) => (
              <tr key={f.id} className="hover:bg-slate-50">
                <td><Link className="font-medium text-marca-700 hover:underline" href={`/contabilidad/facturas/${f.id}`}>{f.prefijo}{f.numero}</Link>
                  {f.leida_con === "ia" && <span className="ml-1 rounded bg-amber-100 px-1 text-xs text-amber-800">leída por IA</span>}
                  {f.tipo !== "factura" && <span className="ml-1 rounded bg-slate-200 px-1 text-xs">{f.tipo.replace("_", " ")}</span>}</td>
                <td><p>{f.emisor_nombre}</p><p className="text-xs text-slate-500">NIT {f.emisor_nit}{f.emisor_dv ? `-${f.emisor_dv}` : ""}</p></td>
                <td>{fecha(f.fecha_emision)}</td>
                <td className="text-right tabular-nums">{plata(f.subtotal)}</td>
                <td className="text-right tabular-nums">{plata(f.total)}</td>
                <td className="text-xs">
                  {estado === "contabilizada" ? <>{f.documento_numero} · {fecha(f.fecha_contable)}</>
                    : estado === "aparte" ? <span className="text-amber-800">{f.motivo_aparte}</span>
                      : f.faltantes.length ? <span className="text-amber-800">{f.faltantes.length} dato(s) por completar</span>
                        : <span className="text-green-700">Completa</span>}
                  {f.avisos.length > 0 && estado !== "contabilizada" && <AlertTriangle className="ml-1 inline h-3.5 w-3.5 text-amber-600" />}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
