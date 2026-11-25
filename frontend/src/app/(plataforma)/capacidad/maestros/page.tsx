"use client";

import { Paginador, metaDe, usePaginacion, type MetaPagina } from "@/components/paginacion";
import { useCallback, useEffect, useState } from "react";
import { Alerta, Insignia, Pestanas, SubirArchivo, Titulo } from "@/components/ui";
import { api, apiEnvelope, mensajeError, subirArchivo, type Novedad, type PorAclarar, type Puesto, type Turno } from "@/lib/api";
import { hora } from "@/lib/formato";
import { FormularioPuesto, type PuestoCreado } from "@/components/formulario-puesto";
import { SelectorPuesto } from "@/components/selector-puesto";
import Link from "next/link";
import { MESES } from "@/lib/formato";
import { usePermiso } from "@/lib/sesion";

type Tab = "aclarar" | "puestos" | "turnos" | "novedades";

export default function MaestrosPage() {
  const [tab, setTab] = useState<Tab>("aclarar");
  return (
    <div className="max-w-6xl">
      <Titulo>Maestros</Titulo>
      <Pestanas<Tab>
        opciones={[["aclarar", "Puestos por aclarar"], ["puestos", "Ubicaciones y puestos"], ["turnos", "Horarios SIESA"], ["novedades", "Novedades"]]}
        valor={tab}
        onChange={setTab}
      />
      {tab === "aclarar" && <PorAclararTab />}
      {tab === "puestos" && <PuestosTab />}
      {tab === "turnos" && <TurnosTab />}
      {tab === "novedades" && <NovedadesTab />}
    </div>
  );
}

