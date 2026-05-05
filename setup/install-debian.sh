#!/bin/bash
# Installation automatique d'À Quai sur Debian/Ubuntu
# Usage: sudo bash install-debian.sh

set -e

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="/opt/dotation"
GIT_REPO="https://github.com/roussim974100/dotation.git"
GIT_BRANCH="main"

echo -e "${GREEN}🌊 Installation d'À Quai${NC}"
echo "=================================================="

# Vérifier root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}❌ Ce script doit être exécuté en tant que root${NC}"
   exit 1
fi

# Vérifier l'OS
if ! grep -q "Debian\|Ubuntu" /etc/os-release; then
    echo -e "${RED}❌ Ce script ne supporte que Debian/Ubuntu${NC}"
    exit 1
fi

echo -e "${YELLOW}📋 Vérification des prérequis...${NC}"

# Vérifier/installer Python 3.11
if ! command -v python3.11 &> /dev/null; then
    echo "  📦 Installation de Python 3.11..."
    apt-get update
    apt-get install -y python3.11 python3.11-venv python3.11-dev
fi
echo -e "  ${GREEN}✓${NC} Python 3.11"

# Vérifier/installer git
if ! command -v git &> /dev/null; then
    echo "  📦 Installation de git..."
    apt-get install -y git
fi
echo -e "  ${GREEN}✓${NC} git"

# Vérifier/installer nginx
if ! command -v nginx &> /dev/null; then
    echo "  📦 Installation de nginx..."
    apt-get install -y nginx
fi
echo -e "  ${GREEN}✓${NC} nginx"

# Vérifier/installer curl
if ! command -v curl &> /dev/null; then
    apt-get install -y curl
fi

echo ""
echo -e "${YELLOW}📥 Préparation du répertoire d'installation...${NC}"

# Créer/nettoyer le répertoire
if [ -d "$INSTALL_DIR" ]; then
    echo "  📁 Répertoire existant trouvé, mise à jour..."
    cd "$INSTALL_DIR"
    git fetch origin
    git checkout $GIT_BRANCH
    git pull origin $GIT_BRANCH
else
    echo "  📁 Création du répertoire $INSTALL_DIR..."
    mkdir -p "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    git clone --branch $GIT_BRANCH $GIT_REPO .
fi

echo -e "  ${GREEN}✓${NC} Code téléchargé"

echo ""
echo -e "${YELLOW}🐍 Configuration Python...${NC}"

# Créer venv
if [ ! -d "venv" ]; then
    echo "  🔧 Création de l'environnement virtuel..."
    python3.11 -m venv venv
fi

# Activer venv et installer dépendances
source venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r backend/requirements.txt

echo -e "  ${GREEN}✓${NC} Dépendances installées"

echo ""
echo -e "${YELLOW}🔧 Configuration du serveur...${NC}"

# Configurer permissions
echo "  ⚙️  Configuration des permissions..."
chown -R www-data:www-data "$INSTALL_DIR"
chmod -R 755 "$INSTALL_DIR"
chmod -R 775 "$INSTALL_DIR/backend/data" 2>/dev/null || mkdir -p "$INSTALL_DIR/backend/data"
chmod -R 775 "$INSTALL_DIR/backend/data"

# Configurer nginx
echo "  ⚙️  Configuration de nginx..."
cat > /etc/nginx/sites-available/dotation <<'NGINX_CONF'
upstream dotation_app {
    server 127.0.0.1:5000;
}

server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    location / {
        proxy_pass http://dotation_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
    }

    location /assets/ {
        alias /opt/dotation/frontend/assets/;
        expires 7d;
    }

    location /css/ {
        alias /opt/dotation/frontend/css/;
        expires 1h;
    }

    location /js/ {
        alias /opt/dotation/frontend/js/;
        expires 1h;
    }
}
NGINX_CONF

# Activer la configuration nginx
if [ -L /etc/nginx/sites-enabled/dotation ]; then
    rm /etc/nginx/sites-enabled/dotation
fi
ln -s /etc/nginx/sites-available/dotation /etc/nginx/sites-enabled/dotation

# Supprimer la config par défaut
rm -f /etc/nginx/sites-enabled/default

# Tester nginx
nginx -t || exit 1
systemctl restart nginx

echo -e "  ${GREEN}✓${NC} nginx configuré"

# Créer service systemd
echo "  ⚙️  Création du service systemd..."
cat > /etc/systemd/system/dotation.service <<'SYSTEMD_CONF'
[Unit]
Description=À Quai - Gestion des dotations matérielles
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/dotation
Environment="FLASK_ENV=production"
ExecStart=/opt/dotation/venv/bin/python /opt/dotation/backend/app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SYSTEMD_CONF

systemctl daemon-reload
systemctl enable dotation
systemctl restart dotation

echo -e "  ${GREEN}✓${NC} Service systemd créé et activé"

echo ""
echo -e "${GREEN}✅ Installation complétée avec succès !${NC}"
echo ""
echo "=================================================="
echo -e "${GREEN}🌊 À Quai est prêt !${NC}"
echo "=================================================="
echo ""
echo "📍 Accès à l'application :"
echo -e "   ${YELLOW}http://localhost${NC}"
echo ""
echo "🔐 Identifiants par défaut :"
echo "   Utilisateur : ${YELLOW}admin${NC}"
echo "   Mot de passe : ${YELLOW}admin${NC}"
echo ""
echo "📖 Première utilisation :"
echo "   1. Accédez à http://localhost/login"
echo "   2. Connectez-vous avec admin/admin"
echo "   3. Suivez le wizard de configuration"
echo ""
echo "📊 Vérifier le statut :"
echo "   systemctl status dotation"
echo ""
echo "📝 Voir les logs :"
echo "   journalctl -u dotation -f"
echo ""
echo "=================================================="
