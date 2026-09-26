"use client";

import { Moon, Plus, Search, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Paginador, metaDe, usePaginacion, type MetaPagina } from "@/components/paginacion";
import { Alerta, Insignia, Titulo } from "@/components/ui";
import { api, apiEnvelope, mensajeError } from "@/lib/api";
import { hora } from "@/lib/formato";
import { CLASES, CONCEPTOS, TIPOS_DIA, horas, type Matriz, type Turno } from "@/lib/liquidador";
import { usePermiso } from "@/lib/sesion";

type Form = {
  id?: number; codigo: string; nombre: string; hora_inicio: string; hora_fin: string;
  horas_ordinarias: string; horas_extras: string; remunerado: boolean; incapacidad: boolean;
};
const VACIO: Form = { codigo: "", nombre: "", hora_inicio: "06:00", hora_fin: "18:00", horas_ordinarias: "0", horas_extras: "0", remunerado: true, incapacidad: false };
const CLASE = Object.fromEntries(CLASES.map(([k, , color, , uno]) => [k, [uno, color]]));

export default function Turnos() {
  const gestionar = usePermiso("liquidador.turnos.gestionar");
  const [lista, setLista] = useState<Turno[]>([]);
  const [meta, setMeta] = useState<MetaPagina | null>(null);
  const [q, setQ] = useState("");
  const [nocturna, setNocturna] = useState<number | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [error, setError] = useState("");
  const [aviso, setAviso] = useState("");
  const pag = usePaginacion([q]);

  const cargar = useCallback(async () => {
    const r = await apiEnvelope<Turno[]>(`/liquidador/turnos?q=${encodeURIComponent(q)}&${pag.query}`);
    setLista(r.data ?? []);
    setMeta(metaDe(r));
  }, [q, pag.query]);

  useEffect(() => {
    const t = setTimeout(() => cargar().catch((e) => setError(mensajeError(e))), 250);
    return () => clearTimeout(t);
  }, [cargar]);

  useEffect(() => {
    api<{ hora_inicio_nocturna: number }>("/liquidador/parametros").then((p) => setNocturna(p.hora_inicio_nocturna)).catch(() => {});
  }, []);

  async function guardarNocturna(h: number) {
    if (!window.confirm(`¿Cambiar el inicio de la jornada nocturna a las ${String(h).padStart(2, "0")}:00? Se recalcula el reparto diurno/nocturno de todos los turnos. Las quincenas ya calculadas solo cambian si se recalculan.`)) return;
    setError("");
    try {
      const r = await apiEnvelope<{ hora_inicio_nocturna: number }>("/liquidador/parametros", { method: "PUT", json: { hora_inicio_nocturna: h } });
      setNocturna(r.data!.hora_inicio_nocturna);
      setAviso(`Hora nocturna actualizada. Se regeneraron ${r.meta.extra?.turnos_regenerados ?? 0} turnos.`);
    } catch (e) {
      setError(mensajeError(e));
    }
  }

  async function abrir(t?: Turno) {
    setAviso("");
    if (!t) return setForm({ ...VACIO });
    setForm({
      id: t.id, codigo: t.codigo, nombre: t.nombre, hora_inicio: hora(t.hora_inicio), hora_fin: hora(t.hora_fin),
      horas_ordinarias: String(t.horas_ordinarias), horas_extras: String(t.horas_extras), remunerado: t.remunerado, incapacidad: t.incapacidad,
    });
  }

  async function activar(t: Turno) {
    try {
      await api(`/liquidador/turnos/${t.id}/activo`, { method: "POST" });
      await cargar();
    } catch (e) {
      setError(mensajeError(e));
    }
  }

  return (
    <div className="space-y-5">
      <Titulo accion={gestionar && <button className="btn-primario inline-flex items-center gap-1.5" onClick={() => abrir()}><Plus className="h-4 w-4" /> Nuevo turno</button>}>
        Turnos
      </Titulo>
      <p className="-mt-4 text-sm text-slate-500">Las horas se cuentan con las <b>horas ordinarias</b> y las <b>horas extras</b> de cada turno desde su hora de inicio; la hora fin es informativa.</p>

      <div className="tarjeta flex flex-wrap items-center gap-3 p-4">
        <Moon className="h-5 w-5 text-indigo-500" />
        <div className="flex-1">
          <p className="font-medium text-slate-800">Hora de inicio de la jornada nocturna</p>
          <p className="text-xs text-slate-500">Lo diurno va de 06:00 a esta hora y lo nocturno de esta hora a las 06:00. Al cambiarla se recalculan las matrices de todos los turnos.</p>
        </div>
        <select className="input w-32" value={nocturna ?? ""} disabled={!gestionar || nocturna === null} onChange={(e) => guardarNocturna(Number(e.target.value))}>
          {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{String(h).padStart(2, "0")}:00</option>)}
        </select>
      </div>

      {error && <Alerta>{error}</Alerta>}
      {aviso && <Alerta tipo="ok">{aviso}</Alerta>}

      <div className="tarjeta overflow-hidden">
        <div className="px-4 py-3">
          <div className="relative w-72">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input className="input pl-8" placeholder="Buscar por código o nombre…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
        </div>
        <div className="overflow-auto">
          <table className="tabla">
            <thead>
              <tr><th>Código</th><th>Nombre</th><th>Horario</th><th className="text-right">Ordinarias</th><th className="text-right">Extras</th><th>Cuenta como</th><th>Remuneración</th><th>Estado</th><th /></tr>
            </thead>
            <tbody>
              {lista.map((t) => {
                const [texto, color] = CLASE[t.clase] ?? [t.clase, ""];
                return (
                  <tr key={t.id} className={t.activo ? "" : "opacity-50"}>
                    <td className="font-mono font-semibold">{t.codigo}</td>
                    <td>{t.nombre}</td>
                    <td className="whitespace-nowrap tabular-nums">{hora(t.hora_inicio)} → {hora(t.hora_fin)}</td>
                    <td className="text-right tabular-nums">{horas(t.horas_ordinarias)}</td>
                    <td className="text-right tabular-nums">{horas(t.horas_extras)}</td>
                    <td><Insignia color={color}>{texto}</Insignia></td>
                    <td className="text-sm">{t.incapacidad ? "Incapacidad" : t.remunerado ? "Remunerado" : "No remunerado"}</td>
                    <td className="text-sm">{t.activo ? "Activo" : "Inactivo"}</td>
                    <td className="whitespace-nowrap text-right text-sm">
                      <button className="font-medium text-marca-600 hover:underline" onClick={() => abrir(t)}>Abrir</button>
                      {gestionar && <button className="ml-3 text-slate-500 hover:underline" onClick={() => activar(t)}>{t.activo ? "Inactivar" : "Activar"}</button>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <Paginador meta={meta} onPagina={pag.setPagina} onTamano={pag.setTamano} />
      </div>

      {form && <EditorTurno inicial={form} soloLectura={!gestionar} onCerrar={() => setForm(null)}
        onGuardado={async (t) => { setForm(null); setAviso(`Turno ${t.codigo} guardado.`); await cargar(); }} />}
    </div>
  );
}

function EditorTurno({ inicial, soloLectura, onCerrar, onGuardado }: {
  inicial: Form; soloLectura: boolean; onCerrar: () => void; onGuardado: (t: Turno) => Promise<void>;
}) {
  const [f, setF] = useState<Form>(inicial);
  const [matriz, setMatriz] = useState<Matriz | null>(null);
  const [error, setError] = useState("");
  const [guardando, setGuardando] = useState(false);

  // Vista previa de la distribución mientras se edita (no guarda nada)
  useEffect(() => {
    const t = setTimeout(() => {
      api<Matriz>("/liquidador/turnos/vista-previa", {
        method: "POST",
        json: { hora_inicio: f.hora_inicio || "00:00", horas_ordinarias: Number(f.horas_ordinarias) || 0, horas_extras: Number(f.horas_extras) || 0, incapacidad: f.incapacidad },
      }).then(setMatriz).catch(() => setMatriz(null));
    }, 300);
    return () => clearTimeout(t);
  }, [f.hora_inicio, f.horas_ordinarias, f.horas_extras, f.incapacidad]);

  async function guardar(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setGuardando(true);
    const datos = { ...f, horas_ordinarias: Number(f.horas_ordinarias) || 0, horas_extras: Number(f.horas_extras) || 0 };
    try {
      const t = await api<Turno>(f.id ? `/liquidador/turnos/${f.id}` : "/liquidador/turnos", { method: f.id ? "PUT" : "POST", json: datos });
      await onGuardado(t);
    } catch (err) {
      setError(mensajeError(err));
    } finally {
      setGuardando(false);
    }
  }

  const campo = (k: keyof Form, v: string | boolean) => setF({ ...f, [k]: v });

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/40" onClick={onCerrar}>
      <aside className="h-full w-full max-w-4xl overflow-y-auto bg-white shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <header className="sticky top-0 z-10 flex items-center gap-3 border-b border-slate-200 bg-white p-5">
          <span className="rounded-lg bg-marca-50 px-2.5 py-1 font-mono text-sm font-bold text-marca-700">{f.codigo || "Nuevo"}</span>
          <h2 className="flex-1 text-lg font-bold text-marca-900">{f.nombre || "Nuevo turno"}</h2>
          <button onClick={onCerrar} className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100" aria-label="Cerrar"><X className="h-5 w-5" /></button>
        </header>
        <form onSubmit={guardar} className="space-y-5 p-5">
          <fieldset disabled={soloLectura} className="grid gap-4 sm:grid-cols-2">
            <div><label className="label">Código</label><input className="input font-mono uppercase" required maxLength={8} value={f.codigo} onChange={(e) => campo("codigo", e.target.value)} /></div>
            <div><label className="label">Nombre</label><input className="input" required maxLength={80} value={f.nombre} onChange={(e) => campo("nombre", e.target.value)} /></div>
            <div><label className="label">Hora inicio</label><input className="input" type="time" required value={f.hora_inicio} onChange={(e) => campo("hora_inicio", e.target.value)} /></div>
            <div><label className="label">Hora fin <span className="font-normal text-slate-400">(informativa)</span></label><input className="input" type="time" required value={f.hora_fin} onChange={(e) => campo("hora_fin", e.target.value)} /></div>
            <div><label className="label">Horas ordinarias</label><input className="input" type="number" min={0} max={24} step="0.01" disabled={f.incapacidad} value={f.incapacidad ? "0" : f.horas_ordinarias} onChange={(e) => campo("horas_ordinarias", e.target.value)} /></div>
            <div><label className="label">Horas extras</label><input className="input" type="number" min={0} max={24} step="0.01" disabled={f.incapacidad} value={f.incapacidad ? "0" : f.horas_extras} onChange={(e) => campo("horas_extras", e.target.value)} /></div>
            <label className={`flex items-center gap-2 text-sm ${f.incapacidad ? "text-slate-400" : "text-slate-700"}`}>
              <input type="checkbox" className="h-4 w-4" disabled={f.incapacidad} checked={f.remunerado && !f.incapacidad} onChange={(e) => campo("remunerado", e.target.checked)} />
              Día remunerado
            </label>
            <label className="flex items-start gap-2 text-sm text-slate-700">
              <input type="checkbox" className="mt-0.5 h-4 w-4" checked={f.incapacidad} onChange={(e) => campo("incapacidad", e.target.checked)} />
              <span>Es incapacidad<span className="block text-xs text-slate-500">Se cuenta como incapacidad (no como día trabajado ni ausencia) y no genera horas.</span></span>
            </label>
          </fieldset>

          <div>
            <h3 className="font-semibold text-slate-900">Distribución calculada</h3>
            <p className="mb-2 text-xs text-slate-500">Se genera sola con las horas ordinarias y extras, la hora de inicio y la hora nocturna. Solo lectura.</p>
            <div className="overflow-auto rounded-lg border border-slate-200">
              <table className="tabla text-xs">
                <thead><tr><th>Concepto</th>{TIPOS_DIA.map(([k, t]) => <th key={k} className="text-right">{t}</th>)}</tr></thead>
                <tbody>
                  {[["ordinary_day", "Diurnas ordinarias"], ["ordinary_night", "Nocturnas ordinarias"], ...CONCEPTOS.slice(2).map(([k, l]) => [k, l])].map(([k, l]) => (
                    <tr key={k}><td className="whitespace-nowrap">{l}</td>{TIPOS_DIA.map(([d]) => <td key={d} className="text-right tabular-nums">{horas(matriz?.[k]?.[d])}</td>)}</tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {error && <Alerta>{error}</Alerta>}
          {!soloLectura && (
            <div className="flex justify-end gap-2">
              <button type="button" className="btn-secundario" onClick={onCerrar}>Cancelar</button>
              <button className="btn-primario" disabled={guardando}>{guardando ? "Guardando…" : "Guardar datos"}</button>
            </div>
          )}
        </form>
      </aside>
    </div>
  );
}
