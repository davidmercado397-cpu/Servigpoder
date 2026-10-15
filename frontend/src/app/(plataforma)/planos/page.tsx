"use client";

import { ProcesarPlano } from "@/components/procesar-plano";
import { Titulo } from "@/components/ui";

export default function PlanoEmpleados() {
  return (
    <>
      <Titulo>Plano de empleados</Titulo>
      <p className="-mt-4 mb-5 text-sm text-slate-500">
        Convierte a código país, departamento y ciudad (nacimiento y expedición), normaliza nombres y fechas y deja los fijos de SIESA.
        Lo que no tiene una lectura segura no se inventa: queda en la hoja «Errores».
      </p>
      <ProcesarPlano tipo="empleados" />
    </>
  );
}
