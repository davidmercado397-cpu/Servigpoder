"use client";

import { X } from "lucide-react";
import { useEffect, useState } from "react";
import { api, mensajeError, type Puesto, type Ubicacion } from "@/lib/api";

export type PuestoCreado = { puesto: Puesto; ubicacion_creada: boolean; equivalencia: string | null; matriz_puesto_id: number | null };

type Props = {
  titulo: string;
  inicial?: { codigo?: string; descripcion?: string; ubicacion_codigo?: string; ubicacion_nombre?: string; codigo_siesa?: string };
  /** Matriz comercial a la que se puede agregar de una vez (mes de la programación) */
  matriz?: { id: number; etiqueta: string } | null;
  onCreado: (r: PuestoCreado) => void;
  onCancelar: () => void;
};

/**
 * Crea un puesto del maestro (y su ubicación si aún no existe). Si viene de SIESA, el código queda asignado
 * (equivalencia) y el puesto se puede agregar a la matriz comercial del mes para configurar su cobertura.
 */
export function FormularioPuesto({ titulo, inicial = {}, matriz, onCreado, onCancelar }: Props) {
  const [codigo, setCodigo] = useState(inicial.codigo ?? "");
  const [descripcion, setDescripcion] = useState(inicial.descripcion ?? "");
  const [codUbicacion, setCodUbicacion] = useState(inicial.ubicacion_codigo ?? "");
  const [ubicacion, setUbicacion] = useState<Ubicacion | null | undefined>(undefined); // undefined = buscando
  const [nombreUbicacion, setNombreUbicacion] = useState(inicial.ubicacion_nombre ?? "");
  const [ciudad, setCiudad] = useState("");
  const [excluido, setExcluido] = useState(false);
  const [agregar, setAgregar] = useState(!!matriz);
  const [hombres, setHombres] = useState("1");
  const [secuencia, setSecuencia] = useState("");
  const [sugerencias, setSugerencias] = useState<Ubicacion[]>([]);
  const [error, setError] = useState("");
  const [guardando, setGuardando] = useState(false);

  // ¿La ubicación ya existe en el maestro?
  useEffect(() => {
    const cod = codUbicacion.trim();
    if (!cod) {
      setUbicacion(null);
      setSugerencias([]);
      return;
    }
    setUbicacion(undefined);
    const t = setTimeout(() => {
      api<Ubicacion[]>(`/capacidad/maestros/ubicaciones/opciones?q=${encodeURIComponent(cod)}`)
        .then((lista) => {
          setSugerencias(lista.slice(0, 6));
          setUbicacion(lista.find((u) => u.codigo.toUpperCase() === cod.replace(/\s+/g, "").toUpperCase()) ?? null);
        })
        .catch(() => setUbicacion(null));
    }, 250);
    return () => clearTimeout(t);
  }, [codUbicacion]);

  async function guardar(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setGuardando(true);
    try {
      const r = await api<PuestoCreado>("/capacidad/maestros/puestos", {
        method: "POST",
        json: {
          codigo, descripcion, ubicacion_codigo: codUbicacion, excluido,
          ...(ubicacion ? {} : { ubicacion_nombre: nombreUbicacion, ubicacion_ciudad: ciudad }),
          ...(inicial.codigo_siesa ? { codigo_siesa: inicial.codigo_siesa } : {}),
          ...(matriz && agregar ? { periodo_id: matriz.id, hombres: hombres || "0", secuencia } : {}),
        },
      });
      onCreado(r);
    } catch (err) {
      setError(mensajeError(err));
      setGuardando(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/40 p-4 pt-16" onClick={onCancelar}>
      <form onSubmit={guardar} onClick={(e) => e.stopPropagation()} className="tarjeta w-full max-w-2xl space-y-4 p-5">
        <div className="flex items-start">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">{titulo}</h2>
            {inicial.codigo_siesa && (
              <p className="text-sm text-slate-500">Llega en la programación de SIESA como <b className="font-mono">{inicial.codigo_siesa}</b>: quedará asignado a este puesto.</p>
            )}
          </div>
          <button type="button" className="ml-auto rounded-md p-1 text-slate-500 hover:bg-slate-100" onClick={onCancelar} aria-label="Cerrar"><X className="h-5 w-5" /></button>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="label">Código del puesto (PODER interno)</label>
            <input className="input font-mono" required maxLength={30} value={codigo} onChange={(e) => setCodigo(e.target.value)} />
          </div>
          <div>
            <label className="label">Descripción</label>
            <input className="input" maxLength={200} placeholder="p. ej. PORTERÍA PRINCIPAL" value={descripcion} onChange={(e) => setDescripcion(e.target.value)} />
          </div>
          <div>
            <label className="label">Ubicación (PODER principal)</label>
            <input className="input font-mono" required maxLength={30} list="ubicaciones-sugeridas" value={codUbicacion} onChange={(e) => setCodUbicacion(e.target.value)} />
            <datalist id="ubicaciones-sugeridas">
              {sugerencias.map((u) => <option key={u.id} value={u.codigo}>{u.nombre}</option>)}
            </datalist>
            <p className="mt-1 text-xs">
              {ubicacion === undefined && codUbicacion.trim() && <span className="text-slate-400">Buscando…</span>}
              {ubicacion && <span className="text-green-700">✓ {ubicacion.nombre}{ubicacion.ciudad ? ` · ${ubicacion.ciudad}` : ""}</span>}
              {ubicacion === null && codUbicacion.trim() && <span className="text-amber-700">Ubicación nueva: escriba su nombre para crearla.</span>}
            </p>
          </div>
          {ubicacion === null && codUbicacion.trim() && (
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="label">Nombre de la ubicación</label>
                <input className="input" required maxLength={200} value={nombreUbicacion} onChange={(e) => setNombreUbicacion(e.target.value)} />
              </div>
              <div>
                <label className="label">Ciudad</label>
                <input className="input" maxLength={80} value={ciudad} onChange={(e) => setCiudad(e.target.value)} />
              </div>
            </div>
          )}
        </div>

        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={excluido} onChange={(e) => setExcluido(e.target.checked)} />
          Excluido del control (escoltas, coordinadores, supervisores)
        </label>

        {matriz && (
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <label className="flex items-center gap-2 text-sm font-medium">
              <input type="checkbox" checked={agregar} onChange={(e) => setAgregar(e.target.checked)} />
              Agregarlo a la matriz comercial de {matriz.etiqueta}
            </label>
            {agregar && (
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <div>
                  <label className="label">Hombres</label>
                  <input className="input" type="number" min={0} step="0.5" value={hombres} onChange={(e) => setHombres(e.target.value)} />
                </div>
                <div>
                  <label className="label">Secuencia</label>
                  <input className="input" maxLength={80} placeholder="p. ej. 4x2" value={secuencia} onChange={(e) => setSecuencia(e.target.value)} />
                </div>
                <p className="text-xs text-slate-500 sm:col-span-2">Queda marcado &quot;por revisar&quot;: configure su cobertura (horarios por día) en la Matriz comercial.</p>
              </div>
            )}
          </div>
        )}

        {error && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
        <div className="flex gap-2">
          <button className="btn-primario" disabled={guardando}>{guardando ? "Creando…" : "Crear puesto"}</button>
          <button type="button" className="btn-secundario" onClick={onCancelar}>Cancelar</button>
        </div>
      </form>
    </div>
  );
}
