import Link from "next/link";

import { Espectrograma } from "@/components/espectrograma";
import {
  BadgeHipotesis,
  BadgeScore,
  BadgeTipo,
  ChipEstado,
} from "@/components/insignias";
import { buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { SegmentoLite } from "@/lib/cocina";
import { cn } from "@/lib/utils";

/**
 * La tarjeta de segmento del explorador y de la búsqueda inversa.
 * El espectrograma es la joya: arriba, a todo el ancho, con marco propio.
 */
export function TarjetaSegmento({ segmento }: { segmento: SegmentoLite }) {
  const s = segmento;
  return (
    <Card className="gap-0 overflow-hidden rounded-sm py-0">
      <Espectrograma filename={s.filename} disponible={s.espectrograma} compacto />
      <div className="flex flex-col gap-2.5 p-3.5">
        <div className="flex flex-wrap items-center gap-1.5">
          {s.score !== undefined && <BadgeScore score={s.score} />}
          <BadgeTipo tipo={s.tipo_efectivo} />
          <BadgeHipotesis />
          <ChipEstado estado={s.estado} className="ml-auto" />
        </div>
        {s.clip ? (
          <audio
            controls
            preload="none"
            src={`/media/clip/${encodeURIComponent(s.filename)}`}
          />
        ) : (
          <p className="text-sm text-muted-foreground">clip no disponible</p>
        )}
        <p className="num truncate text-xs text-mas-tenue" title={s.filename}>
          {s.fecha_linda} · {s.fuente}
        </p>
        <Link
          href={`/parecidos/${encodeURIComponent(s.filename)}`}
          className={cn(
            buttonVariants({ variant: "outline", size: "sm" }),
            "self-start",
          )}
          title="Buscar clips que suenan parecido"
        >
          Buscar parecidos
        </Link>
      </div>
    </Card>
  );
}
