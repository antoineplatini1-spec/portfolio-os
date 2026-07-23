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
export LLM_MODEL=claude-sonnet-5      # Sonnet 5 : ~2,5× moins cher qu'Opus, largement
                                     # assez fin pour de la lecture/extraction de texte.

# venv Python
# shellcheck disable=SC1091
source .venv/bin/activate 2>/dev/null || true

echo "===== $(date -u +'%Y-%m-%dT%H:%M:%SZ') — run_daily ====="

# ── Dead-man's switch (surveillance) ──────────────────────────────
# URL de ping (healthchecks.io ou équivalent), dans data/heartbeat.url (gitignoré) ou
# la var d'env HEARTBEAT_URL. Vide → no-op. Un run manqué/échoué → le service t'alerte.
HEARTBEAT_URL="${HEARTBEAT_URL:-}"
[ -f "$DATA_DIR/heartbeat.url" ] && HEARTBEAT_URL="$(tr -d '[:space:]' < "$DATA_DIR/heartbeat.url")"
[ -n "$HEARTBEAT_URL" ] && curl -fsS -m 10 "$HEARTBEAT_URL/start" >/dev/null 2>&1 || true

# Récupère les éventuels changements distants avant de trader
git pull --rebase --autostash origin master || echo "git pull échoué (on continue)"

# Scan + trading — on capture le code de sortie SANS que set -e ne tue le script,
# pour pouvoir signaler l'échec au dead-man's switch.
set +e
python daily_auto.py
RUN_RC=$?
set -e

# Persiste l'état (état PTF + Momentum + journaux). `git add data/` reste robuste
# même si un fichier manque ; les secrets (email_config.json) sont git-ignorés.
# Garantit l'existence des journaux : un `git add` avec UN fichier manquant échoue et ne
# stage RIEN (donc l'état ne serait pas persisté). postmortems.jsonl n'apparaît qu'à la 1re
# clôture → on le crée vide au besoin (inoffensif : digest lit ligne par ligne).
touch data/decisions_log.jsonl data/postmortems.jsonl \
      data/trade_journal.jsonl data/nav_history.jsonl 2>/dev/null || true
git add data/portfolio_state.json data/momentum_state.json \
        data/momentum_signals.jsonl data/daily_log.txt \
        data/decisions_log.jsonl data/postmortems.jsonl \
        data/trade_journal.jsonl data/nav_history.jsonl 2>/dev/null || true
if ! git diff --staged --quiet; then
    git commit -m "auto(vps): portfolio $(date +%F)"
    # Récupère d'éventuels commits distants (push de dev) AVANT de pousser → plus de conflit.
    git pull --rebase --autostash origin master || echo "git pull avant push échoué (on tente quand même)"
    git push || echo "git push échoué (vérifier la deploy key)"
else
    echo "Aucun changement à committer."
fi

# Ping final : succès → dead-man's switch réarmé ; échec → alerte immédiate.
if [ -n "$HEARTBEAT_URL" ]; then
    if [ "$RUN_RC" -eq 0 ]; then
        curl -fsS -m 10 "$HEARTBEAT_URL" >/dev/null 2>&1 || true
    else
        curl -fsS -m 10 "$HEARTBEAT_URL/fail" >/dev/null 2>&1 || true
    fi
fi

echo "===== fin run_daily (rc=$RUN_RC) ====="
exit $RUN_RC
