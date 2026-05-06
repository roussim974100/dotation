#!/bin/bash
# Installation automatique d'À Quai sur Debian/Ubuntu
# Usage: sudo bash install-debian.sh
# Ou directement en root : bash install-debian.sh
# Note: Ce script n'utilise pas 'sudo -u' ; il fonctionne directement en root
# et ne dépend pas de sudo étant installé dans le conteneur.

set -Eeuo pipefail

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="/opt/dotation"
GIT_REPO="https://github.com/roussim974100/dotation.git"
GIT_BRANCH="${GIT_BRANCH:-dev}"

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

# Vérifier/installer Python 3 (flexible sur la version)
if ! command -v python3 &> /dev/null; then
    echo "  📦 Installation de Python 3..."
    apt-get update
    apt-get install -y python3 python3-venv python3-dev || {
        echo -e "  ${RED}❌ Impossible d'installer Python 3${NC}"
        exit 1
    }
fi

# Vérifier que python3 -m venv est disponible
if ! python3 -m venv --help &>/dev/null; then
    echo "  📦 Installation de python3-venv..."
    apt-get install -y python3-venv || {
        echo -e "  ${RED}❌ Impossible d'installer python3-venv${NC}"
        exit 1
    }
fi

PYTHON_VERSION=$(python3 --version 2>&1)
echo -e "  ${GREEN}✓${NC} $PYTHON_VERSION installé"

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
    if python3 -m venv venv 2>/dev/null; then
        PYTHON_USED=$(./venv/bin/python --version 2>&1)
        echo "  ✓ venv créé avec $PYTHON_USED"
    else
        echo -e "  ${RED}❌ Impossible de créer l'environnement virtuel${NC}"
        exit 1
    fi
fi

# Vérifier que pip existe
if [ ! -f "venv/bin/pip" ]; then
    echo -e "  ${RED}❌ pip n'a pas pu être créé dans venv${NC}"
    exit 1
fi

# Activer venv et installer dépendances
source venv/bin/activate

echo "  📦 Mise à jour de pip..."
pip install --upgrade pip setuptools wheel 2>&1 | grep -i "successfully\|require" || true

echo "  📦 Installation des dépendances d'À Quai..."
if [ -f "backend/requirements.txt" ]; then
    pip install -r backend/requirements.txt || {
        echo -e "  ${RED}⚠️  Erreur lors de l'installation des dépendances${NC}"
        exit 1
    }
else
    echo -e "  ${RED}❌ backend/requirements.txt not found${NC}"
    exit 1
fi

echo "  📦 Installation de Gunicorn..."
pip install gunicorn || {
    echo -e "  ${RED}⚠️  Erreur lors de l'installation de Gunicorn${NC}"
    exit 1
}

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

# Initialiser la base de données
echo "  🗄️  Initialisation de la base de données..."
cd "$INSTALL_DIR/backend"
source "$INSTALL_DIR/venv/bin/activate"
"$INSTALL_DIR/venv/bin/python" -c "from app import init_db, init_users_db; init_db(); init_users_db()" || {
    echo -e "  ${RED}❌ Erreur lors de l'initialisation de la base${NC}"
    exit 1
}

echo -e "  ${GREEN}✓${NC} Base de données initialisée"

# Créer service systemd
echo "  ⚙️  Création du service systemd..."

# Créer le fichier service
cat > /etc/systemd/system/dotation.service <<'SYSTEMD_CONF'
[Unit]
Description=À Quai - Gestion des dotations matérielles
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/dotation/backend
Environment="FLASK_ENV=production"
Environment="PYTHONUNBUFFERED=1"
Environment="HOME=/opt/dotation/backend/data"
ExecStart=/opt/dotation/venv/bin/gunicorn -w 4 -b 127.0.0.1:5000 --timeout 120 --access-logfile - --error-logfile - app:app
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SYSTEMD_CONF

# Vérifier que le fichier a été créé
if [ ! -f /etc/systemd/system/dotation.service ]; then
    echo -e "  ${RED}❌ Impossible de créer le service systemd${NC}"
    exit 1
fi

echo -e "  ${GREEN}✓${NC} Service systemd créé"

# Recharger systemd et activer le service
systemctl daemon-reload
if ! systemctl enable dotation; then
    echo -e "  ${RED}⚠️  Erreur lors de l'activation du service${NC}"
fi

echo -e "  ${GREEN}✓${NC} Service activé et prêt au démarrage"

# Démarrer le service
echo "  🚀 Démarrage du service..."
if systemctl start dotation; then
    sleep 2
    if systemctl is-active --quiet dotation; then
        echo -e "  ${GREEN}✓${NC} Service en cours d'exécution"
    else
        echo -e "  ${RED}⚠️  Service n'a pas pu démarrer${NC}"
        echo "  Vérifiez les logs: journalctl -u dotation -n 20"
    fi
else
    echo -e "  ${RED}⚠️  Erreur au démarrage du service${NC}"
fi

echo ""
echo -e "${GREEN}✅ Installation complétée !${NC}"
echo ""
echo "=================================================="
echo -e "${YELLOW}🔍 Vérification du statut...${NC}"
echo "=================================================="

# Vérifier le service
echo -n "  Service À Quai : "
if systemctl is-active --quiet dotation; then
    echo -e "${GREEN}✓ En cours d'exécution${NC}"
else
    echo -e "${RED}❌ Arrêté${NC}"
    echo "    Redémarrer avec: systemctl restart dotation"
fi

# Vérifier nginx
echo -n "  Reverse proxy nginx : "
if systemctl is-active --quiet nginx; then
    echo -e "${GREEN}✓ En cours d'exécution${NC}"
else
    echo -e "${RED}❌ Arrêté${NC}"
fi

# Vérifier le port 5000
echo -n "  Port 5000 (Flask) : "
if netstat -tlnp 2>/dev/null | grep -q ":5000 "; then
    echo -e "${GREEN}✓ Écoute active${NC}"
else
    echo -e "${YELLOW}⚠️  Pas de réponse (l'app peut démarrer en retard)${NC}"
fi

# Attendre un peu que l'app démarre
sleep 3

echo ""
echo "=================================================="
echo -e "${GREEN}🌊 À Quai est prêt !${NC}"
echo "=================================================="
echo ""
echo "📍 Accès à l'application :"
echo -e "   ${YELLOW}http://localhost${NC}"
echo "   ou"
echo -e "   ${YELLOW}http://$(hostname -I | awk '{print $1}')${NC}"
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
