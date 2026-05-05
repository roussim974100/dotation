#!/bin/bash
# Installation automatique d'A Quai sur Debian/Ubuntu
# Usage:
#   sudo bash setup/install-debian.sh
#   sudo GIT_BRANCH=main bash setup/install-debian.sh

set -Eeuo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

INSTALL_DIR="${INSTALL_DIR:-/opt/dotation}"
GIT_REPO="${GIT_REPO:-https://github.com/roussim974100/dotation.git}"
GIT_BRANCH="${GIT_BRANCH:-dev}"
APP_USER="${APP_USER:-www-data}"
APP_HOST="${APP_HOST:-127.0.0.1}"
APP_PORT="${APP_PORT:-5000}"

log() { echo -e "${YELLOW}$*${NC}"; }
ok() { echo -e "  ${GREEN}✓${NC} $*"; }
fail() { echo -e "  ${RED}❌ $*${NC}" >&2; exit 1; }

run_apt_update_once() {
    if [ "${APT_UPDATED:-0}" != "1" ]; then
        apt-get update
        APT_UPDATED=1
    fi
}

install_packages() {
    run_apt_update_once
    DEBIAN_FRONTEND=noninteractive apt-get install -y "$@"
}

choose_python() {
    for candidate in python3.11 python3.10 python3; do
        if command -v "$candidate" >/dev/null 2>&1; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

create_verified_venv() {
    local python_bin="$1"
    local venv_dir="$2"

    rm -rf "$venv_dir"
    "$python_bin" -m venv "$venv_dir"
    "$venv_dir/bin/python" -m ensurepip --upgrade >/dev/null 2>&1 || true
    "$venv_dir/bin/python" -m pip --version >/dev/null 2>&1
}

echo -e "${GREEN}Installation d'A Quai${NC}"
echo "=================================================="

if [[ $EUID -ne 0 ]]; then
    fail "Ce script doit etre execute en tant que root"
fi

if ! grep -qiE "Debian|Ubuntu" /etc/os-release; then
    fail "Ce script ne supporte que Debian/Ubuntu"
fi

log "Verification des prerequis..."
install_packages git curl ca-certificates nginx net-tools python3 python3-venv python3-pip python3-dev

if command -v python3.11 >/dev/null 2>&1; then
    install_packages python3.11-venv python3.11-dev || true
fi

if command -v python3.10 >/dev/null 2>&1; then
    install_packages python3.10-venv python3.10-dev || true
fi

PYTHON_BIN="$(choose_python)" || fail "Python 3 est introuvable apres installation des paquets"
ok "Python detecte: $($PYTHON_BIN --version 2>&1)"
ok "git: $(git --version)"
ok "nginx: $(nginx -v 2>&1)"

log "Preparation du repertoire d'installation..."
if [ -d "$INSTALL_DIR/.git" ]; then
    cd "$INSTALL_DIR"
    git config --global --add safe.directory "$INSTALL_DIR" >/dev/null 2>&1 || true
    git remote set-url origin "$GIT_REPO"
    git fetch origin "$GIT_BRANCH"
    git checkout -B "$GIT_BRANCH" "origin/$GIT_BRANCH"
else
    rm -rf "$INSTALL_DIR"
    mkdir -p "$INSTALL_DIR"
    git clone --branch "$GIT_BRANCH" "$GIT_REPO" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi
git config --global --add safe.directory "$INSTALL_DIR" >/dev/null 2>&1 || true
DEPLOY_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
DEPLOY_COMMIT="$(git rev-parse --short HEAD)"
ok "Code deploye: branche $DEPLOY_BRANCH, commit $DEPLOY_COMMIT"

log "Configuration Python..."
if [ ! -x "venv/bin/python" ] || ! venv/bin/python -m pip --version >/dev/null 2>&1; then
    echo "  Creation de l'environnement virtuel..."
    if ! create_verified_venv "$PYTHON_BIN" "venv"; then
        echo "  Le venv a echoue avec $PYTHON_BIN, reinstallation de python3-venv..."
        install_packages python3-venv python3-pip python3-dev
        create_verified_venv python3 "venv" || fail "Impossible de creer un venv Python fonctionnel"
    fi
fi

venv/bin/python -m pip install --upgrade pip setuptools wheel
[ -f "backend/requirements.txt" ] || fail "backend/requirements.txt introuvable"
venv/bin/python -m pip install -r backend/requirements.txt
venv/bin/python -m pip install gunicorn
ok "Dependances installees"

log "Preparation des donnees et permissions..."
mkdir -p "$INSTALL_DIR/backend/data"
chown -R "$APP_USER:$APP_USER" "$INSTALL_DIR"
chmod -R u+rwX,g+rwX,o-rwx "$INSTALL_DIR/backend"
chmod -R a+rX "$INSTALL_DIR/frontend"
ok "Permissions configurees"

log "Initialisation de la base de donnees..."
cd "$INSTALL_DIR/backend"
sudo -u "$APP_USER" "$INSTALL_DIR/venv/bin/python" -c "import app; app.init_db(); app.init_users_db()"
ok "Base de donnees initialisee"

log "Creation du service systemd..."
cat > /etc/systemd/system/dotation.service <<SYSTEMD_CONF
[Unit]
Description=A Quai - Gestion des dotations materielles
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$INSTALL_DIR/backend
Environment=FLASK_ENV=production
Environment=PYTHONUNBUFFERED=1
Environment=HOME=$INSTALL_DIR/backend/data
ExecStart=$INSTALL_DIR/venv/bin/gunicorn --workers 2 --bind $APP_HOST:$APP_PORT --access-logfile - --error-logfile - app:app
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SYSTEMD_CONF

systemctl daemon-reload
systemctl enable dotation >/dev/null
ok "Service systemd cree"

log "Configuration nginx..."
cat > /etc/nginx/sites-available/dotation <<NGINX_CONF
upstream dotation_app {
    server $APP_HOST:$APP_PORT;
}

server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    client_max_body_size 20m;

    location / {
        proxy_pass http://dotation_app;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_redirect off;
    }

    location /assets/ {
        alias $INSTALL_DIR/frontend/assets/;
        expires 7d;
    }

    location /css/ {
        alias $INSTALL_DIR/frontend/css/;
        expires 1h;
    }

    location /js/ {
        alias $INSTALL_DIR/frontend/js/;
        expires 1h;
    }
}
NGINX_CONF

