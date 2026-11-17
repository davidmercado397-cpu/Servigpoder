"use client";

import { Calculator, CalendarRange, HandCoins, Settings2, Users } from "lucide-react";
import { ShellApp, type GrupoMenu } from "@/components/shell-app";

const MENU: GrupoMenu[] = [
  {
    grupo: "Nómina",
    items: [
      { href: "/speed", texto: "Quincenas", icono: CalendarRange, permiso: "speed.ver" },
      { href: "/speed/descuentos", texto: "Descuentos y pagos", icono: HandCoins, permiso: "speed.ver" },
    ],
  },
  { grupo: "Personal", items: [{ href: "/speed/empleados", texto: "Empleados (Listado)", icono: Users, permiso: "speed.ver" }] },
  { grupo: "Configuración", items: [{ href: "/speed/configuracion", texto: "Parámetros", icono: Settings2, permiso: "speed.ver" }] },
];

export default function SpeedLayout({ children }: { children: React.ReactNode }) {
  return (
    <ShellApp nombre="Nómina Speed" subtitulo="Quincenas" icono={Calculator} inicio="/speed" menu={MENU}>
      {children}
    </ShellApp>
  );
}
