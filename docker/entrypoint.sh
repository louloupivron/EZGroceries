#!/bin/sh
set -e

mkdir -p /app/data /app/exports /app/docs

PORT="${COMIDA_PORT:-8765}"
echo "Comida UI — port ${PORT} (COMIDA_UI_HOST=${COMIDA_UI_HOST:-0.0.0.0})"

exec uv run python -c "
from comida.ui.server import serve
import os
serve(
    port=int(os.environ.get('COMIDA_PORT', '8765')),
    open_browser=False,
)
"
