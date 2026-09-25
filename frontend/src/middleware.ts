import { NextResponse, type NextRequest } from "next/server";

export function middleware(req: NextRequest) {
  const tieneSesion = req.cookies.has("sesion");
  const esLogin = req.nextUrl.pathname === "/login";
  if (!tieneSesion && !esLogin) {
    return NextResponse.redirect(new URL("/login", req.url));
  }
  return NextResponse.next();
}

export const config = {
  // Todo excepto la API (la protege el backend) y archivos estáticos
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
