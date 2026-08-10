import type { Metadata } from "next";
import Link from "next/link";

import { CocinaApagada } from "@/components/cocina-apagada";
import { BadgeHipotesis, ChipEstado, ETIQUETA_ESTADO } from "@/components/insignias";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
  type Actividad,
  type Campania,
  type Estado,
  type PanelData,
  pedirCocina,
} from "@/lib/cocina";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Panel" };

// Cada etapa lleva su color arriba: el lifecycle es información de primer
// nivel, no decoración. Bio = máquina, ámbar = te toca a vos, verde = curado.
const ACENTO_ETAPA = [
  "bg-mas-tenue",
  "bg-bio",
  "bg-propuesto",
  "bg-ambar-fuerte",
  "bg-confirmado",
  "bg-bio",
] as const;

function Etapa({
  orden,
  numero,
  label,
  desc,
  href,
  indice,
  children,
}: {
  orden: string;
  numero: React.ReactNode;
  label: string;
  desc: React.ReactNode;
  href?: string;
  indice: number;
  children?: React.ReactNode;
}) {
  const cuerpo = (
    <>
      <span className={cn("absolute inset-x-0 top-0 h-0.5", ACENTO_ETAPA[indice])} />
      <span className="font-mono text-[0.64rem] font-semibold tracking-[0.14em] text-mas-tenue uppercase">
        {orden}
      </span>
      <span className="num text-[2rem] leading-tight font-bold">{numero}</span>
      <span className="text-[0.94rem] leading-snug font-semibold">{label}</span>
      {children}
      <span className="text-xs leading-relaxed text-muted-foreground">{desc}</span>
    </>
  );
  const clase =
    "relative flex flex-col gap-1.5 bg-card px-4 pt-4 pb-4 overflow-hidden";
  if (href) {
    return (
      <Link
        href={href}
        className={cn(
          clase,
          "transition-colors hover:bg-panel-2 focus-visible:z-10",
        )}
      >
        {cuerpo}
        <span className="mt-auto pt-2 text-[0.8rem] font-semibold text-ambar">
          Entrar →
        </span>
      </Link>
    );
  }
  return <div className={clase}>{cuerpo}</div>;
}

function SaludCampania({ c }: { c: Campania }) {
  const orden: [Estado, number][] = [
    ["confirmado", c.confirmados],
    ["propuesto", c.propuestos],
    ["desconocido", c.desconocidos],
    ["descartado", c.descartados],
  ];
  const colorBarra: Record<Estado, string> = {
    confirmado: "bg-confirmado",
    propuesto: "bg-propuesto",
    desconocido: "bg-desconocido",
    descartado: "bg-descartado",
  };
  return (
    <Card className="gap-0 rounded-sm p-5">
      <h3 className="font-mono text-sm font-semibold break-all">{c.fuente}</h3>
      <p className="num mt-1 text-3xl font-bold">
        {c.total}{" "}
        <span className="font-sans text-sm font-normal text-muted-foreground">
          segmentos
        </span>
      </p>
      <div
        className="mt-3 flex h-2.5 overflow-hidden rounded-xs bg-panel-3"
        role="img"
        aria-label={`Distribución por estado: ${orden
          .map(([e, n]) => `${n} ${e}s`)
          .join(", ")}`}
      >
        {orden.map(
          ([estado, n]) =>
            n > 0 && (
              <span
                key={estado}
                className={cn("h-full min-w-0.5", colorBarra[estado])}
                style={{ width: `${(100 * n) / c.total}%` }}
                title={`${ETIQUETA_ESTADO[estado]}: ${n}`}
              />
            ),
        )}
      </div>
      <div className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1.5 text-[0.8rem] text-muted-foreground">
        {orden.map(([estado, n]) => (
          <span key={estado} className="inline-flex items-center gap-1.5">
            <i className={cn("size-2 rounded-xs", colorBarra[estado])} />
            <span className="num font-bold text-foreground">{n}</span> {estado}s
          </span>
        ))}
      </div>
      {c.alertas.map((a) => (
        <p
          key={a}
          className="mt-3 rounded-xs border border-ambar-fuerte bg-ambar-fuerte/10 px-3 py-2 text-sm text-ambar"
        >
          <strong className="font-mono text-[0.72rem] tracking-wider">ALERTA</strong>{" "}
          · {a}
        </p>
      ))}
    </Card>
  );
}

function FilaActividad({ v }: { v: Actividad }) {
  let que: React.ReactNode;
  if (v.estado === "confirmado" && v.tipo_corregido && v.tipo_corregido !== v.tipo) {
    que = (
      <>
        corrigió <strong>{v.tipo}</strong> → <strong>{v.tipo_corregido}</strong>
      </>
    );
  } else if (v.estado === "confirmado") {
    que = (
      <>
        confirmó <strong>{v.tipo_corregido ?? v.tipo}</strong>
      </>
    );
  } else if (v.estado === "descartado") {
    que = (
      <>
        descartó un <strong>{v.tipo}</strong> propuesto
      </>
    );
  } else {
    que = (
      <>
        marcó desconocido un <strong>{v.tipo}</strong> propuesto
      </>
    );
  }
  return (
    <li className="flex flex-wrap items-baseline gap-x-4 gap-y-1 px-4 py-2.5 text-[0.88rem]">
      <span className="num min-w-[8.5rem] text-[0.78rem] text-mas-tenue">
        {v.revisado_linda}
      </span>
      <span className="font-semibold">{v.revisor}</span>
      <span>{que}</span>
      <ChipEstado estado={v.estado} />
      <span className="num ml-auto text-[0.76rem] text-mas-tenue">{v.filename}</span>
    </li>
  );
}

