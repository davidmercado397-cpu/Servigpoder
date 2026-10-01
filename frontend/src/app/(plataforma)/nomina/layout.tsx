"use client";

import { BadgeCheck, CalendarRange, ListChecks, Settings2 } from "lucide-react";
import { ShellApp, type GrupoMenu } from "@/components/shell-app";

const MENU: GrupoMenu[] = [
  { grupo: "Validación", items: [{ href: "/nomina", texto: "Periodos", icono: CalendarRange, permiso: "nomina.ver" }] },
  {
    grupo: "Configuración",
    items: [
      { href: "/nomina/codigos", texto: "Códigos que descuentan", icono: ListChecks, permiso: "nomina.ver" },
      { href: "/nomina/configuracion", texto: "Grupos y parámetros", icono: Settings2, permiso: "nomina.ver" },
    ],
  },
];

export default function NominaLayout({ children }: { children: React.ReactNode }) {
  return (
    <ShellApp nombre="Validación de nómina" subtitulo="Modalidades fijas" icono={BadgeCheck} inicio="/nomina" menu={MENU}>
      {children}
    </ShellApp>
  );
}
