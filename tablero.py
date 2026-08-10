"""Tablero local de Ecos del Golfo — prototipo Wow 1 (WCH-467).

Servidor web local sobre stdlib http.server, HTML server-rendered y CSS
propio inline. Sin frameworks JS ni CDNs: todo corre offline. Lee y escribe
exclusivamente sobre ecos.db (única fuente de verdad, D10).

Uso: python tablero.py  →  http://localhost:8477
"""

from __future__ import annotations

import html
import sqlite3
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import base
import embeddings

PUERTO = 8477

ETIQUETA_ESTADO = {
    "propuesto": "PROPUESTO",
    "confirmado": "CONFIRMADO",
    "descartado": "DESCARTADO",
    "desconocido": "DESCONOCIDO",
}

TIPOS_CORREGIBLES = [t for t in base.TIPOS if t not in ("revisar_muy_cortos", "posible_ruido_agua")]

ESTILO = """
:root {
  --fondo: #081120; --panel: #0d1a2e; --panel-2: #122238; --borde: #1d3150;
  --texto: #d7e3f4; --tenue: #7d93b2; --acento: #f0a35e; --acento-fuerte: #e8863a;
  --confirmado: #4fc596; --propuesto: #f0c95e; --descartado: #d97878; --desconocido: #8fa3c4;
  --hipotesis: #e8863a;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--fondo); color: var(--texto);
  font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}
a { color: var(--acento); text-decoration: none; }
a:hover { text-decoration: underline; }
header {
  display: flex; align-items: baseline; gap: 1.6rem; padding: 1rem 2rem;
  border-bottom: 1px solid var(--borde); background: var(--panel);
}
header h1 { font-size: 1.05rem; font-weight: 600; letter-spacing: 0.02em; }
header h1 span { color: var(--acento); }
header nav { display: flex; gap: 1.1rem; font-size: 0.9rem; }
header nav a.activo { color: var(--texto); border-bottom: 2px solid var(--acento); padding-bottom: 2px; }
main { max-width: 1080px; margin: 0 auto; padding: 1.8rem 2rem 4rem; }
h2 { font-size: 1.25rem; font-weight: 600; margin-bottom: 1.1rem; }
h3 { font-size: 1rem; font-weight: 600; }
.tarjetas-campania { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 1.1rem; }
.campania {
  background: var(--panel); border: 1px solid var(--borde); border-radius: 6px; padding: 1.1rem 1.25rem;
}
.campania .total { font-size: 2rem; font-weight: 700; }
.campania .total small { font-size: 0.85rem; font-weight: 400; color: var(--tenue); }
.estados { display: flex; flex-wrap: wrap; gap: 0.45rem; margin: 0.8rem 0; }
.chip {
  font-size: 0.74rem; font-weight: 600; letter-spacing: 0.04em; padding: 0.18rem 0.55rem;
  border-radius: 4px; border: 1px solid;
}
.chip.propuesto   { color: var(--propuesto);   border-color: var(--propuesto); }
.chip.confirmado  { color: var(--confirmado);  border-color: var(--confirmado); }
.chip.descartado  { color: var(--descartado);  border-color: var(--descartado); }
.chip.desconocido { color: var(--desconocido); border-color: var(--desconocido); }
.pct-desconocidos { color: var(--tenue); font-size: 0.85rem; }
.alerta {
  margin-top: 0.8rem; padding: 0.55rem 0.8rem; border-radius: 4px; font-size: 0.85rem;
  background: rgba(232, 134, 58, 0.12); border: 1px solid var(--acento-fuerte); color: var(--acento);
}
.accesos { margin-top: 2rem; display: flex; gap: 1rem; }
.boton {
  display: inline-block; padding: 0.55rem 1.2rem; border-radius: 5px; font-size: 0.92rem;
  font-weight: 600; cursor: pointer; border: 1px solid var(--borde);
  background: var(--panel-2); color: var(--texto);
}
.boton:hover { border-color: var(--acento); text-decoration: none; }
.boton.primario { background: var(--acento-fuerte); border-color: var(--acento-fuerte); color: #14100a; }
.boton.primario:hover { background: var(--acento); }
form.filtros { display: flex; flex-wrap: wrap; gap: 0.7rem; align-items: end; margin-bottom: 1.4rem; }
form.filtros label { display: block; font-size: 0.75rem; color: var(--tenue); margin-bottom: 0.2rem; }
select, form.filtros a { font-size: 0.88rem; }
select {
  background: var(--panel-2); color: var(--texto); border: 1px solid var(--borde);
  border-radius: 5px; padding: 0.4rem 0.6rem;
}
.grilla { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1.1rem; }
.segmento {
  background: var(--panel); border: 1px solid var(--borde); border-radius: 6px; overflow: hidden;
}
.segmento img { width: 100%; display: block; background: #0a1524; }
.segmento .cuerpo { padding: 0.7rem 0.9rem 0.9rem; }
.segmento audio { width: 100%; height: 32px; margin: 0.5rem 0; }
.fila-badges { display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: center; }
.badge-hipotesis {
  font-size: 0.7rem; font-weight: 700; letter-spacing: 0.08em; padding: 0.16rem 0.5rem;
  border-radius: 4px; background: var(--hipotesis); color: #14100a;
}
.badge-tipo {
  font-size: 0.74rem; font-weight: 600; padding: 0.16rem 0.5rem; border-radius: 4px;
  background: var(--panel-2); border: 1px solid var(--borde); color: var(--texto);
}
.meta { color: var(--tenue); font-size: 0.8rem; margin-top: 0.45rem; }
.vacio {
  background: var(--panel); border: 1px dashed var(--borde); border-radius: 6px;
  padding: 2.2rem; text-align: center; color: var(--tenue);
}
.vacio strong { color: var(--texto); }
.vacio code { background: var(--panel-2); padding: 0.1rem 0.4rem; border-radius: 3px; }
.heroe { background: var(--panel); border: 1px solid var(--borde); border-radius: 6px; padding: 1.4rem; }
.heroe img { width: 100%; max-height: 420px; object-fit: contain; background: #0a1524; border-radius: 4px; }
.heroe audio { width: 100%; margin-top: 0.9rem; }
.veredictos { display: flex; flex-wrap: wrap; gap: 0.7rem; margin-top: 1.3rem; align-items: center; }
.veredictos form { display: flex; gap: 0.5rem; align-items: center; }
.metadata-cola {
  margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid var(--borde);
  color: var(--tenue); font-size: 0.8rem;
}
.metadata-cola dl { display: grid; grid-template-columns: auto 1fr; gap: 0.15rem 1rem; }
.metadata-cola dt { font-weight: 600; }
.contador-cola { color: var(--tenue); font-size: 0.88rem; margin-bottom: 0.9rem; }
.logro { text-align: center; padding: 4rem 2rem; }
.logro .emoji { font-size: 3rem; }
.logro h2 { margin-top: 0.8rem; }
.logro p { color: var(--tenue); margin-top: 0.4rem; }
.boton-similares {
  display: inline-block; margin-top: 0.55rem; font-size: 0.8rem; padding: 0.28rem 0.7rem;
  border: 1px solid var(--borde); border-radius: 5px; background: var(--panel-2); color: var(--texto);
}
.boton-similares:hover { border-color: var(--acento); text-decoration: none; }
.badge-score {
  font-size: 0.78rem; font-weight: 700; padding: 0.16rem 0.5rem; border-radius: 4px;
  background: var(--acento-fuerte); color: #14100a;
}
"""


