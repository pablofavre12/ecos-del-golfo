import type { Metadata } from "next";
import Link from "next/link";

import { BallenaFranca } from "@/components/ballena";
import { CocinaApagada } from "@/components/cocina-apagada";
import { MiniClip } from "@/components/mini-clip";
import { ColaInteractiva } from "@/components/revisar/cola-interactiva";
import { RachaLogro, RachaSesion } from "@/components/revisar/racha";
import { buttonVariants } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { type ColaData, pedirCocina, type SegmentoCola } from "@/lib/cocina";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Revisar" };

function coma(n: number, decimales: number): string {
  return n.toFixed(decimales).replace(".", ",");
}

/** "Por qué está en la cola", en criollo — con la confianza del clasificador. */
function Motivo({ s }: { s: SegmentoCola }) {
  const dur = s.duracion_s;
  return (
    <div className="mb-5 rounded-sm border border-border border-l-[3px] border-l-propuesto bg-card px-4.5 py-3.5 text-[0.92rem]">
      <span className="mb-1 block font-mono text-[0.66rem] font-semibold tracking-[0.12em] text-propuesto uppercase">
        Por qué está en la cola
      </span>
      {s.propuesto_por} lo propuso como <strong>{s.tipo}</strong>
      {s.confianza !== null && (
        <>
          {" "}
          con{" "}
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="num cursor-help font-bold text-bio underline decoration-dotted underline-offset-2">
                {Math.round(s.confianza * 100)}% de confianza
              </span>
            </TooltipTrigger>
            <TooltipContent className="max-w-60">
              Qué tan segura estaba la máquina de su propuesta. Por debajo del
              umbral no confirma sola: te lo trae a vos.
            </TooltipContent>
          </Tooltip>
        </>
      )}
      {s.dudoso && (
        <>
          {" "}
          pero lo marcó <strong>dudoso</strong>
        </>
      )}
      .{" "}
      {dur !== null &&
        (dur < 0.3 ? (
          <>
            Dura <span className="num">{coma(dur, 2)}&nbsp;s</span> — por debajo
            de 0,3&nbsp;s el índice armónico no es confiable, así que no puede
            confirmarlo sola.{" "}
          </>
        ) : (
          <>
            Dura <span className="num">{coma(dur, 1)}&nbsp;s</span>, pero no
            alcanzó la confianza para confirmarlo sin ayuda.{" "}
          </>
        ))}
      Tu oído decide.
    </div>
  );
}

/** EA1: cola en cero = logro, con el resumen del día como trofeo. */
function Logro({ d }: { d: ColaData }) {
  const hoy = d.hoy;
  const chips: [string, number, string][] = hoy
    ? [
        ["confirmado", hoy.confirmados, "confirmados"],
        ["confirmado", hoy.corregidos, "corregidos"],
        ["descartado", hoy.descartados, "descartados"],
        ["desconocido", hoy.desconocidos, "desconocidos"],
      ]
    : [];
  const claseChip: Record<string, string> = {
    confirmado: "border-confirmado text-confirmado",
    descartado: "border-descartado text-descartado",
    desconocido: "border-desconocido text-desconocido",
  };
  return (
    <div className="flex flex-col items-center py-16 text-center">
      <BallenaFranca className="w-72 text-confirmado" />
      <h2 className="mt-8 font-display text-3xl font-semibold">Cola en cero</h2>
      <p className="mt-2 max-w-md text-muted-foreground">
        Los <span className="num font-bold text-foreground">{d.revisados}</span>{" "}
        sonidos que la máquina propuso ya tienen veredicto del experto. Buen
        trabajo.
      </p>
      <div className="mt-3">
        <RachaLogro />
      </div>
      {chips.some(([, n]) => n > 0) && (
        <div className="mt-5 flex flex-wrap justify-center gap-2">
          {chips.map(
            ([clase, n, texto]) =>
              n > 0 && (
                <span
                  key={texto}
                  className={cn(
                    "num rounded-sm border px-2.5 py-1 text-[0.78rem] font-bold tracking-wide",
                    claseChip[clase],
                  )}
                >
                  {n} {texto}
                </span>
              ),
          )}
        </div>
      )}
      <div className="mt-8 flex gap-3">
        <Link href="/" className={buttonVariants()}>
          Volver al panel
        </Link>
        <Link
          href="/biblioteca?estado=confirmado"
          className={buttonVariants({ variant: "outline" })}
        >
          Ver los confirmados
        </Link>
      </div>
    </div>
  );
}