ln -sfn /etc/nginx/sites-available/dotation /etc/nginx/sites-enabled/dotation
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl restart nginx
ok "nginx configure"

log "Demarrage de l'application..."
systemctl restart dotation
sleep 3

log "Verification finale..."
systemctl is-active --quiet dotation || {
    journalctl -u dotation -n 80 --no-pager >&2 || true
    fail "Le service dotation n'est pas actif"
}

netstat -tlnp 2>/dev/null | grep -q ":$APP_PORT " || fail "Le port $APP_PORT n'ecoute pas"
curl -fsS "http://$APP_HOST:$APP_PORT/login" >/dev/null || fail "L'application ne repond pas directement sur le port $APP_PORT"
curl -fsS "http://127.0.0.1/login" >/dev/null || fail "nginx ne relaie pas correctement vers l'application"

APP_IP="$(hostname -I | awk '{print $1}')"

echo ""
echo -e "${GREEN}Installation completee avec succes.${NC}"
echo "=================================================="
echo "Branche: $DEPLOY_BRANCH"
echo "Commit: $DEPLOY_COMMIT"
echo "Python: $("$INSTALL_DIR/venv/bin/python" --version 2>&1)"
echo "Service: active"
echo "Ports: $APP_PORT et 80 actifs"
echo ""
echo "Acces application:"
echo "  http://localhost"
echo "  http://$APP_IP"
echo ""
echo "Identifiants par defaut:"
echo "  Utilisateur: admin"
echo "  Mot de passe: admin"
echo ""
echo "Commandes utiles:"
echo "  systemctl status dotation"
echo "  journalctl -u dotation -f"
echo "=================================================="
