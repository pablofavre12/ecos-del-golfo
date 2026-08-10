"""Tablero local de Ecos del Golfo — v2 del panel (WCH-470).

Servidor web local sobre stdlib http.server, HTML server-rendered y CSS
propio inline. Sin frameworks JS ni CDNs: todo corre offline. Lee y escribe
exclusivamente sobre ecos.db (única fuente de verdad, D10).

Vistas:
  /            Panel: el pipeline visible (funnel con números reales de la DB),
               salud por campaña (R19) y actividad reciente (trazabilidad).
  /cola        Modo revisión: progreso, motivo, comparación de oído contra
               confirmados + similares Perch, atajos de teclado, auto-avance.
  /explorador  Catálogo completo con filtros.
  /similares/  Búsqueda inversa por embedding.

Uso: python tablero.py  →  http://localhost:8477
"""

from __future__ import annotations

import csv
import html
import sqlite3
import sys
import wave
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import base
import embeddings

PUERTO = 8477
VERSION = "v2 · WCH-470"
RUTA_RESPALDO_CSV = Path(__file__).parent / "respaldo" / "catalogo-export.csv"

ETIQUETA_ESTADO = {
    "propuesto": "PROPUESTO",
    "confirmado": "CONFIRMADO",
    "descartado": "DESCARTADO",
    "desconocido": "DESCONOCIDO",
}

TIPOS_CORREGIBLES = [t for t in base.TIPOS if t not in ("revisar_muy_cortos", "posible_ruido_agua")]

MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")

