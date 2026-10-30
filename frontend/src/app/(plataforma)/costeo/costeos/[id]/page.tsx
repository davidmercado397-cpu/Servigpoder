"use client";

import { ArrowLeft, Copy, Plus, Save, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Modal } from "@/components/costeo";
import { Alerta } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";
import { ESTADO_COSTEO, hoyISO, pct, pesos, type Cliente } from "@/lib/costeo";
import { usePermiso } from "@/lib/sesion";

type Servicio = { descripcion: string; puesto: string; cantidad: number; tarifa: number; hombres: number };
type Personal = { nombre: string; hombres: number; salario?: number | null; horas_extras: number; auxilio_transporte: boolean; auxilios_no_salariales: number; rodamiento: number };
type Elemento = { nombre: string; valor_unitario: number; cantidad: number; vida_util_meses?: number | null; entregas_anio?: number | null; tipo_item?: string };
type Datos = {
  duracion_meses: number; pct_nota_credito: number; pct_cupo_inversion: number; horas_bolsa_anual: number; donaciones: number;
  pct_comision_vendedor?: number | null;
  servicios: Servicio[]; personal: Personal[]; otros: Elemento[]; dotacion_tarifa: Elemento[]; dotacion_puesto: Elemento[];
};
type Resultado = {
  meses: number; tarifa_decreto: number; descuento_nota_credito: number; tarifa_neta: number; hombres_servicios: number; hombres_personal: number;
  costo_por_hombre: number; mfp: { pct_nota_credito: number; pct_cupo_inversion: number; pct_otros: number; pct_total: number; cupo_inversion_vp: number };
  bolsas: { publicidad: number; representacion: number; horas_anuales: number; valor_hora: number };
  comision: { pct: number; carga_prestacional: number; vendedor_total: number; director_total: number; pct_vendedor?: number; carga_vendedor?: number; vendedor_elegida?: boolean };
  facturacion: { aiu: number; iva: number; reteica: number; total_a_pagar: number };
  personal: { nombre: string; hombres: number; costo_hombre: number; costo_total: number; neto_hombre: number }[];
  costos: Record<string, number>; total_costos: number; antes_renta: number; margen_mensual: number; margen_por_hombre: number; margen_total: number;
  pct_margen: number; pct_rentabilidad_mensual?: number; pct_rentabilidad_total?: number; alertas: string[]; otros: { mensual: number }[]; dotacion_tarifa: { mensual: number }[]; dotacion_puesto: { mensual: number }[];
};
type Costeo = { id: number; cliente: Cliente; nombre: string; version: number; estado: string; datos: Datos; resultado: Resultado; mfp_id: number | null; parametros_aprobados: boolean };
type RangoComision = { id: number; hasta_pct: number | null; pct_comision: number; carga_prestacional: number };
type CatServicio = { id: number; descripcion: string; tarifa: number; hombres: number; activo: boolean };
type CatElemento = { id: number; grupo: string; nombre: string; valor_unitario: number; vida_util_meses: number | null; entregas_anio: number | null; por_hombre: boolean; activo: boolean };

const COSTOS: [string, string][] = [
  ["laboral", "Costo laboral"], ["dotacion_tarifa", "Dotación de la tarifa"], ["dotacion_puesto", "Dotación adicional del puesto"],
  ["horas_adicionales", "Bolsa de horas adicionales"], ["otros_directos", "Otros costos directos"], ["publicidad", "Publicidad"],
  ["cupo_inversion", "Cupo de inversión"], ["comisiones", "Comisiones vendedor y director"], ["donaciones", "Donaciones"],
  ["gasto_administrativo", "Gasto administrativo"], ["representacion", "Reserva de representación"], ["ica", "Industria y comercio"], ["renta", "Impuesto de renta"],
];
const TIPOS_MFP: [string, string][] = [["OTROS", "Otros"], ["ACCES_TOO", "Acces Too"], ["EQUIPOS", "Equipos"], ["NOTA_CREDITO", "Nota crédito / bono tarifa"],
  ["CAPACITACION", "Capacitación"], ["REINVERSION", "Reinversión"]];
