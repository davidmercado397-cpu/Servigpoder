"use client";

import { BookOpenCheck, Loader2, Sparkles } from "lucide-react";
import { useState } from "react";
import { Modal } from "@/components/costeo";
import { Alerta } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";
import type { Correccion, Producto } from "@/lib/contabilidad";

/**
 * Contabilidad cambió la cuenta que propuso el agente: se le ofrece que el agente lo aprenda. El agente redacta la regla
 * (con el motivo, si se lo dan), contabilidad la revisa o la ajusta y la guarda en las reglas de la empresa.
 */
export function AprenderCorrecciones({ facturaId, correcciones, productos, onCerrar }: {
  facturaId: number; correcciones: Correccion[]; productos: Producto[]; onCerrar: () => void;
}) {
  const [i, setI] = useState(0);
  const [motivo, setMotivo] = useState("");
  const [borrador, setBorrador] = useState<{ texto: string; cuentas: string; ejemplo: string } | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState("");
  const [guardadas, setGuardadas] = useState(0);
  const c = correcciones[i];
  const nombre = (codigo: string) => productos.find((p) => p.codigo === codigo)?.nombre ?? "";

  function siguiente() {
    setMotivo(""); setBorrador(null); setError("");
    if (i + 1 < correcciones.length) setI(i + 1); else onCerrar();
  }
  async function redactar() {
    setError(""); setOcupado(true);
    try {
      setBorrador(await api("/contabilidad/reglas/redactar", { method: "POST", json: { factura_id: facturaId, linea_id: c.linea_id,
        cuenta_agente: c.cuenta_agente, cuenta_correcta: c.cuenta_correcta, motivo } }));
    } catch (e) { setError(mensajeError(e)); } finally { setOcupado(false); }
  }
  async function guardar() {
    if (!borrador) return;
    setError(""); setOcupado(true);
    try {
      await api("/contabilidad/reglas", { method: "POST", json: { ...borrador, origen: "correccion" } });
      setGuardadas(guardadas + 1);
      siguiente();
    } catch (e) { setError(mensajeError(e)); } finally { setOcupado(false); }
  }

  return (
    <Modal titulo={`¿El agente debe aprender esta corrección?${correcciones.length > 1 ? ` (${i + 1} de ${correcciones.length})` : ""}`} onCerrar={onCerrar} ancho="max-w-2xl">
      <div className="space-y-3 text-sm">
        <div className="rounded-lg bg-slate-50 p-3">
          <p className="text-slate-500">Línea {c.orden}: {c.descripcion}</p>
          <p className="mt-1">El agente propuso <b>{c.cuenta_agente}</b> {nombre(c.cuenta_agente)} y usted la cambió a{" "}
            <b className="text-marca-700">{c.cuenta_correcta}</b> {nombre(c.cuenta_correcta)}.</p>
        </div>
        {!borrador ? (
          <>
            <div><label className="label">¿Por qué va en esa cuenta? (opcional, ayuda a que la regla quede bien)</label>
              <textarea className="input" rows={2} maxLength={1000} value={motivo} onChange={(e) => setMotivo(e.target.value)}
                placeholder="Ej.: en Speed los intereses de mora se llevan al costo del servicio, no a la cuenta de intereses" /></div>
            {error && <Alerta>{error}</Alerta>}
            <div className="flex justify-end gap-2">
              <button className="btn-secundario" disabled={ocupado} onClick={siguiente}>No, fue un caso puntual</button>
              <button className="btn-primario" disabled={ocupado} onClick={redactar}>
                {ocupado ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} Sí, redactar la regla</button>
            </div>
          </>
        ) : (
          <>
            <div><label className="label">Regla que aprenderá el agente (puede ajustarla)</label>
              <textarea className="input" rows={4} maxLength={2000} value={borrador.texto} onChange={(e) => setBorrador({ ...borrador, texto: e.target.value })} /></div>
            <div><label className="label">Cuentas que menciona</label>
              <input className="input" maxLength={200} value={borrador.cuentas} onChange={(e) => setBorrador({ ...borrador, cuentas: e.target.value })} /></div>
            <p className="text-xs text-slate-500">Queda en Agente contable → Reglas de la empresa, donde se puede editar o desactivar.</p>
            {error && <Alerta>{error}</Alerta>}
            <div className="flex justify-end gap-2">
              <button className="btn-secundario" disabled={ocupado} onClick={siguiente}>No guardar</button>
              <button className="btn-primario" disabled={ocupado || borrador.texto.trim().length < 5} onClick={guardar}>
                {ocupado ? <Loader2 className="h-4 w-4 animate-spin" /> : <BookOpenCheck className="h-4 w-4" />} Guardar la regla</button>
            </div>
          </>
        )}
        {guardadas > 0 && <p className="text-xs text-green-700">{guardadas} {guardadas === 1 ? "regla guardada" : "reglas guardadas"}.</p>}
      </div>
    </Modal>
  );
}
