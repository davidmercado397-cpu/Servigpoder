"use client";

import { ProcesarPlano } from "@/components/procesar-plano";
import { Titulo } from "@/components/ui";

export default function PlanoContratos() {
  return (
    <>
      <Titulo>Plano de contratos</Titulo>
      <p className="-mt-4 mb-5 text-sm text-slate-500">
        Codifica bancos, fondos, EPS, cesantías, cajas y cargos; aplica los valores fijos, las reglas de vigilantes, el auxilio de
        transporte y la fecha «contrato hasta» (ingreso + 3 meses, menos un día, cuando viene vacía).
      </p>
      <ProcesarPlano tipo="contratos" />
    </>
  );
}
