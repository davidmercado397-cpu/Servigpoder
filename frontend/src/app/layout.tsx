import type { Metadata } from "next";
import "./globals.css";
import { CamposNumericos } from "@/components/campos-numericos";
import { MarcaProvider } from "@/lib/marca";

export const metadata: Metadata = {
  title: "Plataforma Servigpoder",
  description: "Desarrollos internos de Servigpoder",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es">
      <body>
        <CamposNumericos />
        <MarcaProvider>{children}</MarcaProvider>
      </body>
    </html>
  );
}
