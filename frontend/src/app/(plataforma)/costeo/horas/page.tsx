"use client";

import { Search } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ModalMovimiento } from "@/components/costeo";
import { Alerta, Titulo } from "@/components/ui";
import { api, mensajeError } from "@/lib/api";
import { fecha, type ItemMfp, type Mfp } from "@/lib/costeo";
import { usePermiso } from "@/lib/sesion";

type Bolsa = { mfp_id: number; numero: string; cliente: string; item_id: number; tipo: string; anio: number | null; desde: string | null;
  hasta: string | null; pactado: number; usado: number; saldo: number };

export default function BolsasHoras() {
  const registrar = usePermiso("costeo.movimientos");
  const [lista, setLista] = useState<Bolsa[] | null>(null);
  const [q, setQ] = useState("");
  const [item, setItem] = useState<ItemMfp | null>(null);
  const [aviso, setAviso] = useState("");
  const [error, setError] = useState("");

  const cargar = useCallback(() => api<Bolsa[]>(`/costeo/bolsas-horas?q=${encodeURIComponent(q)}`).then(setLista).catch((e) => setError(mensajeError(e))), [q]);
  useEffect(() => {
    const t = setTimeout(cargar, 250);
    return () => clearTimeout(t);
  }, [cargar]);

  async function abrir(b: Bolsa) {
    try {
      const m = await api<Mfp>(`/costeo/mfp/${b.mfp_id}`);
      setItem(m.items.find((i) => i.id === b.item_id) ?? null);
    } catch (e) {
      setError(mensajeError(e));
    }
  }

  return (
    <>
      <Titulo>Bolsas de horas</Titulo>
      <p className="-mt-4 mb-5 text-sm text-slate-500">
        Horas de vigilancia de obsequio por cada año de contrato. Cada solicitud del cliente se registra y se descuenta de la bolsa del año en
        que se presta el servicio; lo que no se usa en el año se pierde.
      </p>
      {error && <div className="mb-4"><Alerta>{error}</Alerta></div>}
      {aviso && <div className="mb-4"><Alerta tipo="ok">{aviso}</Alerta></div>}
      <div className="tarjeta overflow-hidden">
        <div className="border-b border-slate-100 p-4">
          <div className="relative w-80">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-slate-400" />
            <input className="input pl-8" placeholder="Cliente, NIT o número de MFP" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="tabla">
            <thead><tr><th>Cliente</th><th>MFP</th><th>Año del contrato</th><th className="text-right">Horas del año</th><th className="text-right">Usadas</th>
              <th className="text-right">Disponibles</th><th /></tr></thead>
            <tbody>
              {(lista ?? []).map((b) => (
                <tr key={b.item_id}>
                  <td className="font-medium">{b.cliente}</td>
                  <td><Link className="text-marca-700 hover:underline" href={`/costeo/mfp/${b.mfp_id}`}>{b.numero}</Link></td>
                  <td className="text-sm text-slate-600">{b.anio ? `Año ${b.anio}: ${fecha(b.desde)} – ${fecha(b.hasta)}` : "—"}</td>
                  <td className="text-right tabular-nums">{b.pactado} h</td>
                  <td className="text-right tabular-nums">{b.usado} h</td>
                  <td className={`text-right font-semibold tabular-nums ${b.saldo <= 0 ? "text-red-700" : "text-green-700"}`}>{b.saldo} h</td>
                  <td className="text-right">{registrar && <button className="btn-primario px-2 py-1 text-xs" onClick={() => abrir(b)}>Registrar solicitud</button>}</td>
                </tr>
              ))}
              {lista && !lista.length && <tr><td colSpan={7} className="py-8 text-center text-slate-400">No hay MFP vigentes con bolsa de horas.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
      {item && (
        <ModalMovimiento item={item} onCerrar={() => setItem(null)} onGuardado={() => { setItem(null); setAviso("Solicitud registrada y descontada de la bolsa."); cargar(); }} />
      )}
    </>
  );
}
