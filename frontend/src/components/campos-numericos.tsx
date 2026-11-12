"use client";

import { useEffect } from "react";

// Setter nativo del valor: React no lo ve como un cambio suyo y dispara su onChange con el valor corregido
const fijarValor = typeof window !== "undefined" ? Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set : undefined;

function esNumero(t: EventTarget | null): t is HTMLInputElement {
  return t instanceof HTMLInputElement && t.type === "number" && !t.readOnly && !t.disabled;
}

/**
 * Comportamiento de todos los campos numéricos de la plataforma:
 * - al entrar al campo se selecciona lo que tiene, así lo que se escribe lo reemplaza (un 0 no estorba);
 * - los ceros de adelante se quitan: sobre un 0, escribir 1 deja 1 y no 01 (los decimales como 0,5 se respetan).
 */
export function CamposNumericos() {
  useEffect(() => {
    const alEntrar = (e: FocusEvent) => {
      const t = e.target;
      if (esNumero(t)) setTimeout(() => document.activeElement === t && t.select(), 0);
    };
    // En la fase de captura del documento: corre antes que React, que lee el valor ya corregido
    const alEscribir = (e: Event) => {
      const t = e.target;
      if (!esNumero(t) || !fijarValor) return;
      const limpio = t.value.replace(/^(-?)0+(?=\d)/, "$1");
      if (limpio !== t.value) fijarValor.call(t, limpio);
    };
    document.addEventListener("focusin", alEntrar);
    document.addEventListener("input", alEscribir, true);
    return () => {
      document.removeEventListener("focusin", alEntrar);
      document.removeEventListener("input", alEscribir, true);
    };
  }, []);
  return null;
}
