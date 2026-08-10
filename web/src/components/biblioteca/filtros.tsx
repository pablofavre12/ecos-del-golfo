"use client";

import { useRouter, useSearchParams } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const TODOS = "todos";

function Filtro({
  nombre,
  etiqueta,
  opciones,
  valor,
  alCambiar,
}: {
  nombre: string;
  etiqueta: string;
  opciones: string[];
  valor: string;
  alCambiar: (nombre: string, valor: string) => void;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label
        htmlFor={`filtro-${nombre}`}
        className="text-xs font-semibold text-muted-foreground"
      >
        {etiqueta}
      </label>
      <Select
        value={valor || TODOS}
        onValueChange={(v) => alCambiar(nombre, v === TODOS ? "" : v)}
      >
        <SelectTrigger id={`filtro-${nombre}`} className="min-w-40 font-mono text-sm">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={TODOS}>todos</SelectItem>
          {opciones.map((o) => (
            <SelectItem key={o} value={o} className="font-mono text-sm">
              {o}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

/** Filtros combinables del explorador. El estado vive en la URL (compartible). */
export function FiltrosBiblioteca({
  tipos,
  estados,
  fuentes,
}: {
  tipos: string[];
  estados: string[];
  fuentes: string[];
}) {
  const router = useRouter();
  const params = useSearchParams();

  const activos = ["tipo", "estado", "fuente"].filter((k) => params.get(k)).length;

  function alCambiar(nombre: string, valor: string) {
    const nuevos = new URLSearchParams(params.toString());
    if (valor) nuevos.set(nombre, valor);
    else nuevos.delete(nombre);
    nuevos.delete("pagina"); // filtro nuevo → primera página
    router.push(`/biblioteca${nuevos.size ? `?${nuevos}` : ""}`);
  }

  return (
    <div className="mb-5 flex flex-wrap items-end gap-3">
      <Filtro
        nombre="tipo"
        etiqueta="Tipo"
        opciones={tipos}
        valor={params.get("tipo") ?? ""}
        alCambiar={alCambiar}
      />
      <Filtro
        nombre="estado"
        etiqueta="Estado"
        opciones={estados}
        valor={params.get("estado") ?? ""}
        alCambiar={alCambiar}
      />
      <Filtro
        nombre="fuente"
        etiqueta="Fuente"
        opciones={fuentes}
        valor={params.get("fuente") ?? ""}
        alCambiar={alCambiar}
      />
      {activos > 0 && (
        <>
          <Badge
            variant="outline"
            className="num mb-2 rounded-full border-bio/50 px-2.5 text-[0.76rem] font-semibold text-bio"
          >
            {activos} filtro{activos !== 1 && "s"} activo{activos !== 1 && "s"}
          </Badge>
          <Button
            variant="ghost"
            size="sm"
            className="mb-1 text-muted-foreground"
            onClick={() => router.push("/biblioteca")}
          >
            Quitar filtros
          </Button>
        </>
      )}
    </div>
  );
}
