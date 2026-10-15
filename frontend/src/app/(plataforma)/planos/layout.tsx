"use client";

import { Database, FileSignature, FileSpreadsheet, Tags, Users, Wrench } from "lucide-react";
import { CruceProvider } from "@/components/procesar-plano";
import { ShellApp, type GrupoMenu } from "@/components/shell-app";

const MENU: GrupoMenu[] = [
  {
    grupo: "Planos",
    items: [
      { href: "/planos", texto: "Empleados", icono: Users, permiso: "planos.procesar" },
      { href: "/planos/contratos", texto: "Contratos", icono: FileSignature, permiso: "planos.procesar" },
    ],
  },
  {
    grupo: "Configuración",
    items: [
      { href: "/planos/alias", texto: "Alias", icono: Tags, permiso: "planos.procesar" },
      { href: "/planos/correcciones", texto: "Correcciones", icono: Wrench, permiso: "planos.procesar" },
      { href: "/planos/catalogos", texto: "Catálogos y salario", icono: Database, permiso: "planos.procesar" },
    ],
  },
];

export default function PlanosLayout({ children }: { children: React.ReactNode }) {
  return (
    <ShellApp nombre="Planos SIESA" subtitulo="Empleados y contratos" icono={FileSpreadsheet} inicio="/planos" menu={MENU}>
      {/* El cruce empleados ↔ contratos vive en memoria mientras se navega dentro de Planos */}
      <CruceProvider>{children}</CruceProvider>
    </ShellApp>
  );
}
