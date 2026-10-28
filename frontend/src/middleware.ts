import { NextResponse, type NextRequest } from "next/server";

export function middleware(req: NextRequest) {
  // El backend reconoce por el host el enlace propio de una empresa (DOMINIOS_EMPRESA); se pisa lo que mande el navegador
  if (req.nextUrl.pathname.startsWith("/api/")) {
    const headers = new Headers(req.headers);
    headers.set("x-plataforma-host", req.headers.get("x-forwarded-host") ?? req.headers.get("host") ?? "");
    return NextResponse.next({ request: { headers } });
  }
  const tieneSesion = req.cookies.has("sesion");
  const esLogin = req.nextUrl.pathname === "/login";
  if (!tieneSesion && !esLogin) {
    return NextResponse.redirect(new URL("/login", req.url));
  }
  return NextResponse.next();
}

export const config = {
  // Todo excepto archivos estáticos; en la API solo se agrega el host (la protege el backend)
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
