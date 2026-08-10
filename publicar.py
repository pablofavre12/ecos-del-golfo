"""Vitrina pública de Ecos del Golfo — sitio estático para GitHub Pages.

Genera docs/ desde ecos.db con SOLO los segmentos confirmados (la vitrina no
publica propuestos ni descartados): portada + catálogo con filtros por tipo
(JS vanilla inline, sin CDNs ni requests externos) y la Bitácora de sonidos
con hasta 5 sonidos curados de tipos distintos. Los clips y espectrogramas
se COPIAN a docs/media/ — el sitio es 100% autocontenido.

Además (R20) cada publicación respalda el catálogo: exporta
respaldo/catalogo-export.csv (dump completo de segmento, con veredictos) y
copia ecos.db a respaldo/ con timestamp. El CSV más reciente se commitea; las
copias .db quedan solo locales (.gitignore).

Uso: python publicar.py [--db ruta/ecos.db]
"""

from __future__ import annotations

import csv
import html
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import base

RAIZ = Path(__file__).parent
REPO_URL = "https://github.com/Perennia-Regeneracion/ecos-del-golfo"
MAILTO = (
    "mailto:ecosdelgolfo@example.com"
    "?subject=Solicitud%20de%20audios%20crudos%20%E2%80%94%20Ecos%20del%20Golfo"
)

# Curaduría de la bitácora: título en criollo + descripción breve apoyada en
# la bibliografía del contrato (Clark 1982, ballena franca austral en
# Península Valdés). El orden define la prioridad si hay más de 5 tipos.
BITACORA = {
    "up_call": (
        "Así suena un up-call — el llamado de contacto",
        "Un barrido grave que sube de tono en un segundo. Es el sonido más "
        "característico de la ballena franca austral: Clark (1982) lo describe "
        "como el llamado de contacto con el que una ballena anuncia dónde está "
        "y busca respuesta de otras.",
    ),
    "high_call": (
        "El high call — un aviso más agudo",
        "Un tono más alto y sostenido que el up-call. En el repertorio que "
        "Clark (1982) registró en Península Valdés aparece asociado a "
        "ballenas activas, muchas veces mezclado con otros llamados en "
        "secuencias de interacción.",
    ),
    "pulsive_call": (
        "El pulsive call — el gruñido áspero de los grupos",
        "Un sonido pulsado, áspero, casi un gruñido bajo el agua. Clark "
        "(1982) lo asocia a los grupos socialmente activos: cuanto más "
        "revuelo hay en superficie, más de estos llamados se escuchan.",
    ),
    "gunshot_call": (
        "El gunshot — un estampido bajo el agua",
        "Un estallido corto y de banda ancha, como un disparo amortiguado "
        "por el mar. Se le atribuye a la ballena franca un rol de señal — "
        "posiblemente de los machos — y es inconfundible en el espectrograma: "
        "una columna vertical que cruza todas las frecuencias.",
    ),
    "no_clasificado": (
        "Un sonido que todavía no tiene nombre",
        "No todo lo que se escucha en el Golfo entra prolijo en una "
        "categoría. Este quedó confirmado como sonido de interés, pero su "
        "tipo sigue abierto — así también se ve la ciencia en proceso.",
    ),
}

ETIQUETA_TIPO = {
    "up_call": "Up-call",
    "high_call": "High call",
    "pulsive_call": "Pulsive call",
    "gunshot_call": "Gunshot",
    "no_clasificado": "Sin clasificar",
}


def e(texto) -> str:
    return html.escape(str(texto if texto is not None else ""))