ESTILO = """
:root {
  --fondo: #08101d; --panel: #0d1a2c; --panel-2: #13233a; --panel-3: #182b46;
  --borde: #1d3150; --borde-fuerte: #2b4a75;
  --texto: #dce7f7; --tenue: #8098b8; --mas-tenue: #5c7494;
  --acento: #f0a35e; --acento-fuerte: #e8863a;
  --confirmado: #4fc596; --propuesto: #f0c95e; --descartado: #d97878; --desconocido: #8fa3c4;
  --hipotesis: #e8863a;
  --sans: "Avenir Next", "Segoe UI Variable", "Segoe UI", system-ui, -apple-system, sans-serif;
  --mono: ui-monospace, "SF Mono", "Cascadia Code", Menlo, Consolas, monospace;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html { scrollbar-gutter: stable; }
body {
  background: var(--fondo); color: var(--texto);
  font: 16px/1.6 var(--sans);
  min-height: 100vh; display: flex; flex-direction: column;
}
a { color: var(--acento); text-decoration: none; }
a:hover { text-decoration: underline; }
:focus-visible { outline: 2px solid var(--acento); outline-offset: 2px; border-radius: 2px; }
kbd {
  font: 600 0.72rem/1 var(--mono); color: var(--texto);
  background: var(--panel-3); border: 1px solid var(--borde-fuerte); border-bottom-width: 2px;
  border-radius: 4px; padding: 0.18rem 0.4rem; white-space: nowrap;
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { transition: none !important; animation: none !important; }
}

/* ---------- marco ---------- */
header.marco {
  display: flex; align-items: center; gap: 2rem; padding: 0.85rem 2rem;
  border-bottom: 1px solid var(--borde); background: var(--panel);
  position: sticky; top: 0; z-index: 10;
}
.marca { display: flex; align-items: center; gap: 0.6rem; }
.marca svg { color: var(--acento); display: block; }
.marca h1 { font-size: 1.02rem; font-weight: 600; letter-spacing: 0.01em; white-space: nowrap; }
.marca h1 span { color: var(--acento); }
header.marco nav { display: flex; gap: 0.35rem; font-size: 0.92rem; }
header.marco nav a {
  color: var(--tenue); padding: 0.35rem 0.85rem; border-radius: 6px; font-weight: 500;
}
header.marco nav a:hover { color: var(--texto); text-decoration: none; background: var(--panel-2); }
header.marco nav a[aria-current="page"] { color: var(--texto); background: var(--panel-3); font-weight: 600; }
header.marco nav a .pendientes-nav {
  font: 700 0.7rem/1 var(--mono); color: #14100a; background: var(--propuesto);
  border-radius: 8px; padding: 0.12rem 0.42rem; margin-left: 0.35rem; vertical-align: 1px;
}
main { width: 100%; max-width: 1180px; margin: 0 auto; padding: 2rem 2rem 4rem; flex: 1; }
footer.marco {
  border-top: 1px solid var(--borde); padding: 0.9rem 2rem; font-size: 0.8rem; color: var(--mas-tenue);
  display: flex; flex-wrap: wrap; gap: 0.4rem 2rem; justify-content: space-between;
}
footer.marco code { font-family: var(--mono); font-size: 0.78rem; }

h2 { font-size: 1.45rem; font-weight: 700; letter-spacing: -0.01em; }
.bajada { color: var(--tenue); margin-top: 0.25rem; margin-bottom: 1.6rem; max-width: 62ch; }
.titulo-seccion {
  font: 600 0.76rem/1 var(--sans); text-transform: uppercase; letter-spacing: 0.12em;
  color: var(--tenue); margin: 2.4rem 0 0.9rem; display: flex; align-items: center; gap: 0.6rem;
}
.titulo-seccion::after { content: ""; flex: 1; border-top: 1px solid var(--borde); }
.num { font-family: var(--mono); font-variant-numeric: tabular-nums; }

/* ---------- funnel del pipeline ---------- */
.funnel { display: flex; align-items: stretch; gap: 0.35rem; }
.etapa {
  flex: 1; min-width: 0; background: var(--panel); border: 1px solid var(--borde);
  border-radius: 4px; padding: 0.9rem 1rem 1rem; display: flex; flex-direction: column; gap: 0.3rem;
  color: var(--texto); position: relative;
}
a.etapa:hover { border-color: var(--acento); text-decoration: none; }
a.etapa:hover .etapa-orden { color: var(--acento); }
.etapa-orden {
  font: 600 0.66rem/1 var(--mono); letter-spacing: 0.14em; text-transform: uppercase;
  color: var(--mas-tenue); white-space: nowrap;
}
.etapa-num { font: 700 2rem/1.15 var(--mono); font-variant-numeric: tabular-nums; }
.etapa-num small { font-size: 1rem; font-weight: 600; color: var(--tenue); }
.etapa-label { font-weight: 600; font-size: 0.94rem; line-height: 1.3; }
.etapa-desc { font-size: 0.8rem; color: var(--tenue); line-height: 1.45; }
.etapa-ir { margin-top: auto; padding-top: 0.5rem; font-size: 0.8rem; font-weight: 600; color: var(--acento); }
.flecha-funnel { align-self: center; color: var(--mas-tenue); flex: 0 0 auto; }
.etapa .barra-progreso { margin-top: 0.2rem; }
.barra-progreso {
  height: 6px; border-radius: 3px; background: var(--panel-3); overflow: hidden;
}
.barra-progreso > span { display: block; height: 100%; background: var(--confirmado); border-radius: 3px; }
.nota-hipotesis {
  margin-top: 1.1rem; font-size: 0.86rem; color: var(--tenue); max-width: 82ch;
  display: flex; gap: 0.6rem; align-items: baseline;
}
@media (max-width: 980px) {
  .funnel { flex-wrap: wrap; }
  .etapa { flex: 1 1 260px; }
  .flecha-funnel { display: none; }
}

/* ---------- salud por campaña ---------- */
.tarjetas-campania { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 1.1rem; }
.campania { background: var(--panel); border: 1px solid var(--borde); border-radius: 4px; padding: 1.1rem 1.25rem; }
.campania h3 { font: 600 0.9rem/1.3 var(--mono); word-break: break-all; }
.campania .total { font: 700 1.9rem/1.2 var(--mono); font-variant-numeric: tabular-nums; margin-top: 0.2rem; }
.campania .total small { font: 400 0.85rem var(--sans); color: var(--tenue); }
.barra-estados { display: flex; height: 10px; border-radius: 3px; overflow: hidden; margin: 0.7rem 0 0.6rem; background: var(--panel-3); }
.barra-estados span { display: block; height: 100%; min-width: 2px; }
.barra-estados .seg-propuesto   { background: var(--propuesto); }
.barra-estados .seg-confirmado  { background: var(--confirmado); }
.barra-estados .seg-descartado  { background: var(--descartado); }
.barra-estados .seg-desconocido { background: var(--desconocido); }
.estados { display: flex; flex-wrap: wrap; gap: 0.45rem 0.9rem; }
.leyenda-estado { font-size: 0.8rem; color: var(--tenue); display: inline-flex; align-items: center; gap: 0.35rem; }
.leyenda-estado i { width: 8px; height: 8px; border-radius: 2px; display: inline-block; }
.leyenda-estado .n { font-family: var(--mono); font-weight: 700; color: var(--texto); }
.chip {
  font: 600 0.72rem/1 var(--mono); letter-spacing: 0.05em; padding: 0.22rem 0.55rem;
  border-radius: 3px; border: 1px solid; white-space: nowrap;
}
.chip.propuesto   { color: var(--propuesto);   border-color: var(--propuesto); }
.chip.confirmado  { color: var(--confirmado);  border-color: var(--confirmado); }
.chip.descartado  { color: var(--descartado);  border-color: var(--descartado); }
.chip.desconocido { color: var(--desconocido); border-color: var(--desconocido); }
.alerta {
  margin-top: 0.8rem; padding: 0.55rem 0.8rem; border-radius: 3px; font-size: 0.85rem;
  background: rgba(232, 134, 58, 0.1); border: 1px solid var(--acento-fuerte); color: var(--acento);
}
.alerta strong { letter-spacing: 0.05em; font-size: 0.75rem; }

/* ---------- actividad reciente ---------- */
.actividad { list-style: none; border: 1px solid var(--borde); border-radius: 4px; background: var(--panel); }
.actividad li {
  display: flex; flex-wrap: wrap; gap: 0.3rem 0.9rem; align-items: baseline;
  padding: 0.65rem 1.1rem; border-top: 1px solid var(--borde); font-size: 0.88rem;
}
.actividad li:first-child { border-top: 0; }
.actividad .cuando { font: 500 0.78rem var(--mono); color: var(--mas-tenue); min-width: 8.5rem; }
.actividad .quien { font-weight: 600; }
.actividad .archivo { font: 400 0.78rem var(--mono); color: var(--mas-tenue); margin-left: auto; }
.decision { font: 600 0.72rem/1 var(--mono); letter-spacing: 0.05em; padding: 0.2rem 0.5rem; border-radius: 3px; border: 1px solid; }
.decision.confirmado  { color: var(--confirmado); border-color: var(--confirmado); }
.decision.descartado  { color: var(--descartado); border-color: var(--descartado); }
.decision.desconocido { color: var(--desconocido); border-color: var(--desconocido); }

/* ---------- botones y forms ---------- */
.boton {
  display: inline-block; padding: 0.55rem 1.2rem; border-radius: 6px; font-size: 0.92rem;
  font-family: var(--sans); font-weight: 600; cursor: pointer; border: 1px solid var(--borde-fuerte);
  background: var(--panel-2); color: var(--texto);
}
.boton:hover { border-color: var(--acento); text-decoration: none; }
.boton.primario { background: var(--acento-fuerte); border-color: var(--acento-fuerte); color: #14100a; }
.boton.primario:hover { background: var(--acento); }
select {
  background: var(--panel-2); color: var(--texto); border: 1px solid var(--borde-fuerte);
  border-radius: 6px; padding: 0.45rem 0.6rem; font: 0.88rem var(--sans);
}
form.filtros { display: flex; flex-wrap: wrap; gap: 0.7rem; align-items: end; margin-bottom: 1.4rem; }
form.filtros label { display: block; font-size: 0.75rem; color: var(--tenue); margin-bottom: 0.25rem; font-weight: 600; }
.contador-filtros {
  font: 600 0.78rem var(--mono); color: var(--acento);
  border: 1px solid var(--acento-fuerte); border-radius: 10px; padding: 0.2rem 0.6rem;
}

/* ---------- tarjetas de segmento ---------- */
.grilla { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1.1rem; }
.segmento { background: var(--panel); border: 1px solid var(--borde); border-radius: 4px; overflow: hidden; }
.segmento img { width: 100%; display: block; background: #060b14; border-bottom: 1px solid var(--borde); }
.segmento .cuerpo { padding: 0.75rem 0.9rem 0.9rem; }
.segmento audio { width: 100%; height: 32px; margin: 0.55rem 0; }
.fila-badges { display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: center; }
.badge-hipotesis {
  font: 700 0.68rem/1 var(--mono); letter-spacing: 0.09em; padding: 0.2rem 0.5rem;
  border-radius: 3px; background: var(--hipotesis); color: #14100a; white-space: nowrap;
}
.badge-tipo {
  font: 600 0.74rem/1 var(--mono); padding: 0.2rem 0.5rem; border-radius: 3px;
  background: var(--panel-2); border: 1px solid var(--borde-fuerte); color: var(--texto);
}
.badge-score {
  font: 700 0.76rem/1 var(--mono); font-variant-numeric: tabular-nums;
  padding: 0.2rem 0.5rem; border-radius: 3px; background: var(--acento-fuerte); color: #14100a;
}
.meta { color: var(--tenue); font-size: 0.8rem; margin-top: 0.45rem; font-family: var(--mono); }
.boton-similares {
  display: inline-block; margin-top: 0.55rem; font-size: 0.8rem; padding: 0.3rem 0.7rem;
  border: 1px solid var(--borde-fuerte); border-radius: 6px; background: var(--panel-2); color: var(--texto);
  font-weight: 600;
}
.boton-similares:hover { border-color: var(--acento); text-decoration: none; }

/* ---------- estados vacíos ---------- */
.vacio {
  background: var(--panel); border: 1px dashed var(--borde-fuerte); border-radius: 4px;
  padding: 2.4rem; text-align: center; color: var(--tenue);
}
.vacio strong { color: var(--texto); }
.vacio code { background: var(--panel-2); padding: 0.15rem 0.45rem; border-radius: 3px; font-family: var(--mono); font-size: 0.88em; }

/* ---------- cola de revisión ---------- */
.cola-progreso {
  background: var(--panel); border: 1px solid var(--borde); border-radius: 4px;
  padding: 0.9rem 1.25rem; margin-bottom: 1.2rem;
}
.cola-progreso .fila {
  display: flex; flex-wrap: wrap; gap: 0.4rem 1.4rem; align-items: baseline; margin-bottom: 0.6rem;
}
.cola-progreso .donde { font-size: 1.05rem; font-weight: 700; }
.cola-progreso .donde .num { color: var(--acento); }
.cola-progreso .racha { font-size: 0.85rem; color: var(--tenue); }
.cola-progreso .hechos { font-size: 0.85rem; color: var(--tenue); margin-left: auto; }
.motivo {
  border: 1px solid var(--borde); border-left: 3px solid var(--propuesto); border-radius: 4px;
  background: var(--panel); padding: 0.8rem 1.1rem; margin-bottom: 1.2rem; font-size: 0.92rem;
}
.motivo .etiqueta {
  font: 600 0.68rem/1 var(--mono); letter-spacing: 0.12em; text-transform: uppercase;
  color: var(--propuesto); display: block; margin-bottom: 0.3rem;
}
.cola-grid { display: grid; grid-template-columns: minmax(0, 2fr) minmax(260px, 1fr); gap: 1.2rem; align-items: start; }
@media (max-width: 900px) { .cola-grid { grid-template-columns: 1fr; } }
.heroe { background: var(--panel); border: 1px solid var(--borde); border-radius: 4px; padding: 1.2rem 1.3rem; }
.heroe .marco-espectro { border: 1px solid var(--borde-fuerte); border-radius: 3px; overflow: hidden; background: #060b14; }
.heroe .marco-espectro img { width: 100%; max-height: 420px; object-fit: contain; display: block; }
.heroe audio { width: 100%; margin-top: 0.9rem; }
.veredictos {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 0.8rem; margin-top: 1.3rem;
}
.veredicto { display: flex; flex-direction: column; gap: 0.35rem; }
.veredicto form { display: flex; flex-direction: column; gap: 0.45rem; }
.veredicto .boton { width: 100%; display: flex; justify-content: center; gap: 0.5rem; align-items: center; }
.veredicto .ayuda { font-size: 0.78rem; color: var(--tenue); line-height: 1.4; text-align: center; }
.atajos {
  margin-top: 1.2rem; padding-top: 0.9rem; border-top: 1px solid var(--borde);
  font-size: 0.78rem; color: var(--mas-tenue); display: flex; flex-wrap: wrap; gap: 0.4rem 1.1rem;
  align-items: center;
}
.atajos span { display: inline-flex; align-items: center; gap: 0.35rem; }
.metadata-cola { margin-top: 1.2rem; padding-top: 1rem; border-top: 1px solid var(--borde); color: var(--tenue); font-size: 0.8rem; }
.metadata-cola dl { display: grid; grid-template-columns: auto 1fr; gap: 0.2rem 1rem; }
.metadata-cola dt { font-weight: 600; }
.metadata-cola dd { font-family: var(--mono); word-break: break-all; }
.referencias { display: flex; flex-direction: column; gap: 1.2rem; }
.panel-referencia { background: var(--panel); border: 1px solid var(--borde); border-radius: 4px; padding: 1rem 1.1rem; }
.panel-referencia h3 { font-size: 0.9rem; font-weight: 600; margin-bottom: 0.2rem; }
.panel-referencia .sub { font-size: 0.78rem; color: var(--tenue); margin-bottom: 0.8rem; }
.mini { border: 1px solid var(--borde); border-radius: 3px; overflow: hidden; margin-top: 0.7rem; background: var(--panel-2); }
.mini:first-of-type { margin-top: 0; }
.mini img { width: 100%; height: 84px; object-fit: cover; display: block; background: #060b14; border-bottom: 1px solid var(--borde); }
.mini .pie { display: flex; align-items: center; gap: 0.5rem; padding: 0.4rem 0.6rem; }
.mini audio { width: 100%; height: 28px; flex: 1; min-width: 0; }
.mini .pie .badge-score { flex: 0 0 auto; }
.mini .pie .badge-tipo { flex: 0 0 auto; }
.ver-mas { display: inline-block; margin-top: 0.8rem; font-size: 0.82rem; font-weight: 600; }

/* ---------- logro ---------- */
.logro { text-align: center; padding: 3.5rem 2rem; }
.logro svg { color: var(--confirmado); }
.logro h2 { margin-top: 1rem; }
.logro p { color: var(--tenue); margin-top: 0.4rem; }
.logro .resumen {
  display: inline-flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 1.3rem; justify-content: center;
}
"""

