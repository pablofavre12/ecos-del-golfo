#!/usr/bin/env bash
# Ecos del Golfo — levanta la cocina Python (:8477) y la web Next (:3477).
# Uso: ./ecos.sh          (Ctrl+C frena las dos)
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "✗ Falta el venv de Python. Crealo así:"
  echo "    python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

if [ ! -d web/node_modules ]; then
  echo "→ Primera vez: instalando dependencias de la web (npm install)…"
  (cd web && npm install)
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "→ Cocina (tablero.py) en http://localhost:8477"
python tablero.py &
COCINA_PID=$!

frenar() {
  echo ""
  echo "→ Frenando cocina y web…"
  kill "$COCINA_PID" 2>/dev/null || true
  exit 0
}
trap frenar INT TERM

sleep 1
if ! kill -0 "$COCINA_PID" 2>/dev/null; then
  echo "✗ La cocina no arrancó (¿puerto 8477 ocupado?). Mirá el error de arriba."
  exit 1
fi

echo "→ Web en http://localhost:3477  (Ctrl+C frena las dos)"
cd web && npm run dev
frenar
