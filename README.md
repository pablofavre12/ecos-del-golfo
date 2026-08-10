# Ecos del Golfo — Wow 1: prototipo del tablero

Prototipo local del tablero de revisión de la biblioteca acústica del Golfo
(WCH-467). Tres piezas: generador de fixtures sintéticos, importador a SQLite
y tablero web local con salud del catálogo, explorador y cola de revisión.

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
python tablero.py               # → http://localhost:8477
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
tests/                pytest: importador feliz, esquema cambiado, idempotencia,
                      escritura de veredictos
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

## Nomenclatura de datos (esquema §5.3 del informe exploratorio)

- `catalogo.csv`: `filename, type, recording_source, recording_start,
  offset_in_recording_s, absolute_datetime, status`
- `candidatos.csv`: ídem + `confirmed_by_ear` (vacía = pendiente; entran a la
  cola como `propuesto`)
- Clips: `{YYYY-MM-DD}_{HHhMMmSSs}_{tipo}.wav` (fecha/hora absoluta real)
