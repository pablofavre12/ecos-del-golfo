# Ecos del Golfo — web

La puerta principal del tablero: Next.js 16 + shadcn/ui con la identidad
"abismo" (el Golfo Nuevo de noche). Toda la lógica y los datos viven en la
cocina Python (`../tablero.py`, puerto 8477): esta web consume su API JSON
(`/api/*`) y su media (`/media/*`) vía rewrites — acá no hay reglas de
negocio ni acceso a `ecos.db`.

## Correr

```bash
../ecos.sh        # cocina + web juntas (recomendado)
# o a mano:
npm install
npm run dev       # → http://localhost:3477  (la cocina debe estar corriendo)
```

## Páginas

| Ruta | Qué se hace ahí |
|---|---|
| `/` | Panel: el viaje de un sonido (funnel, salud por campaña, actividad) |
| `/revisar` | La cola: escuchar, comparar de oído y dar veredicto (C/X/D/espacio/flechas) |
| `/biblioteca` | Explorador del catálogo con filtros combinables y paginación |
| `/parecidos/[filename]` | Búsqueda inversa por similitud (embeddings Perch) |

## Piezas

- `src/lib/cocina.ts` — cliente tipado de la API Python (+ pantalla útil si la cocina está apagada).
- `src/app/globals.css` — el tema "abismo": tokens de color, tipografía y foco.
- `src/components/` — marca (waveform), ballena franca (SVG línea fina), insignias de estado/HIPÓTESIS, tarjetas de segmento, la cola interactiva.

`npm run build` exige types y lint limpios; el tablero HTML v2 (`python
tablero.py` solo) sigue funcionando como fallback sin Node.
