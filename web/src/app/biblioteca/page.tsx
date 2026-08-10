import type { Metadata } from "next";
import Link from "next/link";

import { FiltrosBiblioteca } from "@/components/biblioteca/filtros";
import { CocinaApagada } from "@/components/cocina-apagada";
import { TarjetaSegmento } from "@/components/tarjeta-segmento";
import { buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { pedirCocina, type SegmentosData } from "@/lib/cocina";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Biblioteca" };

type Filtros = { tipo?: string; estado?: string; fuente?: string; pagina?: string };

function armarQuery(f: Filtros, pagina?: number): string {
  const q = new URLSearchParams();
  if (f.tipo) q.set("tipo", f.tipo);
  if (f.estado) q.set("estado", f.estado);
  if (f.fuente) q.set("fuente", f.fuente);
  if (pagina && pagina > 1) q.set("pagina", String(pagina));
  const s = q.toString();
  return s ? `?${s}` : "";
}

export default async function PaginaBiblioteca({
  searchParams,
}: {
  searchParams: Promise<Filtros>;
}) {
  const filtros = await searchParams;
  const pagina = Number.parseInt(filtros.pagina ?? "1", 10) || 1;

  let d: SegmentosData;
  try {
    d = await pedirCocina<SegmentosData>(
      `/api/segmentos${armarQuery(filtros, pagina)}`,
    );
  } catch {
    return <CocinaApagada />;
  }

  const hayFiltros = Boolean(filtros.tipo || filtros.estado || filtros.fuente);

  return (
    <>
      <div className="flex flex-wrap items-baseline gap-x-4">
        <h2 className="font-display text-[1.9rem] font-semibold tracking-tight">
          Biblioteca
        </h2>
        <span className="num text-sm text-muted-foreground">
          {d.total} segmento{d.total !== 1 && "s"}
        </span>
      </div>
      <p className="mt-1 mb-6 max-w-[62ch] text-muted-foreground">
        Todo el catálogo con su estado de revisión. Los filtros combinan entre
        sí y quedan en la URL — un link filtrado se puede compartir.
      </p>

      <FiltrosBiblioteca tipos={d.tipos} estados={d.estados} fuentes={d.fuentes} />

      {d.items.length === 0 ? (
        <Card className="rounded-sm border-dashed border-borde-fuerte p-10 text-center text-muted-foreground">
          {hayFiltros ? (
            <>
              <p className="font-semibold text-foreground">
                Ningún segmento coincide con esos filtros.
              </p>
              <p>
                Probá aflojar alguno, o{" "}
                <Link href="/biblioteca" className="text-ambar hover:underline">
                  quitá todos los filtros
                </Link>{" "}
                para ver el catálogo completo.
              </p>
            </>
          ) : (
            <>
              <p className="font-semibold text-foreground">
                Todavía no hay nada en el catálogo.
              </p>
              <p>
                Importá los datos con{" "}
                <code className="rounded-sm bg-panel-2 px-1.5 py-0.5 font-mono text-[0.85em] text-foreground">
                  python importar.py fixtures
                </code>{" "}
                y volvé a esta página.
              </p>
            </>
          )}
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-4">
            {d.items.map((s) => (
              <TarjetaSegmento key={s.filename} segmento={s} />
            ))}
          </div>
          {d.paginas > 1 && (
            <nav
              aria-label="Paginación del catálogo"
              className="mt-7 flex items-center justify-center gap-4"
            >
              <Link
                href={`/biblioteca${armarQuery(filtros, d.pagina - 1)}`}
                aria-disabled={d.pagina <= 1}
                tabIndex={d.pagina <= 1 ? -1 : undefined}
                className={cn(
                  buttonVariants({ variant: "outline", size: "sm" }),
                  d.pagina <= 1 && "pointer-events-none opacity-40",
                )}
              >
                ← Anterior
              </Link>
              <span className="num text-sm text-muted-foreground">
                página <span className="font-bold text-foreground">{d.pagina}</span>{" "}
                de {d.paginas}
              </span>
              <Link
                href={`/biblioteca${armarQuery(filtros, d.pagina + 1)}`}
                aria-disabled={d.pagina >= d.paginas}
                tabIndex={d.pagina >= d.paginas ? -1 : undefined}
                className={cn(
                  buttonVariants({ variant: "outline", size: "sm" }),
                  d.pagina >= d.paginas && "pointer-events-none opacity-40",
                )}
              >
                Siguiente →
              </Link>
            </nav>
          )}
        </>
      )}
    </>
  );
}
