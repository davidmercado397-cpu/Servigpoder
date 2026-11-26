"use client";

import { BookOpenCheck, FileSpreadsheet, Inbox, Mail, Settings2 } from "lucide-react";
import { ShellApp, type GrupoMenu } from "@/components/shell-app";

const MENU: GrupoMenu[] = [
  {
    grupo: "Facturas de compra",
    items: [
      { href: "/contabilidad", texto: "Facturas recibidas", icono: Inbox, permiso: "contabilidad.ver" },
      { href: "/contabilidad/plano", texto: "Plano World Office", icono: FileSpreadsheet, permiso: "contabilidad.ver" },
      { href: "/contabilidad/correos", texto: "Correos leídos", icono: Mail, permiso: "contabilidad.ver" },
    ],
  },
  { grupo: "Agente contable", items: [{ href: "/contabilidad/reglas", texto: "Reglas de la empresa", icono: BookOpenCheck, permiso: "contabilidad.ver" }] },
  { grupo: "Configuración", items: [{ href: "/contabilidad/configuracion", texto: "Buzón y catálogos", icono: Settings2, permiso: "contabilidad.ver" }] },
];

export default function ContabilidadLayout({ children }: { children: React.ReactNode }) {
  return (
    <ShellApp nombre="Contabilidad" subtitulo="Facturas → World Office" icono={FileSpreadsheet} inicio="/contabilidad" menu={MENU}>
      {children}
    </ShellApp>
  );
}
