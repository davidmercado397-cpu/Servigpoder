"use client";

import { BadgePercent, CalendarDays, CalendarRange, Calculator, Clock3, HandCoins, Users } from "lucide-react";
import { ShellApp, type GrupoMenu } from "@/components/shell-app";

const MENU: GrupoMenu[] = [
  {
    grupo: "Liquidación",
    items: [
      { href: "/liquidador", texto: "Periodos", icono: CalendarRange, permiso: "liquidador.periodos.ver" },
      { href: "/liquidador/empleados", texto: "Empleados", icono: Users, permiso: "liquidador.periodos.ver" },
    ],
  },
  {
    grupo: "Nómina",
    items: [
      { href: "/liquidador/recargos", texto: "Recargos y salario", icono: BadgePercent, permiso: "liquidador.nomina.ver" },
      { href: "/liquidador/descuentos", texto: "Préstamos y embargos", icono: HandCoins, permiso: "liquidador.nomina.ver" },
    ],
  },
  {
    grupo: "Configuración",
    items: [
      { href: "/liquidador/turnos", texto: "Turnos", icono: Clock3, permiso: "liquidador.turnos.ver" },
      { href: "/liquidador/festivos", texto: "Festivos", icono: CalendarDays, permiso: "liquidador.turnos.ver" },
    ],
  },
];

const ASISTENTE = {
  permiso: "liquidador.asistente.usar",
  base: "/liquidador/asistente",
  bienvenida: "Pregúntame por las horas contadas de un periodo o de una persona, o cómo reparte las horas un turno. Consulto los datos reales antes de responder.",
  sugerencias: [
    "Resume las horas de la última quincena",
    "¿Quiénes tienen días con novedad en la última quincena?",
    "¿Cómo reparte las horas el turno N un sábado?",
    "Explícame de dónde salen las horas de una cédula",
  ],
};

export default function LiquidadorLayout({ children }: { children: React.ReactNode }) {
  return (
    <ShellApp nombre="Liquidador de horas" subtitulo="Quincenas y meses" icono={Calculator} inicio="/liquidador" menu={MENU} asistente={ASISTENTE}>
      {children}
    </ShellApp>
  );
}
