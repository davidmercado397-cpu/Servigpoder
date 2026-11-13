"use client";

import { useEffect, useState } from "react";

/** $1.234.567,5 a partir de un número (vacío si no hay valor) */
function formatear(v: number | null): string {
  if (v === null || Number.isNaN(v)) return "";
  const [entero, decimal] = String(Math.abs(v)).split(".");
  return `${v < 0 ? "-" : ""}$${entero.replace(/\B(?=(\d{3})+(?!\d))/g, ".")}${decimal ? `,${decimal.slice(0, 2)}` : ""}`;
}

/** Lo que se escribió → número: los puntos son de miles y la coma es decimal */
function leer(texto: string): number | null {
  const limpio = texto.replace(/[^\d,-]/g, "").replace(/(?!^)-/g, "");
  if (limpio === "" || limpio === "-") return null;
  const [entero, decimal] = limpio.split(",");
  const n = Number(`${entero || "0"}${decimal !== undefined ? `.${decimal.slice(0, 2)}` : ""}`);
  return Number.isNaN(n) ? null : n;
}

const aNumero = (v: number | string | null | undefined): number | null =>
  v === null || v === undefined || v === "" ? null : typeof v === "number" ? v : Number(v);

/**
 * Campo de dinero: se ve con signo pesos y puntos de miles ($57.120) mientras se escribe.
 * `vacio`: si el campo puede quedar vacío (null); si no, vacío vale 0.
 */
export function InputPesos({ valor, onValor, className = "input", disabled, placeholder, vacio = false }: {
  valor: number | string | null | undefined; onValor: (v: number | null) => void; className?: string; disabled?: boolean;
  placeholder?: string; vacio?: boolean;
}) {
  const [texto, setTexto] = useState(formatear(aNumero(valor)));
  // Si el valor cambia desde afuera (otra fila, la IA, un recálculo), se muestra el nuevo
  useEffect(() => {
    setTexto((actual) => (leer(actual) === aNumero(valor) ? actual : formatear(aNumero(valor))));
  }, [valor]);
  return (
    <input className={className} type="text" inputMode="decimal" disabled={disabled} placeholder={placeholder} value={texto}
      onFocus={(e) => { const t = e.target; setTimeout(() => document.activeElement === t && t.select(), 0); }}
      onChange={(e) => {
        const n = leer(e.target.value);
        // Se conserva la coma final mientras se escriben los decimales
        const coma = /,\d{0,2}$/.test(e.target.value) ? e.target.value.slice(e.target.value.lastIndexOf(",")) : "";
        setTexto(n === null ? (e.target.value.includes("-") ? "-" : "") : formatear(Math.trunc(n)) + (coma || (n % 1 ? formatear(n).slice(formatear(n).indexOf(",")) : "")));
        onValor(n === null ? (vacio ? null : 0) : n);
      }}
      onBlur={() => setTexto(formatear(aNumero(valor)))} />
  );
}
