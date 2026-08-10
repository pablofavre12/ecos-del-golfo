import type { Metadata } from "next";
import Link from "next/link";

import { CocinaApagada } from "@/components/cocina-apagada";
import { Espectrograma } from "@/components/espectrograma";
import { BadgeHipotesis, BadgeTipo, ChipEstado } from "@/components/insignias";
import { TarjetaSegmento } from "@/components/tarjeta-segmento";
import { Card } from "@/components/ui/card";
import {
  CocinaApagadaError,
  NoEncontradoError,
  pedirCocina,
  type SimilaresData,
} from "@/lib/cocina";

type Props = { params: Promise<{ filename: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { filename } = await params;
  return { title: `Parecidos a ${decodeURIComponent(filename)}` };
}

function VacioConComando({
  titulo,
  children,
}: {
  titulo: string;
  children: React.ReactNode;
}) {
  return (
    <Card className="rounded-sm border-dashed border-borde-fuerte p-10 text-center text-muted-foreground">
      <p className="font-semibold text-foreground">{titulo}</p>
      <div>{children}</div>
    </Card>
  );
}

export default async function PaginaParecidos({ params }: Props) {
  const { filename: crudo } = await params;
  const filename = decodeURIComponent(crudo);

  let d: SimilaresData | null = null;
  let inexistente = false;
  try {
    d = await pedirCocina<SimilaresData>(
      `/api/similares/${encodeURIComponent(filename)}`,
    );
  } catch (err) {
    if (err instanceof CocinaApagadaError) return <CocinaApagada />;
    if (err instanceof NoEncontradoError) inexistente = true;
    else throw err;
  }

  const encabezado = (
    <>
      <h2 className="font-display text-[1.9rem] font-semibold tracking-tight">
        Suenan parecido
      </h2>
      <p className="mt-1 mb-6 max-w-[62ch] text-muted-foreground">
        Vecinos más cercanos por similitud de sonido (embeddings Perch) contra
        todo el catálogo indexado — sin importar la etiqueta.
      </p>
    </>
  );

  if (inexistente || !d) {
    return (
      <>
        {encabezado}
        <VacioConComando titulo="Ese segmento no está en el catálogo.">
          <p>
            <code className="rounded-sm bg-panel-2 px-1.5 py-0.5 font-mono text-[0.85em] text-foreground">
              {filename}
            </code>{" "}
            —{" "}
            <Link href="/biblioteca" className="text-ambar hover:underline">
              volver a la biblioteca
            </Link>
          </p>
        </VacioConComando>
      </>
    );
  }

  if (!d.indice) {
    return (
      <>
        {encabezado}
        <VacioConComando titulo="Todavía no hay índice de embeddings.">
          <p>
            Generalo con{" "}
            <code className="rounded-sm bg-panel-2 px-1.5 py-0.5 font-mono text-[0.85em] text-foreground">
              python indexar.py
            </code>{" "}
            y volvé: cada clip queda vectorizado y esta vista te muestra los que
            suenan parecido.
          </p>
        </VacioConComando>
      </>
    );
  }

  if (d.resultados === null) {
    return (
      <>
        {encabezado}
        <VacioConComando titulo="Este clip todavía no está indexado.">
          <p>
            Corré{" "}
            <code className="rounded-sm bg-panel-2 px-1.5 py-0.5 font-mono text-[0.85em] text-foreground">
              python indexar.py
            </code>{" "}
            para ponerlo al día (indexa solo lo que falta) y volvé a esta página.
          </p>
        </VacioConComando>
      </>
    );
  }

  const s = d.segmento;
  return (
    <>
      {encabezado}
      <section className="rounded-sm border border-border bg-card p-5">
        <Espectrograma filename={s.filename} disponible={s.espectrograma} />
        {s.clip ? (
          <audio
            controls
            preload="auto"
            src={`/media/clip/${encodeURIComponent(s.filename)}`}
            className="mt-4"
          />
        ) : (
          <p className="mt-4 text-sm text-muted-foreground">clip no disponible</p>
        )}
        <div className="mt-3.5 flex flex-wrap items-center gap-2">
          <BadgeTipo tipo={s.tipo_efectivo} />
          <BadgeHipotesis />
          <ChipEstado estado={s.estado} />
        </div>
        <p className="num mt-2 text-xs text-mas-tenue">
          {s.filename} · {s.fuente} · {s.fecha_linda}
        </p>
      </section>

      <h3 className="mt-10 mb-3.5 flex items-center gap-2.5 text-[0.76rem] font-semibold tracking-[0.12em] text-muted-foreground uppercase after:flex-1 after:border-t after:border-border">
        Top {d.resultados.length} por similitud
      </h3>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-4">
        {d.resultados.map((r) => (
          <TarjetaSegmento key={r.filename} segmento={r} />
        ))}
      </div>
    </>
  );
}
