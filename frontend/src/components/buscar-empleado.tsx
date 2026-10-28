"use client";

import { useEffect, useId, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { Empleado } from "@/lib/liquidador";

/** Campo de cédula con sugerencias de los empleados del liquidador: se busca por cédula o nombre y al elegir uno
 * queda su cédula. Se puede seguir escribiendo una cédula a mano. */
export function BuscarEmpleado({ valor, onCambio, nombreInicial }: {
  valor: string; onCambio: (documento: string) => void; nombreInicial?: string;
}) {
  const [abierto, setAbierto] = useState(false);
  const [opciones, setOpciones] = useState<Empleado[]>([]);
  const [cargando, setCargando] = useState(false);
  const [activo, setActivo] = useState(-1);
  const [elegido, setElegido] = useState<{ documento: string; nombre: string } | null>(
    nombreInicial && valor ? { documento: valor, nombre: nombreInicial } : null);
  const caja = useRef<HTMLDivElement>(null);
  const lista = useId();

  useEffect(() => {
    if (!abierto) return;
    let vigente = true;
    setCargando(true);
    const t = setTimeout(() => {
      api<Empleado[]>(`/liquidador/empleados?q=${encodeURIComponent(valor.trim())}&tamano=50`)
        .then((x) => { if (vigente) { setOpciones(x.slice(0, 10)); setActivo(-1); } })
        .catch(() => { if (vigente) setOpciones([]); })
        .finally(() => { if (vigente) setCargando(false); });
    }, 250);
    return () => { vigente = false; clearTimeout(t); };
  }, [valor, abierto]);

  useEffect(() => {
    function fuera(e: MouseEvent) {
      if (caja.current && !caja.current.contains(e.target as Node)) setAbierto(false);
    }
    document.addEventListener("mousedown", fuera);
    return () => document.removeEventListener("mousedown", fuera);
  }, []);

  function elegir(e: Empleado) {
    setElegido({ documento: e.documento, nombre: e.nombre });
    onCambio(e.documento);
    setAbierto(false);
  }

  function teclas(ev: React.KeyboardEvent<HTMLInputElement>) {
    if (!abierto || opciones.length === 0) return;
    if (ev.key === "ArrowDown") { ev.preventDefault(); setActivo((i) => Math.min(i + 1, opciones.length - 1)); }
    else if (ev.key === "ArrowUp") { ev.preventDefault(); setActivo((i) => Math.max(i - 1, 0)); }
    else if (ev.key === "Enter" && activo >= 0) { ev.preventDefault(); elegir(opciones[activo]); }
    else if (ev.key === "Escape") setAbierto(false);
  }

  const nombre = elegido && elegido.documento === valor ? elegido.nombre : null;
  return (
    <div className="relative" ref={caja}>
      <input className="input font-mono" required autoComplete="off" placeholder="Cédula o nombre" value={valor}
        role="combobox" aria-expanded={abierto} aria-controls={lista} aria-autocomplete="list"
        onFocus={() => setAbierto(true)} onKeyDown={teclas}
        onChange={(e) => { onCambio(e.target.value); setAbierto(true); }} />
      {nombre && <p className="mt-1 truncate text-xs text-slate-600">{nombre}</p>}
      {abierto && (
        <ul id={lista} role="listbox" className="absolute z-20 mt-1 max-h-72 w-[min(26rem,90vw)] overflow-auto rounded-lg border border-slate-200 bg-white py-1 shadow-lg">
          {cargando && opciones.length === 0 && <li className="px-3 py-2 text-sm text-slate-500">Buscando…</li>}
          {!cargando && opciones.length === 0 && (
            <li className="px-3 py-2 text-sm text-slate-500">
              {valor.trim() ? "Ningún empleado coincide. Los empleados se crean al cargar el Excel de un periodo." : "No hay empleados registrados."}
            </li>
          )}
          {opciones.map((e, i) => (
            <li key={e.id} role="option" aria-selected={i === activo}>
              <button type="button" onMouseDown={(ev) => ev.preventDefault()} onClick={() => elegir(e)} onMouseEnter={() => setActivo(i)}
                className={`flex w-full flex-col items-start px-3 py-1.5 text-left ${i === activo ? "bg-slate-100" : ""}`}>
                <span className="text-sm font-medium text-slate-900">{e.nombre}</span>
                <span className="text-xs text-slate-500"><span className="font-mono">{e.documento}</span>{e.cargo ? ` · ${e.cargo}` : ""}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
