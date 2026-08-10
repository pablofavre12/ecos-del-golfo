# Ecos del Golfo — tablero de revisión + búsqueda inversa + vitrina

Prototipo local de la biblioteca acústica del Golfo. Wow 1 (WCH-467): generador
de fixtures sintéticos, importador a SQLite y tablero web local con salud del
catálogo, explorador y cola de revisión. Wow 2 (WCH-468): búsqueda inversa por
similitud ("¿qué otros clips suenan como este?") y la vitrina pública estática
para GitHub Pages. WCH-473: la **web nueva** (`web/`, Next.js + shadcn/ui, tema
"abismo") como puerta principal del tablero.

## La puerta principal: la web

```bash
./ecos.sh     # levanta la cocina Python (:8477) + la web (:3477) juntas
```

→ **http://localhost:3477** — Panel (el viaje de un sonido), Revisar (la cola,
con atajos de teclado), Biblioteca (explorador con filtros) y búsqueda inversa.
La web consume la API JSON de `tablero.py`; los datos siguen saliendo solo de
`ecos.db`. Detalles en [`web/README.md`](web/README.md).

El **tablero HTML v2** (`python tablero.py` → http://localhost:8477) queda como
fallback sin Node: mismas vistas, cero dependencias.

El catálogo (SQLite, `ecos.db`) es la **única fuente de verdad** de conteos y
estados (D10 del contrato de producto): todo lo que ves en el tablero sale de
ahí, y los CSV/carpetas son insumos o derivados regenerables.

> **Los fixtures son SINTÉTICOS de desarrollo.** Los clips de `fixtures/` se
> generan con numpy (barridos, tonos, impulsos) imitando la *forma* de los
> tipos de sonido del informe exploratorio — no son grabaciones reales ni
> sirven para ningún análisis bioacústico. Los datos reales nunca entran al
> repo.

## Cómo correr

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python generar_fixtures.py      # genera fixtures/ (CSVs + clips + espectrogramas)
python importar.py fixtures     # carga todo a ecos.db (idempotente)
python indexar.py               # indexa embeddings para la búsqueda inversa
python tablero.py               # → http://localhost:8477
python publicar.py              # regenera la vitrina pública en docs/
```

## Estructura

```
generar_fixtures.py   genera fixtures/catalogo.csv, fixtures/candidatos.csv,
                      fixtures/clips/*.wav y fixtures/espectrogramas/*.png
importar.py           CLI: importa una carpeta con ese layout a ecos.db.
                      Tolerante a esquema: valida columnas, mapea lo que puede
                      y reporta diferencias en un resumen claro.
base.py               esquema SQLite + conexión + registro de veredictos
                      (compartido por importador, tablero y tests)
tablero.py            servidor web local (stdlib http.server, HTML server-rendered,
                      CSS propio, sin JS externo — todo offline)
embeddings.py         interfaz Embedder + EmbedderEspectral (numpy) y el
                      adaptador EmbedderPerch para producción
indexar.py            CLI: puebla la tabla embedding de ecos.db (idempotente)
publicar.py           CLI: genera la vitrina estática en docs/ y el respaldo
                      del catálogo en respaldo/ (R20)
tests/                pytest: importador, veredictos, embedder determinista,
                      búsqueda inversa y vitrina
```

## Las tres vistas del tablero

- **Inicio / Salud** (`/`): por campaña/fuente, total de segmentos, conteos por
  estado, % de desconocidos y alerta si la tasa es anómala (R19).
- **Explorador** (`/explorador`): filtros por tipo/estado/fuente, tarjetas con
  espectrograma + player. Todo segmento lleva el badge **HIPÓTESIS**: la
  especie no está validada por un experto independiente (EA2).
- **Cola de revisión** (`/cola`): los segmentos `propuesto` de a uno.
  Espectrograma y play primero, veredicto segundo, metadata tercero (EA3).
  Cada veredicto queda asentado en SQLite con timestamp y revisor.

## Búsqueda inversa (R10)

Cada clip del catálogo se vectoriza y la vista `/similares/<filename>` del
tablero (botón **🔍 Buscar parecidos** en cada tarjeta y en la cola) muestra el
top-10 por similitud coseno, con su score, espectrograma y play.

```bash
python indexar.py               # idempotente: indexa solo lo que falta
python indexar.py --embedder perch   # producción, ver nota abajo
```

El diseño es **enchufable** (`embeddings.py`):

- `EmbedderEspectral` (default) funciona hoy con numpy puro: banco de 32
  filtros log-espaciados sobre el espectro (tipo mel simplificado) con
  estadísticas temporales por banda, normalizado y determinista. Alcanza para
  que los fixtures del mismo tipo se encuentren entre sí.
- `EmbedderPerch` es el adaptador para los **datos reales**: usa
  [perch-hoplite](https://github.com/google-research/perch-hoplite) (Google),
  que arrastra TensorFlow y por eso **no se instala en este repo de
  desarrollo**. En la máquina del admin: `pip install perch-hoplite` y correr
  `python indexar.py --embedder perch`. La tabla `embedding` asienta con qué
  embedder se indexó cada clip, así que cambiar de embedder re-indexa solo.

## Vitrina pública (`docs/`)

`python publicar.py` regenera el sitio estático de GitHub Pages en `docs/`
desde `ecos.db`:

- Publica **solo los segmentos confirmados** — los propuestos y descartados
  nunca llegan a la vitrina.
- `index.html`: catálogo con filtros por tipo (JS vanilla inline, sin CDNs ni
  requests externos — autocontenido, con los clips y espectrogramas copiados a
  `docs/media/`).
- `bitacora.html`: la **Bitácora de sonidos** — 5 sonidos curados de tipos
  distintos, con descripciones apoyadas en Clark (1982).
- Banner fijo en todas las páginas: *demostración con datos sintéticos* — que
  nadie confunda fixtures con ciencia. Todo clip lleva el badge **HIPÓTESIS**
  (identificación pendiente de validación experta, EA2).
- Cada publicación además **respalda el catálogo** (R20):
  `respaldo/catalogo-export.csv` (dump completo con veredictos, se commitea)
  y una copia de `ecos.db` con timestamp (solo local).

Para servirla: GitHub Pages → *Deploy from a branch* → `main` /`docs/`.

## Nomenclatura de datos (esquema §5.3 del informe exploratorio)

- `catalogo.csv`: `filename, type, recording_source, recording_start,
  offset_in_recording_s, absolute_datetime, status`
- `candidatos.csv`: ídem + `confirmed_by_ear` (vacía = pendiente; entran a la
  cola como `propuesto`)
- Clips: `{YYYY-MM-DD}_{HHhMMmSSs}_{tipo}.wav` (fecha/hora absoluta real)