ESTILO = """
:root {
  --fondo: #071019; --panel: #0c1b2b; --panel-2: #112438; --borde: #1c344f;
  --texto: #dce8f7; --tenue: #8aa2c0; --acento: #f0a35e; --acento-fuerte: #e8863a;
  --hipotesis: #e8863a;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html { scroll-behavior: smooth; }
body {
  background: var(--fondo); color: var(--texto);
  font: 16px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
        "Helvetica Neue", Arial, sans-serif;
  padding-top: 3.4rem; /* deja lugar al banner fijo */
}
a { color: var(--acento); text-decoration: none; }
a:hover { text-decoration: underline; }

.banner-demo {
  position: fixed; top: 0; left: 0; right: 0; z-index: 10;
  background: #2b1a08; color: var(--acento); border-bottom: 1px solid var(--acento-fuerte);
  padding: 0.55rem 1rem; text-align: center; font-size: 0.88rem; font-weight: 600;
}

header.portada {
  max-width: 960px; margin: 0 auto; padding: 3.5rem 1.5rem 2.5rem; text-align: center;
}
header.portada h1 { font-size: clamp(1.9rem, 5vw, 3rem); font-weight: 700; letter-spacing: -0.01em; }
header.portada h1 span { color: var(--acento); }
header.portada .bajada {
  color: var(--tenue); max-width: 620px; margin: 0.9rem auto 0; font-size: 1.05rem;
}
nav.publica {
  display: flex; justify-content: center; gap: 1.6rem; margin-top: 1.6rem; font-size: 0.95rem;
}
nav.publica a.activo { color: var(--texto); border-bottom: 2px solid var(--acento); padding-bottom: 2px; }

main { max-width: 1080px; margin: 0 auto; padding: 0 1.5rem 4rem; }
h2 { font-size: 1.45rem; font-weight: 700; margin: 2.2rem 0 1.2rem; }

.acciones { display: flex; justify-content: center; gap: 1rem; margin-top: 1.6rem; flex-wrap: wrap; }
.boton {
  display: inline-block; padding: 0.6rem 1.3rem; border-radius: 6px; font-size: 0.95rem;
  font-weight: 600; border: 1px solid var(--borde); background: var(--panel-2); color: var(--texto);
}
.boton:hover { border-color: var(--acento); text-decoration: none; }
.boton.primario { background: var(--acento-fuerte); border-color: var(--acento-fuerte); color: #14100a; }
.boton.primario:hover { background: var(--acento); }

.filtros { display: flex; flex-wrap: wrap; gap: 0.55rem; margin-bottom: 1.6rem; }
.filtros button {
  font: inherit; font-size: 0.86rem; font-weight: 600; cursor: pointer;
  padding: 0.38rem 0.95rem; border-radius: 999px; border: 1px solid var(--borde);
  background: var(--panel-2); color: var(--texto);
}
.filtros button:hover { border-color: var(--acento); }
.filtros button.activo { background: var(--acento-fuerte); border-color: var(--acento-fuerte); color: #14100a; }

.grilla { display: grid; grid-template-columns: repeat(auto-fill, minmax(290px, 1fr)); gap: 1.3rem; }
.sonido {
  background: var(--panel); border: 1px solid var(--borde); border-radius: 8px; overflow: hidden;
}
.sonido img { width: 100%; display: block; background: #0a1524; }
.sonido .cuerpo { padding: 0.9rem 1.05rem 1.1rem; }
.sonido audio { width: 100%; height: 34px; margin: 0.6rem 0 0.2rem; }
.fila-badges { display: flex; flex-wrap: wrap; gap: 0.45rem; align-items: center; }
.badge-tipo {
  font-size: 0.76rem; font-weight: 600; padding: 0.18rem 0.55rem; border-radius: 4px;
  background: var(--panel-2); border: 1px solid var(--borde);
}
.badge-hipotesis {
  font-size: 0.7rem; font-weight: 700; letter-spacing: 0.08em; padding: 0.18rem 0.55rem;
  border-radius: 4px; background: var(--hipotesis); color: #14100a; cursor: help;
}
.meta { color: var(--tenue); font-size: 0.82rem; margin-top: 0.5rem; }

.entrada-bitacora {
  background: var(--panel); border: 1px solid var(--borde); border-radius: 8px;
  padding: 1.6rem; margin-bottom: 1.8rem;
}
.entrada-bitacora h3 { font-size: 1.2rem; font-weight: 700; }
.entrada-bitacora .descripcion { color: var(--tenue); margin: 0.6rem 0 1rem; max-width: 640px; }
.entrada-bitacora img { width: 100%; max-height: 340px; object-fit: contain; background: #0a1524; border-radius: 6px; }
.entrada-bitacora audio { width: 100%; margin-top: 0.8rem; }

.nota-hipotesis {
  background: var(--panel); border: 1px solid var(--borde); border-left: 3px solid var(--hipotesis);
  border-radius: 6px; padding: 0.9rem 1.1rem; color: var(--tenue); font-size: 0.9rem; margin: 1.4rem 0;
}

footer {
  border-top: 1px solid var(--borde); margin-top: 2rem; padding: 1.8rem 1.5rem 2.4rem;
  text-align: center; color: var(--tenue); font-size: 0.88rem;
}
@media (max-width: 560px) {
  body { padding-top: 4.1rem; }
  header.portada { padding-top: 2.2rem; }
  .grilla { grid-template-columns: 1fr; }
}
"""


