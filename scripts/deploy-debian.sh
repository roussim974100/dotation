#!/usr/bin/env bash
# ============================================================================
# deploy-debian.sh — Installation complete de l'application "A Quai"
# sur un conteneur LXC Debian 12+ vierge.
#
# Usage :
#   chmod +x deploy-debian.sh
#   sudo ./deploy-debian.sh                          # installation standard (HTTP)
#   sudo ./deploy-debian.sh --behind-proxy           # derriere un reverse proxy TLS
#   sudo ./deploy-debian.sh --upgrade                # met aussi a jour les paquets systeme
#   sudo ./deploy-debian.sh --upgrade --behind-proxy # les deux
#
# --behind-proxy : nginx relaie les headers X-Forwarded-* du proxy externe
#                  au lieu de les reecrire avec les valeurs locales.
#                  A utiliser quand un HAProxy, nginx frontal ou Traefik
#                  termine le TLS en amont.
# ============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration (modifier selon l'environnement)
# ---------------------------------------------------------------------------
APP_NAME="dotation"
APP_DIR="/opt/dotation"
APP_USER="www-data"
APP_GROUP="www-data"
VENV_DIR="${APP_DIR}/.venv"
REPO_URL="https://github.com/roussim974100/dotation.git"
BRANCH="main"
SERVER_NAME="_"                # Nom de domaine nginx ("_" = toutes les requetes)
LISTEN_PORT="80"               # Port nginx
GUNICORN_PORT="5000"           # Port interne gunicorn
GUNICORN_WORKERS="2"           # Nombre de workers gunicorn

# ---------------------------------------------------------------------------
# Couleurs
# ---------------------------------------------------------------------------
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[!!]${NC} $1"; }
fail() { echo -e "${RED}[ERREUR]${NC} $1"; exit 1; }

# ---------------------------------------------------------------------------
# Parsing des arguments
# ---------------------------------------------------------------------------
OPT_UPGRADE=0
OPT_BEHIND_PROXY=0

for arg in "$@"; do
    case "${arg}" in
        --upgrade)       OPT_UPGRADE=1 ;;
        --behind-proxy)  OPT_BEHIND_PROXY=1 ;;
        *) fail "Argument inconnu : ${arg}. Options : --upgrade, --behind-proxy" ;;
    esac
done

# ---------------------------------------------------------------------------
# Verification root
# ---------------------------------------------------------------------------
if [ "$(id -u)" -ne 0 ]; then
    fail "Ce script doit etre lance avec sudo ou en root."
fi

echo ""
echo "=========================================="
echo "  Installation A Quai — Debian LXC"
if [ "${OPT_BEHIND_PROXY}" -eq 1 ]; then
echo "  Mode : derriere un reverse proxy TLS"
fi
echo "=========================================="
echo ""

# ---------------------------------------------------------------------------
# 1. Mise a jour systeme + paquets
# ---------------------------------------------------------------------------
log "Mise a jour des sources..."
apt-get update -qq

if [ "${OPT_UPGRADE}" -eq 1 ]; then
    log "Mise a jour des paquets systeme (--upgrade)..."
    apt-get upgrade -y -qq
else
    warn "Paquets systeme non mis a jour (ajouter --upgrade pour forcer)."
fi

log "Installation des paquets..."
apt-get install -y -qq \
    python3 \
    python3-venv \
    python3-pip \
    python3-dev \
    build-essential \
    nginx \
    git \
    curl

# ---------------------------------------------------------------------------
# 2. Clonage du depot
# ---------------------------------------------------------------------------
if [ -d "${APP_DIR}/.git" ]; then
    warn "Repertoire ${APP_DIR} existe deja, mise a jour (git pull)..."
    cd "${APP_DIR}"
    git pull origin "${BRANCH}"
else
    log "Clonage du depot dans ${APP_DIR}..."
    mkdir -p "${APP_DIR}"
    git clone --branch "${BRANCH}" "${REPO_URL}" "${APP_DIR}"
fi

chown -R "${APP_USER}:${APP_GROUP}" "${APP_DIR}"

# ---------------------------------------------------------------------------
# 3. Environnement virtuel Python + dependances
# ---------------------------------------------------------------------------
log "Creation du venv Python..."
python3 -m venv "${VENV_DIR}"

log "Installation des dependances Python..."
"${VENV_DIR}/bin/pip" install --upgrade pip -q
"${VENV_DIR}/bin/pip" install -r "${APP_DIR}/backend/requirements.txt" -q
"${VENV_DIR}/bin/pip" install gunicorn -q

# ---------------------------------------------------------------------------
# 4. Cle secrete applicative
# ---------------------------------------------------------------------------
SECRET_FILE="${APP_DIR}/backend/.app_secret_key"
if [ ! -f "${SECRET_FILE}" ]; then
    log "Generation de la cle secrete..."
    python3 -c "import secrets; print(secrets.token_hex(32))" > "${SECRET_FILE}"
    chown "${APP_USER}:${APP_GROUP}" "${SECRET_FILE}"
    chmod 600 "${SECRET_FILE}"
else
    warn "Cle secrete existante conservee."
fi

