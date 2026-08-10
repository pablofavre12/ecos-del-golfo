import type { Metadata } from "next";
import { Fraunces, Instrument_Sans, Spline_Sans_Mono } from "next/font/google";
import Link from "next/link";

import { LogoOnda } from "@/components/marca";
import { NavLinks } from "@/components/nav-links";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { pedirPendientes } from "@/lib/cocina";

import "./globals.css";

// Tipografía autoalojada en build (next/font): cero CDNs en runtime.
// Fraunces: display con carácter de cuaderno de naturalista para los títulos.
// Instrument Sans: la UI, limpia y sin pose. Spline Sans Mono: datos,
// archivos y números (tabulares) — el idioma de la máquina.
const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--font-fraunces",
  display: "swap",
});
const instrument = Instrument_Sans({
  subsets: ["latin"],
  variable: "--font-instrument",
  display: "swap",
});
const splineMono = Spline_Sans_Mono({
  subsets: ["latin"],
  variable: "--font-spline-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Ecos del Golfo",
    template: "%s — Ecos del Golfo",
  },
  description:
    "La biblioteca acústica del Golfo Nuevo: la máquina propone, el experto confirma.",
};

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const pendientes = await pedirPendientes();

  return (
    <html lang="es" className="dark">
      <body
        className={`${fraunces.variable} ${instrument.variable} ${splineMono.variable} flex min-h-dvh flex-col antialiased`}
      >
        <TooltipProvider delayDuration={150}>
          <header className="sticky top-0 z-10 border-b border-border bg-card/90 backdrop-blur-sm">
            <div className="mx-auto flex w-full max-w-[1180px] items-center gap-8 px-6 py-3">
              <Link
                href="/"
                aria-label="Ecos del Golfo — panel"
                className="flex items-center gap-2.5"
              >
                <LogoOnda />
                <span className="font-display text-[1.06rem] font-semibold tracking-tight whitespace-nowrap">
                  Ecos <span className="text-ambar">del Golfo</span>
                </span>
              </Link>
              <NavLinks pendientes={pendientes} />
            </div>
          </header>

          <main className="mx-auto w-full max-w-[1180px] flex-1 px-6 pt-8 pb-16">
            {children}
          </main>

          <footer className="border-t border-border">
            <div className="mx-auto flex w-full max-w-[1180px] flex-wrap justify-between gap-x-8 gap-y-1 px-6 py-3.5 text-[0.8rem] text-mas-tenue">
              <span>Ecos del Golfo · web local · WCH-473</span>
              <span>
                La máquina propone, el experto confirma · fuente de verdad:{" "}
                <code className="font-mono text-[0.78rem]">ecos.db</code>
              </span>
            </div>
          </footer>
        </TooltipProvider>
        <Toaster position="bottom-right" />
      </body>
    </html>
  );
}