function PorAclararTab() {
  const puedeEditar = usePermiso("capacidad.maestros.gestionar");
  const [items, setItems] = useState<PorAclarar[]>([]);
  const [msg, setMsg] = useState<{ tipo: "ok" | "error"; texto: string } | null>(null);
  const [meta, setMeta] = useState<MetaPagina | null>(null);
  const [creando, setCreando] = useState<PorAclarar | null>(null);
  const [matriz, setMatriz] = useState<{ id: number; etiqueta: string; estado: string } | null>(null);
  const pag = usePaginacion();

  const cargar = useCallback(async () => {
    const r = await apiEnvelope<PorAclarar[]>(`/capacidad/maestros/por-aclarar?${pag.query}`);
    setItems(r.data ?? []);
    setMeta(metaDe(r));
    const m = r.meta.extra?.matriz as { id: number; estado: string } | null | undefined;
    const mes = r.meta.extra?.mes as number | undefined;
    const anio = r.meta.extra?.anio as number | undefined;
    setMatriz(m && mes && anio ? { ...m, etiqueta: `${MESES[mes - 1]} ${anio}` } : null);
  }, [pag.query]);

  function creado(r: PuestoCreado) {
    setCreando(null);
    setMsg({
      tipo: "ok",
      texto: `Puesto ${r.puesto.codigo} creado${r.ubicacion_creada ? ` (y la ubicación ${r.puesto.ubicacion.codigo})` : ""}` +
        `${r.equivalencia ? `; el código ${r.equivalencia} de SIESA quedó asignado` : ""}` +
        `${r.matriz_puesto_id ? `. Configure su cobertura en la Matriz comercial (está en "por revisar")` : ""}.`,
    });
    cargar();
  }

  useEffect(() => {
    cargar();
  }, [cargar]);

  async function asignar(codigo: string, puestoId: number) {
    try {
      await api("/capacidad/maestros/equivalencias", { method: "PUT", json: { codigo_siesa: codigo, puesto_id: puestoId } });
      setMsg({ tipo: "ok", texto: `Equivalencia de ${codigo} guardada` });
      cargar();
    } catch (e) {
      setMsg({ tipo: "error", texto: mensajeError(e) });
    }
  }

  return (
    <div className="space-y-4">
      <Alerta tipo="info">
        Códigos de puesto de la última programación cargada que no se encontraron en la matriz, o que se cruzaron de forma
        aproximada. Asigne a qué puesto corresponden o confirme la sugerencia.
      </Alerta>
      {msg && <Alerta tipo={msg.tipo}>{msg.texto}</Alerta>}
      <div className="tarjeta overflow-x-auto">
        <table className="tabla">
          <thead>
            <tr><th>Código SIESA</th><th>Descripción en SIESA</th><th>Ubicación en SIESA</th><th>Filas</th><th>Estado</th><th>Puesto del maestro</th></tr>
          </thead>
          <tbody>
            {items.length === 0 && <tr><td colSpan={6} className="text-center text-slate-500">No hay puestos por aclarar</td></tr>}
            {items.map((i) => (
              <tr key={i.codigo_siesa}>
                <td className="font-mono font-semibold">{i.codigo_siesa}</td>
                <td className="max-w-md">{i.descripcion}</td>
                <td className="text-sm">
                  <span className="font-mono">{i.ubicacion_siesa}</span>
                  <span className="block text-xs text-slate-500">{i.ubicacion?.nombre ?? i.ubicacion_nombre}</span>
                </td>
                <td>{i.filas}</td>
                <td>
                  {i.motivo === "aproximada" ? <Insignia color="bg-amber-100 text-amber-800">Verificar</Insignia> : <Insignia color="bg-red-100 text-red-700">Sin equivalencia</Insignia>}
                </td>
                <td>
                  {puedeEditar ? (
                    <div className="flex items-center gap-2">
                      <SelectorPuesto onElegir={(p) => asignar(i.codigo_siesa, p.id)} />
                      {i.puesto_sugerido && (
                        <button className="btn-secundario whitespace-nowrap" onClick={() => asignar(i.codigo_siesa, i.puesto_sugerido!.id)}>
                          Confirmar {i.puesto_sugerido.codigo}
                        </button>
                      )}
                      <button className="btn-secundario whitespace-nowrap" onClick={() => { setMsg(null); setCreando(i); }}
                        title="El puesto no existe en el maestro: crearlo con este código">
                        Crear puesto
                      </button>
                    </div>
                  ) : (
                    i.puesto_sugerido?.codigo ?? "—"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <Paginador meta={meta} onPagina={pag.setPagina} onTamano={pag.setTamano} />
      </div>
      {matriz && (
        <p className="text-xs text-slate-500">
          Al crear un puesto se puede agregar a la <Link href="/capacidad/matriz" className="text-marca-600 hover:underline">matriz comercial de {matriz.etiqueta}</Link>
          {matriz.estado !== "borrador" && ` (está ${matriz.estado})`}.
        </p>
      )}
      {creando && (
        <FormularioPuesto
          titulo="Crear puesto de SIESA"
          inicial={{
            codigo: creando.codigo_siesa, descripcion: creando.descripcion, codigo_siesa: creando.codigo_siesa,
            ubicacion_codigo: creando.ubicacion?.codigo ?? creando.ubicacion_siesa, ubicacion_nombre: creando.ubicacion_nombre,
          }}
          matriz={matriz && matriz.estado !== "cerrado" ? matriz : null}
          onCreado={creado}
          onCancelar={() => setCreando(null)}
        />
      )}
    </div>
  );
}

function PuestosTab() {
  const puedeEditar = usePermiso("capacidad.maestros.gestionar");
  const [q, setQ] = useState("");
  const [puestos, setPuestos] = useState<Puesto[]>([]);
  const [meta, setMeta] = useState<MetaPagina | null>(null);
  // Orden por la columna escogida (clic en el título; otro clic invierte)
  const [orden, setOrden] = useState<{ campo: string; direccion: "asc" | "desc" }>({ campo: "poder", direccion: "asc" });
  const pag = usePaginacion([q, orden.campo, orden.direccion]);
  // Puestos marcados para cambiarles la ciudad a la vez (se conservan al pasar de página)
  const [marcados, setMarcados] = useState<Map<number, string>>(new Map());
  const [ciudadVarios, setCiudadVarios] = useState("");

  const cargar = useCallback(async () => {
    const params = new URLSearchParams({ q, orden: orden.campo, direccion: orden.direccion });
    const r = await apiEnvelope<Puesto[]>(`/capacidad/maestros/puestos?${params}&${pag.query}`);
    setPuestos(r.data ?? []);
    setMeta(metaDe(r));
  }, [q, orden, pag.query]);

  function ordenar(campo: string) {
    setOrden((o) => ({ campo, direccion: o.campo === campo && o.direccion === "asc" ? "desc" : "asc" }));
  }

  function marcar(lista: Puesto[], si: boolean) {
    setMarcados((m) => {
      const n = new Map(m);
      lista.forEach((p) => (si ? n.set(p.id, p.codigo) : n.delete(p.id)));
      return n;
    });
  }

  async function cambiarCiudadVarios() {
    setError("");
    const ciudad = ciudadVarios.trim();
    const texto = ciudad ? `la ciudad ${ciudad.toUpperCase()}` : "la ciudad de su ubicación (se quita la corrección)";
    if (!confirm(`¿Poner ${texto} a ${marcados.size} puesto(s)?`)) return;
    try {
      const r = await api<{ actualizados: number }>("/capacidad/maestros/puestos/ciudad", { method: "POST", json: { ids: [...marcados.keys()], ciudad } });
      setAviso(`${r.actualizados} puesto(s) quedaron con ${texto}. Al importar la matriz o la programación de SIESA se respeta.`);
      setMarcados(new Map());
      setCiudadVarios("");
      cargar();
      api<string[]>("/capacidad/maestros/ciudades").then(setCiudades).catch(() => {});
    } catch (e) {
      setError(mensajeError(e));
    }
  }

  useEffect(() => {
    const t = setTimeout(cargar, 250);
    return () => clearTimeout(t);
  }, [cargar]);

  const [creando, setCreando] = useState(false);
  const [aviso, setAviso] = useState("");
  const [error, setError] = useState("");
  const [edicion, setEdicion] = useState<{ id: number; codigo: string; descripcion: string; ciudad: string } | null>(null);
  const [ciudades, setCiudades] = useState<string[]>([]);
  useEffect(() => {
    api<string[]>("/capacidad/maestros/ciudades").then(setCiudades).catch(() => {});
  }, []);

  async function cambiar(p: Puesto, campo: "excluido" | "activo" | "cubre_descansos", valor: boolean) {
    await api(`/capacidad/maestros/puestos/${p.id}`, { method: "PATCH", json: { [campo]: valor } });
    cargar();
  }

  async function guardarEdicion() {
    if (!edicion) return;
    setError("");
    try {
      const p = await api<Puesto>(`/capacidad/maestros/puestos/${edicion.id}`, {
        method: "PATCH", json: { codigo: edicion.codigo, descripcion: edicion.descripcion, ciudad: edicion.ciudad },
      });
      setEdicion(null);
      setAviso(`Puesto ${p.codigo} actualizado. Al importar la matriz o la programación de SIESA se respeta lo corregido aquí.`);
      cargar();
      api<string[]>("/capacidad/maestros/ciudades").then(setCiudades).catch(() => {});
    } catch (e) {
      setError(mensajeError(e));
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <input className="input max-w-sm" placeholder="Buscar por código, puesto o ubicación…" value={q} onChange={(e) => setQ(e.target.value)} />
        {puedeEditar && <button className="btn-primario ml-auto" onClick={() => { setAviso(""); setCreando(true); }}>Nuevo puesto</button>}
      </div>
      {aviso && <Alerta tipo="ok">{aviso}</Alerta>}
      {error && <Alerta>{error}</Alerta>}
      <datalist id="ciudades-puesto">{ciudades.map((c) => <option key={c} value={c} />)}</datalist>
      {creando && (
        <FormularioPuesto
          titulo="Nuevo puesto"
          onCreado={(r) => {
            setCreando(false);
            setAviso(`Puesto ${r.puesto.codigo} creado. Para incluirlo en la base comercial, agréguelo en la Matriz comercial del mes.`);
            setQ(r.puesto.codigo);
          }}
          onCancelar={() => setCreando(false)}
        />
      )}
      {puedeEditar && marcados.size > 0 && (
        <div className="tarjeta flex flex-wrap items-center gap-3 border-marca-200 bg-marca-50 p-3 text-sm">
          <span className="font-semibold text-marca-900">{marcados.size} puesto(s) seleccionado(s)</span>
          <span className="max-w-xs truncate text-xs text-slate-500" title={[...marcados.values()].join(", ")}>{[...marcados.values()].join(", ")}</span>
          <input className="input w-48" list="ciudades-puesto" placeholder="Nueva ciudad" value={ciudadVarios} onChange={(e) => setCiudadVarios(e.target.value)}
            title="Vacía = cada puesto vuelve a la ciudad de su ubicación" />
          <button className="btn-primario" onClick={cambiarCiudadVarios}>Cambiar ciudad</button>
          <button className="btn-secundario" onClick={() => setMarcados(new Map())}>Quitar selección</button>
        </div>
      )}
      <div className="tarjeta overflow-x-auto">
        <table className="tabla">
          <thead>
            <tr>
              {puedeEditar && (
                <th className="w-8"><input type="checkbox" title="Seleccionar todos los de esta página"
                  checked={puestos.length > 0 && puestos.every((p) => marcados.has(p.id))}
                  onChange={(e) => marcar(puestos, e.target.checked)} /></th>
              )}
              {([["poder", "PODER"], ["ubicacion", "Ubicación"], ["puesto", "Puesto"], ["descripcion", "Descripción"], ["ciudad", "Ciudad"],
                ["tipo", "Tipo"], ["excluido", "Excluido"], ["activo", "Activo"], ["descansos", "Descansos se cubren"]] as const).map(([campo, titulo]) => (
                <th key={campo}>
                  <button type="button" className="inline-flex items-center gap-1 hover:text-marca-700" onClick={() => ordenar(campo)}
                    title={`Ordenar por ${titulo.toLowerCase()}`}>
                    {titulo}
                    <span className={orden.campo === campo ? "text-marca-600" : "text-slate-300"}>
                      {orden.campo === campo && orden.direccion === "desc" ? "▼" : "▲"}
                    </span>
                  </button>
                </th>
              ))}
              <th />
            </tr>
          </thead>
          <tbody>
            {puestos.map((p) => edicion?.id === p.id ? (
              <tr key={p.id} className="bg-marca-50">
                {puedeEditar && <td />}
                <td className="font-mono">{p.ubicacion.codigo}</td>
                <td>{p.ubicacion.nombre}</td>
                <td><input className="input w-28 font-mono" value={edicion.codigo} onChange={(e) => setEdicion({ ...edicion, codigo: e.target.value })} /></td>
                <td><input className="input min-w-48" value={edicion.descripcion} onChange={(e) => setEdicion({ ...edicion, descripcion: e.target.value })} /></td>
                <td><input className="input w-40" list="ciudades-puesto" placeholder={p.ubicacion.ciudad ?? "Ciudad"} value={edicion.ciudad}
                  onChange={(e) => setEdicion({ ...edicion, ciudad: e.target.value })} title="Vacía = la ciudad de la ubicación" /></td>
                <td colSpan={4} className="text-xs text-slate-500">El código anterior se sigue reconociendo al importar.</td>
                <td className="whitespace-nowrap">
                  <button className="btn-primario px-2 py-1 text-xs" onClick={guardarEdicion}>Guardar</button>
                  <button className="ml-1 btn-secundario px-2 py-1 text-xs" onClick={() => { setEdicion(null); setError(""); }}>Cancelar</button>
                </td>
              </tr>
            ) : (
              <tr key={p.id} className={marcados.has(p.id) ? "bg-marca-50/60" : ""}>
                {puedeEditar && <td><input type="checkbox" checked={marcados.has(p.id)} onChange={(e) => marcar([p], e.target.checked)} /></td>}
                <td className="font-mono">{p.ubicacion.codigo}</td>
                <td>{p.ubicacion.nombre}</td>
                <td className="font-mono font-semibold">{p.codigo}</td>
                <td>{p.descripcion}{p.descripcion_manual && <span className="ml-1 text-xs text-sky-700" title="Corregida a mano: la importación no la cambia">✎</span>}</td>
                <td>{p.ciudad ?? p.ubicacion.ciudad ?? "—"}{p.ciudad_manual && <span className="ml-1 text-xs text-sky-700" title={`Corregida a mano (la ubicación dice ${p.ubicacion.ciudad ?? "—"}): la importación no la cambia`}>✎</span>}</td>
                <td>{p.tipo === "bolsa" ? <Insignia color="bg-purple-100 text-purple-800">Bolsa</Insignia> : "Operativo"}</td>
                <td><input type="checkbox" checked={p.excluido} disabled={!puedeEditar} onChange={(e) => cambiar(p, "excluido", e.target.checked)} /></td>
                <td><input type="checkbox" checked={p.activo} disabled={!puedeEditar} onChange={(e) => cambiar(p, "activo", e.target.checked)} /></td>
                <td><input type="checkbox" checked={p.cubre_descansos ?? true} disabled={!puedeEditar} onChange={(e) => cambiar(p, "cubre_descansos", e.target.checked)}
                  title="Marcado: el día de descanso de un titular se cubre con un relevo. Sin marcar: ese día nadie se programa (no cuenta como hueco)" /></td>
                <td>{puedeEditar && <button className="text-sm text-marca-600 hover:underline" onClick={() => {
                  setError(""); setEdicion({ id: p.id, codigo: p.codigo, descripcion: p.descripcion, ciudad: p.ciudad_manual ?? "" });
                }}>Editar</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <Paginador meta={meta} onPagina={pag.setPagina} onTamano={pag.setTamano} />
      </div>
      <p className="text-xs text-slate-500">{(meta?.total ?? 0).toLocaleString("es-CO")} puestos. Un puesto inactivo no se proyecta al mes siguiente; uno excluido no entra al control.
        Lo corregido con «Editar» (código, descripción y ciudad, marcado con ✎) manda sobre lo que llega al importar la matriz o la programación de SIESA.
        «Descansos se cubren» sin marcar: el día que un titular descansa nadie se programa; ese día no cuenta como hueco y un relevo programado queda para revisión.</p>
    </div>
  );
}

function TurnosTab() {
  const puedeEditar = usePermiso("capacidad.maestros.gestionar");
  const [turnos, setTurnos] = useState<Turno[]>([]);
  const [msg, setMsg] = useState<{ tipo: "ok" | "error"; texto: string } | null>(null);
  const [meta, setMeta] = useState<MetaPagina | null>(null);
  const pag = usePaginacion();
  const cargar = useCallback(async () => {
    const r = await apiEnvelope<Turno[]>(`/capacidad/catalogos/turnos?${pag.query}`);
    setTurnos(r.data ?? []);
    setMeta(metaDe(r));
  }, [pag.query]);
  useEffect(() => {
    cargar();
  }, [cargar]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-slate-600">Catálogo de horarios configurados en SIESA (archivo GenConsultaMaestroGrid). Al cargarlo se reemplaza el catálogo completo.</p>
        {puedeEditar && (
          <SubirArchivo
            texto="Cargar horarios de SIESA"
            onArchivo={async (f) => {
              try {
                const r = await subirArchivo<{ turnos: number }>("/capacidad/catalogos/turnos/importar", f);
                setMsg({ tipo: "ok", texto: `${r.turnos} horarios cargados` });
                cargar();
              } catch (e) {
                setMsg({ tipo: "error", texto: mensajeError(e) });
              }
            }}
          />
        )}
      </div>
      {msg && <Alerta tipo={msg.tipo}>{msg.texto}</Alerta>}
      <div className="tarjeta overflow-x-auto">
        <table className="tabla">
          <thead><tr><th>Código</th><th>Descripción</th><th>Clase</th><th>Franjas</th></tr></thead>
          <tbody>
            {turnos.map((t) => (
              <tr key={t.codigo}>
                <td className="font-mono font-semibold">{t.codigo}</td>
                <td>{t.descripcion}</td>
                <td>{t.clase === "descanso" ? <Insignia>Descanso</Insignia> : <Insignia color="bg-marca-100 text-marca-900">Trabajo</Insignia>}</td>
                <td>{t.franjas.map((f) => `${hora(f.inicio)}–${hora(f.fin)}`).join(" y ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <Paginador meta={meta} onPagina={pag.setPagina} onTamano={pag.setTamano} />
      </div>
    </div>
  );
}

function NovedadesTab() {
  const puedeEditar = usePermiso("capacidad.maestros.gestionar");
  const [items, setItems] = useState<Novedad[]>([]);
  const [nueva, setNueva] = useState({ codigo: "", descripcion: "" });
  const [error, setError] = useState("");
  const cargar = useCallback(async () => setItems(await api<Novedad[]>("/capacidad/catalogos/novedades")), []);
  useEffect(() => {
    cargar();
  }, [cargar]);

  async function guardar(n: Novedad) {
    setError("");
    try {
      await api("/capacidad/catalogos/novedades", { method: "PUT", json: n });
      cargar();
    } catch (e) {
      setError(mensajeError(e));
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600">
        Códigos de SIESA que indican que la persona no trabaja ese día. Si requieren cubrimiento, otra persona debe cubrir el puesto.
      </p>
      {error && <Alerta>{error}</Alerta>}
      <div className="tarjeta overflow-x-auto">
        <table className="tabla">
          <thead><tr><th>Código</th><th>Descripción</th><th>Requiere cubrimiento</th></tr></thead>
          <tbody>
            {items.map((n) => (
              <tr key={n.codigo}>
                <td className="font-mono font-semibold">{n.codigo}</td>
                <td>{n.descripcion}</td>
                <td>
                  <input type="checkbox" checked={n.requiere_cubrimiento} disabled={!puedeEditar}
                    onChange={(e) => guardar({ ...n, requiere_cubrimiento: e.target.checked })} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {puedeEditar && (
        <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); guardar({ ...nueva, requiere_cubrimiento: true }); setNueva({ codigo: "", descripcion: "" }); }}>
          <div><label className="label">Código</label><input className="input w-32" value={nueva.codigo} onChange={(e) => setNueva({ ...nueva, codigo: e.target.value })} required /></div>
          <div><label className="label">Descripción</label><input className="input w-72" value={nueva.descripcion} onChange={(e) => setNueva({ ...nueva, descripcion: e.target.value })} required /></div>
          <button className="btn-secundario">Agregar novedad</button>
        </form>
      )}
    </div>
  );
}
