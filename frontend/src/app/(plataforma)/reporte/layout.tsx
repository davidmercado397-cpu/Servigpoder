"use client";

import { FileText } from "lucide-react";
import { ShellApp, type GrupoMenu } from "@/components/shell-app";

const MENU: GrupoMenu[] = [
  { grupo: "Reporte", items: [{ href: "/reporte", texto: "Generar PDF", icono: FileText, permiso: "reporte.generar" }] },
];

export default function ReporteLayout({ children }: { children: React.ReactNode }) {
  return (
    <ShellApp nombre="Reporte de programación" subtitulo="SIESA → PDF" icono={FileText} inicio="/reporte" menu={MENU}>
      {children}
    </ShellApp>
  );
}