export default async function PaginaRevisar({
  searchParams,
}: {
  searchParams: Promise<{ pos?: string }>;
}) {
  const { pos: posCrudo } = await searchParams;
  const pos = Number.parseInt(posCrudo ?? "0", 10) || 0;

  let d: ColaData;
  try {
    d = await pedirCocina<ColaData>(`/api/cola?pos=${pos}`);
  } catch {
    return <CocinaApagada />;
  }

  if (d.pendientes === 0 || !d.segmento) {
    return <Logro d={d} />;
  }

  const s = d.segmento;
  const posReal = d.pos ?? 0;
  const pct = d.total ? (100 * d.revisados) / d.total : 0;

  return (
    <>
      <div className="mb-4 flex flex-wrap items-baseline gap-x-4">
        <h2 className="font-display text-[1.9rem] font-semibold tracking-tight">
          Revisar
        </h2>
        <p className="text-muted-foreground">
          Escuchá, compará de oído y da tu veredicto — la máquina no decide sola.
        </p>
      </div>
      {/* progreso */}
      <div className="mb-4 rounded-sm border border-border bg-card px-4.5 py-3.5">
        <div className="mb-2 flex flex-wrap items-baseline gap-x-5 gap-y-1">
          <span className="text-[1.05rem] font-bold">
            Revisando{" "}
            <span className="num text-ambar">{d.revisados + posReal + 1}</span> de{" "}
            <span className="num">{d.total}</span>
          </span>
          <RachaSesion />
          <span className="ml-auto text-sm text-muted-foreground">
            <span className="num font-bold text-foreground">{d.revisados}</span>{" "}
            con veredicto ·{" "}
            <span className="num font-bold text-foreground">{d.pendientes}</span>{" "}
            pendientes
          </span>
        </div>
        <Progress
          value={pct}
          aria-label="Progreso de la cola de revisión"
          className="h-1.5 rounded-xs bg-panel-3 [&>[data-slot=progress-indicator]]:bg-confirmado"
        />
      </div>

      <Motivo s={s} />

      <div className="grid grid-cols-1 items-start gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(280px,1fr)]">
        <ColaInteractiva
          key={s.filename}
          segmento={s}
          tiposCorregibles={d.tipos_corregibles ?? []}
          pos={posReal}
          pendientes={d.pendientes}
        />

        <aside
          className="flex flex-col gap-5"
          aria-label="Material de referencia para comparar"
        >
          {d.ejemplares && d.ejemplares.items.length > 0 ? (
            <section className="rounded-sm border border-border bg-card p-4">
              <h3 className="text-[0.92rem] font-semibold">
                Así suenan los <span className="num text-bio">{s.tipo}</span>{" "}
                confirmados
              </h3>
              <p className="mt-0.5 mb-3 text-[0.78rem] text-muted-foreground">
                {d.ejemplares.total} en la biblioteca — compará de oído antes de
                decidir.
              </p>
              <div className="flex flex-col gap-2.5">
                {d.ejemplares.items.map((x) => (
                  <MiniClip key={x.filename} segmento={x} />
                ))}
              </div>
              <Link
                href={`/biblioteca?tipo=${encodeURIComponent(s.tipo)}&estado=confirmado`}
                className="mt-3 inline-block text-[0.82rem] font-semibold text-ambar hover:underline"
              >
                Ver todos los {s.tipo} →
              </Link>
            </section>
          ) : (
            <section className="rounded-sm border border-dashed border-borde-fuerte bg-card p-4">
              <h3 className="text-[0.92rem] font-semibold">
                Sin ejemplares confirmados de{" "}
                <span className="num text-bio">{s.tipo}</span>
              </h3>
              <p className="mt-1 text-[0.78rem] text-muted-foreground">
                Todavía no hay ninguno en la biblioteca para comparar. Este
                veredicto puede ser el primero.
              </p>
            </section>
          )}

          {d.similares && d.similares.length > 0 && (
            <section className="rounded-sm border border-border bg-card p-4">
              <h3 className="text-[0.92rem] font-semibold">
                Lo más parecido según Perch
              </h3>
              <p className="mt-0.5 mb-3 text-[0.78rem] text-muted-foreground">
                Vecinos por embedding en todo el catálogo — sin importar la
                etiqueta.
              </p>
              <div className="flex flex-col gap-2.5">
                {d.similares.map((x) => (
                  <MiniClip key={x.filename} segmento={x} />
                ))}
              </div>
              <Link
                href={`/parecidos/${encodeURIComponent(s.filename)}`}
                className="mt-3 inline-block text-[0.82rem] font-semibold text-ambar hover:underline"
              >
                Ver el top 10 completo →
              </Link>
            </section>
          )}
        </aside>
      </div>
    </>
  );
}
