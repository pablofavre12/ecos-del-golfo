import type { NextConfig } from "next";

// La cocina Python (tablero.py) escucha en 8477. El navegador nunca la toca
// directo: /api/* y /media/* pasan por acá, así todo es mismo-origen.
const COCINA = process.env.COCINA_URL ?? "http://127.0.0.1:8477";

const nextConfig: NextConfig = {
  // El repo tiene su lockfile propio; que Turbopack no mire fuera de web/.
  turbopack: { root: __dirname },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${COCINA}/api/:path*` },
      { source: "/media/:path*", destination: `${COCINA}/media/:path*` },
    ];
  },
};

export default nextConfig;
