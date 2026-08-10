import { cn } from "@/lib/utils";

/**
 * La marca: el waveform del tablero v2 evolucionado. Las barras trazan la
 * subida de un up_call (la vocalización estrella del catálogo) y la última
 * barra remata en bioluminiscente — el dato que emerge del abismo.
 */
export function LogoOnda({ className }: { className?: string }) {
  return (
    <svg
      width="30"
      height="18"
      viewBox="0 0 30 18"
      aria-hidden="true"
      fill="none"
      className={cn("shrink-0", className)}
    >
      <path
        d="M2 10h1M6 11V8M10 12V6M14 13V4M18 14V3M22 15V2"
        stroke="var(--ambar)"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <path
        d="M26 16V1"
        stroke="var(--bio)"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}