LOGO_SVG = (
    '<svg width="26" height="16" viewBox="0 0 28 16" aria-hidden="true" fill="none">'
    '<path d="M1 8h2M6 5v6M10 2v12M14 6v4M18 1v14M22 5v6M26 8h1" '
    'stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>'
)

FLECHA_SVG = (
    '<svg class="flecha-funnel" width="18" height="18" viewBox="0 0 20 20" aria-hidden="true" '
    'fill="none"><path d="M4 10h11m-4-4 4 4-4 4" stroke="currentColor" stroke-width="1.8" '
    'stroke-linecap="round" stroke-linejoin="round"/></svg>'
)

TILDE_SVG = (
    '<svg width="52" height="52" viewBox="0 0 52 52" aria-hidden="true" fill="none">'
    '<circle cx="26" cy="26" r="24" stroke="currentColor" stroke-width="3"/>'
    '<path d="M16 27l7 7 13-14" stroke="currentColor" stroke-width="3" '
    'stroke-linecap="round" stroke-linejoin="round"/></svg>'
)


def e(texto) -> str:
    return html.escape(str(texto if texto is not None else ""))


def fecha_linda(iso: str | None) -> str:
    """'2026-08-03T17:42:28' → '03 ago 17:42'. Si no parsea, devuelve el crudo."""
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso)
        return f"{dt.day:02d} {MESES[dt.month - 1]} {dt:%H:%M}"
    except ValueError:
        return iso


def duracion_clip(ruta: str | None) -> float | None:
    """Duración del WAV en segundos, o None si no se puede leer."""
    if not ruta or not Path(ruta).exists():
        return None
    try:
        with wave.open(ruta, "rb") as w:
            frames, sr = w.getnframes(), w.getframerate()
        return frames / sr if sr else None
    except (wave.Error, OSError):
        return None


def publicados_en_vitrina() -> tuple[int, str] | None:
    """Cuántos confirmados salieron en la última publicación (respaldo R20).

    Lee respaldo/catalogo-export.csv — el dump que publicar.py escribe en cada
    publicación. Devuelve (cantidad, fecha legible) o None si nunca se publicó.
    """
    if not RUTA_RESPALDO_CSV.exists():
        return None
    try:
        with open(RUTA_RESPALDO_CSV, newline="") as f:
            cantidad = sum(1 for fila in csv.DictReader(f) if fila.get("estado") == "confirmado")
        fecha = datetime.fromtimestamp(RUTA_RESPALDO_CSV.stat().st_mtime)
        return cantidad, fecha_linda(fecha.isoformat())
    except (OSError, csv.Error):
        return None


def pagina(titulo: str, activo: str, cuerpo: str, pendientes: int = 0, extra: str = "") -> str:
    def nav(ruta, nombre, clave, badge=""):
        actual = ' aria-current="page"' if activo == clave else ""
        return f'<a href="{ruta}"{actual}>{nombre}{badge}</a>'

    badge_cola = (
        f'<span class="pendientes-nav num">{pendientes}</span>' if pendientes > 0 else ""
    )
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(titulo)} — Ecos del Golfo</title>
<style>{ESTILO}</style>
</head>
<body>
<header class="marco">
  <a class="marca" href="/" aria-label="Ecos del Golfo — panel">{LOGO_SVG}<h1>Ecos <span>del Golfo</span></h1></a>
  <nav aria-label="Secciones del tablero">
    {nav("/", "Panel", "panel")}
    {nav("/cola", "Cola de revisión", "cola", badge_cola)}
    {nav("/explorador", "Explorador", "explorador")}
  </nav>
</header>
<main>
{cuerpo}
</main>
<footer class="marco">
  <span>Ecos del Golfo · tablero local · {e(VERSION)}</span>
  <span>La máquina propone, el experto confirma · fuente de verdad: <code>ecos.db</code></span>
