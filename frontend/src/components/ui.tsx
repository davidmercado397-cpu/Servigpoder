"use client";

import { useRef, useState } from "react";

export function Titulo({ children, accion }: { children: React.ReactNode; accion?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
      <h1 className="text-2xl font-bold text-marca-900">{children}</h1>
      {accion}
    </div>
  );
}

export function Alerta({ tipo = "error", children }: { tipo?: "error" | "ok" | "info"; children: React.ReactNode }) {
  const color = { error: "bg-red-50 text-red-700", ok: "bg-green-50 text-green-800", info: "bg-marca-50 text-marca-900" }[tipo];
  return <div className={`rounded-md px-3 py-2 text-sm ${color}`}>{children}</div>;
}

export function Pestanas<T extends string>({ opciones, valor, onChange }: { opciones: [T, string][]; valor: T; onChange: (v: T) => void }) {
  return (
    <div className="mb-4 flex gap-1 border-b border-slate-200">
      {opciones.map(([v, texto]) => (
        <button
          key={v}
          onClick={() => onChange(v)}
          className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium ${valor === v ? "border-marca-600 text-marca-700" : "border-transparent text-slate-500 hover:text-slate-700"}`}
        >
          {texto}
        </button>
      ))}
    </div>
  );
}

export function SubirArchivo({ texto, onArchivo, deshabilitado }: { texto: string; onArchivo: (f: File) => Promise<void>; deshabilitado?: boolean }) {
  const ref = useRef<HTMLInputElement>(null);
  const [cargando, setCargando] = useState(false);
  return (
    <>
      <input
        ref={ref}
        type="file"
        accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        className="hidden"
        onChange={async (e) => {
          const f = e.target.files?.[0];
          e.target.value = "";
          if (!f) return;
          setCargando(true);
          try {
            await onArchivo(f);
          } finally {
            setCargando(false);
          }
        }}
      />
      <button className="btn-primario" disabled={cargando || deshabilitado} onClick={() => ref.current?.click()}>
        {cargando ? "Procesando…" : texto}
      </button>
    </>
  );
}

export function Insignia({ children, color = "bg-slate-100 text-slate-700" }: { children: React.ReactNode; color?: string }) {
  return <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${color}`}>{children}</span>;
}