const VACIO: Datos = { duracion_meses: 12, pct_nota_credito: 0, pct_cupo_inversion: 0, horas_bolsa_anual: 0, donaciones: 0, servicios: [], personal: [], otros: [], dotacion_tarifa: [], dotacion_puesto: [] };
const n = (v: string) => (v === "" ? 0 : Number(v));

export default function EditorCosteo() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const costear = usePermiso("costeo.costear");
  const gestionar = usePermiso("costeo.mfp");
  const configurar = usePermiso("costeo.configurar");
  const [c, setC] = useState<Costeo | null>(null);
  const [d, setD] = useState<Datos>(VACIO);
  const [nombre, setNombre] = useState("");
  const [r, setR] = useState<Resultado | null>(null);
  const [servicios, setServicios] = useState<CatServicio[]>([]);
  const [catalogo, setCatalogo] = useState<CatElemento[]>([]);
  const [rangos, setRangos] = useState<RangoComision[]>([]);
  const [cambios, setCambios] = useState(false);
  const [crearMfp, setCrearMfp] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "ok" | "error"; texto: string } | null>(null);
  const primera = useRef(true);

  const cargar = useCallback(() => api<Costeo>(`/costeo/costeos/${id}`).then((x) => {
    setC(x);
    setD({ ...VACIO, ...x.datos });
    setNombre(x.nombre);
    setR(x.resultado);
    setCambios(false);
    primera.current = true;
  }).catch((e) => setMsg({ tipo: "error", texto: mensajeError(e) })), [id]);
  useEffect(() => {
    cargar();
    api<CatServicio[]>("/costeo/servicios").then((s) => setServicios(s.filter((x) => x.activo))).catch(() => {});
    api<CatElemento[]>("/costeo/catalogo").then((s) => setCatalogo(s.filter((x) => x.activo))).catch(() => {});
    api<RangoComision[]>("/costeo/comisiones").then(setRangos).catch(() => {});
  }, [cargar]);

  // Resultado en vivo mientras se edita
  useEffect(() => {
    if (!c || c.estado === "aprobado") return;
    if (primera.current) { primera.current = false; return; }
    const t = setTimeout(() => api<Resultado>("/costeo/costeos/calcular", { method: "POST", json: d }).then(setR).catch(() => {}), 400);
    return () => clearTimeout(t);
  }, [d, c]);

  if (!c || !r) return msg ? <Alerta>{msg.texto}</Alerta> : <p className="text-sm text-slate-500">Cargando…</p>;
  const editable = costear && c.estado !== "aprobado";
  const cambiar = (x: Partial<Datos>) => { setD({ ...d, ...x }); setCambios(true); };
  const hombres = d.personal.reduce((s, p) => s + Number(p.hombres || 0), 0) || r.hombres_servicios;
  // Comisiones que se pueden escoger: las de los rangos configurados (y la ya guardada, si ese rango cambió)
  const comisiones = [...new Set([...rangos.map((x) => x.pct_comision), ...(d.pct_comision_vendedor != null ? [d.pct_comision_vendedor] : [])])].sort((a, b) => b - a);

  async function guardar() {
    try {
      const x = await api<Costeo>(`/costeo/costeos/${id}`, { method: "PUT", json: { cliente_id: c!.cliente.id, nombre, datos: d } });
      setC(x); setR(x.resultado); setCambios(false);
      setMsg({ tipo: "ok", texto: "Costeo guardado." });
    } catch (e) { setMsg({ tipo: "error", texto: mensajeError(e) }); }
  }
  async function estado(e: string) {
    try {
      if (cambios) await guardar();
      const x = await api<Costeo>(`/costeo/costeos/${id}/estado`, { method: "POST", json: { estado: e } });
      setC(x); setR(x.resultado);
      setMsg({ tipo: "ok", texto: e === "aprobado" ? "Costeo aprobado: quedan congelados los parámetros con que se aprobó." : `Costeo ${e}.` });
    } catch (err) { setMsg({ tipo: "error", texto: mensajeError(err) }); }
  }
  async function version() {
    try {
      const x = await api<{ id: number }>(`/costeo/costeos/${id}/version`, { method: "POST" });
      router.push(`/costeo/costeos/${x.id}`);
    } catch (e) { setMsg({ tipo: "error", texto: mensajeError(e) }); }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <Link href="/costeo/costeos" className="text-slate-400 hover:text-slate-600"><ArrowLeft className="h-5 w-5" /></Link>
        <div>
          {editable ? <input className="input text-lg font-bold" value={nombre} onChange={(e) => { setNombre(e.target.value); setCambios(true); }} />
            : <h1 className="text-2xl font-bold text-marca-900">{c.nombre}</h1>}
          <p className="text-sm text-slate-500">{c.cliente.nombre} · versión {c.version}</p>
        </div>
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${ESTADO_COSTEO[c.estado]}`}>{c.estado}</span>
        <div className="ml-auto flex flex-wrap gap-2">
          {editable && <button className="btn-primario" disabled={!cambios} onClick={guardar}><Save className="h-4 w-4" /> Guardar</button>}
          {editable && c.estado === "borrador" && <button className="btn-secundario" onClick={() => estado("enviado")}>Marcar enviado</button>}
          {c.estado !== "aprobado" && (gestionar || configurar) && <button className="btn-secundario" onClick={() => estado("aprobado")}>Aprobar</button>}
          {editable && c.estado === "enviado" && <button className="btn-secundario" onClick={() => estado("rechazado")}>Rechazado</button>}
          {c.estado === "aprobado" && !c.mfp_id && gestionar && <button className="btn-primario" onClick={() => setCrearMfp(true)}>Crear MFP del contrato</button>}
          {c.mfp_id && <Link className="btn-secundario" href={`/costeo/mfp/${c.mfp_id}`}>Ver MFP</Link>}
          {costear && <button className="btn-secundario" onClick={version}><Copy className="h-4 w-4" /> Nueva versión</button>}
        </div>
      </div>
      {msg && <Alerta tipo={msg.tipo}>{msg.texto}</Alerta>}
      {c.estado === "aprobado" && <Alerta tipo="info">Costeo aprobado: no se edita y conserva los parámetros con que se aprobó. Para cambiarlo, cree una nueva versión.</Alerta>}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <div className="space-y-5">
          <Seccion titulo="Condiciones">
            <div className="grid gap-3 sm:grid-cols-3">
              <Num etiqueta="Duración (meses)" v={d.duracion_meses} on={(v) => cambiar({ duracion_meses: v })} off={!editable} />
              <Num etiqueta="Nota crédito (%)" v={+(d.pct_nota_credito * 100).toFixed(4)} on={(v) => cambiar({ pct_nota_credito: v / 100 })} off={!editable} />
              <Num etiqueta="Cupo de inversión (%)" v={+(d.pct_cupo_inversion * 100).toFixed(4)} on={(v) => cambiar({ pct_cupo_inversion: v / 100 })} off={!editable} />
              <Num etiqueta="Horas de obsequio por año" v={d.horas_bolsa_anual} on={(v) => cambiar({ horas_bolsa_anual: v })} off={!editable} />
              <Num etiqueta="Donaciones (total)" v={d.donaciones} on={(v) => cambiar({ donaciones: v })} off={!editable} />
              <div><label className="label">Comisión del vendedor</label>
                <select className="input" disabled={!editable} value={d.pct_comision_vendedor ?? ""}
                  onChange={(e) => cambiar({ pct_comision_vendedor: e.target.value === "" ? null : Number(e.target.value) })}>
                  <option value="">Automática según % MFP ({pct(r.comision.pct, 1)})</option>
                  {comisiones.map((x) => <option key={x} value={x}>{pct(x, 1)}</option>)}
                </select></div>
            </div>
          </Seccion>

          <Seccion titulo="Servicios" accion={editable && (
            <select className="input w-72" value="" onChange={(e) => {
              const s = servicios.find((x) => String(x.id) === e.target.value);
              if (s) cambiar({ servicios: [...d.servicios, { descripcion: s.descripcion, puesto: "", cantidad: 1, tarifa: s.tarifa, hombres: s.hombres }] });
            }}><option value="">+ Agregar servicio…</option>{servicios.map((s) => <option key={s.id} value={s.id}>{s.descripcion.slice(0, 80)}</option>)}</select>
          )}>
            <Tabla columnas={["Servicio", "Puesto", "Cant.", "Tarifa", "Hombres", ""]}>
              {d.servicios.map((s, i) => {
                const set = (x: Partial<Servicio>) => cambiar({ servicios: d.servicios.map((y, j) => (j === i ? { ...y, ...x } : y)) });
                return (
                  <tr key={i}>
                    <td className="max-w-xs text-xs">{s.descripcion}</td>
                    <td><input className="input w-28" disabled={!editable} value={s.puesto} onChange={(e) => set({ puesto: e.target.value })} /></td>
                    <td><input className="input w-16" type="number" disabled={!editable} value={s.cantidad} onChange={(e) => set({ cantidad: n(e.target.value) })} /></td>
                    <td><input className="input w-32" type="number" disabled={!editable} value={s.tarifa} onChange={(e) => set({ tarifa: n(e.target.value) })} /></td>
                    <td><input className="input w-20" type="number" min={0} step="0.5" disabled={!editable} value={s.hombres} onChange={(e) => set({ hombres: n(e.target.value) })} /></td>
                    <td>{editable && <Quitar on={() => cambiar({ servicios: d.servicios.filter((_, j) => j !== i) })} />}</td>
                  </tr>
                );
              })}
            </Tabla>
          </Seccion>

          <Seccion titulo="Personal" accion={editable && <button className="btn-secundario" onClick={() => cambiar({ personal: [...d.personal, { nombre: "Guarda", hombres: 0, horas_extras: 0, auxilio_transporte: true, auxilios_no_salariales: 0, rodamiento: 0 }] })}><Plus className="h-4 w-4" /> Tipo de personal</button>}>
            <p className="mb-2 text-xs text-slate-500">Las horas extras son el valor negociado con el cliente por hombre al mes. Salario vacío = salario mínimo.</p>
            <Tabla columnas={["Tipo", "Hombres", "Salario", "Horas extras", "Aux. transporte", "Aux. no salariales", "Rodamiento", "Costo por hombre", ""]}>
              {d.personal.map((p, i) => {
                const set = (x: Partial<Personal>) => cambiar({ personal: d.personal.map((y, j) => (j === i ? { ...y, ...x } : y)) });
                return (
                  <tr key={i}>
                    <td><input className="input w-28" disabled={!editable} value={p.nombre} onChange={(e) => set({ nombre: e.target.value })} /></td>
                    <td><input className="input w-20" type="number" min={0} step="0.5" disabled={!editable} value={p.hombres} onChange={(e) => set({ hombres: n(e.target.value) })} /></td>
                    <td><input className="input w-28" type="number" disabled={!editable} placeholder="Mínimo" value={p.salario ?? ""} onChange={(e) => set({ salario: e.target.value === "" ? null : n(e.target.value) })} /></td>
                    <td><input className="input w-28" type="number" disabled={!editable} value={p.horas_extras} onChange={(e) => set({ horas_extras: n(e.target.value) })} /></td>
                    <td className="text-center"><input type="checkbox" disabled={!editable} checked={p.auxilio_transporte} onChange={(e) => set({ auxilio_transporte: e.target.checked })} /></td>
                    <td><input className="input w-24" type="number" disabled={!editable} value={p.auxilios_no_salariales} onChange={(e) => set({ auxilios_no_salariales: n(e.target.value) })} /></td>
                    <td><input className="input w-24" type="number" disabled={!editable} value={p.rodamiento} onChange={(e) => set({ rodamiento: n(e.target.value) })} /></td>
                    <td className="text-right tabular-nums">{pesos(r.personal[i]?.costo_hombre)}</td>
                    <td>{editable && <Quitar on={() => cambiar({ personal: d.personal.filter((_, j) => j !== i) })} />}</td>
                  </tr>
                );
              })}
            </Tabla>
          </Seccion>

          <Elementos titulo="Otros costos directos (MFP)" ayuda="Se reparten en la vida útil indicada (vacía = los meses del contrato). Al crear la MFP, cada uno queda como un ítem del tipo elegido."
            filas={d.otros} catalogo={catalogo.filter((x) => x.grupo === "otros")} hombres={hombres} editable={editable} conTipo
            on={(f) => cambiar({ otros: f })} mensuales={r.otros?.map((x) => x.mensual) ?? []} />
          <Elementos titulo="Dotación de la tarifa" ayuda="Con entregas al año: valor × cantidad × entregas ÷ 12. Con vida útil: valor × cantidad ÷ vida útil."
            filas={d.dotacion_tarifa} catalogo={catalogo.filter((x) => x.grupo === "dotacion_tarifa")} hombres={hombres} editable={editable}
            on={(f) => cambiar({ dotacion_tarifa: f })} mensuales={r.dotacion_tarifa?.map((x) => x.mensual) ?? []} />
          <Elementos titulo="Dotación adicional del puesto" ayuda="Elementos que no hacen parte de la tarifa mínima, repartidos en su vida útil."
            filas={d.dotacion_puesto} catalogo={catalogo.filter((x) => x.grupo === "dotacion_puesto")} hombres={hombres} editable={editable}
            on={(f) => cambiar({ dotacion_puesto: f })} mensuales={r.dotacion_puesto?.map((x) => x.mensual) ?? []} />
        </div>

        <PanelResultado r={r} />
      </div>
      {crearMfp && (
        <Modal titulo="Crear la MFP del contrato" onCerrar={() => setCrearMfp(false)}>
          <CrearMfp costeoId={c.id} onCreada={(mid) => router.push(`/costeo/mfp/${mid}`)} />
        </Modal>
      )}
    </div>
  );
}

function PanelResultado({ r }: { r: Resultado }) {
  const fila = (t: string, v: string, fuerte = false, rojo = false) => (
    <div className={`flex justify-between gap-3 py-0.5 ${fuerte ? "font-semibold" : ""} ${rojo ? "text-red-700" : ""}`}><span>{t}</span><span className="tabular-nums">{v}</span></div>
  );
  return (
    <div className="space-y-3 xl:sticky xl:top-4 xl:self-start">
      <div className={`tarjeta p-4 ${r.margen_mensual < 0 ? "border-red-300" : ""}`}>
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Margen mensual del negocio</p>
        <p className={`text-2xl font-bold ${r.margen_mensual < 0 ? "text-red-700" : "text-green-700"}`}>{pesos(r.margen_mensual)} <span className="text-base">({pct(r.pct_margen)})</span></p>
        <p className="text-sm text-slate-600">Por hombre {pesos(r.margen_por_hombre)} · total del contrato {pesos(r.margen_total)}</p>
        <div className="mt-2 grid grid-cols-2 gap-2 border-t border-slate-100 pt-2">
          <div><p className="text-xs text-slate-500">Rentabilidad mensual</p><p className="font-semibold tabular-nums">{pct(r.pct_rentabilidad_mensual ?? r.pct_margen)}</p></div>
          <div><p className="text-xs text-slate-500">Rentabilidad total del contrato</p><p className="font-semibold tabular-nums">{pct(r.pct_rentabilidad_total ?? r.pct_margen)}</p></div>
        </div>
        {r.alertas.length > 0 && <ul className="mt-2 space-y-0.5 text-xs text-red-700">{r.alertas.map((a) => <li key={a}>• {a}</li>)}</ul>}
      </div>
      <div className="tarjeta p-4 text-sm">
        {fila("Tarifa decreto", pesos(r.tarifa_decreto))}
        {fila(`Nota crédito (${pct(r.mfp.pct_nota_credito)})`, `−${pesos(r.descuento_nota_credito)}`)}
        {fila("Tarifa neta", pesos(r.tarifa_neta), true)}
        <div className="my-2 border-t border-slate-100" />
        {COSTOS.map(([k, t]) => r.costos[k] ? <div key={k}>{fila(t, pesos(r.costos[k]))}</div> : null)}
        {fila("Costos totales", pesos(r.total_costos), true)}
        <div className="my-2 border-t border-slate-100" />
        {fila("MFP total", pct(r.mfp.pct_total), true)}
        <p className="text-xs text-slate-500">Nota crédito {pct(r.mfp.pct_nota_credito)} · cupo {pct(r.mfp.pct_cupo_inversion)} · otros {pct(r.mfp.pct_otros)}</p>
        <p className="text-xs text-slate-500">Cupo de inversión (valor presente): {pesos(r.mfp.cupo_inversion_vp)}</p>
        <p className="text-xs text-slate-500">Comisión vendedor {pct(r.comision.pct_vendedor ?? r.comision.pct, 1)}{r.comision.vendedor_elegida ? " (escogida)" : ""} · carga {r.comision.carga_vendedor ?? r.comision.carga_prestacional} · {pesos(r.comision.vendedor_total)}</p>
        <p className="text-xs text-slate-500">Comisión director {pct(r.comision.pct, 1)} (según % MFP) · carga {r.comision.carga_prestacional} · {pesos(r.comision.director_total)}</p>
        <p className="text-xs text-slate-500">Bolsas del contrato: publicidad {pesos(r.bolsas.publicidad)} · representación {pesos(r.bolsas.representacion)}
          {r.bolsas.horas_anuales ? ` · ${r.bolsas.horas_anuales} h/año a ${pesos(r.bolsas.valor_hora)} la hora` : ""}</p>
        <div className="my-2 border-t border-slate-100" />
        <p className="text-xs text-slate-500">Hombres: servicios {r.hombres_servicios} · personal {r.hombres_personal} · costo promedio {pesos(r.costo_por_hombre)}</p>
        <p className="text-xs text-slate-500">Factura: AIU {pesos(r.facturacion.aiu)} · IVA {pesos(r.facturacion.iva)} · total a pagar {pesos(r.facturacion.total_a_pagar)}</p>
      </div>
    </div>
  );
}

function Elementos({ titulo, ayuda, filas, catalogo, hombres, editable, on, mensuales, conTipo }: {
  titulo: string; ayuda: string; filas: Elemento[]; catalogo: CatElemento[]; hombres: number; editable: boolean; on: (f: Elemento[]) => void;
  mensuales: number[]; conTipo?: boolean;
}) {
  return (
    <Seccion titulo={titulo} accion={editable && (
      <div className="flex gap-2">
        <select className="input w-64" value="" onChange={(e) => {
          const x = catalogo.find((c) => String(c.id) === e.target.value);
          if (x) on([...filas, { nombre: x.nombre, valor_unitario: x.valor_unitario, cantidad: x.por_hombre ? hombres : 1, vida_util_meses: x.vida_util_meses, entregas_anio: x.entregas_anio,
            ...(conTipo ? { tipo_item: x.nombre.includes("ACCES") ? "ACCES_TOO" : x.nombre.includes("BONO TARIFA") ? "NOTA_CREDITO" : "OTROS" } : {}) }]);
        }}><option value="">+ Del catálogo…</option>{catalogo.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}</select>
        <button className="btn-secundario" onClick={() => on([...filas, { nombre: "", valor_unitario: 0, cantidad: 1, ...(conTipo ? { tipo_item: "OTROS" } : {}) }])}><Plus className="h-4 w-4" /></button>
      </div>
    )}>
      <p className="mb-2 text-xs text-slate-500">{ayuda}</p>
      <Tabla columnas={["Elemento", "Valor unitario", "Cantidad", "Vida útil (meses)", "Entregas al año", ...(conTipo ? ["Ítem de MFP"] : []), "Mensual", ""]}>
        {filas.map((x, i) => {
          const set = (y: Partial<Elemento>) => on(filas.map((z, j) => (j === i ? { ...z, ...y } : z)));
          return (
            <tr key={i}>
              <td><input className="input w-48" disabled={!editable} value={x.nombre} onChange={(e) => set({ nombre: e.target.value })} /></td>
              <td><input className="input w-28" type="number" disabled={!editable} value={x.valor_unitario} onChange={(e) => set({ valor_unitario: n(e.target.value) })} /></td>
              <td><input className="input w-16" type="number" step="any" disabled={!editable} value={x.cantidad} onChange={(e) => set({ cantidad: n(e.target.value) })} /></td>
              <td><input className="input w-20" type="number" disabled={!editable} placeholder="Contrato" value={x.vida_util_meses ?? ""} onChange={(e) => set({ vida_util_meses: e.target.value === "" ? null : n(e.target.value) })} /></td>
              <td><input className="input w-20" type="number" disabled={!editable} value={x.entregas_anio ?? ""} onChange={(e) => set({ entregas_anio: e.target.value === "" ? null : n(e.target.value) })} /></td>
              {conTipo && (
                <td><select className="input w-36" disabled={!editable} value={x.tipo_item ?? "OTROS"} onChange={(e) => set({ tipo_item: e.target.value })}>
                  {TIPOS_MFP.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></td>
              )}
              <td className="text-right tabular-nums">{pesos(mensuales[i])}</td>
              <td>{editable && <Quitar on={() => on(filas.filter((_, j) => j !== i))} />}</td>
            </tr>
          );
        })}
      </Tabla>
    </Seccion>
  );
}

function CrearMfp({ costeoId, onCreada }: { costeoId: number; onCreada: (id: number) => void }) {
  const [f, setF] = useState({ numero: "", contrato: "", fecha_inicio: hoyISO() });
  const [error, setError] = useState("");
  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-600">Con el contrato firmado, se crea la MFP con lo pactado en este costeo: nota crédito, cupo de inversión (reinversión), otros costos
        directos, bolsa de horas y las bolsas internas de publicidad y representación.</p>
      <div className="grid gap-3 sm:grid-cols-3">
        <div><label className="label">Número de MFP</label><input className="input" value={f.numero} onChange={(e) => setF({ ...f, numero: e.target.value })} /></div>
        <div><label className="label">Contrato</label><input className="input" value={f.contrato} onChange={(e) => setF({ ...f, contrato: e.target.value })} /></div>
        <div><label className="label">Inicio</label><input className="input" type="date" value={f.fecha_inicio} onChange={(e) => setF({ ...f, fecha_inicio: e.target.value })} /></div>
      </div>
      {error && <Alerta>{error}</Alerta>}
      <div className="flex justify-end">
        <button className="btn-primario" disabled={!f.numero} onClick={async () => {
          try { onCreada((await api<{ mfp_id: number }>(`/costeo/costeos/${costeoId}/crear-mfp`, { method: "POST", json: f })).mfp_id); } catch (e) { setError(mensajeError(e)); }
        }}>Crear MFP</button>
      </div>
    </div>
  );
}

function Seccion({ titulo, accion, children }: { titulo: string; accion?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="tarjeta p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2"><h2 className="font-semibold text-slate-800">{titulo}</h2>{accion}</div>
      {children}
    </section>
  );
}

function Tabla({ columnas, children }: { columnas: string[]; children: React.ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead><tr className="text-left text-xs text-slate-500">{columnas.map((c, i) => <th key={i} className="pb-1 pr-2 font-medium">{c}</th>)}</tr></thead>
        <tbody className="[&_td]:py-1 [&_td]:pr-2">{children}</tbody>
      </table>
    </div>
  );
}

function Num({ etiqueta, v, on, off }: { etiqueta: string; v: number; on: (v: number) => void; off?: boolean }) {
  return <div><label className="label">{etiqueta}</label><input className="input" type="number" disabled={off} value={v} onChange={(e) => on(n(e.target.value))} /></div>;
}

function Quitar({ on }: { on: () => void }) {
  return <button title="Quitar" onClick={on}><Trash2 className="h-4 w-4 text-slate-400 hover:text-red-600" /></button>;
}
