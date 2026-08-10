/**
 * Cliente de la cocina Python (tablero.py, puerto 8477).
 *
 * Los Server Components le pegan directo a la API JSON; el navegador llega a
 * /api/* y /media/* por los rewrites de next.config.ts. Si la cocina no está
 * corriendo, `pedirCocina` tira `CocinaApagadaError` y cada página la atrapa
 * para mostrar una pantalla útil en vez de un crash.
 */

export const COCINA_URL = process.env.COCINA_URL ?? "http://127.0.0.1:8477";

export class CocinaApagadaError extends Error {
  constructor(ruta: string) {
    super(`La cocina no respondió en ${ruta}`);
    this.name = "CocinaApagadaError";
  }
}

export type Estado = "propuesto" | "confirmado" | "descartado" | "desconocido";

export interface SegmentoLite {
  filename: string;
  tipo: string;
  tipo_corregido: string | null;
  tipo_efectivo: string;
  estado: Estado;
  fuente: string;
  fecha_hora_absoluta: string | null;
  fecha_linda: string;
  espectrograma: boolean;
  clip: boolean;
  /** Similitud coseno 0-1 (solo en resultados de búsqueda inversa). */
  score?: number;
}

export interface SegmentoCola extends SegmentoLite {
  inicio_grabacion: string | null;
  offset_s: number | null;
  duracion_s: number | null;
  /** Quién propuso el tipo, en criollo ("El clasificador v1", …). */
  propuesto_por: string;
  /** Confianza 0-1 del clasificador, o null en históricos. */
  confianza: number | null;
  dudoso: boolean;
  /** false si dura menos de 0,3 s (el índice armónico no es confiable ahí). */
  duracion_confiable: boolean;
}

export interface Campania {
  fuente: string;
  total: number;
  propuestos: number;
  confirmados: number;
  descartados: number;
  desconocidos: number;
  alertas: string[];
}

export interface Actividad {
  filename: string;
  tipo: string;
  tipo_corregido: string | null;
  estado: Estado;
  revisor: string;
  revisado_en: string;
  revisado_linda: string;
}

export interface PanelData {
  funnel: {
    fuentes: number;
    detectados: number;
    en_cola: number;
    revisados: number;
    pendientes: number;
    confirmados: number;
    vitrina: { cantidad: number; fecha: string } | null;
  };
  campanias: Campania[];
  actividad: Actividad[];
  pendientes: number;
}

export interface ColaData {
  pendientes: number;
  revisados: number;
  total: number;
  pos?: number;
  segmento: SegmentoCola | null;
  tipos_corregibles?: string[];
  ejemplares?: { total: number; items: SegmentoLite[] };
  similares?: SegmentoLite[] | null;
  hoy?: {
    confirmados: number;
    corregidos: number;
    descartados: number;
    desconocidos: number;
  };
}

export interface SegmentosData {
  total: number;
  pagina: number;
  paginas: number;
  items: SegmentoLite[];
  tipos: string[];
  estados: Estado[];
  fuentes: string[];
  pendientes: number;
}

export interface SimilaresData {
  segmento: SegmentoLite;
  indice: boolean;
  resultados: SegmentoLite[] | null;
}

export async function pedirCocina<T>(ruta: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${COCINA_URL}${ruta}`, { cache: "no-store" });
  } catch {
    throw new CocinaApagadaError(ruta);
  }
  if (res.status === 404) {
    throw new NoEncontradoError(ruta);
  }
  if (!res.ok) {
    throw new Error(`La cocina respondió ${res.status} en ${ruta}`);
  }
  return res.json() as Promise<T>;
}

export class NoEncontradoError extends Error {
  constructor(ruta: string) {
    super(`404 de la cocina en ${ruta}`);
    this.name = "NoEncontradoError";
  }
}

/** Pendientes para el badge de navegación; null si la cocina está apagada. */
export async function pedirPendientes(): Promise<number | null> {
  try {
    const d = await pedirCocina<{ pendientes: number }>("/api/pendientes");
    return d.pendientes;
  } catch {
    return null;
  }
}
