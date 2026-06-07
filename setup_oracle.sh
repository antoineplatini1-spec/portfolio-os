#!/bin/bash
# =============================================================================
# setup_oracle.sh — Portfolio Manager on Oracle Cloud Free Tier (ARM Ubuntu)
# =============================================================================
# Cible  : VM.Standard.A1.Flex — Ubuntu 22.04 LTS (aarch64)
# Projet : Portfolio Manager (Streamlit + daily_auto.py + Cloudflare Tunnel)
# Usage  : bash setup_oracle.sh
# =============================================================================

set -euo pipefail

# --- Variables à personnaliser -----------------------------------------------
APP_USER="ubuntu"                        # utilisateur système (Ubuntu = ubuntu)
APP_DIR="/home/${APP_USER}/portfolio_manager"
VENV_DIR="${APP_DIR}/.venv"
STREAMLIT_PORT="8501"
DAILY_SCRIPT="daily_auto.py"
CRON_SCHEDULE="30 13 * * 1-5"           # 13h30 UTC = 9h30 ET (hiver)
                                          # En été (EDT) changer en : 30 13 * * 1-5
                                          # EDT = UTC-4, donc 9h30 ET = 13h30 UTC
                                          # EST = UTC-5, donc 9h30 ET = 14h30 UTC
# Pour gérer automatiquement heure d'été/hiver, voir note bas de script
# -----------------------------------------------------------------------------

COLOR_GREEN='\033[0;32m'
COLOR_YELLOW='\033[1;33m'
COLOR_RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${COLOR_GREEN}[SETUP]${NC} $1"; }
warn() { echo -e "${COLOR_YELLOW}[WARN] ${NC} $1"; }
err()  { echo -e "${COLOR_RED}[ERROR]${NC} $1"; exit 1; }

# === 0. Vérification architecture ============================================
log "Vérification de l'architecture..."
ARCH=$(uname -m)
if [[ "$ARCH" != "aarch64" ]]; then
    warn "Architecture détectée : $ARCH (attendu : aarch64). Continuer quand même ? (y/N)"
    read -r answer
    [[ "$answer" =~ ^[Yy]$ ]] || err "Abandon."
fi
log "Architecture : $ARCH — OK"

# === 1. Mise à jour système ===================================================
log "Mise à jour du système..."
sudo apt-get update -y
sudo apt-get upgrade -y
sudo apt-get install -y \
    curl \
    wget \
    git \
    unzip \
    software-properties-common \
    build-essential \
    libssl-dev \
    libffi-dev \
    ca-certificates \
    gnupg \
    lsb-release

# === 2. Python 3.11 ===========================================================
log "Installation de Python 3.11..."

# Ubuntu 22.04 : Python 3.10 par défaut, on installe 3.11 via deadsnakes
if ! python3.11 --version &>/dev/null 2>&1; then
    sudo add-apt-repository ppa:deadsnakes/ppa -y
    sudo apt-get update -y
    sudo apt-get install -y python3.11 python3.11-venv python3.11-dev python3.11-distutils
else
    log "Python 3.11 déjà installé : $(python3.11 --version)"
fi

# pip pour Python 3.11
if ! python3.11 -m pip --version &>/dev/null 2>&1; then
    curl -sS https://bootstrap.pypa.io/get-pip.py | sudo python3.11
fi

log "Python 3.11 : $(python3.11 --version)"

# === 3. Création du répertoire de l'app =======================================
log "Création du répertoire de l'application : $APP_DIR"
mkdir -p "$APP_DIR"
mkdir -p "$APP_DIR/data"

# === 4. Environnement virtuel Python ==========================================
log "Création de l'environnement virtuel Python..."
if [[ ! -d "$VENV_DIR" ]]; then
    python3.11 -m venv "$VENV_DIR"
fi

# Activation du venv
source "$VENV_DIR/bin/activate"

log "Mise à jour de pip dans le venv..."
pip install --upgrade pip wheel setuptools

# === 5. Installation des dépendances Python ===================================
log "Installation des dépendances Python..."

if [[ -f "$APP_DIR/requirements.txt" ]]; then
    pip install -r "$APP_DIR/requirements.txt"
else
    warn "requirements.txt non trouvé dans $APP_DIR — installation des packages de base..."
    pip install \
        "streamlit==1.56.0" \
        "pandas==3.0.2" \
        "pandas-ta==0.4.71b0" \
        "numpy==2.2.6" \
        "yfinance==1.2.1" \
        "plotly==6.7.0" \
        "pyarrow==23.0.1" \
        "apscheduler==3.10.4"
fi

deactivate
log "Dépendances Python installées."

# === 6. Configuration Streamlit ===============================================
log "Configuration de Streamlit..."
STREAMLIT_CONFIG_DIR="/home/${APP_USER}/.streamlit"
mkdir -p "$STREAMLIT_CONFIG_DIR"

cat > "$STREAMLIT_CONFIG_DIR/config.toml" << EOF
[server]
port = ${STREAMLIT_PORT}
address = "127.0.0.1"
headless = true
enableCORS = false
enableXsrfProtection = false

[browser]
gatherUsageStats = false

[theme]
base = "dark"
EOF

log "Config Streamlit écrite dans $STREAMLIT_CONFIG_DIR/config.toml"

# === 7. Service systemd pour Streamlit ========================================
log "Création du service systemd pour Streamlit..."

sudo tee /etc/systemd/system/portfolio-dashboard.service > /dev/null << EOF
[Unit]
Description=Portfolio Manager — Streamlit Dashboard
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
Environment="PATH=${VENV_DIR}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
Environment="PYTHONUNBUFFERED=1"
ExecStart=${VENV_DIR}/bin/streamlit run ${APP_DIR}/app.py \
    --server.port ${STREAMLIT_PORT} \
    --server.address 127.0.0.1 \
    --server.headless true
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable portfolio-dashboard.service
log "Service portfolio-dashboard.service créé et activé."