def _pagina(titulo: str, activo: str, cuerpo: str, extra_js: str = "") -> str:
    def nav(ruta, nombre, clave):
        clase = ' class="activo"' if activo == clave else ""
        return f'<a href="{ruta}"{clase}>{nombre}</a>'

    js = f"<script>{extra_js}</script>" if extra_js else ""
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Ecos del Golfo — biblioteca abierta de sonidos de ballena franca austral en Puerto Pirámides, Golfo Nuevo.">
<title>{e(titulo)} — Ecos del Golfo</title>
<style>{ESTILO}</style>
</head>
<body>
<div class="banner-demo">⚠️ Demostración con datos sintéticos — los sonidos reales del Golfo se cargan próximamente</div>
<header class="portada">
  <h1>Ecos <span>del Golfo</span></h1>
  <p class="bajada">Una biblioteca abierta de los sonidos de la ballena franca austral
  registrados desde Puerto Pirámides, Golfo Nuevo, Península Valdés.</p>
  <nav class="publica">
    {nav("index.html", "Catálogo", "catalogo")}
    {nav("bitacora.html", "Bitácora de sonidos", "bitacora")}
  </nav>
</header>
<main>
{cuerpo}
</main>
<footer>
  <p>Ecos del Golfo · Puerto Pirámides · código abierto (<a href="{REPO_URL}/blob/main/LICENSE">MIT</a>)</p>
  <p style="margin-top:0.3rem"><a href="{REPO_URL}">Ver el código y los datos en el repositorio</a></p>
</footer>
{js}
</body>
</html>"""


def _badge_hipotesis() -> str:
    return (
        '<span class="badge-hipotesis" '
        'title="Identificación pendiente de validación experta">HIPÓTESIS</span>'
    )


def _tarjeta(s: sqlite3.Row) -> str:
    tipo = s["tipo_corregido"] or s["tipo"]
    espectro = (
        f'<img src="media/espectrogramas/{e(Path(s["filename"]).stem)}.png" '
        f'alt="Espectrograma de {e(s["filename"])}" loading="lazy">'
        if s["espectrograma_path"]
        else ""
    )
    audio = (
        f'<audio controls preload="none" src="media/clips/{e(s["filename"])}"></audio>'
        if s["clip_path"]
        else '<p class="meta">clip no disponible</p>'
    )
    return f"""<article class="sonido" data-tipo="{e(tipo)}">
  {espectro}
  <div class="cuerpo">
    <div class="fila-badges">
      <span class="badge-tipo">{e(ETIQUETA_TIPO.get(tipo, tipo))}</span>
      {_badge_hipotesis()}
    </div>
    {audio}
    <p class="meta">{e(s["fecha_hora_absoluta"] or "sin fecha")} · {e(s["fuente"])}</p>
  </div>
</article>"""


JS_FILTROS = """
document.querySelectorAll('.filtros button').forEach(function (boton) {
  boton.addEventListener('click', function () {
    var tipo = boton.dataset.tipo;
    document.querySelectorAll('.filtros button').forEach(function (b) {
      b.classList.toggle('activo', b === boton);
    });
    document.querySelectorAll('.grilla .sonido').forEach(function (tarjeta) {
      tarjeta.style.display = (!tipo || tarjeta.dataset.tipo === tipo) ? '' : 'none';
    });
  });
});
"""


def _pagina_indice(confirmados: list[sqlite3.Row]) -> str:
    tipos = sorted({(s["tipo_corregido"] or s["tipo"]) for s in confirmados})
    botones = ['<button class="activo" data-tipo="">Todos</button>'] + [
        f'<button data-tipo="{e(t)}">{e(ETIQUETA_TIPO.get(t, t))}</button>' for t in tipos
    ]
    tarjetas = "".join(_tarjeta(s) for s in confirmados)
    cuerpo = f"""<div class="acciones">
  <a class="boton primario" href="bitacora.html">Escuchar la bitácora de sonidos</a>
  <a class="boton" href="{MAILTO}">Solicitar audios crudos</a>
