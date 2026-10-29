"use client";

import {
  BadgePercent, BriefcaseMedical, CalendarCheck, CalendarDays, CalendarRange, Calculator, Clock3, Gift, GitCompare, HandCoins, History, PiggyBank, ReceiptText,
  Scale, Stethoscope, TreePalm, Users,
} from "lucide-react";
import { ShellApp, type GrupoMenu } from "@/components/shell-app";

const MENU: GrupoMenu[] = [
  {
    grupo: "Nómina",
    items: [
      { href: "/liquidador", texto: "Periodos", icono: CalendarRange, permiso: "liquidador.periodos.ver" },
      { href: "/liquidador/pagado", texto: "Pagado por mes", icono: CalendarCheck, permiso: "liquidador.nomina.ver" },
      { href: "/liquidador/recargos", texto: "Recargos y salario", icono: BadgePercent, permiso: "liquidador.nomina.ver" },
      { href: "/liquidador/descuentos", texto: "Préstamos, embargos y cuotas", icono: HandCoins, permiso: "liquidador.nomina.ver" },
      { href: "/liquidador/auxilios", texto: "Auxilios no prestacionales", icono: Gift, permiso: "liquidador.nomina.ver" },
      { href: "/liquidador/vacaciones", texto: "Liquidar vacaciones", icono: TreePalm, permiso: "liquidador.nomina.ver" },
      { href: "/liquidador/comparar-siigo", texto: "Comparar con Siigo", icono: GitCompare, permiso: "liquidador.nomina.ver" },
    ],
  },
  {
    grupo: "Gestión humana",
    items: [
      { href: "/liquidador/empleados", texto: "Empleados", icono: Users, permiso: "liquidador.periodos.ver" },
      { href: "/liquidador/historico-vacaciones", texto: "Histórico de vacaciones", icono: History, permiso: "liquidador.personal.ver" },
      { href: "/liquidador/cuotas-pendientes", texto: "Cuotas pendientes", icono: ReceiptText, permiso: "liquidador.personal.ver" },
      { href: "/liquidador/incapacidades", texto: "Registro de incapacidades", icono: BriefcaseMedical, permiso: "liquidador.salud.ver" },
      { href: "/liquidador/restricciones", texto: "Restricciones médicas", icono: Stethoscope, permiso: "liquidador.salud.ver" },
      { href: "/liquidador/tutelas", texto: "Tutelas y demandas", icono: Scale, permiso: "liquidador.juridico.ver" },
    ],
  },
  {
    grupo: "Costeo",
    items: [
      { href: "/liquidador/costeos", texto: "Costeo de nómina", icono: PiggyBank, permiso: "liquidador.costeo.ver" },
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