</footer>
{extra}
</body>
</html>"""


def badge_hipotesis() -> str:
    return (
        '<span class="badge-hipotesis" '
        'title="La especie no está validada por un experto independiente">HIPÓTESIS</span>'
    )


def boton_similares(filename: str) -> str:
    return (
        f'<a class="boton-similares" href="/similares/{e(filename)}" '
        'title="Buscar clips que suenan parecido">Buscar parecidos</a>'
    )


def tarjeta_segmento(s: sqlite3.Row, score: float | None = None) -> str:
    tipo = s["tipo_corregido"] or s["tipo"]
    estado = s["estado"]
    espectro = (
        f'<img src="/media/espectro/{e(s["filename"])}" alt="Espectrograma de {e(s["filename"])}" loading="lazy">'
        if s["espectrograma_path"]
        else '<div class="vacio" style="padding:1.2rem">sin espectrograma</div>'
    )
    audio = (
        f'<audio controls preload="none" src="/media/clip/{e(s["filename"])}"></audio>'
        if s["clip_path"]
        else '<p class="meta">clip no disponible</p>'
    )
    badge_score = f'<span class="badge-score">{score * 100:.0f}%</span>' if score is not None else ""
    return f"""<article class="segmento">
  {espectro}
  <div class="cuerpo">
    <div class="fila-badges">
      {badge_score}
      <span class="badge-tipo">{e(tipo)}</span>
      {badge_hipotesis()}
      <span class="chip {e(estado)}">{e(ETIQUETA_ESTADO.get(estado, estado))}</span>
    </div>
    {audio}
    <p class="meta">{e(fecha_linda(s["fecha_hora_absoluta"]))} · {e(s["fuente"])}</p>
    {boton_similares(s["filename"])}
  </div>
</article>"""


def mini_clip(s: sqlite3.Row, score: float | None = None) -> str:
    """Tarjeta compacta para los paneles de referencia de la cola."""
    espectro = (
        f'<img src="/media/espectro/{e(s["filename"])}" alt="Espectrograma de {e(s["filename"])}" loading="lazy">'
        if s["espectrograma_path"]
        else ""
    )
    audio = (
        f'<audio controls preload="none" src="/media/clip/{e(s["filename"])}"></audio>'
        if s["clip_path"]
        else '<span class="meta">clip no disponible</span>'
    )
    tipo = s["tipo_corregido"] or s["tipo"]
    insignia = (
        f'<span class="badge-score">{score * 100:.0f}%</span>'
        if score is not None
        else f'<span class="badge-tipo">{e(tipo)}</span>'
    )
    return f"""<div class="mini">
  {espectro}
  <div class="pie">{audio}{insignia}</div>
</div>"""


def contar_pendientes(con: sqlite3.Connection) -> int:
    return con.execute("SELECT COUNT(*) FROM segmento WHERE estado = 'propuesto'").fetchone()[0]


# ---------- vistas ----------


def vista_panel(con: sqlite3.Connection) -> str:
    tot = con.execute(
        """
        SELECT COUNT(*)                    AS detectados,
               COUNT(DISTINCT fuente)      AS fuentes,
               SUM(estado = 'propuesto')   AS pendientes,
               SUM(estado = 'confirmado')  AS confirmados,
               SUM(revisor IS NOT NULL)    AS revisados
        FROM segmento
        """
    ).fetchone()

    if not tot["detectados"]:
        cuerpo = """<h2>Panel</h2>
<div class="vacio">
  <p><strong>El catálogo está vacío.</strong></p>
  <p>Generá los fixtures y cargalos así:</p>
  <p><code>python generar_fixtures.py</code> y después <code>python importar.py fixtures</code></p>
</div>"""
        return pagina("Panel", "panel", cuerpo)

    pendientes = tot["pendientes"] or 0
    revisados = tot["revisados"] or 0
    en_cola = pendientes + revisados  # todo lo que entró (o está) en revisión humana
    pct_revision = 100.0 * revisados / en_cola if en_cola else 0.0

    vitrina = publicados_en_vitrina()
    if vitrina:
        num_vitrina, fecha_vitrina = vitrina
        etapa_vitrina = f"""<div class="etapa">
  <span class="etapa-orden">06 · Vitrina</span>
  <p class="etapa-num">{num_vitrina}</p>
  <p class="etapa-label">Publicados en la vitrina</p>
  <p class="etapa-desc">Los que cualquiera puede escuchar en la web pública. Última publicación: {e(fecha_vitrina)}.</p>
</div>"""
    else:
        etapa_vitrina = """<div class="etapa">
  <span class="etapa-orden">06 · Vitrina</span>
  <p class="etapa-num">—</p>
  <p class="etapa-label">Publicados en la vitrina</p>
  <p class="etapa-desc">Todavía sin publicar. Corré <code>python publicar.py</code> para generar la web pública.</p>
</div>"""

    ir_cola = (
        f'<span class="etapa-ir">Revisar los {pendientes} pendientes →</span>'
        if pendientes
        else '<span class="etapa-ir">Cola en cero — todo revisado</span>'
    )
    funnel = f"""<div class="funnel">
<div class="etapa">
  <span class="etapa-orden">01 · Campo</span>
  <p class="etapa-num">{tot["fuentes"]}</p>
  <p class="etapa-label">{"Grabación" if tot["fuentes"] == 1 else "Grabaciones"}</p>
  <p class="etapa-desc">Las campañas de grabación en el mar: la fuente cruda de todo.</p>
</div>
{FLECHA_SVG}
<a class="etapa" href="/explorador">
  <span class="etapa-orden">02 · Detección</span>
  <p class="etapa-num">{tot["detectados"]}</p>
  <p class="etapa-label">Sonidos detectados</p>
  <p class="etapa-desc">Segmentos con actividad acústica que la máquina recortó de las grabaciones.</p>
</a>
{FLECHA_SVG}
<div class="etapa">
  <span class="etapa-orden">03 · Propuesta</span>
  <p class="etapa-num">{en_cola}</p>
  <p class="etapa-label">Propuestos a revisión</p>
  <p class="etapa-desc">Los que la máquina marcó dudosos: propone un tipo, pero no decide sola.</p>
</div>
{FLECHA_SVG}
<a class="etapa" href="/cola">
  <span class="etapa-orden">04 · Oído</span>
  <p class="etapa-num">{revisados}<small> / {en_cola}</small></p>
  <p class="etapa-label">Revisión del experto</p>
  <div class="barra-progreso" role="progressbar" aria-valuenow="{revisados}" aria-valuemin="0"
       aria-valuemax="{en_cola}" aria-label="Progreso de revisión">
    <span style="width:{pct_revision:.0f}%"></span>
  </div>
  <p class="etapa-desc">{revisados} revisados · {pendientes} pendientes. El experto confirma, corrige o descarta escuchando.</p>
  {ir_cola}
</a>
{FLECHA_SVG}
<a class="etapa" href="/explorador?estado=confirmado">
  <span class="etapa-orden">05 · Biblioteca</span>
  <p class="etapa-num">{tot["confirmados"]}</p>
  <p class="etapa-label">Confirmados</p>
  <p class="etapa-desc">Ya son parte de la biblioteca curada del paisaje sonoro del Golfo.</p>