def e(texto) -> str:
    return html.escape(str(texto if texto is not None else ""))


def pagina(titulo: str, activo: str, cuerpo: str) -> str:
    def nav(ruta, nombre, clave):
        clase = ' class="activo"' if activo == clave else ""
        return f'<a href="{ruta}"{clase}>{nombre}</a>'

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(titulo)} — Ecos del Golfo</title>
<style>{ESTILO}</style>
</head>
<body>
<header>
  <h1>Ecos <span>del Golfo</span></h1>
  <nav>
    {nav("/", "Salud", "salud")}
    {nav("/explorador", "Explorador", "explorador")}
    {nav("/cola", "Cola de revisión", "cola")}
  </nav>
</header>
<main>
{cuerpo}
</main>
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
        'title="Buscar clips que suenan parecido">🔍 Buscar parecidos</a>'
    )


def tarjeta_segmento(s: sqlite3.Row, score: float | None = None) -> str:
    tipo = s["tipo_corregido"] or s["tipo"]
    estado = s["estado"]
    espectro = (
        f'<img src="/media/espectro/{e(s["filename"])}" alt="Espectrograma de {e(s["filename"])}">'
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
    <p class="meta">{e(s["fecha_hora_absoluta"] or "sin fecha")} · {e(s["fuente"])}</p>
    {boton_similares(s["filename"])}
  </div>
</article>"""


# ---------- vistas ----------


def vista_salud(con: sqlite3.Connection) -> str:
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

    if not campanias:
        cuerpo = """<h2>Salud del catálogo</h2>
<div class="vacio">
  <p><strong>El catálogo está vacío.</strong></p>
  <p>Generá los fixtures y cargalos así:</p>
  <p><code>python generar_fixtures.py</code> y después <code>python importar.py fixtures</code></p>
</div>"""
        return pagina("Salud", "salud", cuerpo)

    tarjetas = []
    for c in campanias:
        total = c["total"]
        pct_desc = 100.0 * c["desconocidos"] / total
        pct_descartado = 100.0 * c["descartados"] / total
        pct_pendiente = 100.0 * c["propuestos"] / total

        alertas = []
        if pct_desc >= 15:
            alertas.append(f"{pct_desc:.0f}% de segmentos desconocidos — tasa anómala")
        if pct_descartado >= 30:
            alertas.append(f"{pct_descartado:.0f}% descartados — revisar calidad de la campaña")
        if pct_pendiente >= 70:
            alertas.append(f"{pct_pendiente:.0f}% sin revisar — la campaña está casi toda pendiente")
        alerta_html = "".join(f'<div class="alerta">⚠ {e(a)}</div>' for a in alertas)

        chips = "".join(
            f'<span class="chip {clave}">{ETIQUETA_ESTADO[clave]} · {c[col]}</span>'
            for clave, col in (
                ("propuesto", "propuestos"),
                ("confirmado", "confirmados"),
                ("descartado", "descartados"),
                ("desconocido", "desconocidos"),
            )
        )
        tarjetas.append(f"""<section class="campania">
  <h3>{e(c["fuente"])}</h3>
  <p class="total">{total} <small>segmentos</small></p>
  <div class="estados">{chips}</div>
  <p class="pct-desconocidos">{pct_desc:.1f}% desconocidos</p>
  {alerta_html}
</section>""")

    pendientes = con.execute(
        "SELECT COUNT(*) FROM segmento WHERE estado = 'propuesto'"
    ).fetchone()[0]

    cuerpo = f"""<h2>Salud del catálogo</h2>
<div class="tarjetas-campania">{"".join(tarjetas)}</div>
<div class="accesos">
  <a class="boton primario" href="/cola">Ir a la cola de revisión ({pendientes} pendientes)</a>
  <a class="boton" href="/explorador">Abrir el explorador</a>
</div>"""
    return pagina("Salud", "salud", cuerpo)


def vista_explorador(con: sqlite3.Connection, filtros: dict) -> str:
    hay_catalogo = con.execute("SELECT COUNT(*) FROM segmento").fetchone()[0] > 0
    if not hay_catalogo:
        cuerpo = """<h2>Explorador</h2>
<div class="vacio">
  <p><strong>Todavía no hay nada en el catálogo.</strong></p>
  <p>Importá los datos con <code>python importar.py fixtures</code> y volvé a esta página.</p>
</div>"""
        return pagina("Explorador", "explorador", cuerpo)

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

    formulario = f"""<form class="filtros" method="get" action="/explorador">
  <div><label>Tipo</label><select name="tipo">{opciones(tipos, filtros.get("tipo"))}</select></div>
  <div><label>Estado</label><select name="estado">{opciones(list(base.ESTADOS), filtros.get("estado"))}</select></div>
  <div><label>Fuente</label><select name="fuente">{opciones(fuentes, filtros.get("fuente"))}</select></div>
  <button class="boton" type="submit">Filtrar</button>
  <a href="/explorador">Quitar filtros</a>
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
        cuerpo = f"""<h2>Explorador <small style="color:var(--tenue);font-size:0.85rem;font-weight:400">
{len(segmentos)} segmentos</small></h2>
{formulario}
<div class="grilla">{tarjetas}</div>"""
    return pagina("Explorador", "explorador", cuerpo)


def vista_cola(con: sqlite3.Connection) -> str:
    pendientes = con.execute(
        "SELECT COUNT(*) FROM segmento WHERE estado = 'propuesto'"
    ).fetchone()[0]

    if pendientes == 0:
        cuerpo = """<div class="logro">
  <div class="emoji">🎉</div>
  <h2>Todo revisado</h2>
  <p>No queda nada pendiente en la cola. Buen trabajo.</p>
  <p style="margin-top:1.2rem"><a class="boton" href="/explorador">Ver el catálogo</a></p>
</div>"""
        return pagina("Cola de revisión", "cola", cuerpo)

    s = con.execute(
        "SELECT * FROM segmento WHERE estado = 'propuesto' ORDER BY fecha_hora_absoluta LIMIT 1"
    ).fetchone()

    espectro = (
        f'<img src="/media/espectro/{e(s["filename"])}" alt="Espectrograma de {e(s["filename"])}">'
        if s["espectrograma_path"]
        else '<div class="vacio">sin espectrograma para este segmento</div>'
    )
    audio = (
        f'<audio controls preload="auto" src="/media/clip/{e(s["filename"])}"></audio>'
        if s["clip_path"]
        else '<p class="meta">clip no disponible</p>'
    )
    opciones_tipo = "".join(
        f'<option value="{e(t)}"{" selected" if t == s["tipo"] else ""}>{e(t)}</option>'
        for t in TIPOS_CORREGIBLES
    )

    # Jerarquía EA3: 1) espectrograma + play, 2) veredicto, 3) metadata chica.
    cuerpo = f"""<p class="contador-cola">Cola de revisión · quedan <strong>{pendientes}</strong> por revisar</p>
<div class="heroe">
  {espectro}
  {audio}

  <div class="veredictos">
    <form method="post" action="/cola/veredicto">
      <input type="hidden" name="filename" value="{e(s["filename"])}">
      <input type="hidden" name="accion" value="confirmar">
      <button class="boton primario" type="submit">Confirmar {e(s["tipo"])}</button>
    </form>
    <form method="post" action="/cola/veredicto">
      <input type="hidden" name="filename" value="{e(s["filename"])}">
      <input type="hidden" name="accion" value="corregir">
      <select name="tipo_corregido">{opciones_tipo}</select>
      <button class="boton" type="submit">Corregir tipo</button>
    </form>
    <form method="post" action="/cola/veredicto">
      <input type="hidden" name="filename" value="{e(s["filename"])}">
      <input type="hidden" name="accion" value="descartar">
      <button class="boton" type="submit">Descartar</button>
    </form>
    <form method="post" action="/cola/veredicto">
      <input type="hidden" name="filename" value="{e(s["filename"])}">
      <input type="hidden" name="accion" value="desconocido">
      <button class="boton" type="submit">Desconocido</button>
    </form>
  </div>

  <div class="metadata-cola">
    <div class="fila-badges" style="margin-bottom:0.6rem">
      <span class="badge-tipo">{e(s["tipo"])}</span>
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
  </div>
</div>"""
    return pagina("Cola de revisión", "cola", cuerpo)


def vista_similares(con: sqlite3.Connection, filename: str) -> str:
    s = con.execute("SELECT * FROM segmento WHERE filename = ?", (filename,)).fetchone()
    if not s:
        cuerpo = f"""<h2>Búsqueda inversa</h2>
<div class="vacio">
  <p><strong>Ese segmento no está en el catálogo.</strong></p>
  <p><code>{e(filename)}</code> — <a href="/explorador">volver al explorador</a></p>
</div>"""
        return pagina("Búsqueda inversa", "explorador", cuerpo)

    # Estado vacío como feature (EA1): sin índice, la vista te dice qué correr.
    if not embeddings.hay_indice(con):
        cuerpo = """<h2>Búsqueda inversa</h2>
<div class="vacio">
  <p><strong>Todavía no hay índice de embeddings.</strong></p>
  <p>Generalo con <code>python indexar.py</code> y volvé a esta página:
  cada clip del catálogo queda vectorizado y esta vista te muestra los que suenan parecido.</p>
</div>"""
        return pagina("Búsqueda inversa", "explorador", cuerpo)

    resultados = embeddings.similares(con, filename, n=10)
    if resultados is None:
        cuerpo = """<h2>Búsqueda inversa</h2>
<div class="vacio">
  <p><strong>Este clip todavía no está indexado.</strong></p>
  <p>Corré <code>python indexar.py</code> para ponerlo al día
  (indexa solo lo que falta) y volvé a esta página.</p>
</div>"""
        return pagina("Búsqueda inversa", "explorador", cuerpo)

    tipo = s["tipo_corregido"] or s["tipo"]
    espectro = (
        f'<img src="/media/espectro/{e(filename)}" alt="Espectrograma de {e(filename)}">'
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
<div class="heroe">
  {espectro}
  {audio}
  <div class="fila-badges" style="margin-top:0.9rem">
    <span class="badge-tipo">{e(tipo)}</span>
    {badge_hipotesis()}
    <span class="chip {e(s["estado"])}">{e(ETIQUETA_ESTADO.get(s["estado"], s["estado"]))}</span>
  </div>
  <p class="meta">{e(filename)} · {e(s["fuente"])} · {e(s["fecha_hora_absoluta"] or "sin fecha")}</p>
</div>
<h3 style="margin:1.6rem 0 1rem">Top {len(tarjetas)} por similitud coseno</h3>
<div class="grilla">{"".join(tarjetas)}</div>"""
    return pagina("Búsqueda inversa", "explorador", cuerpo)


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
                self._responder(vista_salud(con))
            elif url.path == "/explorador":
                q = parse_qs(url.query)
                filtros = {k: q.get(k, [""])[0] for k in ("tipo", "estado", "fuente")}
                self._responder(vista_explorador(con, filtros))
            elif url.path == "/cola":
                self._responder(vista_cola(con))
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

        con = base.conectar(self.ruta_db)
        try:
            base.registrar_veredicto(con, filename, accion, tipo_corregido, revisor="local")
        except ValueError as err:
            self._responder(f"<h1>Veredicto inválido</h1><p>{e(err)}</p>", 400)
            return
        finally:
            con.close()
        self._redirigir("/cola")

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
