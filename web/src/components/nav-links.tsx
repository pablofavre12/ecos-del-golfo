"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const SECCIONES = [
  { href: "/", nombre: "Panel", tarea: "Ver dónde está parado cada sonido" },
  { href: "/revisar", nombre: "Revisar", tarea: "Escuchar y dar veredicto" },
  { href: "/biblioteca", nombre: "Biblioteca", tarea: "Explorar el catálogo" },
] as const;

function activa(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  if (href === "/biblioteca") {
    return pathname.startsWith("/biblioteca") || pathname.startsWith("/parecidos");
  }
  return pathname.startsWith(href);
}

/** Navegación por TAREA, con badge de pendientes en Revisar. */
export function NavLinks({ pendientes }: { pendientes: number | null }) {
  const pathname = usePathname();
  return (
    <nav aria-label="Secciones" className="flex items-center gap-1 text-[0.94rem]">
      {SECCIONES.map((s) => (
        <Link
          key={s.href}
          href={s.href}
          title={s.tarea}
          aria-current={activa(pathname, s.href) ? "page" : undefined}
          className={cn(
            "rounded-lg px-3.5 py-1.5 font-medium text-muted-foreground transition-colors",
            "hover:bg-panel-2 hover:text-foreground",
            activa(pathname, s.href) && "bg-panel-3 font-semibold text-foreground",
          )}
        >
          {s.nombre}
          {s.href === "/revisar" && pendientes !== null && pendientes > 0 && (
            <span className="num ml-2 rounded-full bg-propuesto px-1.5 py-0.5 align-[2px] text-[0.68rem] font-bold text-sobre-ambar">
              {pendientes}
            </span>
          )}
        </Link>
      ))}
    </nav>
  );
}