</a>
{FLECHA_SVG}
{etapa_vitrina}
</div>
<p class="nota-hipotesis">{badge_hipotesis()}
<span>Todos los sonidos llevan este badge: la identificación de especie (franca austral) es una
hipótesis de trabajo hasta que la valide un experto independiente (ICB / CENPAT).</span></p>"""

    # --- salud por campaña (R19) ---
    campanias = con.execute(
        """
        SELECT fuente,
               COUNT(*) AS total,
               SUM(estado = 'propuesto')   AS propuestos,
               SUM(estado = 'confirmado')  AS confirmados,
               SUM(estado = 'descartado')  AS descartados,
               SUM(estado = 'desconocido') AS desconocidos
        FROM segmento GROUP BY fuente ORDER BY fuente
        """
    ).fetchall()

    tarjetas = []
    for c in campanias:
        total = c["total"]
        pct = {clave: 100.0 * (c[col] or 0) / total for clave, col in (
            ("propuesto", "propuestos"),
            ("confirmado", "confirmados"),
            ("descartado", "descartados"),
            ("desconocido", "desconocidos"),
        )}

        alertas = []
        if pct["desconocido"] >= 15:
            alertas.append(f"{pct['desconocido']:.0f}% de segmentos desconocidos — tasa anómala")
        if pct["descartado"] >= 30:
            alertas.append(f"{pct['descartado']:.0f}% descartados — revisar calidad de la campaña")
        if pct["propuesto"] >= 70:
            alertas.append(f"{pct['propuesto']:.0f}% sin revisar — la campaña está casi toda pendiente")
        alerta_html = "".join(
            f'<div class="alerta"><strong>ALERTA</strong> · {e(a)}</div>' for a in alertas
        )

        barra = "".join(
            f'<span class="seg-{clave}" style="width:{pct[clave]:.1f}%" title="{ETIQUETA_ESTADO[clave]}: {c[col] or 0}"></span>'
            for clave, col in (
                ("confirmado", "confirmados"),
                ("propuesto", "propuestos"),
                ("desconocido", "desconocidos"),
                ("descartado", "descartados"),
            )
            if (c[col] or 0) > 0
        )
        leyenda = "".join(
            f'<span class="leyenda-estado"><i style="background:var(--{clave})"></i>'
            f'<span class="n">{c[col] or 0}</span> {clave}s</span>'
            for clave, col in (
                ("confirmado", "confirmados"),
                ("propuesto", "propuestos"),
                ("desconocido", "desconocidos"),
                ("descartado", "descartados"),
            )
        )
        tarjetas.append(f"""<section class="campania">
  <h3>{e(c["fuente"])}</h3>
  <p class="total">{total} <small>segmentos</small></p>
  <div class="barra-estados" role="img" aria-label="Distribución por estado">{barra}</div>
  <div class="estados">{leyenda}</div>
  {alerta_html}
</section>""")

    # --- actividad reciente (trazabilidad: quién, cuándo, qué decidió) ---
    veredictos = con.execute(
        """
        SELECT filename, tipo, tipo_corregido, estado, revisor, revisado_en
        FROM segmento WHERE revisor IS NOT NULL
        ORDER BY revisado_en DESC LIMIT 6
        """
    ).fetchall()

    if veredictos:
        filas = []
        for v in veredictos:
            if v["estado"] == "confirmado" and v["tipo_corregido"] and v["tipo_corregido"] != v["tipo"]:
                que = f'corrigió <strong>{e(v["tipo"])}</strong> → <strong>{e(v["tipo_corregido"])}</strong>'
            elif v["estado"] == "confirmado":
                que = f'confirmó <strong>{e(v["tipo_corregido"] or v["tipo"])}</strong>'
            elif v["estado"] == "descartado":
                que = f'descartó un <strong>{e(v["tipo"])}</strong> propuesto'
            else:
                que = f'marcó desconocido un <strong>{e(v["tipo"])}</strong> propuesto'
            filas.append(f"""<li>
  <span class="cuando">{e(fecha_linda(v["revisado_en"]))}</span>
  <span class="quien">{e(v["revisor"])}</span>
  <span>{que}</span>
  <span class="decision {e(v["estado"])}">{e(ETIQUETA_ESTADO.get(v["estado"], v["estado"]))}</span>
  <span class="archivo">{e(v["filename"])}</span>
</li>""")
        actividad = f'<ul class="actividad">{"".join(filas)}</ul>'
    else:
        actividad = """<div class="vacio">
  <p><strong>Todavía no hay veredictos humanos registrados.</strong></p>
  <p>Cuando el experto revise la cola, acá queda la traza: quién decidió qué, y cuándo.</p>
</div>"""

    cuerpo = f"""<h2>El viaje de un sonido</h2>
<p class="bajada">Del hidrófono a la biblioteca pública: la máquina detecta y propone,
el experto confirma con el oído. Este panel muestra dónde está parado cada sonido hoy.</p>
{funnel}
<h3 class="titulo-seccion">Salud por campaña</h3>
<div class="tarjetas-campania">{"".join(tarjetas)}</div>
<h3 class="titulo-seccion">Actividad reciente</h3>
{actividad}"""
    return pagina("Panel", "panel", cuerpo, pendientes=pendientes)


def vista_explorador(con: sqlite3.Connection, filtros: dict) -> str:
    pendientes = contar_pendientes(con)
    hay_catalogo = con.execute("SELECT COUNT(*) FROM segmento").fetchone()[0] > 0
    if not hay_catalogo:
        cuerpo = """<h2>Explorador</h2>
<div class="vacio">
  <p><strong>Todavía no hay nada en el catálogo.</strong></p>
  <p>Importá los datos con <code>python importar.py fixtures</code> y volvé a esta página.</p>
</div>"""
        return pagina("Explorador", "explorador", cuerpo, pendientes=pendientes)

    condiciones, valores = [], []
    for campo, columna in (("tipo", "tipo"), ("estado", "estado"), ("fuente", "fuente")):
        if filtros.get(campo):
            condiciones.append(f"{columna} = ?")
            valores.append(filtros[campo])
    donde = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""
    segmentos = con.execute(
        f"SELECT * FROM segmento {donde} ORDER BY fecha_hora_absoluta", valores
    ).fetchall()

    tipos = [r[0] for r in con.execute("SELECT DISTINCT tipo FROM segmento ORDER BY tipo")]
    fuentes = [r[0] for r in con.execute("SELECT DISTINCT fuente FROM segmento ORDER BY fuente")]

    def opciones(valores_posibles, elegido):
        out = ['<option value="">todos</option>']
        for v in valores_posibles:
            sel = " selected" if v == elegido else ""
            out.append(f'<option value="{e(v)}"{sel}>{e(v)}</option>')
        return "".join(out)

    activos = sum(1 for v in filtros.values() if v)
    badge_activos = (
        f'<span class="contador-filtros">{activos} filtro{"s" if activos != 1 else ""} activo{"s" if activos != 1 else ""}</span>'
        if activos
        else ""
    )
    quitar = '<a href="/explorador">Quitar filtros</a>' if activos else ""
    formulario = f"""<form class="filtros" method="get" action="/explorador">
  <div><label for="f-tipo">Tipo</label><select id="f-tipo" name="tipo">{opciones(tipos, filtros.get("tipo"))}</select></div>
  <div><label for="f-estado">Estado</label><select id="f-estado" name="estado">{opciones(list(base.ESTADOS), filtros.get("estado"))}</select></div>
  <div><label for="f-fuente">Fuente</label><select id="f-fuente" name="fuente">{opciones(fuentes, filtros.get("fuente"))}</select></div>
  <button class="boton" type="submit">Filtrar</button>
  {badge_activos}
  {quitar}
