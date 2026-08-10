/* eslint-disable @next/next/no-img-element */
import { cn } from "@/lib/utils";

/**
 * El marco digno del espectrograma: fondo abisal, borde propio.
 * Sirve PNGs dinámicos de la cocina — <img> directo, sin optimizador.
 */
export function Espectrograma({
  filename,
  disponible,
  compacto = false,
  className,
}: {
  filename: string;
  disponible: boolean;
  compacto?: boolean;
  className?: string;
}) {
  if (!disponible) {
    return (
      <div
        className={cn(
          "flex items-center justify-center border-b border-dashed border-borde-fuerte bg-abisal py-8 text-sm text-muted-foreground",
          className,
        )}
      >
        sin espectrograma para este segmento
      </div>
    );
  }
  return (
    <div
      className={cn(
        "border-b border-border bg-abisal",
        !compacto && "rounded-sm border",
        className,
      )}
    >
      <img
        src={`/media/espectro/${encodeURIComponent(filename)}`}
        alt={`Espectrograma de ${filename}`}
        loading={compacto ? "lazy" : "eager"}
        className={cn(
          "block w-full",
          compacto ? "max-h-44 object-cover" : "max-h-[420px] object-contain",
        )}
      />
    </div>
  );
}
