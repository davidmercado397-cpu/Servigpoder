"use client";

import { Calculator, Clock, FileStack, HandCoins, LayoutDashboard, Settings, Users } from "lucide-react";
import { ShellApp, type GrupoMenu } from "@/components/shell-app";

const MENU: GrupoMenu[] = [
  {
    grupo: "MFP",
    items: [
      { href: "/costeo", texto: "Resumen", icono: LayoutDashboard, permiso: "costeo.ver" },
      { href: "/costeo/mfp", texto: "MFP", icono: FileStack, permiso: "costeo.ver" },
      { href: "/costeo/horas", texto: "Bolsas de horas", icono: Clock, permiso: "costeo.ver" },
      { href: "/costeo/clientes", texto: "Clientes", icono: Users, permiso: "costeo.ver" },
    ],
  },
  {
    grupo: "Costeo",
    items: [
      { href: "/costeo/costeos", texto: "Costeos", icono: Calculator, permiso: "costeo.ver" },
      { href: "/costeo/configuracion", texto: "Configuración", icono: Settings, permiso: "costeo.ver" },
    ],
  },
];

export default function CosteoLayout({ children }: { children: React.ReactNode }) {
  return (
    <ShellApp nombre="Costeo y MFP's" subtitulo="Matriz de fortalecimiento de puesto" icono={HandCoins} inicio="/costeo" menu={MENU}>
      {children}
    </ShellApp>
  );
}
