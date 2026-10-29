"use client";

import { AlertTriangle, FileUp, Pencil, Plus, Search, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { BuscarEmpleado } from "@/components/buscar-empleado";
import { BuscarCie, ImportarAusentismo, Soportes } from "@/components/gestion-humana";
import { Paginador, metaDe, usePaginacion, type MetaPagina } from "@/components/paginacion";
import { Alerta, Insignia, Modal, Pestanas, Titulo } from "@/components/ui";
import { api, apiEnvelope, mensajeError } from "@/lib/api";
import {
  NOVEDADES, ORIGEN_CORTO, ORIGENES, SOPORTES, etiqueta, fechaCorta, qInicial, type Incapacidad, type ResumenIncapacidades,
} from "@/lib/gestion";
import { usePermiso } from "@/lib/sesion";

type Vista = "todas" | "vigentes" | "prolongadas";
type Formulario = {
  documento: string; nombre: string; puesto: string; novedad: string; origen: string; prorroga: boolean; desde: string; hasta: string;
  entidad: string; cie: string; diagnostico: string; soporte: string; observacion: string;
};

const VACIO: Formulario = { documento: "", nombre: "", puesto: "", novedad: "incapacidad", origen: "enfermedad_general", prorroga: false,
  desde: "", hasta: "", entidad: "", cie: "", diagnostico: "", soporte: "", observacion: "" };

const dias = (desde: string, hasta: string) =>
  desde && hasta ? Math.round((Date.parse(hasta) - Date.parse(desde)) / 86_400_000) + 1 : null;

function FormularioIncapacidad({ registro, onGuardado, onCancelar }: { registro: Incapacidad | null; onGuardado: (aviso: string) => void; onCancelar: () => void }) {
  const [f, setF] = useState<Formulario>(() => registro ? {
    documento: registro.documento, nombre: registro.empleado_id ? "" : registro.nombre, puesto: registro.puesto ?? "", novedad: registro.novedad,
    origen: registro.origen ?? "", prorroga: registro.prorroga, desde: registro.desde, hasta: registro.hasta, entidad: registro.entidad ?? "",
    cie: registro.cie?.replaceAll(",", ", ") ?? "", diagnostico: registro.diagnostico ?? "", soporte: registro.soporte ?? "", observacion: registro.observacion ?? "",
  } : VACIO);
  const [error, setError] = useState("");
  const cambiar = (c: Partial<Formulario>) => setF({ ...f, ...c });
  const n = dias(f.desde, f.hasta);

  async function guardar(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    const datos = { ...f, nombre: f.nombre || null, puesto: f.puesto || null, origen: f.origen || null, entidad: f.entidad || null,
      cie: f.cie || null, diagnostico: f.diagnostico || null, soporte: f.soporte || null, observacion: f.observacion || null };
    try {
      const r = await apiEnvelope(registro ? `/liquidador/incapacidades/${registro.id}` : "/liquidador/incapacidades",
        { method: registro ? "PUT" : "POST", json: datos });
      const aviso = (r.meta?.extra as { aviso?: string } | null)?.aviso;
      onGuardado(aviso ? `Incapacidad guardada. ${aviso}.` : "Incapacidad guardada.");
    } catch (err) {
      setError(mensajeError(err));
    }
  }

  return (
    <form onSubmit={guardar} className="tarjeta space-y-4 p-5">
      <div className="flex items-center">
        <h2 className="font-semibold text-slate-900">{registro ? "Editar incapacidad" : "Nueva incapacidad"}</h2>
        <button type="button" className="ml-auto rounded-md p-1 text-slate-500 hover:bg-slate-100" onClick={onCancelar} aria-label="Cerrar"><X className="h-5 w-5" /></button>
      </div>
      {error && <Alerta>{error}</Alerta>}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <label className="label">Cédula</label>
          <BuscarEmpleado key={registro?.id ?? "nueva"} valor={f.documento} nombreInicial={registro?.nombre} onCambio={(d) => cambiar({ documento: d })} />
        </div>
        <div>
          <label className="label">Nombre <span className="font-normal text-slate-400">(si no está en la base)</span></label>
          <input className="input" maxLength={200} value={f.nombre} onChange={(e) => cambiar({ nombre: e.target.value })} />
        </div>
        <div>
          <label className="label">Novedad</label>
          <select className="input" value={f.novedad} onChange={(e) => cambiar({ novedad: e.target.value })}>
            {NOVEDADES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
          </select>
        </div>
        <div>
          <label className="label">Origen</label>
          <select className="input" value={f.origen} onChange={(e) => cambiar({ origen: e.target.value })}>
            <option value="">Sin origen (licencias)</option>
            {ORIGENES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
          </select>
        </div>
        <div>
          <label className="label">Desde</label>
          <input className="input" type="date" required value={f.desde} onChange={(e) => cambiar({ desde: e.target.value })} />
        </div>
        <div>
          <label className="label">Hasta</label>
          <input className="input" type="date" required value={f.hasta} onChange={(e) => cambiar({ hasta: e.target.value })} />
          {n !== null && <p className={`mt-1 text-xs ${n < 1 ? "text-red-700" : "text-slate-500"}`}>{n < 1 ? "La fecha de fin es anterior" : `${n} días calendario`}</p>}
        </div>
        <div className="flex items-end pb-2">
          <label className="inline-flex items-center gap-2 text-sm">
            <input type="checkbox" checked={f.prorroga} onChange={(e) => cambiar({ prorroga: e.target.checked })} /> Es prórroga de la anterior
          </label>
        </div>
        <div>
          <label className="label">EPS / ARL / centro médico</label>
          <input className="input" maxLength={80} value={f.entidad} onChange={(e) => cambiar({ entidad: e.target.value })} />
        </div>
        <div>
          <label className="label">Código CIE-10</label>
          <BuscarCie valor={f.cie} onCambio={(v) => cambiar({ cie: v })} onDiagnostico={(d) => setF((x) => ({ ...x, diagnostico: d }))} />
        </div>
        <div className="sm:col-span-2 lg:col-span-3">
          <label className="label">Diagnóstico</label>
          <input className="input" maxLength={300} value={f.diagnostico} placeholder="Se toma del catálogo al elegir el código"
            onChange={(e) => cambiar({ diagnostico: e.target.value })} />
        </div>
        <div>
          <label className="label">Soporte</label>
          <select className="input" value={f.soporte} onChange={(e) => cambiar({ soporte: e.target.value })}>
            <option value="">Sin soporte</option>
            {SOPORTES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
          </select>
        </div>
        <div className="sm:col-span-2">
          <label className="label">Puesto <span className="font-normal text-slate-400">(vacío: el de la ficha)</span></label>
          <input className="input" maxLength={200} value={f.puesto} onChange={(e) => cambiar({ puesto: e.target.value })} />
        </div>
        <div className="sm:col-span-2">
          <label className="label">Observación</label>
          <input className="input" maxLength={300} value={f.observacion} placeholder="p. ej. Falta historia clínica" onChange={(e) => cambiar({ observacion: e.target.value })} />
        </div>
      </div>
      <p className="text-xs text-slate-500">Los soportes (PDF o imagen) se adjuntan desde la lista, después de guardar.</p>
      <div className="flex gap-2">
        <button className="btn-primario">Guardar</button>
        <button type="button" className="btn-secundario" onClick={onCancelar}>Cancelar</button>
      </div>
    </form>
  );
}

export default function Incapacidades() {
  const gestionar = usePermiso("liquidador.salud.gestionar");
  const juridico = usePermiso("liquidador.juridico.gestionar");
  const importa = gestionar || juridico;
  const [lista, setLista] = useState<Incapacidad[]>([]);
  const [meta, setMeta] = useState<MetaPagina | null>(null);
  const [resumen, setResumen] = useState<ResumenIncapacidades | null>(null);
  const [anios, setAnios] = useState<number[]>([]);
  const [q, setQ] = useState("");
  useEffect(() => setQ(qInicial()), []);  // desde la ficha llega ?q=documento
  const [anio, setAnio] = useState("");
  const [origen, setOrigen] = useState("");
  const [vista, setVista] = useState<Vista>("todas");
  const [edicion, setEdicion] = useState<{ registro: Incapacidad | null } | null>(null);
  const [importar, setImportar] = useState(false);
  const [error, setError] = useState("");
  const [aviso, setAviso] = useState("");
  const pag = usePaginacion([q, anio, origen, vista]);

  const cargar = useCallback(async () => {
    const r = await apiEnvelope<Incapacidad[]>(`/liquidador/incapacidades?q=${encodeURIComponent(q)}&anio=${anio}&origen=${origen}&vista=${vista}&${pag.query}`);
    setLista(r.data ?? []);
    setMeta(metaDe(r));
    const extra = r.meta?.extra as { resumen: ResumenIncapacidades; anios: number[] } | null;
    setResumen(extra?.resumen ?? null);
    setAnios(extra?.anios ?? []);
  }, [q, anio, origen, vista, pag.query]);

  useEffect(() => {
    const t = setTimeout(() => cargar().catch((e) => setError(mensajeError(e))), 250);
    return () => clearTimeout(t);
  }, [cargar]);

  async function eliminar(x: Incapacidad) {
    if (!window.confirm(`¿Eliminar la incapacidad de ${x.nombre} del ${fechaCorta(x.desde)}${x.documentos.length ? " y sus soportes" : ""}?`)) return;
    try {
      await api(`/liquidador/incapacidades/${x.id}`, { method: "DELETE" });
      await cargar();
    } catch (err) {
      setError(mensajeError(err));
    }
  }

  const tarjeta = (titulo: string, valor: number | undefined, alerta = false) => (
    <div className={`rounded-lg px-4 py-3 ${alerta && valor ? "bg-amber-50 text-amber-900" : "bg-slate-50"}`}>
      <p className="text-xs text-slate-500">{titulo}</p>
      <p className="text-xl font-semibold tabular-nums">{(valor ?? 0).toLocaleString("es-CO")}</p>
    </div>
  );

  return (
    <div className="space-y-5">
      <Titulo accion={!edicion && (
        <div className="flex flex-wrap gap-2">
          {importa && (
            <button className="btn-secundario inline-flex items-center gap-1.5" onClick={() => setImportar(!importar)}>
              <FileUp className="h-4 w-4" /> Importar formato de ausentismo
            </button>
          )}
          {gestionar && (
            <button className="btn-primario inline-flex items-center gap-1.5" onClick={() => { setAviso(""); setEdicion({ registro: null }); }}>
              <Plus className="h-4 w-4" /> Nueva incapacidad
            </button>
          )}
        </div>
      )}>Registro de incapacidades</Titulo>
      <p className="-mt-4 text-sm text-slate-500">
        Repositorio de consulta con el diagnóstico CIE-10 y los soportes: no afecta la nómina. Los días acumulados suman la incapacidad
        inicial con sus prórrogas (marcadas como prórroga o con la misma categoría CIE, con menos de 30 días de diferencia) y avisan al pasar
        180 y 540 días.
      </p>
      {error && <Alerta>{error}</Alerta>}
      {aviso && <Alerta tipo="ok">{aviso}</Alerta>}
      {importar && <ImportarAusentismo onCerrar={() => setImportar(false)} onImportado={() => cargar().catch(() => {})} />}
      {edicion && (
        <Modal onCerrar={() => setEdicion(null)}>
          <FormularioIncapacidad key={edicion.registro?.id ?? "nueva"} registro={edicion.registro} onCancelar={() => setEdicion(null)}
            onGuardado={(m) => { setEdicion(null); setAviso(m); cargar().catch(() => {}); }} />
        </Modal>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {tarjeta(anio ? `Registros ${anio}` : "Registros", resumen?.registros)}
        {tarjeta(anio ? `Días ${anio}` : "Días de incapacidad", resumen?.dias)}
        {tarjeta("Vigentes hoy", resumen?.vigentes)}
        {tarjeta("Más de 180 días", resumen?.prolongadas, true)}
      </div>

      <div className="tarjeta overflow-hidden">
        <div className="px-4 pt-3">
          <Pestanas<Vista> opciones={[["todas", "Todas"], ["vigentes", "Vigentes hoy"], ["prolongadas", "Prolongadas (más de 180 días)"]]} valor={vista} onChange={setVista} />
        </div>
        <div className="flex flex-wrap items-center gap-3 px-4 pb-3">
          <div className="relative w-72">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input className="input pl-8" placeholder="Cédula, nombre, CIE o diagnóstico…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <select className="input w-32" value={anio} onChange={(e) => setAnio(e.target.value)} aria-label="Año">
            <option value="">Todos los años</option>
            {anios.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
          <select className="input w-48" value={origen} onChange={(e) => setOrigen(e.target.value)} aria-label="Origen">
            <option value="">Todo origen</option>
            {ORIGENES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
          </select>
          {meta && <span className="text-sm text-slate-500">{meta.total.toLocaleString("es-CO")} registros</span>}
        </div>
        <div className="overflow-auto">
          <table className="tabla text-sm">
            <thead>
              <tr><th>Persona</th><th>Fechas</th><th className="text-right">Días</th><th>Diagnóstico</th><th>Origen</th><th>Entidad</th><th>Soportes</th><th /></tr>
            </thead>
            <tbody>
              {lista.map((x) => (
                <tr key={x.id} className="align-top">
                  <td className="min-w-[180px]">
                    <span className="font-medium">{x.nombre}</span>
                    <span className="block text-xs text-slate-500"><span className="font-mono">{x.documento}</span>{x.puesto ? ` · ${x.puesto}` : ""}</span>
                    {x.vigente && <Insignia color="mt-1 bg-sky-100 text-sky-800">Vigente</Insignia>}
                  </td>
                  <td className="whitespace-nowrap text-xs">{fechaCorta(x.desde)}<br />{fechaCorta(x.hasta)}</td>
                  <td className="text-right tabular-nums">
                    {x.dias}
                    {x.acumulado !== null && x.acumulado !== x.dias && (
                      <span className={`block text-xs ${x.alerta ? "font-semibold text-amber-700" : "text-slate-500"}`} title={`Desde el ${fechaCorta(x.inicio_caso)}`}>
                        {x.acumulado} acum.
                      </span>
                    )}
                  </td>
                  <td className="min-w-[220px]">
                    {x.cie && <span className="mr-1 font-mono text-xs text-marca-700">{x.cie.replaceAll(",", ", ")}</span>}
                    <span className="text-xs">{x.diagnostico ?? (x.cie ? "" : "Sin diagnóstico")}</span>
                    {x.cie_desconocidos.length > 0 && <span className="block text-xs text-amber-700">{x.cie_desconocidos.join(", ")} no está en el catálogo CIE-10</span>}
                    {x.alerta && <span className="mt-0.5 flex items-center gap-1 text-xs font-medium text-amber-800"><AlertTriangle className="h-3.5 w-3.5" />{x.alerta} desde el {fechaCorta(x.inicio_caso)}</span>}
                    {x.observacion && <span className="block text-xs text-slate-500">{x.observacion}</span>}
                  </td>
                  <td className="whitespace-nowrap text-xs">
                    {x.novedad === "incapacidad" ? (ORIGEN_CORTO[x.origen ?? ""] ?? "—") : etiqueta(NOVEDADES, x.novedad)}
                    <span className="block text-slate-500">{x.prorroga ? "Prórroga" : "Inicial"}</span>
                  </td>
                  <td className="text-xs">{x.entidad ?? "—"}{x.soporte && <span className="block text-slate-500">{etiqueta(SOPORTES, x.soporte)}</span>}</td>
                  <td className="min-w-[140px]">
                    <Soportes modulo="incapacidad" registroId={x.id} documentos={x.documentos} editable={gestionar}
                      onCambio={() => cargar().catch(() => {})} onError={setError} />
                  </td>
                  <td className="whitespace-nowrap text-right">
                    {gestionar && (
                      <>
                        <button className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100" onClick={() => { setAviso(""); setEdicion({ registro: x }); }} aria-label="Editar"><Pencil className="h-4 w-4" /></button>
                        <button className="rounded-md p-1.5 text-slate-500 hover:bg-red-50 hover:text-red-700" onClick={() => eliminar(x)} aria-label="Eliminar"><Trash2 className="h-4 w-4" /></button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {lista.length === 0 && <p className="p-6 text-center text-sm text-slate-500">No hay incapacidades con esos filtros.</p>}
        </div>
        <Paginador meta={meta} onPagina={pag.setPagina} onTamano={pag.setTamano} />
      </div>
    </div>
  );
}