</form>"""

    if not segmentos:
        cuerpo = f"""<h2>Explorador</h2>
{formulario}
<div class="vacio">
  <p><strong>Ningún segmento coincide con esos filtros.</strong></p>
  <p>Probá aflojar alguno, o <a href="/explorador">quitá todos los filtros</a> para ver el catálogo completo.</p>
</div>"""
    else:
        tarjetas = "".join(tarjeta_segmento(s) for s in segmentos)
        cuerpo = f"""<h2>Explorador <small style="color:var(--tenue);font-size:0.9rem;font-weight:500" class="num">
{len(segmentos)} segmentos</small></h2>
<p class="bajada">Todo el catálogo, con su estado de revisión. Los filtros combinan entre sí.</p>
{formulario}
<div class="grilla">{tarjetas}</div>"""
    return pagina("Explorador", "explorador", cuerpo, pendientes=pendientes)


def quien_propuso(s: sqlite3.Row) -> tuple[str, float | None]:
    """(nombre en criollo del motor que propuso el segmento, confianza 0-1).

    `tipo_propuesto_por` / `confianza` los escribe la ingesta (WCH-471);
    para los históricos de la sesión exploratoria la confianza es NULL.
    """
    claves = s.keys()
    por = s["tipo_propuesto_por"] if "tipo_propuesto_por" in claves else None
    confianza = s["confianza"] if "confianza" in claves else None
    if por and por.startswith("clasificador-v"):
        return f"El clasificador {por.removeprefix('clasificador-')}", confianza
    if por == "vecinos":
        return "El voto de vecinos por embedding", confianza
    return "La máquina", confianza


def motivo_en_cola(s: sqlite3.Row) -> str:
    """Explica en criollo por qué este segmento espera veredicto humano."""
    dur = duracion_clip(s["clip_path"])
    quien, confianza = quien_propuso(s)
    partes = [f"{quien} lo propuso como <strong>{e(s['tipo'])}</strong>"]
    if confianza is not None:
        partes.append(f" con <span class='num'>{confianza * 100:.0f}%</span> de confianza")
    if "dudoso" in (s["filename"] or ""):
        partes.append(" pero lo marcó <strong>dudoso</strong>")
    frase = "".join(partes) + "."
    if dur is not None:
        dur_txt = (f"{dur:.2f}" if dur < 0.3 else f"{dur:.1f}").replace(".", ",")
        if dur < 0.3:
            frase += (
                f" Dura <span class='num'>{dur_txt}&nbsp;s</span> — por debajo de 0,3 s el índice"
                " armónico no es confiable, así que no puede confirmarlo sola."
            )
        else:
            frase += (
                f" Dura <span class='num'>{dur_txt}&nbsp;s</span>, pero no alcanzó la confianza"
                " para confirmarlo sin ayuda."
            )
    frase += " Tu oído decide."
    return f'<div class="motivo"><span class="etiqueta">Por qué está en la cola</span>{frase}</div>'


JS_COLA = """<script>
(function () {
  var audio = document.getElementById("clip-principal");
  if (audio) { try { audio.focus(); } catch (err) {} }

  // Racha de la sesión (sessionStorage: sobrevive a la navegación, no al cierre).
  var racha = 0;
  try { racha = parseInt(sessionStorage.getItem("ecos-racha") || "0", 10) || 0; } catch (err) {}
  var elRacha = document.getElementById("racha-sesion");
  if (elRacha && racha > 0) {
    elRacha.textContent = "Racha de la sesión: " + racha + (racha === 1 ? " veredicto" : " veredictos");
  }
  var elRachaLogro = document.getElementById("racha-logro");
  if (elRachaLogro && racha > 0) {
    elRachaLogro.textContent = "Esta sesión cerraste " + racha + (racha === 1 ? " veredicto." : " veredictos.");
    try { sessionStorage.removeItem("ecos-racha"); } catch (err) {}
  }
  document.querySelectorAll("form[data-veredicto]").forEach(function (f) {
    f.addEventListener("submit", function () {
      try { sessionStorage.setItem("ecos-racha", String(racha + 1)); } catch (err) {}
    });
  });

  function enviar(accion) {
    var f = document.querySelector('form[data-veredicto="' + accion + '"]');
    if (f) { f.requestSubmit ? f.requestSubmit() : f.submit(); }
  }

  document.addEventListener("keydown", function (ev) {
    var t = ev.target, tag = t && t.tagName;
    if (tag === "SELECT" || tag === "INPUT" || tag === "TEXTAREA" || tag === "AUDIO" || tag === "BUTTON") return;
    if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
    var k = ev.key;
    if (k === " ") {
      if (audio) { ev.preventDefault(); audio.paused ? audio.play() : audio.pause(); }
    } else if (k === "c" || k === "C") { enviar("confirmar"); }
    else if (k === "x" || k === "X") { enviar("descartar"); }
    else if (k === "d" || k === "D") { enviar("desconocido"); }
    else if (k === "ArrowRight") { var s = document.body.getAttribute("data-sig"); if (s) location.href = s; }
    else if (k === "ArrowLeft") { var p = document.body.getAttribute("data-ant"); if (p) location.href = p; }
  });
})();
</script>"""


def vista_cola(con: sqlite3.Connection, pos: int = 0) -> str:
    hay_catalogo = con.execute("SELECT COUNT(*) FROM segmento").fetchone()[0] > 0
    if not hay_catalogo:
        cuerpo = """<h2>Cola de revisión</h2>
<div class="vacio">
  <p><strong>Todavía no hay nada en el catálogo.</strong></p>
  <p>Importá los datos con <code>python importar.py fixtures</code> y volvé a esta página.</p>
</div>"""
        return pagina("Cola de revisión", "cola", cuerpo)

    filas = con.execute(
        "SELECT * FROM segmento WHERE estado = 'propuesto' ORDER BY fecha_hora_absoluta"
    ).fetchall()
    pendientes = len(filas)
    revisados = con.execute(
        "SELECT COUNT(*) FROM segmento WHERE revisor IS NOT NULL"
    ).fetchone()[0]
    total_cola = pendientes + revisados

    if pendientes == 0:
        # EA1: cola en cero = logro, con el resumen del día como trofeo.
        hoy = con.execute(
            """
            SELECT SUM(estado = 'confirmado' AND tipo_corregido IS NULL) AS confirmados,
                   SUM(estado = 'confirmado' AND tipo_corregido IS NOT NULL) AS corregidos,
                   SUM(estado = 'descartado')  AS descartados,
                   SUM(estado = 'desconocido') AS desconocidos
            FROM segmento
            WHERE revisor IS NOT NULL AND date(revisado_en) = date('now', 'localtime')
            """
        ).fetchone()
        chips_hoy = "".join(
            f'<span class="chip {clase}">{n} {texto}</span>'
            for clase, n, texto in (
                ("confirmado", hoy["confirmados"] or 0, "confirmados"),
                ("confirmado", hoy["corregidos"] or 0, "corregidos"),
                ("descartado", hoy["descartados"] or 0, "descartados"),
                ("desconocido", hoy["desconocidos"] or 0, "desconocidos"),
            )
            if n
        )
        resumen = (
            f'<div class="resumen">{chips_hoy}</div>' if chips_hoy else ""
        )
        cuerpo = f"""<div class="logro">
  {TILDE_SVG}
  <h2>Cola en cero</h2>
  <p>Los <span class="num">{revisados}</span> sonidos que la máquina propuso ya tienen veredicto del experto. Buen trabajo.</p>
  <p id="racha-logro"></p>
  {resumen}
  <p style="margin-top:1.6rem">
    <a class="boton primario" href="/">Volver al panel</a>
    <a class="boton" href="/explorador?estado=confirmado">Ver los confirmados</a>
  </p>
