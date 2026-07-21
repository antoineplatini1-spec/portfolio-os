#!/usr/bin/env bash
#
# Tick du watcher de sorties (email quand un stop/TP IBKR est touché).
# Cron toutes les ~15 min EN SÉANCE US. Lecture seule IBKR (clientId 18, distinct du bot=17).
# No-op silencieux s'il n'y a aucune nouvelle vente → coût quasi nul.
#   Logs → data/exit_watch.log
#
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

export TZ="America/New_York"
export DATA_DIR="$REPO_DIR/data"
export IBKR_ENABLED=1
export IBKR_HOST=127.0.0.1
export IBKR_PORT=4002
export IBKR_ACCOUNT=DUP588572

# shellcheck disable=SC1091
source .venv/bin/activate 2>/dev/null || true

python exit_watcher.py
