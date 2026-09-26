"use client";

import { Paginador, metaDe, usePaginacion, type MetaPagina } from "@/components/paginacion";
import { useCallback, useEffect, useState } from "react";
import { Alerta, Insignia, Pestanas, SubirArchivo, Titulo } from "@/components/ui";
import { api, apiEnvelope, mensajeError, subirArchivo, type Novedad, type PorAclarar, type Puesto, type Turno } from "@/lib/api";
import { hora } from "@/lib/formato";
import { SelectorPuesto } from "@/components/selector-puesto";
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
  const pag = usePaginacion();

  const cargar = useCallback(async () => {
    const r = await apiEnvelope<PorAclarar[]>(`/capacidad/maestros/por-aclarar?${pag.query}`);
    setItems(r.data ?? []);
    setMeta(metaDe(r));
  }, [pag.query]);

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
            <tr><th>Código SIESA</th><th>Descripción en SIESA</th><th>Filas</th><th>Estado</th><th>Puesto del maestro</th></tr>
          </thead>
          <tbody>
            {items.length === 0 && <tr><td colSpan={5} className="text-center text-slate-500">No hay puestos por aclarar</td></tr>}
            {items.map((i) => (
              <tr key={i.codigo_siesa}>
                <td className="font-mono font-semibold">{i.codigo_siesa}</td>
                <td className="max-w-md">{i.descripcion}</td>
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
    </div>
  );
}

function PuestosTab() {
  const puedeEditar = usePermiso("capacidad.maestros.gestionar");
  const [q, setQ] = useState("");
  const [puestos, setPuestos] = useState<Puesto[]>([]);
  const [meta, setMeta] = useState<MetaPagina | null>(null);
  const pag = usePaginacion([q]);

  const cargar = useCallback(async () => {
    const r = await apiEnvelope<Puesto[]>(`/capacidad/maestros/puestos?q=${encodeURIComponent(q)}&${pag.query}`);
    setPuestos(r.data ?? []);
    setMeta(metaDe(r));
  }, [q, pag.query]);

  useEffect(() => {
    const t = setTimeout(cargar, 250);
    return () => clearTimeout(t);
  }, [cargar]);

  async function cambiar(p: Puesto, campo: "excluido" | "activo", valor: boolean) {
    await api(`/capacidad/maestros/puestos/${p.id}`, { method: "PATCH", json: { [campo]: valor } });
    cargar();
  }

  return (
    <div className="space-y-4">
      <input className="input max-w-sm" placeholder="Buscar por código, puesto o ubicación…" value={q} onChange={(e) => setQ(e.target.value)} />
      <div className="tarjeta overflow-x-auto">
        <table className="tabla">
          <thead>
            <tr><th>PODER</th><th>Ubicación</th><th>Puesto</th><th>Descripción</th><th>Tipo</th><th>Excluido</th><th>Activo</th></tr>
          </thead>
          <tbody>
            {puestos.map((p) => (
              <tr key={p.id}>
                <td className="font-mono">{p.ubicacion.codigo}</td>
                <td>{p.ubicacion.nombre}</td>
                <td className="font-mono font-semibold">{p.codigo}</td>
                <td>{p.descripcion}</td>
                <td>{p.tipo === "bolsa" ? <Insignia color="bg-purple-100 text-purple-800">Bolsa</Insignia> : "Operativo"}</td>
                <td><input type="checkbox" checked={p.excluido} disabled={!puedeEditar} onChange={(e) => cambiar(p, "excluido", e.target.checked)} /></td>
                <td><input type="checkbox" checked={p.activo} disabled={!puedeEditar} onChange={(e) => cambiar(p, "activo", e.target.checked)} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        <Paginador meta={meta} onPagina={pag.setPagina} onTamano={pag.setTamano} />
      </div>
      <p className="text-xs text-slate-500">{(meta?.total ?? 0).toLocaleString("es-CO")} puestos. Un puesto inactivo no se proyecta al mes siguiente; uno excluido no entra al control.</p>
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