export default async function PaginaPanel() {
  let d: PanelData;
  try {
    d = await pedirCocina<PanelData>("/api/panel");
  } catch {
    return <CocinaApagada />;
  }
  const f = d.funnel;
  const pctRevision = f.en_cola ? (100 * f.revisados) / f.en_cola : 0;

  return (
    <>
      <h2 className="font-display text-[1.9rem] font-semibold tracking-tight">
        El viaje de un sonido
      </h2>
      <p className="mt-1 mb-7 max-w-[62ch] text-muted-foreground">
        Del hidrófono a la biblioteca pública: la máquina detecta y propone, el
        experto confirma con el oído. Acá se ve dónde está parado cada sonido hoy.
      </p>

      <div className="grid grid-cols-1 gap-px overflow-hidden rounded-sm border border-border bg-border sm:grid-cols-2 xl:grid-cols-6">
        <Etapa
          indice={0}
          orden="01 · Campo"
          numero={f.fuentes}
          label={f.fuentes === 1 ? "Grabación" : "Grabaciones"}
          desc="Las campañas de grabación en el mar: la fuente cruda de todo."
        />
        <Etapa
          indice={1}
          orden="02 · Detección"
          numero={f.detectados}
          label="Sonidos detectados"
          desc="Segmentos con actividad acústica que la máquina recortó de las grabaciones."
          href="/biblioteca"
        />
        <Etapa
          indice={2}
          orden="03 · Propuesta"
          numero={f.en_cola}
          label="Propuestos a revisión"
          desc="Los que la máquina marcó dudosos: propone un tipo, pero no decide sola."
        />
        <Etapa
          indice={3}
          orden="04 · Oído"
          numero={
            <>
              {f.revisados}
              <span className="text-base font-semibold text-muted-foreground">
                {" "}
                / {f.en_cola}
              </span>
            </>
          }
          label="Revisión del experto"
          desc={`${f.revisados} revisados · ${f.pendientes} pendientes. El experto confirma, corrige o descarta escuchando.`}
          href="/revisar"
        >
          <Progress
            value={pctRevision}
            aria-label="Progreso de revisión"
            className="my-0.5 h-1.5 rounded-xs bg-panel-3 [&>[data-slot=progress-indicator]]:bg-confirmado"
          />
        </Etapa>
        <Etapa
          indice={4}
          orden="05 · Biblioteca"
          numero={f.confirmados}
          label="Confirmados"
          desc="Ya son parte de la biblioteca curada del paisaje sonoro del Golfo."
          href="/biblioteca?estado=confirmado"
        />
        <Etapa
          indice={5}
          orden="06 · Vitrina"
          numero={f.vitrina ? f.vitrina.cantidad : "—"}
          label="Publicados en la vitrina"
          desc={
            f.vitrina ? (
              `Los que cualquiera puede escuchar en la web pública. Última publicación: ${f.vitrina.fecha}.`
            ) : (
              <>
                Todavía sin publicar. Corré{" "}
                <code className="font-mono">python publicar.py</code> para
                generar la web pública.
              </>
            )
          }
        />
      </div>

      <p className="mt-4 flex max-w-[82ch] items-baseline gap-2.5 text-[0.86rem] text-muted-foreground">
        <BadgeHipotesis />
        <span>
          Todos los sonidos llevan este badge: la identificación de especie
          (franca austral) es una hipótesis de trabajo hasta que la valide un
          experto independiente (ICB / CENPAT).
        </span>
      </p>

      <h3 className="mt-10 mb-3.5 flex items-center gap-2.5 text-[0.76rem] font-semibold tracking-[0.12em] text-muted-foreground uppercase after:flex-1 after:border-t after:border-border">
        Salud por campaña
      </h3>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(340px,1fr))] gap-4">
        {d.campanias.map((c) => (
          <SaludCampania key={c.fuente} c={c} />
        ))}
      </div>

      <h3 className="mt-10 mb-3.5 flex items-center gap-2.5 text-[0.76rem] font-semibold tracking-[0.12em] text-muted-foreground uppercase after:flex-1 after:border-t after:border-border">
        Actividad reciente
      </h3>
      {d.actividad.length > 0 ? (
        <ul className="divide-y divide-border rounded-sm border border-border bg-card">
          {d.actividad.map((v) => (
            <FilaActividad key={`${v.filename}-${v.revisado_en}`} v={v} />
          ))}
        </ul>
      ) : (
        <Card className="rounded-sm border-dashed border-borde-fuerte p-8 text-center text-muted-foreground">
          <p className="font-semibold text-foreground">
            Todavía no hay veredictos humanos registrados.
          </p>
          <p>Cuando el experto revise la cola, acá queda la traza: quién decidió qué, y cuándo.</p>
        </Card>
      )}
    </>
  );
}