</div>

<div class="nota-hipotesis">Todos los sonidos publicados llevan el sello
<strong>HIPÓTESIS</strong>: la identificación de cada tipo está pendiente de
validación experta independiente.</div>

<h2>Catálogo · {len(confirmados)} sonidos confirmados</h2>
<div class="filtros">{"".join(botones)}</div>
<div class="grilla">{tarjetas}</div>"""
    return _pagina("Catálogo", "catalogo", cuerpo, extra_js=JS_FILTROS)


def _pagina_bitacora(curados: list[sqlite3.Row]) -> str:
    entradas = []
    for s in curados:
        tipo = s["tipo_corregido"] or s["tipo"]
        titulo, descripcion = BITACORA.get(
            tipo,
            (
                f"Así suena un {tipo}",
                "Un sonido confirmado del catálogo del Golfo, a la espera de "
                "una descripción curada.",
            ),
        )
        espectro = (
            f'<img src="media/espectrogramas/{e(Path(s["filename"]).stem)}.png" '
            f'alt="Espectrograma de {e(s["filename"])}" loading="lazy">'
            if s["espectrograma_path"]
            else ""
        )
        audio = (
            f'<audio controls preload="none" src="media/clips/{e(s["filename"])}"></audio>'
            if s["clip_path"]
            else '<p class="meta">clip no disponible</p>'
        )
        entradas.append(f"""<section class="entrada-bitacora">
  <div class="fila-badges" style="margin-bottom:0.5rem">
    <span class="badge-tipo">{e(ETIQUETA_TIPO.get(tipo, tipo))}</span>
    {_badge_hipotesis()}
  </div>
  <h3>{e(titulo)}</h3>
  <p class="descripcion">{e(descripcion)}</p>
  {espectro}
  {audio}
  <p class="meta">{e(s["fecha_hora_absoluta"] or "sin fecha")} · {e(s["fuente"])}</p>
</section>""")

    numeros = {2: "Dos", 3: "Tres", 4: "Cuatro", 5: "Cinco"}
    cuantos = numeros.get(len(curados), str(len(curados)))
    cuerpo = f"""<h2>Bitácora de sonidos</h2>
<p style="color:var(--tenue);max-width:640px;margin-bottom:1.6rem">
{cuantos} sonidos elegidos del catálogo para conocer el repertorio de la ballena
franca austral, con las descripciones apoyadas en la bibliografía clásica del
área (Clark, 1982).</p>
{"".join(entradas)}
<div class="acciones" style="justify-content:flex-start">
  <a class="boton" href="index.html">Volver al catálogo completo</a>
  <a class="boton" href="{MAILTO}">Solicitar audios crudos</a>
