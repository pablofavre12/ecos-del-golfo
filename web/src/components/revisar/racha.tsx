"use client";

import { useEffect, useSyncExternalStore } from "react";

const CLAVE = "ecos-racha";
const EVENTO = "ecos-racha-cambio";

export function leerRacha(): number {
  try {
    return Number.parseInt(sessionStorage.getItem(CLAVE) ?? "0", 10) || 0;
  } catch {
    return 0;
  }
}

export function sumarRacha(): void {
  try {
    sessionStorage.setItem(CLAVE, String(leerRacha() + 1));
    window.dispatchEvent(new Event(EVENTO));
  } catch {
    /* sessionStorage bloqueado: la racha es un mimo, no un dato */
  }
}

function suscribir(alCambiar: () => void): () => void {
  window.addEventListener(EVENTO, alCambiar);
  return () => window.removeEventListener(EVENTO, alCambiar);
}

/** "Racha de la sesión: N veredictos" — vive en sessionStorage. */
export function RachaSesion() {
  const racha = useSyncExternalStore(suscribir, leerRacha, () => 0);
  if (racha === 0) return null;
  return (
    <span className="text-sm text-muted-foreground">
      Racha de la sesión: <span className="num font-bold text-bio">{racha}</span>{" "}
      {racha === 1 ? "veredicto" : "veredictos"}
    </span>
  );
}

/**
 * En la pantalla de logro: muestra la racha y la limpia (cierre de ciclo).
 * La limpieza no dispara el evento, así el número mostrado no desaparece.
 */
export function RachaLogro() {
  const racha = useSyncExternalStore(suscribir, leerRacha, () => 0);
  useEffect(() => {
    try {
      sessionStorage.removeItem(CLAVE);
    } catch {
      /* ídem */
    }
  }, []);
  if (racha === 0) return null;
  return (
    <p className="text-muted-foreground">
      Esta sesión cerraste <span className="num font-bold text-bio">{racha}</span>{" "}
      {racha === 1 ? "veredicto" : "veredictos"}.
    </p>
  );
}
