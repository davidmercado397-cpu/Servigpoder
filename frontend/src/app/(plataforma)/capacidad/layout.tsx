"use client";

import { Database, FileSpreadsheet, Gauge, History, Inbox, LayoutDashboard, ShieldCheck, SlidersHorizontal, Table2, Users } from "lucide-react";
import { ShellApp, type GrupoMenu } from "@/components/shell-app";

const MENU: GrupoMenu[] = [
  { grupo: "General", items: [{ href: "/capacidad", texto: "Inicio", icono: LayoutDashboard, contador: "alertas_criticas", critico: true }] },
  {
    grupo: "Operación",
    items: [
      { href: "/capacidad/programacion", texto: "Programación SIESA", icono: FileSpreadsheet, permiso: "capacidad.analisis.ver" },
      { href: "/capacidad/cobertura", texto: "Cobertura", icono: Gauge, permiso: "capacidad.analisis.ver" },
      { href: "/capacidad/cubrimientos", texto: "Cubrimientos (nómina)", icono: Inbox, permiso: "capacidad.analisis.ver", contador: "cubrimientos_pendientes" },
      { href: "/capacidad/bolsas", texto: "Personas en bolsa", icono: Users, permiso: "capacidad.analisis.ver" },
      { href: "/capacidad/historico", texto: "Histórico y novedades", icono: History, permiso: "capacidad.analisis.ver" },
    ],
  },
  {
    grupo: "Configuración",
    items: [
      { href: "/capacidad/matriz", texto: "Matriz comercial", icono: Table2, permiso: "capacidad.matriz.ver" },
      { href: "/capacidad/maestros", texto: "Maestros", icono: Database, permiso: "capacidad.maestros.ver", contador: "por_aclarar" },
      { href: "/capacidad/parametros", texto: "Parámetros de alertas", icono: SlidersHorizontal, permiso: "capacidad.parametros.gestionar" },
    ],
  },
];

const ASISTENTE = {
  permiso: "capacidad.asistente.usar",
  base: "/capacidad/asistente",
  bienvenida: "Pregúntame sobre la cobertura, la matriz, los cubrimientos o cualquier cifra de los tableros. Consulto los datos reales antes de responder.",
  sugerencias: [
    "¿De dónde sale el porcentaje de cobertura del mes?",
    "¿Cuáles son los 5 puestos con más horas descubiertas y por qué?",
    "¿Qué cubrimientos están pendientes para nómina?",
    "Explícame cómo se calculan los hombres esperados de un 4x2",
  ],
};

export default function CapacidadLayout({ children }: { children: React.ReactNode }) {
  return (
    <ShellApp nombre="Capacidad Operativa" subtitulo="Servigpoder" icono={ShieldCheck} inicio="/capacidad" menu={MENU}
      contadores={{ url: "/capacidad/menu/contadores", permiso: "capacidad.analisis.ver" }}
      campana={{ total: "alertas", criticas: "alertas_criticas" }} asistente={ASISTENTE}>
      {children}
    </ShellApp>
  );
}