# ---------------------------------------------------------------------------
# 5. Permissions
# ---------------------------------------------------------------------------
log "Application des permissions..."
chown -R "${APP_USER}:${APP_GROUP}" "${APP_DIR}"
chmod 750 "${APP_DIR}/backend"
# La DB et users.json doivent etre accessibles en ecriture
touch "${APP_DIR}/backend/dotation.db"
chown "${APP_USER}:${APP_GROUP}" "${APP_DIR}/backend/dotation.db"
chmod 660 "${APP_DIR}/backend/dotation.db"

# ---------------------------------------------------------------------------
# 6. Service systemd
# ---------------------------------------------------------------------------
log "Configuration du service systemd..."
cat > /etc/systemd/system/${APP_NAME}.service << EOFSERVICE
[Unit]
Description=A Quai — Dotation Flask via Gunicorn
After=network.target

[Service]
User=${APP_USER}
Group=${APP_GROUP}
WorkingDirectory=${APP_DIR}
Environment="SESSION_COOKIE_SECURE=1"
ExecStart=${VENV_DIR}/bin/gunicorn -w ${GUNICORN_WORKERS} -b 127.0.0.1:${GUNICORN_PORT} backend.app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOFSERVICE

systemctl daemon-reload
systemctl enable "${APP_NAME}"
systemctl restart "${APP_NAME}"
log "Service ${APP_NAME} demarre."

# ---------------------------------------------------------------------------
# 7. Configuration nginx
# ---------------------------------------------------------------------------
log "Configuration de nginx..."

if [ "${OPT_BEHIND_PROXY}" -eq 1 ]; then
    # Mode reverse proxy : nginx relaie les headers X-Forwarded-* recus
    # du proxy frontal (HAProxy, nginx externe, Traefik…) sans les reecrire.
    # X-Forwarded-Proto vaut "https" cote client meme si nginx est en HTTP ici.
    cat > /etc/nginx/sites-available/${APP_NAME} << EOFNGINX
server {
    listen ${LISTEN_PORT};
    server_name ${SERVER_NAME};

    client_max_body_size 5M;

    location / {
        proxy_pass         http://127.0.0.1:${GUNICORN_PORT};
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$remote_addr;
        proxy_set_header   X-Forwarded-Proto \$http_x_forwarded_proto;
        proxy_set_header   X-Forwarded-Host  \$http_x_forwarded_host;
    }
}
EOFNGINX
    warn "Mode reverse proxy : verifier que le proxy frontal envoie bien X-Forwarded-Proto: https."
else
    # Mode standard : nginx termine lui-meme la connexion, les headers sont ecrits localement.
    cat > /etc/nginx/sites-available/${APP_NAME} << EOFNGINX
server {
    listen ${LISTEN_PORT};
    server_name ${SERVER_NAME};

    client_max_body_size 5M;

    location / {
        proxy_pass         http://127.0.0.1:${GUNICORN_PORT};
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$remote_addr;
        proxy_set_header   X-Forwarded-Proto \$scheme;
        proxy_set_header   X-Forwarded-Host  \$host;
    }
}
EOFNGINX
fi

# Activer le site, desactiver le default
ln -sf /etc/nginx/sites-available/${APP_NAME} /etc/nginx/sites-enabled/${APP_NAME}
rm -f /etc/nginx/sites-enabled/default

nginx -t 2>/dev/null || fail "Configuration nginx invalide."
systemctl enable nginx
systemctl restart nginx
log "Nginx configure et demarre."

# ---------------------------------------------------------------------------
# 8. Verification finale
# ---------------------------------------------------------------------------
echo ""
sleep 2
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:${LISTEN_PORT}/login 2>/dev/null || echo "000")

if [ "${HTTP_CODE}" = "200" ]; then
    log "Application accessible sur le port ${LISTEN_PORT} (HTTP ${HTTP_CODE})."
else
    warn "L'application repond HTTP ${HTTP_CODE}. Verifier les logs :"
    warn "  journalctl -u ${APP_NAME} -n 30"
    warn "  journalctl -u nginx -n 10"
fi

echo ""
echo "=========================================="
echo "  Installation terminee"
echo "=========================================="
echo ""
if [ "${OPT_BEHIND_PROXY}" -eq 1 ]; then
echo "  Mode          : derriere un reverse proxy TLS"
echo "  Application   : accessible via le proxy frontal (HTTPS)"
echo "  URL locale    : http://<IP_DU_LXC>:${LISTEN_PORT}  (HTTP uniquement)"
echo ""
echo "  >> Verifier que votre proxy frontal envoie :"
echo "       X-Forwarded-Proto: https"
echo "       X-Forwarded-Host:  <nom de domaine>"
echo "     Sinon : boucle de login (cookie Secure non pose)."
else
echo "  Application   : http://<IP_DU_LXC>:${LISTEN_PORT}"
fi
echo ""
echo "  Service     : systemctl status ${APP_NAME}"
echo "  Logs app    : journalctl -u ${APP_NAME} -f"
echo "  Logs nginx  : journalctl -u nginx -f"
echo ""
echo "  Mise a jour future :"
echo "    cd ${APP_DIR} && git pull"
echo "    ${VENV_DIR}/bin/pip install -r backend/requirements.txt"
echo "    sudo systemctl restart ${APP_NAME}"
echo ""
