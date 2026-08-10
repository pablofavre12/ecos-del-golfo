"use client";

import { CircleHelp } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, useTransition } from "react";
import { toast } from "sonner";

import { Espectrograma } from "@/components/espectrograma";
import { BadgeHipotesis, BadgeTipo } from "@/components/insignias";
import { sumarRacha } from "@/components/revisar/racha";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import type { SegmentoCola } from "@/lib/cocina";
import Link from "next/link";

type Accion = "confirmar" | "corregir" | "descartar" | "desconocido";

const ETIQUETA_ACCION: Record<Accion, string> = {
  confirmar: "Confirmado",
  corregir: "Corregido",
  descartar: "Descartado",
  desconocido: "Marcado desconocido",
};

/**
 * El corazón de la cola (EA3): espectrograma + play primero, veredictos
 * segundo, metadata tercero. Atajos C / X / D / espacio / flechas, con
 * ayuda en un Dialog (tecla ?).
 */
export function ColaInteractiva({
  segmento,
  tiposCorregibles,
  pos,
  pendientes,
}: {
  segmento: SegmentoCola;
  tiposCorregibles: string[];
  pos: number;
  pendientes: number;
}) {
  const s = segmento;
  const router = useRouter();
  const [enviando, startTransition] = useTransition();
  // El padre nos monta con key={filename}: al avanzar la cola, el estado
  // (select de corrección, dialog) arranca limpio para el segmento nuevo.
  // Si el tipo propuesto no es corregible (p. ej. posible_ruido_agua), el
  // select arranca en el primer tipo corregible — nunca vacío.
  const [tipoCorregido, setTipoCorregido] = useState(
    tiposCorregibles.includes(s.tipo) ? s.tipo : (tiposCorregibles[0] ?? s.tipo),
  );
  const [ayudaAbierta, setAyudaAbierta] = useState(false);
  const audioRef = useRef<HTMLAudioElement>(null);

  const veredicto = useCallback(
    (accion: Accion, tipo?: string) => {
      if (enviando) return;
      startTransition(async () => {
        let res: Response;
        try {
          res = await fetch("/api/veredicto", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              filename: s.filename,
              accion,
              tipo_corregido: accion === "corregir" ? tipo : undefined,
            }),
          });
        } catch {
          toast.error("No se pudo hablar con la cocina — ¿sigue corriendo?");
          return;
        }
        if (!res.ok) {
          const cuerpo = (await res.json().catch(() => null)) as {
            error?: string;
          } | null;
          toast.error(cuerpo?.error ?? `La cocina respondió ${res.status}`);
          return;
        }
        sumarRacha();
        toast.success(
          accion === "corregir"
            ? `Corregido a ${tipo}`
            : `${ETIQUETA_ACCION[accion]} — siguiente de la cola`,
        );
        router.refresh(); // misma posición: ya muestra el siguiente pendiente
      });
    },
    [enviando, router, s.filename],
  );

  const irA = useCallback(
    (nuevaPos: number) => {
      if (nuevaPos >= 0 && nuevaPos < pendientes) {
        router.push(`/revisar?pos=${nuevaPos}`);
      }
    },
    [pendientes, router],
  );

  useEffect(() => {
    function alTeclear(ev: KeyboardEvent) {
      const t = ev.target as HTMLElement | null;
      const tag = t?.tagName;
      if (
        tag === "SELECT" ||
        tag === "INPUT" ||
        tag === "TEXTAREA" ||
        tag === "AUDIO" ||
        tag === "BUTTON" ||
        t?.closest("[role=dialog]") ||
        t?.closest("[role=listbox]")
      ) {
        return;
      }
      if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
      const k = ev.key;
      if (k === " ") {
        const audio = audioRef.current;
        if (audio) {
          ev.preventDefault();
          if (audio.paused) void audio.play();
          else audio.pause();
        }
      } else if (k === "c" || k === "C") veredicto("confirmar");
      else if (k === "x" || k === "X") veredicto("descartar");
      else if (k === "d" || k === "D") veredicto("desconocido");
      else if (k === "?") setAyudaAbierta(true);
      else if (k === "ArrowRight") irA(pos + 1);
      else if (k === "ArrowLeft") irA(pos - 1);
    }
    document.addEventListener("keydown", alTeclear);
    return () => document.removeEventListener("keydown", alTeclear);
  }, [veredicto, irA, pos]);

  return (
    <section className="rounded-sm border border-border bg-card p-5">
      {/* 1 · la joya: espectrograma + play */}
      <Espectrograma filename={s.filename} disponible={s.espectrograma} />
      {s.clip ? (
        <audio
          ref={audioRef}
          controls
          preload="auto"
          src={`/media/clip/${encodeURIComponent(s.filename)}`}
          className="mt-4"
        />
      ) : (
        <p className="mt-4 text-sm text-muted-foreground">clip no disponible</p>
      )}

      {/* 2 · los cuatro veredictos, explicados */}
      <div className="mt-5 grid grid-cols-1 gap-x-4 gap-y-4 sm:grid-cols-2">
        <div className="flex min-w-0 flex-col gap-1.5">
          <Button
            onClick={() => veredicto("confirmar")}
            disabled={enviando}
            className="h-auto w-full justify-center gap-2 whitespace-normal font-semibold"
          >
            <span className="min-w-0 break-words">Confirmar {s.tipo}</span>{" "}
            <kbd className="shrink-0 border-ambar/40 bg-ambar/20 text-sobre-ambar">C</kbd>
          </Button>
          <span className="text-center text-xs leading-normal text-muted-foreground">
            Es lo que dice la máquina
          </span>
        </div>
        <div className="flex min-w-0 flex-col gap-1.5">
          <div className="flex flex-col gap-2">
            <Select value={tipoCorregido} onValueChange={setTipoCorregido}>
              <SelectTrigger aria-label="Tipo corregido" className="w-full font-mono text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {tiposCorregibles.map((t) => (
                  <SelectItem key={t} value={t} className="font-mono text-sm">
                    {t}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              variant="outline"
              onClick={() => veredicto("corregir", tipoCorregido)}
              disabled={enviando}
              className="w-full"
            >
              Corregir tipo
            </Button>
          </div>
          <span className="text-center text-xs leading-normal text-muted-foreground">
            Es un sonido real, pero de otro tipo
          </span>
        </div>
        <div className="flex flex-col gap-1.5">
          <Button
            variant="outline"
            onClick={() => veredicto("descartar")}
            disabled={enviando}
            className="w-full justify-center gap-2"
          >
            Descartar <kbd>X</kbd>
          </Button>
          <span className="text-center text-xs leading-normal text-muted-foreground">
            No es un sonido de interés (ruido, agua, motor)
          </span>
        </div>
        <div className="flex flex-col gap-1.5">
          <Button
            variant="outline"
            onClick={() => veredicto("desconocido")}
            disabled={enviando}
            className="w-full justify-center gap-2"
          >
            Desconocido <kbd>D</kbd>
          </Button>
          <span className="text-center text-xs leading-normal text-muted-foreground">
            Es algo real, pero no sé qué
          </span>
        </div>
      </div>

      {/* atajos + ayuda */}
      <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border pt-3.5 text-[0.78rem] text-mas-tenue">
        <span className="inline-flex items-center gap-1.5">
          <kbd>C</kbd> confirmar
        </span>
        <span className="inline-flex items-center gap-1.5">
          <kbd>X</kbd> descartar
        </span>
        <span className="inline-flex items-center gap-1.5">
          <kbd>D</kbd> desconocido
        </span>
        <span className="inline-flex items-center gap-1.5">
          <kbd>espacio</kbd> play / pausa
        </span>
        <span className="inline-flex items-center gap-1.5">
          <kbd>←</kbd>
          <kbd>→</kbd> moverse en la cola
        </span>
        <Dialog open={ayudaAbierta} onOpenChange={setAyudaAbierta}>
          <DialogTrigger asChild>
            <Button variant="ghost" size="sm" className="ml-auto gap-1.5 text-mas-tenue">
              <CircleHelp className="size-4" aria-hidden /> Ayuda
            </Button>
          </DialogTrigger>
          <DialogContent className="flex max-h-[90dvh] flex-col">
            <DialogHeader className="shrink-0">
              <DialogTitle className="font-display">Cómo se revisa</DialogTitle>
              <DialogDescription>
                Escuchás, mirás el espectrograma, comparás con las referencias y
                decidís. La máquina nunca decide sola.
              </DialogDescription>
            </DialogHeader>
            <div className="min-h-0 flex-1 space-y-3 overflow-y-auto text-sm">
              <dl className="space-y-2.5">
                <div className="flex items-baseline gap-3">
                  <dt className="shrink-0"><kbd>C</kbd></dt>
                  <dd>
                    <strong>Confirmar:</strong> el clip es lo que la máquina
                    propuso. Entra a la biblioteca curada.
                  </dd>
                </div>
                <div className="flex items-baseline gap-3">
                  <dt className="shrink-0 font-mono text-xs text-muted-foreground">select</dt>
                  <dd>
                    <strong>Corregir tipo:</strong> es una vocalización real,
                    pero de otro tipo. Elegí el correcto y corregí — también
                    entra a la biblioteca.
                  </dd>
                </div>
                <div className="flex items-baseline gap-3">
                  <dt className="shrink-0"><kbd>X</kbd></dt>
                  <dd>
                    <strong>Descartar:</strong> ruido, agua, motor — no es
                    material de interés.
                  </dd>
                </div>
                <div className="flex items-baseline gap-3">
                  <dt className="shrink-0"><kbd>D</kbd></dt>
                  <dd>
                    <strong>Desconocido:</strong> es algo real que no podés
                    identificar. Queda marcado para volver con más contexto.
                  </dd>
                </div>
                <div className="flex items-baseline gap-3">
                  <dt className="shrink-0"><kbd>espacio</kbd></dt>
                  <dd>Play / pausa del clip principal.</dd>
                </div>
                <div className="flex items-baseline gap-3">
                  <dt className="shrink-0"><kbd>←</kbd> <kbd>→</kbd></dt>
                  <dd>Moverse en la cola sin dar veredicto (para pispear).</dd>
                </div>
              </dl>
              <Separator />
              <p className="text-muted-foreground">
                Cada veredicto queda asentado con tu nombre y la hora — la
                trazabilidad es lo que le da valor científico al catálogo.
              </p>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {/* 3 · metadata, al final a propósito (EA3) */}
      <div className="mt-4 border-t border-border pt-4 text-[0.8rem] text-muted-foreground">
        <div className="mb-2.5 flex flex-wrap items-center gap-2">
          <BadgeTipo tipo={s.tipo} />
          <BadgeHipotesis />
          <Link
            href={`/parecidos/${encodeURIComponent(s.filename)}`}
            className="ml-auto text-[0.82rem] font-semibold text-ambar hover:underline"
            title="Buscar clips que suenan parecido"
          >
            Buscar parecidos →
          </Link>
        </div>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-0.5">
          <dt className="font-semibold">Archivo</dt>
          <dd className="num break-all">{s.filename}</dd>
          <dt className="font-semibold">Fuente</dt>
          <dd className="num break-all">{s.fuente}</dd>
          <dt className="font-semibold">Fecha/hora absoluta</dt>
          <dd className="num">{s.fecha_hora_absoluta ?? "—"}</dd>
          <dt className="font-semibold">Inicio de grabación</dt>
          <dd className="num">{s.inicio_grabacion ?? "—"}</dd>
          <dt className="font-semibold">Offset en la grabación</dt>
          <dd className="num">
            {s.offset_s !== null ? `${s.offset_s.toFixed(1)} s` : "—"}
          </dd>
        </dl>
      </div>
    </section>
  );
}
