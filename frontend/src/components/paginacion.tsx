"use client";

import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { Envelope } from "@/lib/api";

export const TAMANOS = [50, 100, 150] as const;
const CLAVE = "paginacion-tamano";

export type MetaPagina = { total: number; pagina: number; tamano: number; paginas: number };

export function metaDe(r: Envelope<unknown>): MetaPagina {
  const e = (r.meta.extra ?? {}) as Partial<MetaPagina>;
  return { total: e.total ?? 0, pagina: e.pagina ?? 1, tamano: e.tamano ?? 50, paginas: e.paginas ?? 1 };
}

/**
 * Estado de paginación de una tabla. Vuelve a la página 1 cuando cambian los filtros
 * (`reiniciarCon`). El tamaño de página elegido se recuerda en este navegador.
 */
export function usePaginacion(reiniciarCon: unknown[] = []) {
  const [pagina, setPagina] = useState(1);
  const [tamano, setTamanoEstado] = useState<number>(50);
  const clave = JSON.stringify(reiniciarCon);
  const primera = useRef(true);

  useEffect(() => {
    try {
      const guardado = Number(localStorage.getItem(CLAVE));
      if ((TAMANOS as readonly number[]).includes(guardado)) setTamanoEstado(guardado);
    } catch {}
  }, []);

  useEffect(() => {
    if (primera.current) {
      primera.current = false;
      return;
    }
    setPagina(1);
  }, [clave]);

  function setTamano(t: number) {
    setTamanoEstado(t);
    setPagina(1);
    try {
      localStorage.setItem(CLAVE, String(t));
    } catch {}
  }

  return { pagina, tamano, setPagina, setTamano, query: `pagina=${pagina}&tamano=${tamano}` };
}

export function Paginador({ meta, onPagina, onTamano, className = "" }: {
  meta: MetaPagina | null;
  onPagina: (p: number) => void;
  onTamano: (t: number) => void;
  className?: string;
}) {
  if (!meta) return null;
  const { total, pagina, tamano, paginas } = meta;
  const desde = total === 0 ? 0 : (pagina - 1) * tamano + 1;
  const hasta = Math.min(pagina * tamano, total);
  const boton = "flex h-8 w-8 items-center justify-center rounded-md border border-slate-300 bg-white text-slate-600 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40";

  return (
    <div className={`flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-600 ${className}`}>
      <span>
        Mostrando <b className="tabular-nums text-slate-800">{desde.toLocaleString("es-CO")}–{hasta.toLocaleString("es-CO")}</b> de{" "}
        <b className="tabular-nums text-slate-800">{total.toLocaleString("es-CO")}</b>
      </span>
      <div className="flex items-center gap-4">
        <label className="flex items-center gap-2">
          Filas por página
          <select className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm" value={tamano} onChange={(e) => onTamano(Number(e.target.value))}>
            {TAMANOS.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        <div className="flex items-center gap-1">
          <button className={boton} onClick={() => onPagina(1)} disabled={pagina <= 1} aria-label="Primera página"><ChevronsLeft className="h-4 w-4" /></button>
          <button className={boton} onClick={() => onPagina(pagina - 1)} disabled={pagina <= 1} aria-label="Página anterior"><ChevronLeft className="h-4 w-4" /></button>
          <span className="px-2 tabular-nums">Página {pagina} de {paginas}</span>
          <button className={boton} onClick={() => onPagina(pagina + 1)} disabled={pagina >= paginas} aria-label="Página siguiente"><ChevronRight className="h-4 w-4" /></button>
          <button className={boton} onClick={() => onPagina(paginas)} disabled={pagina >= paginas} aria-label="Última página"><ChevronsRight className="h-4 w-4" /></button>
        </div>
      </div>
    </div>
  );
}
