"use client";

import { CircleAlert, Download, FileSpreadsheet, Link2, Loader2, RotateCcw, Search, Upload, Wrench, X } from "lucide-react";
import { createContext, useContext, useMemo, useRef, useState } from "react";
import { FormularioAlias, type SugerenciaAlias } from "@/components/formulario-alias";
import { Alerta } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";
import { usePermiso } from "@/lib/sesion";

type Hallazgo = { fila: number; cedula: string; columna: string; tipo: string; problema: string; alias: SugerenciaAlias | null };
type Respuesta = {
  nombre: string; archivo: string; resumen: Record<string, number>; cambios: Record<string, number>; hallazgos: Hallazgo[];
  cruce?: Record<string, string>; cruzado?: boolean;
};
type Tipo = "empleados" | "contratos";

// ---- Cruce empleados ↔ contratos: solo en memoria del navegador, se pierde al recargar ----

type Cruce = { cedulas: Record<string, string>; archivo: string } | null;
const CruceCtx = createContext<{ cruce: Cruce; setCruce: (c: Cruce) => void }>({ cruce: null, setCruce: () => {} });

export function CruceProvider({ children }: { children: React.ReactNode }) {
  const [cruce, setCruce] = useState<Cruce>(null);
  return <CruceCtx.Provider value={{ cruce, setCruce }}>{children}</CruceCtx.Provider>;
}

const COLORES: Record<string, string> = {
  Error: "bg-red-100 text-red-700", Revisar: "bg-amber-100 text-amber-800", Advertencia: "bg-orange-50 text-orange-700",
  Informativo: "bg-slate-100 text-slate-600",
};
const TIPOS = ["Error", "Revisar", "Advertencia", "Informativo"];
const NOMBRE_TIPO: Record<string, [string, string]> = {
  Error: ["error", "errores"], Revisar: ["por revisar", "por revisar"], Advertencia: ["advertencia", "advertencias"],
  Informativo: ["informativo", "informativos"],
};
const POR_PAGINA = 100;