</div>"""
    return _pagina("Bitácora de sonidos", "bitacora", cuerpo)


def _curar_bitacora(confirmados: list[sqlite3.Row], maximo: int = 5) -> list[sqlite3.Row]:
    """Hasta 5 confirmados de tipos distintos, priorizando el orden curado de
    BITACORA y, dentro de cada tipo, los que tienen clip + espectrograma."""
    prioridad = list(BITACORA)
    por_tipo: dict[str, list[sqlite3.Row]] = {}
    for s in confirmados:
        por_tipo.setdefault(s["tipo_corregido"] or s["tipo"], []).append(s)

    tipos_ordenados = [t for t in prioridad if t in por_tipo]
    tipos_ordenados += [t for t in sorted(por_tipo) if t not in tipos_ordenados]

    curados = []
    for tipo in tipos_ordenados[:maximo]:
        candidatos = sorted(
            por_tipo[tipo],
            key=lambda s: (not (s["clip_path"] and s["espectrograma_path"]), s["filename"]),
        )
        curados.append(candidatos[0])
    return curados


def _copiar_media(confirmados: list[sqlite3.Row], destino: Path) -> int:
    carpeta_clips = destino / "media" / "clips"
    carpeta_espectros = destino / "media" / "espectrogramas"
    carpeta_clips.mkdir(parents=True, exist_ok=True)
    carpeta_espectros.mkdir(parents=True, exist_ok=True)
    copiados = 0
    for s in confirmados:
        if s["clip_path"] and Path(s["clip_path"]).exists():
            shutil.copy2(s["clip_path"], carpeta_clips / s["filename"])
            copiados += 1
        if s["espectrograma_path"] and Path(s["espectrograma_path"]).exists():
            shutil.copy2(
                s["espectrograma_path"],
                carpeta_espectros / (Path(s["filename"]).stem + ".png"),
            )
    return copiados


def _respaldar(ruta_db: Path, carpeta: Path) -> tuple[int, Path]:
    """R20: dump completo de segmento a CSV + copia timestampeada de la DB."""
    carpeta.mkdir(parents=True, exist_ok=True)
    con = base.conectar(ruta_db)
    try:
        filas = con.execute("SELECT * FROM segmento ORDER BY filename").fetchall()
        columnas = [d[0] for d in con.execute("SELECT * FROM segmento LIMIT 0").description]
    finally:
        con.close()

    ruta_csv = carpeta / "catalogo-export.csv"
    with open(ruta_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(columnas)
        for fila in filas:
            w.writerow([fila[c] for c in columnas])

    marca = datetime.now().strftime("%Y%m%d-%H%M%S")
    ruta_copia = carpeta / f"ecos-{marca}.db"
    shutil.copy2(ruta_db, ruta_copia)
    return len(filas), ruta_copia


def publicar(
    ruta_db: Path | str = base.RUTA_DB,
    destino: Path | str | None = None,
    carpeta_respaldo: Path | str | None = None,
) -> dict:
    ruta_db = Path(ruta_db)
    destino = Path(destino) if destino else RAIZ / "docs"
    carpeta_respaldo = Path(carpeta_respaldo) if carpeta_respaldo else RAIZ / "respaldo"

    con = base.conectar(ruta_db)
    try:
        confirmados = con.execute(
            "SELECT * FROM segmento WHERE estado = 'confirmado' ORDER BY fecha_hora_absoluta"
        ).fetchall()
    finally:
        con.close()

    destino.mkdir(parents=True, exist_ok=True)
    clips_copiados = _copiar_media(confirmados, destino)
    curados = _curar_bitacora(confirmados)

    (destino / "index.html").write_text(_pagina_indice(confirmados), encoding="utf-8")
    (destino / "bitacora.html").write_text(_pagina_bitacora(curados), encoding="utf-8")
    # GitHub Pages: sin Jekyll, así media/ y demás se sirven tal cual.
    (destino / ".nojekyll").write_text("", encoding="utf-8")

    filas_respaldadas, ruta_copia = _respaldar(ruta_db, carpeta_respaldo)

    return {
        "publicados": len(confirmados),
        "clips_copiados": clips_copiados,
        "curados_bitacora": len(curados),
        "filas_respaldadas": filas_respaldadas,
        "copia_db": ruta_copia,
        "destino": destino,
    }


def main(argv: list[str]) -> int:
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    ruta_db = Path(argv[argv.index("--db") + 1]) if "--db" in argv else base.RUTA_DB

    r = publicar(ruta_db)
    print(f"Vitrina publicada en {r['destino']}/")
    print(f"  {r['publicados']} segmentos confirmados (solo confirmados se publican)")
    print(f"  {r['clips_copiados']} clips copiados a docs/media/ · sitio autocontenido")
    print(f"  {r['curados_bitacora']} sonidos curados en la bitácora")
    print(f"Respaldo del catálogo (R20):")
    print(f"  respaldo/catalogo-export.csv con {r['filas_respaldadas']} filas (se commitea)")
    print(f"  copia local de la DB: {r['copia_db'].name} (gitignoreada)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
