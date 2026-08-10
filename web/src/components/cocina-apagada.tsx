import { BallenaFranca } from "@/components/ballena";
import { Card, CardContent } from "@/components/ui/card";

/**
 * La API Python no responde. No es un crash: es una pantalla que te dice
 * exactamente qué correr para seguir.
 */
export function CocinaApagada() {
  return (
    <div className="mx-auto flex max-w-xl flex-col items-center py-20 text-center">
      <BallenaFranca className="w-52 text-mas-tenue" />
      <h2 className="mt-8 font-display text-2xl font-semibold">
        La cocina no está corriendo
      </h2>
      <p className="mt-2 text-muted-foreground">
        Esta web lee todo de la cocina Python (puerto{" "}
        <span className="num">8477</span>) y no obtuvo respuesta. Levantala y
        recargá la página:
      </p>
      <Card className="mt-6 w-full">
        <CardContent className="py-4 text-left">
          <pre className="overflow-x-auto font-mono text-sm leading-7 text-bio">
            <code>{`cd ecos-del-golfo\n./ecos.sh          # cocina + web juntas`}</code>
          </pre>
          <p className="mt-3 text-sm text-muted-foreground">
            O solo la cocina:{" "}
            <code className="rounded-sm bg-panel-2 px-1.5 py-0.5 font-mono text-[0.85em] text-foreground">
              source .venv/bin/activate && python tablero.py
            </code>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
