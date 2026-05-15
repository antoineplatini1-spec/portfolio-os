#!/bin/bash
# ============================================================
# run_daily.sh — Wrapper quotidien pour Oracle Cloud
# Appelé par le cron à 15h15 CET (13h15 UTC en été)
#
# Séquence :
#   1. git pull  (récupère les changements locaux : watchlist, config...)
#   2. python daily_auto.py
#   3. git push  (sauvegarde l'état du portefeuille)
# ============================================================
set -e

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$APP_DIR/.venv/bin/python"
LOG="$APP_DIR/data/daily_log.txt"

cd "$APP_DIR"

# Timestamp
echo "" >> "$LOG"
echo "============================================" >> "$LOG"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] RUN_DAILY START" >> "$LOG"
echo "============================================" >> "$LOG"

# ── 1. Sync depuis GitHub ──────────────────────────────────
echo "[$(date '+%H:%M:%S')] git pull..." >> "$LOG"
git pull --rebase origin main >> "$LOG" 2>&1 || {
    echo "[$(date '+%H:%M:%S')] ⚠ git pull échoué — on continue quand même" >> "$LOG"
}

# ── 2. Exécution du script principal ──────────────────────
echo "[$(date '+%H:%M:%S')] Lancement daily_auto.py..." >> "$LOG"
$PYTHON daily_auto.py >> "$LOG" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "[$(date '+%H:%M:%S')] ❌ daily_auto.py a terminé avec code $EXIT_CODE" >> "$LOG"
else
    echo "[$(date '+%H:%M:%S')] ✅ daily_auto.py terminé OK" >> "$LOG"
fi

# ── 3. Push de l'état du portefeuille ─────────────────────
echo "[$(date '+%H:%M:%S')] git push état portefeuille..." >> "$LOG"
git add data/portfolio_state.json data/daily_log.txt 2>/dev/null || true
git diff --cached --quiet || git commit -m "auto: portfolio state $(date '+%Y-%m-%d %H:%M')" >> "$LOG" 2>&1
git push origin main >> "$LOG" 2>&1 || {
    echo "[$(date '+%H:%M:%S')] ⚠ git push échoué — état non synchronisé" >> "$LOG"
}

echo "[$(date '+%H:%M:%S')] RUN_DAILY END" >> "$LOG"
