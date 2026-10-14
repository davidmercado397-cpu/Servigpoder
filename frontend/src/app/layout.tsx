import type { Metadata } from "next";
import "./globals.css";
import { MarcaProvider } from "@/lib/marca";

export const metadata: Metadata = {
  title: "Plataforma Servigpoder",
  description: "Desarrollos internos de Servigpoder",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es">
      <body>
        <MarcaProvider>{children}</MarcaProvider>
      </body>
    </html>
  );
}