</div>"""
        return pagina("Cola de revisión", "cola", cuerpo, extra=JS_COLA)

    pos = max(0, min(pos, pendientes - 1))
    s = filas[pos]
    tipo_propuesto = s["tipo"]

    # --- progreso ---
    pct = 100.0 * revisados / total_cola if total_cola else 0
    ant = f"/cola?pos={pos - 1}" if pos > 0 else ""
    sig = f"/cola?pos={pos + 1}" if pos + 1 < pendientes else ""
    progreso = f"""<div class="cola-progreso">
  <div class="fila">
    <span class="donde">Revisando <span class="num">{revisados + pos + 1}</span> de <span class="num">{total_cola}</span></span>
    <span class="racha" id="racha-sesion"></span>
    <span class="hechos"><span class="num">{revisados}</span> con veredicto · <span class="num">{pendientes}</span> pendientes</span>
  </div>
  <div class="barra-progreso" role="progressbar" aria-valuenow="{revisados}" aria-valuemin="0"
       aria-valuemax="{total_cola}" aria-label="Progreso de la cola de revisión">
    <span style="width:{pct:.0f}%"></span>
  </div>
</div>"""

    # --- clip principal (jerarquía EA3: espectrograma+play, veredicto, metadata) ---
    espectro = (
        f'<div class="marco-espectro"><img src="/media/espectro/{e(s["filename"])}" '
        f'alt="Espectrograma de {e(s["filename"])}"></div>'
        if s["espectrograma_path"]
        else '<div class="vacio">sin espectrograma para este segmento</div>'
    )
    audio = (
        f'<audio id="clip-principal" controls preload="auto" src="/media/clip/{e(s["filename"])}"></audio>'
        if s["clip_path"]
        else '<p class="meta">clip no disponible</p>'
    )
    opciones_tipo = "".join(
        f'<option value="{e(t)}"{" selected" if t == tipo_propuesto else ""}>{e(t)}</option>'
        for t in TIPOS_CORREGIBLES
    )

    def form_veredicto(accion: str, boton: str, ayuda: str, primario: bool = False, tecla: str = "") -> str:
        clase = "boton primario" if primario else "boton"
        kbd = f" <kbd>{tecla}</kbd>" if tecla else ""
        return f"""<div class="veredicto">
  <form method="post" action="/cola/veredicto" data-veredicto="{accion}">
    <input type="hidden" name="filename" value="{e(s["filename"])}">
    <input type="hidden" name="accion" value="{accion}">
    <input type="hidden" name="pos" value="{pos}">
    <button class="{clase}" type="submit">{boton}{kbd}</button>
  </form>
  <span class="ayuda">{ayuda}</span>
</div>"""

    veredictos = f"""<div class="veredictos">
{form_veredicto("confirmar", f"Confirmar {e(tipo_propuesto)}", "Es lo que dice la máquina", primario=True, tecla="C")}
<div class="veredicto">
  <form method="post" action="/cola/veredicto" data-veredicto="corregir">
    <input type="hidden" name="filename" value="{e(s["filename"])}">
    <input type="hidden" name="accion" value="corregir">
    <input type="hidden" name="pos" value="{pos}">
    <select name="tipo_corregido" aria-label="Tipo corregido">{opciones_tipo}</select>
    <button class="boton" type="submit">Corregir tipo</button>
  </form>
  <span class="ayuda">Es un sonido real, pero de otro tipo</span>
</div>
{form_veredicto("descartar", "Descartar", "No es un sonido de interés (ruido, agua, motor)", tecla="X")}
{form_veredicto("desconocido", "Desconocido", "Es algo real, pero no sé qué", tecla="D")}
</div>"""

    atajos = """<p class="atajos" aria-label="Atajos de teclado">
  <span><kbd>C</kbd> confirmar</span>
  <span><kbd>X</kbd> descartar</span>
  <span><kbd>D</kbd> desconocido</span>
  <span><kbd>espacio</kbd> play / pausa</span>
  <span><kbd>←</kbd><kbd>→</kbd> moverse en la cola</span>
</p>"""

    metadata = f"""<div class="metadata-cola">
  <div class="fila-badges" style="margin-bottom:0.6rem">
    <span class="badge-tipo">{e(tipo_propuesto)}</span>
    {badge_hipotesis()}
    {boton_similares(s["filename"])}
  </div>
  <dl>
    <dt>Archivo</dt><dd>{e(s["filename"])}</dd>
    <dt>Fuente</dt><dd>{e(s["fuente"])}</dd>
    <dt>Fecha/hora absoluta</dt><dd>{e(s["fecha_hora_absoluta"] or "—")}</dd>
    <dt>Inicio de grabación</dt><dd>{e(s["inicio_grabacion"] or "—")}</dd>
    <dt>Offset en la grabación</dt><dd>{e(f"{s['offset_s']:.1f} s" if s["offset_s"] is not None else "—")}</dd>
  </dl>
</div>"""

    # --- referencias: así suenan los confirmados de este tipo ---
    ejemplares = con.execute(
        """
        SELECT * FROM segmento
        WHERE estado = 'confirmado' AND COALESCE(tipo_corregido, tipo) = ? AND filename != ?
        ORDER BY (revisor IS NOT NULL) DESC, fecha_hora_absoluta LIMIT 3
        """,
        (tipo_propuesto, s["filename"]),
    ).fetchall()
    if ejemplares:
        cuantos = con.execute(
            "SELECT COUNT(*) FROM segmento WHERE estado = 'confirmado' AND COALESCE(tipo_corregido, tipo) = ?",
            (tipo_propuesto,),
        ).fetchone()[0]
        panel_tipo = f"""<section class="panel-referencia">
  <h3>Así suenan los <span class="num">{e(tipo_propuesto)}</span> confirmados</h3>
  <p class="sub">{cuantos} en la biblioteca — compará de oído antes de decidir.</p>
  {"".join(mini_clip(x) for x in ejemplares)}
  <a class="ver-mas" href="/explorador?tipo={e(tipo_propuesto)}&estado=confirmado">Ver todos los {e(tipo_propuesto)} →</a>
</section>"""
    else:
        panel_tipo = f"""<section class="panel-referencia">
  <h3>Sin ejemplares confirmados de <span class="num">{e(tipo_propuesto)}</span></h3>
  <p class="sub">Todavía no hay ninguno en la biblioteca para comparar. Este veredicto puede ser el primero.</p>
</section>"""

    # --- referencias: lo más parecido según Perch ---
    panel_similares = ""
    if embeddings.hay_indice(con):
        parecidos = embeddings.similares(con, s["filename"], n=3)
        if parecidos:
            minis = []
            for otro, score in parecidos:
                fila = con.execute("SELECT * FROM segmento WHERE filename = ?", (otro,)).fetchone()
                if fila:
                    minis.append(mini_clip(fila, score=score))
            panel_similares = f"""<section class="panel-referencia">
  <h3>Lo más parecido según Perch</h3>
  <p class="sub">Vecinos por embedding en todo el catálogo — sin importar la etiqueta.</p>
  {"".join(minis)}
  <a class="ver-mas" href="/similares/{e(s["filename"])}">Ver el top 10 completo →</a>
</section>"""

    cuerpo = f"""{progreso}
{motivo_en_cola(s)}
<div class="cola-grid">
  <section class="heroe">
    {espectro}
    {audio}
    {veredictos}
    {atajos}
    {metadata}
  </section>
  <aside class="referencias" aria-label="Material de referencia para comparar">
    {panel_tipo}
    {panel_similares}
  </aside>
