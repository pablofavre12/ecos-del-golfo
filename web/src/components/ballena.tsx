import { cn } from "@/lib/utils";

/**
 * Ballena franca austral en línea fina: el lomo continuo SIN aleta dorsal
 * (la firma de la especie), la cabeza grande con callosidades y la boca
 * arqueada. Para estados vacíos, la pantalla de logro y el 404 — nunca
 * como decoración regada.
 */
export function BallenaFranca({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 280 130"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={cn("h-auto w-64", className)}
    >
      {/* lomo: arco alto adelante (sobre la cabeza), sin aleta dorsal,
          afinándose largo hacia el pedúnculo */}
      <path d="M30 66 C38 40 64 26 100 24 C150 21 196 34 224 50 C234 56 242 62 247 69" />
      {/* vientre: mandíbula honda adelante, taper fuerte hacia atrás */}
      <path d="M30 66 C32 84 42 98 58 106 C80 116 104 117 120 110 C156 118 186 108 212 96 C226 89 238 80 246 76" />
      {/* boca arqueada característica */}
      <path d="M32 70 C46 92 68 103 94 104" />
      {/* callosidades sobre el rostrum */}
      <path d="M36 52 q3 -6 8 -4" />
      <path d="M52 40 q4 -5 9 -3" />
      <path d="M72 31 q4 -4 9 -2" />
      {/* ojo, bajo, cerca de la comisura */}
      <circle cx="102" cy="92" r="2.2" fill="currentColor" stroke="none" />
      {/* aleta pectoral ancha (espátula) */}
      <path d="M130 108 C138 118 138 128 127 134 C123 124 124 114 130 108" />
      {/* cola en V, lóbulos anchos */}
      <path d="M247 69 C254 64 262 55 266 43 C267 54 265 63 261 71 C268 76 274 85 276 96 C266 88 257 84 248 83 C243 78 243 73 247 69" />
    </svg>
  );
}
