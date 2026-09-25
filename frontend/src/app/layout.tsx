import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Capacidad Operativa · Servigpoder",
  description: "Control de capacidad operativa de la programación de personal",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
