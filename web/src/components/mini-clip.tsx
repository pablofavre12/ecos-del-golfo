/* eslint-disable @next/next/no-img-element */
import { BadgeScore, BadgeTipo } from "@/components/insignias";
import type { SegmentoLite } from "@/lib/cocina";

/** Tarjeta compacta para los paneles de referencia de la cola. */
export function MiniClip({ segmento }: { segmento: SegmentoLite }) {
  const s = segmento;
  return (
    <div className="overflow-hidden rounded-sm border border-border bg-panel-2">
      {s.espectrograma && (
        <img
          src={`/media/espectro/${encodeURIComponent(s.filename)}`}
          alt={`Espectrograma de ${s.filename}`}
          loading="lazy"
          className="block h-[84px] w-full border-b border-border bg-abisal object-cover"
        />
      )}
      <div className="flex items-center gap-2 px-2.5 py-2">
        {s.clip ? (
          <audio
            controls
            preload="none"
            src={`/media/clip/${encodeURIComponent(s.filename)}`}
            className="h-7 min-w-0 flex-1"
          />
        ) : (
          <span className="flex-1 text-xs text-muted-foreground">
            clip no disponible
          </span>
        )}
        {s.score !== undefined ? (
          <BadgeScore score={s.score} />
        ) : (
          <BadgeTipo tipo={s.tipo_efectivo} />
        )}
      </div>
    </div>
  );
}
