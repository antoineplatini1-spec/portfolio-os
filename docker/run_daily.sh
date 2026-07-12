#!/usr/bin/env bash
#
# Wrapper cron du scan quotidien sur le VPS (remplace GitHub Actions une fois IBKR actif).
# Se lance peu après l'ouverture US pour des fills réels immédiats (MKT en séance).
#
#   Installé par vps_setup.sh dans le crontab.
#   Logs → data/cron.log
#
set -euo pipefail

# Racine du repo (le script est dans docker/)
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

# ── Environnement d'exécution ─────────────────────────────────────
export TZ="America/New_York"
export DATA_DIR="$REPO_DIR/data"

# Routage IBKR (paper). Le Gateway tourne dans Docker sur le même host.
export IBKR_ENABLED=1
export IBKR_HOST=127.0.0.1
export IBKR_PORT=4002                 # 4002 = paper, 4001 = live (go-live)
export IBKR_ACCOUNT=DUP588572
export IBKR_ORDER_TYPE=MKT            # MKT car le cron tourne EN SÉANCE (voir crontab)
export IBKR_SHADOW=0                  # pur IBKR : on a laissé tomber la simulation parallèle

# ── Enrichissement LLM : couche de LECTURE (news + biais secteur) ─
# S'active seulement si LLM_ENABLED=1 ET une clé API présente
# (cf. llm_enrich.is_enabled). La clé vit dans data/llm.env — fichier GITIGNORÉ
# rempli par l'utilisateur — jamais en dur dans ce script (qui est versionné).
export LLM_ENABLED=1
if [ -f "$DATA_DIR/llm.env" ]; then
    set -a; . "$DATA_DIR/llm.env"; set +a
fi
# export LLM_MODEL=claude-sonnet-5   # décommenter pour ~2,5× moins cher (extraction)

# venv Python
# shellcheck disable=SC1091
source .venv/bin/activate 2>/dev/null || true

echo "===== $(date -u +'%Y-%m-%dT%H:%M:%SZ') — run_daily ====="

# Récupère les éventuels changements distants avant de trader
git pull --rebase --autostash origin master || echo "git pull échoué (on continue)"

# Scan + trading
python daily_auto.py

# Persiste l'état (état PTF + Momentum + journaux). `git add data/` reste robuste
# même si un fichier manque ; les secrets (email_config.json) sont git-ignorés.
git add data/portfolio_state.json data/momentum_state.json \
        data/momentum_signals.jsonl data/daily_log.txt 2>/dev/null || true
if ! git diff --staged --quiet; then
    git commit -m "auto(vps): portfolio $(date +%F)"
    git push || echo "git push échoué (vérifier la deploy key)"
else
    echo "Aucun changement à committer."
fi

echo "===== fin run_daily ====="