</div>"""
    html_pagina = pagina("Cola de revisión", "cola", cuerpo, pendientes=pendientes, extra=JS_COLA)
    # Los atajos ← → navegan la cola sin emitir veredicto.
    atributos = []
    if ant:
        atributos.append(f'data-ant="{ant}"')
    if sig:
        atributos.append(f'data-sig="{sig}"')
    if atributos:
        html_pagina = html_pagina.replace("<body>", f"<body {' '.join(atributos)}>", 1)
    return html_pagina


def vista_similares(con: sqlite3.Connection, filename: str) -> str:
    pendientes = contar_pendientes(con)
    s = con.execute("SELECT * FROM segmento WHERE filename = ?", (filename,)).fetchone()
    if not s:
        cuerpo = f"""<h2>Búsqueda inversa</h2>
<div class="vacio">
  <p><strong>Ese segmento no está en el catálogo.</strong></p>
  <p><code>{e(filename)}</code> — <a href="/explorador">volver al explorador</a></p>
</div>"""
        return pagina("Búsqueda inversa", "explorador", cuerpo, pendientes=pendientes)

    # Estado vacío como feature (EA1): sin índice, la vista te dice qué correr.
    if not embeddings.hay_indice(con):
        cuerpo = """<h2>Búsqueda inversa</h2>
<div class="vacio">
  <p><strong>Todavía no hay índice de embeddings.</strong></p>
  <p>Generalo con <code>python indexar.py</code> y volvé a esta página:
  cada clip del catálogo queda vectorizado y esta vista te muestra los que suenan parecido.</p>
</div>"""
        return pagina("Búsqueda inversa", "explorador", cuerpo, pendientes=pendientes)

    resultados = embeddings.similares(con, filename, n=10)
    if resultados is None:
        cuerpo = """<h2>Búsqueda inversa</h2>
<div class="vacio">
  <p><strong>Este clip todavía no está indexado.</strong></p>
  <p>Corré <code>python indexar.py</code> para ponerlo al día
  (indexa solo lo que falta) y volvé a esta página.</p>
</div>"""
        return pagina("Búsqueda inversa", "explorador", cuerpo, pendientes=pendientes)

    tipo = s["tipo_corregido"] or s["tipo"]
    espectro = (
        f'<div class="marco-espectro"><img src="/media/espectro/{e(filename)}" '
        f'alt="Espectrograma de {e(filename)}"></div>'
        if s["espectrograma_path"]
        else '<div class="vacio">sin espectrograma para este segmento</div>'
    )
    audio = (
        f'<audio controls preload="auto" src="/media/clip/{e(filename)}"></audio>'
        if s["clip_path"]
        else '<p class="meta">clip no disponible</p>'
    )

    tarjetas = []
    for otro, score in resultados:
        fila = con.execute("SELECT * FROM segmento WHERE filename = ?", (otro,)).fetchone()
        if fila:
            tarjetas.append(tarjeta_segmento(fila, score=score))

    cuerpo = f"""<h2>Suenan parecido a este clip</h2>
<p class="bajada">Vecinos más cercanos por embedding (similitud coseno) contra todo el catálogo indexado.</p>
<div class="heroe">
  {espectro}
  {audio}
  <div class="fila-badges" style="margin-top:0.9rem">
    <span class="badge-tipo">{e(tipo)}</span>
    {badge_hipotesis()}
    <span class="chip {e(s["estado"])}">{e(ETIQUETA_ESTADO.get(s["estado"], s["estado"]))}</span>
  </div>
  <p class="meta">{e(filename)} · {e(s["fuente"])} · {e(fecha_linda(s["fecha_hora_absoluta"]))}</p>
</div>
<h3 class="titulo-seccion">Top {len(tarjetas)} por similitud</h3>
<div class="grilla">{"".join(tarjetas)}</div>"""
    return pagina("Búsqueda inversa", "explorador", cuerpo, pendientes=pendientes)


# ---------- servidor ----------


class Manejador(BaseHTTPRequestHandler):
    ruta_db: Path = base.RUTA_DB

    def _responder(self, contenido: str, codigo: int = 200) -> None:
        datos = contenido.encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def _redirigir(self, destino: str) -> None:
        self.send_response(303)
        self.send_header("Location", destino)
        self.end_headers()

    def _servir_media(self, con: sqlite3.Connection, clase: str, filename: str) -> None:
        columna = "clip_path" if clase == "clip" else "espectrograma_path"
        fila = con.execute(
            f"SELECT {columna} AS ruta FROM segmento WHERE filename = ?", (filename,)
        ).fetchone()
        if not fila or not fila["ruta"] or not Path(fila["ruta"]).exists():
            self._responder("<h1>No encontrado</h1>", 404)
            return
        datos = Path(fila["ruta"]).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav" if clase == "clip" else "image/png")
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def do_GET(self) -> None:  # noqa: N802 (nombre que exige http.server)
        url = urlparse(self.path)
        con = base.conectar(self.ruta_db)
        try:
            if url.path == "/":
                self._responder(vista_panel(con))
            elif url.path == "/explorador":
                q = parse_qs(url.query)
                filtros = {k: q.get(k, [""])[0] for k in ("tipo", "estado", "fuente")}
                self._responder(vista_explorador(con, filtros))
            elif url.path == "/cola":
                q = parse_qs(url.query)
                try:
                    pos = int(q.get("pos", ["0"])[0])
                except ValueError:
                    pos = 0
                self._responder(vista_cola(con, pos))
            elif url.path.startswith("/similares/"):
                self._responder(vista_similares(con, url.path.removeprefix("/similares/")))
            elif url.path.startswith("/media/clip/"):
                self._servir_media(con, "clip", url.path.removeprefix("/media/clip/"))
            elif url.path.startswith("/media/espectro/"):
                self._servir_media(con, "espectro", url.path.removeprefix("/media/espectro/"))
            else:
                self._responder("<h1>404 — esa página no existe</h1>", 404)
        finally:
            con.close()

    def do_POST(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        if url.path != "/cola/veredicto":
            self._responder("<h1>404</h1>", 404)
            return
        largo = int(self.headers.get("Content-Length", 0))
        datos = parse_qs(self.rfile.read(largo).decode("utf-8"))
        filename = datos.get("filename", [""])[0]
        accion = datos.get("accion", [""])[0]
        tipo_corregido = datos.get("tipo_corregido", [None])[0]
        try:
            pos = int(datos.get("pos", ["0"])[0])
        except ValueError:
            pos = 0

        con = base.conectar(self.ruta_db)
        try:
            base.registrar_veredicto(con, filename, accion, tipo_corregido, revisor="local")
        except ValueError as err:
            self._responder(f"<h1>Veredicto inválido</h1><p>{e(err)}</p>", 400)
            return
        finally:
            con.close()
        # Auto-avance: al salir este segmento de la cola, la misma posición
        # ya muestra el siguiente pendiente (la vista clampa si era el último).
        self._redirigir(f"/cola?pos={pos}")

    def log_message(self, formato: str, *args) -> None:
        pass  # sin ruido en consola


def correr(puerto: int = PUERTO, ruta_db: Path | str = base.RUTA_DB) -> None:
    Manejador.ruta_db = Path(ruta_db)
    servidor = ThreadingHTTPServer(("127.0.0.1", puerto), Manejador)
    print(f"Tablero de Ecos del Golfo en http://localhost:{puerto}  (Ctrl+C para frenar)")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nTablero frenado.")


if __name__ == "__main__":
    puerto = int(sys.argv[1]) if len(sys.argv) > 1 else PUERTO
    correr(puerto)
