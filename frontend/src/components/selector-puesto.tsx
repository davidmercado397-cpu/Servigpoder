"use client";

import { Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, type Puesto } from "@/lib/api";

/** Busca puestos en el servidor (máx. 20 coincidencias) en lugar de cargar los cientos de puestos en una lista. */
export function SelectorPuesto({ onElegir }: { onElegir: (p: Puesto) => void }) {
  const [q, setQ] = useState("");
  const [opciones, setOpciones] = useState<Puesto[]>([]);
  const [abierto, setAbierto] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!abierto) return;
    const t = setTimeout(() => {
      api<Puesto[]>(`/capacidad/maestros/puestos/opciones?q=${encodeURIComponent(q)}`).then(setOpciones).catch(() => setOpciones([]));
    }, 250);
    return () => clearTimeout(t);
  }, [q, abierto]);

  useEffect(() => {
    const cerrar = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setAbierto(false); };
    document.addEventListener("mousedown", cerrar);
    return () => document.removeEventListener("mousedown", cerrar);
  }, []);

  return (
    <div className="relative w-72" ref={ref}>
      <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
      <input className="input pl-8" placeholder="Buscar puesto por código o cliente…" value={q}
        onFocus={() => setAbierto(true)} onChange={(e) => { setQ(e.target.value); setAbierto(true); }} />
      {abierto && (
        <ul className="absolute z-20 mt-1 max-h-64 w-full overflow-auto rounded-md border border-slate-200 bg-white text-sm shadow-lg">
          {opciones.length === 0 && <li className="px-3 py-2 text-slate-400">Sin coincidencias</li>}
          {opciones.map((p) => (
            <li key={p.id}>
              <button type="button" className="block w-full px-3 py-1.5 text-left hover:bg-marca-50"
                onClick={() => { onElegir(p); setAbierto(false); setQ(""); }}>
                <span className="font-mono font-semibold">{p.codigo}</span> · {p.ubicacion.nombre}
                <span className="block text-xs text-slate-500">{p.descripcion}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
