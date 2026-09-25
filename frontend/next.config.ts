import type { NextConfig } from "next";

// El navegador siempre habla con el mismo origen (/api/...) y Next.js lo
// reenvía al backend. Así la cookie de sesión funciona sin CORS.
const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendUrl}/api/:path*` }];
  },
};

export default nextConfig;
