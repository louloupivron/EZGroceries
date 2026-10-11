#!/bin/zsh
# Planification Comida → Telegram (launchd / cron sur le Mac).
# Usage : scripts/telegram-schedule.sh [thu-am|thu-pm|fri-am]

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

STEP="${1:-}"
exec uv run python validate.py telegram-schedule ${STEP:+$STEP}
