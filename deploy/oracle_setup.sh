#!/bin/bash
# ============================================================
# oracle_setup.sh — Installation complète sur Oracle Cloud VM
# À exécuter une seule fois après création de la VM Ubuntu
# Usage : bash oracle_setup.sh
# ============================================================
set -e

REPO_URL="https://github.com/antoineplatini1-spec/portfolio-os.git"
APP_DIR="$HOME/portfolio_manager"
PYTHON_VERSION="3.11"

echo "==================================================="
echo " SETUP PORTFOLIO MANAGER — Oracle Cloud"
echo "==================================================="

# ── 1. Mise à jour système ────────────────────────────────
echo "[1/7] Mise à jour du système..."
sudo apt-get update -qq && sudo apt-get upgrade -y -qq

# ── 2. Python 3.11 ───────────────────────────────────────
echo "[2/7] Installation Python $PYTHON_VERSION..."
sudo apt-get install -y -qq python3.11 python3.11-venv python3.11-dev python3-pip git

# ── 3. Clone du repo ─────────────────────────────────────
echo "[3/7] Clone du repo GitHub..."
if [ -d "$APP_DIR" ]; then
    echo "  Repo déjà présent, git pull..."
    cd "$APP_DIR" && git pull
else
    git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

# ── 4. Environnement virtuel + dépendances ────────────────
echo "[4/7] Création de l'environnement virtuel..."
python3.11 -m venv .venv
source .venv/bin/activate

echo "  Installation des dépendances..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

# ── 5. Dossier data + email_config ───────────────────────
echo "[5/7] Configuration..."
mkdir -p data

if [ ! -f data/email_config.json ]; then
    cat > data/email_config.json << 'EOF'
{
  "smtp_server": "smtp.gmail.com",
  "smtp_port": 587,
  "sender": "le.glaude.intelligence@gmail.com",
  "password": "REMPLACE_MOI",
  "recipient": "antoine.platini@outlook.fr",
  "reader": {
    "email": "antoine.platini1@gmail.com",
    "password": "APP_PASSWORD_READER",
    "imap_server": "imap.gmail.com"
  },
  "gdrive_cache_url": "REMPLACE_MOI_AVEC_URL_GDRIVE"
}
EOF
    echo "  ⚠  data/email_config.json créé — à compléter manuellement (voir étape suivante)"
fi

# ── 6. Git config pour les commits automatiques ───────────
echo "[6/7] Configuration Git..."
git config user.email "oracle-vm@portfolio-auto"
git config user.name "Oracle VM Auto"

# ── 7. Cron job ───────────────────────────────────────────
echo "[7/7] Installation du cron job (15h15 CET = 13h15 UTC en été)..."
CRON_CMD="15 13 * * 1-5 cd $APP_DIR && bash deploy/run_daily.sh >> data/cron.log 2>&1"
# Supprimer l'ancien cron si existe, puis ajouter
(crontab -l 2>/dev/null | grep -v "run_daily.sh"; echo "$CRON_CMD") | crontab -

echo ""
echo "==================================================="
echo " ✅  Setup terminé !"
echo "==================================================="
echo ""
echo " PROCHAINES ÉTAPES MANUELLES :"
echo " 1. Édite data/email_config.json :"
echo "    nano $APP_DIR/data/email_config.json"
echo "    → remplace REMPLACE_MOI par ton vrai mot de passe Gmail SMTP"
echo "    → remplace REMPLACE_MOI_AVEC_URL_GDRIVE par l'URL Google Drive"
echo ""
echo " 2. Configure GitHub token pour les push automatiques :"
echo "    git remote set-url origin https://TON_TOKEN@github.com/antoineplatini1-spec/portfolio-os.git"
echo ""
echo " 3. Test manuel :"
echo "    cd $APP_DIR && bash deploy/run_daily.sh"
echo ""
echo " Le cron tourne du lundi au vendredi à 13h15 UTC (15h15 CET)."
