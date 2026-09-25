export const MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];

export const DIAS = ["L", "M", "X", "J", "V", "S", "D"];

export function nombreMes(anio: number, mes: number) {
  return `${MESES[mes - 1]} ${anio}`;
}

export function hora(h: string | null) {
  return h ? h.slice(0, 5) : "";
}

export function diasTexto(mascara: number) {
  if (mascara === 127) return "L-D";
  if (mascara === 31) return "L-V";
  if (mascara === 63) return "L-S";
  return DIAS.filter((_, i) => mascara & (1 << i)).join(" ");
}

export function franjaTexto(f: { dias: number; inicio: string; fin: string; cantidad: number }) {
  const rango = f.inicio === f.fin ? "24 h" : `${hora(f.inicio)}–${hora(f.fin)}`;
  return `${diasTexto(f.dias)} ${rango}${f.cantidad > 1 ? ` ×${f.cantidad}` : ""}`;
}

export const ESTADO_COLOR: Record<string, string> = {
  borrador: "bg-amber-100 text-amber-800",
  aprobado: "bg-green-100 text-green-800",
  cerrado: "bg-slate-200 text-slate-700",
};