# === 8. Cron pour daily_auto.py ===============================================
log "Configuration du cron pour daily_auto.py..."

# Crée un script wrapper pour activer le venv
cat > "$APP_DIR/run_daily.sh" << EOF
#!/bin/bash
# Wrapper cron — active le venv et lance daily_auto.py
source ${VENV_DIR}/bin/activate
cd ${APP_DIR}
python ${DAILY_SCRIPT} >> /var/log/portfolio_daily.log 2>&1
EOF

chmod +x "$APP_DIR/run_daily.sh"

# Fichier de log
sudo touch /var/log/portfolio_daily.log
sudo chown "${APP_USER}:${APP_USER}" /var/log/portfolio_daily.log

# Ajout de la crontab (sans doublon)
CRON_JOB="${CRON_SCHEDULE} ${APP_DIR}/run_daily.sh"
(crontab -l 2>/dev/null | grep -v "run_daily.sh"; echo "$CRON_JOB") | crontab -

log "Cron configuré : $CRON_JOB"
log "Logs daily_auto.py : /var/log/portfolio_daily.log"

# Note sur la gestion heure d'été / hiver
warn "-------------------------------------------------------------------"
warn "HEURE D'ÉTÉ / HIVER (ET) :"
warn "  • EST (nov→mar) : 9h30 ET = 14h30 UTC → cron : 30 14 * * 1-5"
warn "  • EDT (mar→nov) : 9h30 ET = 13h30 UTC → cron : 30 13 * * 1-5"
warn "  Ajustez manuellement avec : crontab -e"
warn "  Ou installez un script de gestion DST (voir guide complet)"
warn "-------------------------------------------------------------------"

# === 9. Installation de cloudflared (ARM64) ===================================
log "Installation de cloudflared (ARM64)..."

if ! command -v cloudflared &>/dev/null; then
    # Méthode officielle via .deb ARM64
    CLOUDFLARED_DEB="cloudflared-linux-arm64.deb"
    wget -q "https://github.com/cloudflare/cloudflared/releases/latest/download/${CLOUDFLARED_DEB}" \
        -O "/tmp/${CLOUDFLARED_DEB}"
    sudo dpkg -i "/tmp/${CLOUDFLARED_DEB}"
    rm -f "/tmp/${CLOUDFLARED_DEB}"
    log "cloudflared installé : $(cloudflared --version)"
else
    log "cloudflared déjà installé : $(cloudflared --version)"
fi

# === 10. Firewall — iptables ==================================================
log "Configuration du firewall (iptables)..."

# Sur Oracle Cloud, on N'utilise PAS ufw.
# Le port 8501 n'a pas besoin d'être ouvert sur Internet car Cloudflare Tunnel
# utilise une connexion sortante. On ouvre seulement SSH (22) et on bloque le reste.
# Cependant, si vous voulez accès direct (test), décommentez les lignes ci-dessous.

# Autoriser loopback
sudo iptables -I INPUT -i lo -j ACCEPT 2>/dev/null || true
sudo iptables -I OUTPUT -o lo -j ACCEPT 2>/dev/null || true

# Autoriser connexions établies
sudo iptables -I INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || true

# SSH (déjà ouvert normalement, on s'assure)
sudo iptables -I INPUT -p tcp --dport 22 -j ACCEPT 2>/dev/null || true

# Streamlit (optionnel — utile pour test direct, sinon Cloudflare suffit)
# Décommentez si vous voulez accès IP:8501 direct :
# sudo iptables -I INPUT -p tcp --dport 8501 -j ACCEPT 2>/dev/null || true

# Sauvegarder les règles iptables (persistance)
sudo apt-get install -y iptables-persistent netfilter-persistent 2>/dev/null || true
sudo netfilter-persistent save 2>/dev/null || true

log "Firewall configuré."

# === 11. Résumé final =========================================================
echo ""
echo "============================================================"
echo -e "${COLOR_GREEN}  SETUP TERMINÉ — Portfolio Manager sur Oracle Cloud${NC}"
echo "============================================================"
echo ""
echo "Répertoire app      : $APP_DIR"
echo "Venv Python         : $VENV_DIR"
echo "Service systemd     : portfolio-dashboard.service"
echo "Cron daily_auto.py  : $CRON_SCHEDULE"
echo "Log daily           : /var/log/portfolio_daily.log"
echo ""
echo "PROCHAINES ÉTAPES :"
echo ""
echo "1. Transférer vos fichiers depuis Windows (voir guide)"
echo "   > scp -r -i ~/.ssh/oracle_key C:\\chemin\\portfolio_manager\\ ubuntu@<IP>:~/"
echo ""
echo "2. Configurer Cloudflare Tunnel :"
echo "   > cloudflared tunnel login"
echo "   > cloudflared tunnel create portfolio-tunnel"
echo "   > cloudflared tunnel route dns portfolio-tunnel dashboard.votre-domaine.com"
echo "   > sudo cloudflared service install"
echo ""
echo "3. Démarrer le dashboard Streamlit :"
echo "   > sudo systemctl start portfolio-dashboard"
echo "   > sudo systemctl status portfolio-dashboard"
echo ""
echo "4. Vérifier le cron :"
echo "   > crontab -l"
echo ""
echo "5. Tester daily_auto.py manuellement :"
echo "   > $APP_DIR/run_daily.sh"
echo ""
echo "============================================================"