function descargar(r: Respuesta) {
  const bytes = Uint8Array.from(atob(r.archivo), (c) => c.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = r.nombre;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function ProcesarPlano({ tipo }: { tipo: Tipo }) {
  const configurar = usePermiso("planos.configurar");
  const { cruce, setCruce } = useContext(CruceCtx);
  const input = useRef<HTMLInputElement>(null);
  const [archivo, setArchivo] = useState<File | null>(null);
  const [modo, setModo] = useState<"completo" | "codigos">("completo");
  const [enie, setEnie] = useState(false);
  const [filaEjemplo, setFilaEjemplo] = useState("");
  const [usarCruce, setUsarCruce] = useState(true);
  const [res, setRes] = useState<Respuesta | null>(null);
  const [procesando, setProcesando] = useState(false);
  const [error, setError] = useState("");
  const [filtro, setFiltro] = useState<string>("");
  const [q, setQ] = useState("");
  const [pagina, setPagina] = useState(0);
  const [alias, setAlias] = useState<SugerenciaAlias | null>(null);
  const [correccion, setCorreccion] = useState<{ cedula: string; columna: string; valor: string } | null>(null);
  const [pendiente, setPendiente] = useState(false); // hay alias o correcciones nuevas sin aplicar

  async function procesar(f: File | null = archivo) {
    if (!f) return;
    setProcesando(true);
    setError("");
    try {
      const form = new FormData();
      form.append("archivo", f);
      if (filaEjemplo.trim()) form.append("fila_ejemplo", filaEjemplo.trim());
      if (tipo === "empleados") {
        form.append("modo", modo);
        form.append("conservar_enie", String(enie));
      } else if (cruce && usarCruce) {
        form.append("empleados_cruce", JSON.stringify(cruce.cedulas));
      }
      const r = await api<Respuesta>(`/planos/${tipo}`, { method: "POST", body: form });
      setRes(r);
      setPagina(0);
      setPendiente(false);
      if (tipo === "empleados" && r.cruce) setCruce({ cedulas: r.cruce, archivo: f.name });
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setProcesando(false);
    }
  }

  function elegir(f: File | undefined) {
    if (!f) return;
    setArchivo(f);
    setRes(null);
    procesar(f);
  }

  const conteo = useMemo(() => {
    const c: Record<string, number> = {};
    res?.hallazgos.forEach((h) => (c[h.tipo] = (c[h.tipo] ?? 0) + 1));
    return c;
  }, [res]);
  const visibles = useMemo(() => {
    const t = q.trim().toLowerCase();
    return (res?.hallazgos ?? []).filter((h) => (!filtro || h.tipo === filtro) &&
      (!t || h.cedula.includes(t) || h.problema.toLowerCase().includes(t) || h.columna.toLowerCase() === t));
  }, [res, filtro, q]);

  async function guardarCorreccion() {
    if (!correccion) return;
    try {
      await api("/planos/correcciones", { method: "POST", json: { plano: tipo, ...correccion } });
      setCorreccion(null);
      setPendiente(true);
    } catch (e) {
      setError(mensajeError(e));
    }
  }

  const r = res?.resumen ?? {};
  return (
    <div className="space-y-5">
      <div className="tarjeta p-5">
        <div className="flex flex-wrap items-end gap-4">
          {tipo === "empleados" && (
            <div>
              <label className="label">Qué convertir</label>
              <div className="flex rounded-md border border-slate-300 bg-white p-0.5 text-sm">
                {([["completo", "Todo el plano"], ["codigos", "Solo códigos y fechas"]] as const).map(([v, t]) => (
                  <button key={v} onClick={() => setModo(v)}
                    className={`rounded px-3 py-1.5 ${modo === v ? "bg-marca-600 text-white" : "text-slate-600 hover:bg-slate-100"}`}>{t}</button>
                ))}
              </div>
            </div>
          )}
          <div className="w-40">
            <label className="label">Fila de ejemplo</label>
            <input className="input" inputMode="numeric" placeholder="Ninguna" value={filaEjemplo}
              onChange={(e) => setFilaEjemplo(e.target.value.replace(/\D/g, ""))} />
          </div>
          {tipo === "empleados" && modo === "completo" && (
            <label className="flex items-center gap-2 pb-2 text-sm text-slate-600">
              <input type="checkbox" checked={enie} onChange={(e) => setEnie(e.target.checked)} /> Conservar la Ñ en nombres
            </label>
          )}
          <div className="ml-auto flex gap-2">
            <input ref={input} type="file" accept=".xlsx" className="hidden"
              onChange={(e) => { elegir(e.target.files?.[0]); e.target.value = ""; }} />
            <button className="btn-primario" disabled={procesando} onClick={() => input.current?.click()}>
              {procesando ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
              {procesando ? "Procesando…" : archivo ? "Otro plano" : "Cargar plano"}
            </button>
            {archivo && (
              <button className={pendiente ? "btn-primario" : "btn-secundario"} disabled={procesando} onClick={() => procesar()}>
                <RotateCcw className="h-4 w-4" /> Volver a procesar
              </button>
            )}
          </div>
        </div>
        {tipo === "contratos" && (
          <div className="mt-4 flex items-center gap-2 text-sm">
            <Link2 className="h-4 w-4 text-slate-400" />
            {cruce ? (
              <label className="flex items-center gap-2 text-slate-600">
                <input type="checkbox" checked={usarCruce} onChange={(e) => setUsarCruce(e.target.checked)} />
                Cruzar con el plano de empleados «{cruce.archivo}» ({Object.keys(cruce.cedulas).length} cédulas): cédula y fecha de ingreso
              </label>
            ) : (
              <span className="text-slate-500">Si procesas primero el plano de empleados en esta sesión, se verifica que cada contrato tenga su empleado y la misma fecha de ingreso.</span>
            )}
          </div>
        )}
        <p className="mt-3 text-xs text-slate-500">
          El plano debe traer una sola hoja con información. No se guarda en el servidor: se procesa y se devuelve listo para SIESA, con una hoja «Errores».
        </p>
      </div>

      {error && <Alerta>{error}</Alerta>}
      {pendiente && <Alerta tipo="info">Guardaste alias o correcciones: pulsa «Volver a procesar» para aplicarlos.</Alerta>}

      {res && (
        <>
          <div className="tarjeta flex flex-wrap items-center gap-6 p-5">
            <div className="flex items-center gap-3">
              <FileSpreadsheet className="h-9 w-9 text-violet-600" />
              <div>
                <p className="font-semibold text-slate-800">{res.nombre}</p>
                <p className="text-sm text-slate-500">
                  {r.filas ?? 0} filas{r.filas_eliminadas ? ` · ${r.filas_eliminadas} vacías quitadas` : ""}
                  {r.lugares_codificados ? ` · ${r.lugares_codificados} lugares codificados` : ""}
                  {r.fechas_hasta_calculadas ? ` · ${r.fechas_hasta_calculadas} fechas «hasta» calculadas` : ""}
                  {r.correcciones ? ` · ${r.correcciones} correcciones aplicadas` : ""}
                  {res.cruzado ? " · cruzado con empleados" : ""}
                </p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {TIPOS.filter((t) => conteo[t]).map((t) => (
                <span key={t} className={`rounded-full px-3 py-1 text-sm font-medium ${COLORES[t]}`}>{conteo[t]} {(conteo[t] === 1 ? NOMBRE_TIPO[t][0] : NOMBRE_TIPO[t][1])}</span>
              ))}
              {!res.hallazgos.length && <span className="rounded-full bg-green-100 px-3 py-1 text-sm font-medium text-green-800">Sin hallazgos</span>}
            </div>
            <button className="btn-primario ml-auto" onClick={() => descargar(res)}><Download className="h-4 w-4" /> Descargar para SIESA</button>
          </div>

          {Object.keys(res.cambios).length > 0 && (
            <div className="tarjeta p-5">
              <h2 className="mb-2 font-semibold text-slate-700">Valores corregidos por regla</h2>
              <ul className="grid gap-1 text-sm text-slate-600 sm:grid-cols-2">
                {Object.entries(res.cambios).map(([c, n]) => <li key={c}><span className="font-mono">{c}</span> <span className="text-slate-400">· {n} {n === 1 ? "fila" : "filas"}</span></li>)}
              </ul>
            </div>
          )}

          {res.hallazgos.length > 0 && (
            <div className="tarjeta overflow-hidden">
              <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 p-4">
                <button onClick={() => setFiltro("")} className={`rounded-full px-3 py-1 text-sm ${!filtro ? "bg-marca-600 text-white" : "bg-slate-100 text-slate-600"}`}>
                  Todos ({res.hallazgos.length})
                </button>
                {TIPOS.filter((t) => conteo[t]).map((t) => (
                  <button key={t} onClick={() => { setFiltro(t); setPagina(0); }}
                    className={`rounded-full px-3 py-1 text-sm ${filtro === t ? "bg-marca-600 text-white" : "bg-slate-100 text-slate-600"}`}>{t} ({conteo[t]})</button>
                ))}
                <div className="relative ml-auto w-64">
                  <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-slate-400" />
                  <input className="input pl-8" placeholder="Cédula, columna o texto" value={q} onChange={(e) => { setQ(e.target.value); setPagina(0); }} />
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="tabla">
                  <thead><tr><th>Fila</th><th>Cédula</th><th>Columna</th><th>Tipo</th><th>Problema</th>{configurar && <th />}</tr></thead>
                  <tbody>
                    {visibles.slice(pagina * POR_PAGINA, (pagina + 1) * POR_PAGINA).map((h, i) => (
                      <tr key={`${h.fila}-${h.columna}-${i}`}>
                        <td className="text-slate-500">{h.fila}</td>
                        <td className="font-mono text-xs">{h.cedula}</td>
                        <td className="font-mono text-xs">{h.columna}</td>
                        <td><span className={`rounded-full px-2 py-0.5 text-xs font-medium ${COLORES[h.tipo] ?? ""}`}>{h.tipo}</span></td>
                        <td className="text-slate-700">{h.problema}</td>
                        {configurar && (
                          <td className="whitespace-nowrap text-right">
                            {h.alias && (
                              <button className="text-xs font-medium text-marca-700 hover:underline" onClick={() => setAlias(h.alias)}>
                                {h.tipo === "Revisar" ? "Confirmar como alias" : "Crear alias"}
                              </button>
                            )}
                            {!h.alias && /^[A-Z]{1,2}$/.test(h.columna) && h.cedula && (
                              <button className="inline-flex items-center gap-1 text-xs font-medium text-marca-700 hover:underline"
                                onClick={() => setCorreccion({ cedula: h.cedula, columna: h.columna, valor: "" })}>
                                <Wrench className="h-3 w-3" /> Corregir
                              </button>
                            )}
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {visibles.length > POR_PAGINA && (
                <div className="flex items-center justify-between border-t border-slate-100 px-4 py-2 text-sm text-slate-500">
                  <span>{pagina * POR_PAGINA + 1}–{Math.min((pagina + 1) * POR_PAGINA, visibles.length)} de {visibles.length}</span>
                  <div className="flex gap-2">
                    <button className="btn-secundario" disabled={pagina === 0} onClick={() => setPagina(pagina - 1)}>Anterior</button>
                    <button className="btn-secundario" disabled={(pagina + 1) * POR_PAGINA >= visibles.length} onClick={() => setPagina(pagina + 1)}>Siguiente</button>
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}

      {!res && !procesando && !error && (
        <div className="flex flex-col items-center gap-2 rounded-lg border-2 border-dashed border-slate-200 p-10 text-center text-slate-500"
          onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); elegir(e.dataTransfer.files?.[0]); }}>
          <CircleAlert className="h-8 w-8 text-slate-300" />
          Arrastra aquí el plano de {tipo} (.xlsx) o usa «Cargar plano».
        </div>
      )}

      {(alias || correccion) && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-4" onClick={() => { setAlias(null); setCorreccion(null); }}>
          <div className="tarjeta w-full max-w-lg p-5" onClick={(e) => e.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="font-semibold text-slate-800">{alias ? "Alias" : "Corrección manual"}</h2>
              <button onClick={() => { setAlias(null); setCorreccion(null); }}><X className="h-5 w-5 text-slate-400" /></button>
            </div>
            {alias && <FormularioAlias inicial={alias} onCancelar={() => setAlias(null)} onGuardado={() => { setAlias(null); setPendiente(true); }} />}
            {correccion && (
              <div className="space-y-3">
                <p className="text-sm text-slate-600">
                  Cada vez que llegue la cédula <b>{correccion.cedula}</b>, la columna <b>{correccion.columna}</b> se reemplaza por este valor.
                  Para fechas use AAAAMMDD.
                </p>
                <input className="input" autoFocus value={correccion.valor} onChange={(e) => setCorreccion({ ...correccion, valor: e.target.value })}
                  onKeyDown={(e) => e.key === "Enter" && correccion.valor.trim() && guardarCorreccion()} />
                <div className="flex justify-end gap-2">
                  <button className="btn-secundario" onClick={() => setCorreccion(null)}>Cancelar</button>
                  <button className="btn-primario" disabled={!correccion.valor.trim()} onClick={guardarCorreccion}>Guardar corrección</button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
