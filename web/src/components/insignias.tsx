import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { Estado } from "@/lib/cocina";
import { cn } from "@/lib/utils";

export const ETIQUETA_ESTADO: Record<Estado, string> = {
  propuesto: "PROPUESTO",
  confirmado: "CONFIRMADO",
  descartado: "DESCARTADO",
  desconocido: "DESCONOCIDO",
};

const CLASE_ESTADO: Record<Estado, string> = {
  propuesto: "border-propuesto text-propuesto",
  confirmado: "border-confirmado text-confirmado",
  descartado: "border-descartado text-descartado",
  desconocido: "border-desconocido text-desconocido",
};

/** Chip de estado: jewel color + mono UPPERCASE. El color ES el estado. */
export function ChipEstado({
  estado,
  className,
}: {
  estado: Estado;
  className?: string;
}) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "rounded-sm font-mono text-[0.68rem] font-bold tracking-wider",
        CLASE_ESTADO[estado],
        className,
      )}
    >
      {ETIQUETA_ESTADO[estado]}
    </Badge>
  );
}

/**
 * EA2: TODO segmento lleva este badge hasta que un experto independiente
 * (ICB / CENPAT) valide la especie. Con tooltip en criollo.
 */
export function BadgeHipotesis() {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge className="cursor-help rounded-sm border-transparent bg-ambar-fuerte font-mono text-[0.66rem] font-bold tracking-[0.09em] text-sobre-ambar">
          HIPÓTESIS
        </Badge>
      </TooltipTrigger>
      <TooltipContent className="max-w-64">
        La especie (franca austral) todavía no está validada por un experto
        independiente — es una hipótesis de trabajo del grupo.
      </TooltipContent>
    </Tooltip>
  );
}

/** Tipo propuesto/confirmado, en mono — es un dato, no una decoración. */
export function BadgeTipo({ tipo }: { tipo: string }) {
  return (
    <Badge
      variant="secondary"
      className="rounded-sm border border-borde-fuerte bg-panel-2 font-mono text-[0.72rem] font-semibold text-foreground"
    >
      {tipo}
    </Badge>
  );
}

/** Similitud coseno como porcentaje — bioluminiscente: es un dato. */
export function BadgeScore({ score }: { score: number }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge className="num cursor-help rounded-sm border-transparent bg-bio/15 text-[0.74rem] font-bold text-bio">
          {Math.round(score * 100)}%
        </Badge>
      </TooltipTrigger>
      <TooltipContent className="max-w-60">
        Qué tan parecido suena a este clip según Perch (la red que convierte
        cada sonido en un punto en un mapa: puntos cercanos, sonidos parecidos).
      </TooltipContent>
    </Tooltip>
  );
}
