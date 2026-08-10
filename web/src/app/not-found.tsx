import Link from "next/link";

import { BallenaFranca } from "@/components/ballena";
import { buttonVariants } from "@/components/ui/button";

export default function NoEncontrada() {
  return (
    <div className="flex flex-col items-center py-20 text-center">
      <BallenaFranca className="w-64 text-mas-tenue" />
      <h2 className="mt-8 font-display text-2xl font-semibold">
        Esa página no existe
      </h2>
      <p className="mt-2 max-w-sm text-muted-foreground">
        Se hundió, o nunca estuvo. Todo lo que hay vive en el panel, la cola de
        revisión y la biblioteca.
      </p>
      <Link href="/" className={`${buttonVariants()} mt-7`}>
        Volver al panel
      </Link>
    </div>
  );
}
