#!/usr/bin/env bash
#
# Bootstrap du VPS Hetzner (Ubuntu 22.04/24.04) pour le trading IBKR paper.
# Idempotent : peut être relancé sans casse.
#
#   ssh root@<IP_DU_VPS>
#   curl -fsSL https://raw.githubusercontent.com/antoineplatini1-spec/portfolio-os/master/docker/vps_setup.sh | bash
#   # ...ou clone d'abord le repo puis: bash docker/vps_setup.sh
#
set -euo pipefail

REPO_URL="https://github.com/antoineplatini1-spec/portfolio-os.git"
REPO_DIR="${HOME}/portfolio-os"

echo "── 1/5 · Paquets système ────────────────────────────────────"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y git python3 python3-venv python3-pip ca-certificates curl

echo "── 2/5 · Docker ─────────────────────────────────────────────"
if ! command -v docker >/dev/null 2>&1; then
    curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker

echo "── 3/5 · Repo ───────────────────────────────────────────────"
if [ -d "$REPO_DIR/.git" ]; then
    git -C "$REPO_DIR" pull --ff-only || true
else
    git clone "$REPO_URL" "$REPO_DIR"
fi
cd "$REPO_DIR"

echo "── 4/5 · Environnement Python ───────────────────────────────"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

chmod +x docker/run_daily.sh || true

echo "── 5/5 · Terminé ────────────────────────────────────────────"
cat <<'NEXT'

✅ Base installée. Étapes MANUELLES restantes (toi, jamais de secret automatisé) :

  1. Identifiants Gateway :
       cd ~/portfolio-os/docker
       cp .env.example .env && nano .env      # TWS_USERID / TWS_PASSWORD (paper)
       docker compose up -d
       docker compose logs -f ib-gateway      # attendre "IBC: Login has completed"

  2. Config email (comme sur GitHub Actions) :
       nano ~/portfolio-os/data/email_config.json   # coller ton JSON

  3. Smoke test (aucun ordre) :
       cd ~/portfolio-os && source .venv/bin/activate
       IBKR_ENABLED=1 python tools/ibkr_smoketest.py

  4. Deploy key GitHub (pour que le cron puisse push l'état) :
       ssh-keygen -t ed25519 -C "vps-portfolio" -f ~/.ssh/id_ed25519 -N ""
       cat ~/.ssh/id_ed25519.pub
       # → ajouter dans GitHub : repo > Settings > Deploy keys > Add (Allow write access)
       cd ~/portfolio-os && git remote set-url origin git@github.com:antoineplatini1-spec/portfolio-os.git

  5. Cron (scan en séance US, ~10h30 ET = 14h30 UTC, lun-ven) :
       ( crontab -l 2>/dev/null; echo "30 14 * * 1-5 ~/portfolio-os/docker/run_daily.sh" ) | crontab -

NEXT
