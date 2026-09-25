// Estados de cobertura: color de estado reservado + ícono + texto (nunca solo color)
export const ESTADOS: Record<string, { texto: string; icono: string; clase: string; celda: string }> = {
  ok: { texto: "Cubierto", icono: "✓", clase: "bg-[#0ca30c]/10 text-[#086b08] ring-[#0ca30c]/40", celda: "bg-[#0ca30c]/15 text-[#086b08]" },
  exceso: { texto: "Exceso", icono: "▲", clase: "bg-[#fab219]/15 text-[#8a5a00] ring-[#fab219]/60", celda: "bg-[#fab219]/25 text-[#8a5a00]" },
  mixto: { texto: "Hueco y exceso", icono: "◆", clase: "bg-[#ec835a]/15 text-[#9a3f1a] ring-[#ec835a]/60", celda: "bg-[#ec835a]/25 text-[#9a3f1a]" },
  hueco: { texto: "Hueco", icono: "▼", clase: "bg-[#d03b3b]/10 text-[#a32525] ring-[#d03b3b]/40", celda: "bg-[#d03b3b]/20 text-[#a32525]" },
  sin_servicio: { texto: "Sin servicio", icono: "–", clase: "bg-slate-100 text-slate-500 ring-slate-200", celda: "bg-slate-50 text-slate-400" },
};

export function EstadoInsignia({ estado }: { estado: string }) {
  const e = ESTADOS[estado] ?? ESTADOS.ok;
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${e.clase}`}>
      <span aria-hidden>{e.icono}</span>
      {e.texto}
    </span>
  );
}

export function num(v: string | number | null | undefined, dec = 0) {
  const n = Number(v ?? 0);
  return n.toLocaleString("es-CO", { maximumFractionDigits: dec, minimumFractionDigits: 0 });
}
