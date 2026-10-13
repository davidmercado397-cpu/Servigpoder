"use client";

import { BookOpen, Library, MessagesSquare } from "lucide-react";
import { ShellApp, type GrupoMenu } from "@/components/shell-app";

const MENU: GrupoMenu[] = [
  {
    grupo: "Instructivos",
    items: [
      { href: "/siesa", texto: "Chat", icono: MessagesSquare, permiso: "siesa.consultar" },
      { href: "/siesa/documentos", texto: "Base de conocimiento", icono: Library, permiso: "siesa.consultar" },
    ],
  },
];

export default function SiesaLayout({ children }: { children: React.ReactNode }) {
  return (
    <ShellApp nombre="Instructivos SIESA" subtitulo="Chat de consulta" icono={BookOpen} inicio="/siesa" menu={MENU}>
      {children}
    </ShellApp>
  );
}
