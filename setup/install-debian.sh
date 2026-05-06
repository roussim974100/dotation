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

echo ""
echo -e "${YELLOW}🔄 Mise à jour du système${NC}"
read -p "Voulez-vous mettre à jour les packages du système ? (y/n) [recommandé] : " -n 1 -r UPDATE_SYS
echo
if [[ $UPDATE_SYS =~ ^[Yy]$ ]]; then
    echo "  📦 Mise à jour du système en cours..."
    apt-get update || {
        echo -e "  ${RED}❌ Erreur lors de apt-get update${NC}"
        exit 1
    }
    apt-get upgrade -y || {
        echo -e "  ${RED}❌ Erreur lors de apt-get upgrade${NC}"
        exit 1
    }
    echo -e "  ${GREEN}✓${NC} Système mis à jour"
else
    echo -e "  ${YELLOW}⚠️  Mise à jour système ignorée${NC}"
fi

echo ""
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

# Installer python3-venv et venv spécifique à la version
echo "  📦 Installation de python3-venv..."
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
apt-get install -y python3-venv python3.${PYTHON_VERSION}-venv || {
    # Essayer sans la version spécifique
    apt-get install -y python3-venv || {
        echo -e "  ${RED}❌ Impossible d'installer python3-venv${NC}"
        exit 1
    }
}

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

# Créer venv avec gestion d'erreurs robuste
if [ ! -d "venv" ]; then
    echo "  🔧 Création de l'environnement virtuel..."

    # Essayer de créer le venv
    if python3 -m venv venv 2>/dev/null; then
        PYTHON_USED=$(./venv/bin/python --version 2>&1)
        echo "  ✓ venv créé avec $PYTHON_USED"
    else
        echo -e "  ${RED}❌ Impossible de créer l'environnement virtuel${NC}"
        exit 1
    fi
fi

# Vérifier et fixer pip s'il manque
if [ ! -f "venv/bin/pip" ] || [ ! -f "venv/bin/pip3" ]; then
    echo "  ⚠️  pip manquant, tentative de correction..."

    # Essayer d'installer python3-pip
    apt-get install -y python3-pip || {
        echo -e "  ${YELLOW}⚠️  python3-pip non disponible${NC}"
    }

    # Réessayer de créer le venv avec upgrade
    rm -rf venv
    if ! python3 -m venv --upgrade venv 2>/dev/null; then
        python3 -m venv venv
    fi

    # Dernier recours : installer pip manuellement
    if [ ! -f "venv/bin/pip" ]; then
        echo "  🔧 Installation manuelle de pip..."
        ./venv/bin/python -m ensurepip --upgrade 2>/dev/null || {
            ./venv/bin/python -m ensurepip 2>/dev/null || {
                echo -e "  ${RED}❌ Impossible d'installer pip${NC}"
                exit 1
            }
        }
    fi
fi

# Vérification finale
if [ ! -f "venv/bin/pip" ] && [ ! -f "venv/bin/pip3" ]; then
    echo -e "  ${RED}❌ Impossible de créer pip dans venv${NC}"
    echo "  Essayez : sudo apt-get install -y python3.${PYTHON_VERSION}-venv python3-pip"
    exit 1
fi

# Activer venv et installer dépendances
PIP_CMD="venv/bin/pip"
if [ ! -f "$PIP_CMD" ]; then
    PIP_CMD="venv/bin/pip3"
fi

echo "  📦 Mise à jour de pip..."
$PIP_CMD install --upgrade pip setuptools wheel 2>&1 | grep -i "successfully\|require" || true

# Vérifier que requirements.txt existe
if [ ! -f "backend/requirements.txt" ]; then
    echo -e "  ${RED}❌ backend/requirements.txt introuvable${NC}"
    exit 1
fi

echo "  📦 Installation des dépendances d'À Quai..."
if ! $PIP_CMD install -r backend/requirements.txt; then
    echo -e "  ${YELLOW}⚠️  Première tentative d'installation échouée, nouvelle tentative...${NC}"
    sleep 2
    if ! $PIP_CMD install -r backend/requirements.txt; then
        echo -e "  ${RED}❌ Impossible d'installer les dépendances${NC}"
        exit 1
    fi
fi

echo "  📦 Installation de Gunicorn..."
if ! $PIP_CMD install gunicorn; then
    echo -e "  ${YELLOW}⚠️  Première tentative échouée, nouvelle tentative...${NC}"
    sleep 2
    if ! $PIP_CMD install gunicorn; then
        echo -e "  ${RED}❌ Impossible d'installer Gunicorn${NC}"
        exit 1
    fi
fi

echo -e "  ${GREEN}✓${NC} Dépendances installées"

echo ""
echo -e "${YELLOW}🔧 Configuration du serveur...${NC}"

# Configurer permissions
echo "  ⚙️  Configuration des permissions..."

# Créer et préparer le répertoire data
mkdir -p "$INSTALL_DIR/backend/data"
mkdir -p "$INSTALL_DIR/backend/logs"

# Fixer les permissions de manière robuste
chown -R www-data:www-data "$INSTALL_DIR" || {
    echo -e "  ${YELLOW}⚠️  Impossible de changer le propriétaire, essai avec sudo...${NC}"
    sudo chown -R www-data:www-data "$INSTALL_DIR"
}

# Permissions pour que www-data puisse écrire
chmod -R 755 "$INSTALL_DIR"
chmod -R 775 "$INSTALL_DIR/backend/data"
chmod -R 775 "$INSTALL_DIR/backend/logs"
chmod -R 755 "$INSTALL_DIR/venv"
chmod -R 755 "$INSTALL_DIR/backend"

# Vérifier que les permissions sont correctes
if ! su - www-data -s /bin/bash -c "test -w $INSTALL_DIR/backend/data" 2>/dev/null; then
    echo -e "  ${YELLOW}⚠️  Permissions insuffisantes, correction...${NC}"
    chmod 777 "$INSTALL_DIR/backend/data"
    chmod 777 "$INSTALL_DIR/backend/logs"
fi

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

# Fixer les permissions sur les fichiers créés par init_db
echo "  ⚙️  Correction des permissions post-initialisation..."
chown -R www-data:www-data "$INSTALL_DIR/backend" || true
chmod 755 "$INSTALL_DIR/backend"
chmod 644 "$INSTALL_DIR/backend/.app_secret_key" 2>/dev/null || true
chmod 666 "$INSTALL_DIR/backend/dotation.db" 2>/dev/null || true
chmod 666 "$INSTALL_DIR/backend/users.db" 2>/dev/null || true
chmod -R 755 "$INSTALL_DIR/backend/venv" || true

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

# Démarrer le service avec vérification robuste
echo "  🚀 Démarrage du service..."
systemctl start dotation

# Attendre que le service démarre et réponde
echo "  ⏳ Attente du démarrage de l'application..."
MAX_ATTEMPTS=30
ATTEMPT=0
while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    if systemctl is-active --quiet dotation; then
        # Vérifier que l'app répond réellement
        if curl -s http://localhost:5000/ > /dev/null 2>&1; then
            echo -e "  ${GREEN}✓${NC} Service en cours d'exécution et répond"
            break
        fi
    fi

    ATTEMPT=$((ATTEMPT + 1))
    if [ $ATTEMPT -lt $MAX_ATTEMPTS ]; then
        sleep 1
    fi
done

# Vérifier le résultat final
if ! systemctl is-active --quiet dotation; then
    echo -e "  ${RED}❌ Le service n'a pas pu démarrer${NC}"
    echo ""
    echo -e "  ${YELLOW}Logs d'erreur:${NC}"
    journalctl -u dotation -n 20 --no-pager
    exit 1
elif ! curl -s http://localhost:5000/ > /dev/null 2>&1; then
    echo -e "  ${YELLOW}⚠️  Le service est actif mais ne répond pas${NC}"
    echo "  Attendez quelques secondes et vérifiez les logs:"
    echo "  journalctl -u dotation -f"
else
    echo -e "  ${GREEN}✓${NC} L'application est prête"
fi

echo ""
echo "=================================================="
echo -e "${GREEN}✅ Installation complétée avec succès !${NC}"
echo "=================================================="
echo ""

# Vérification finale
echo -e "${YELLOW}🔍 Vérifications finales...${NC}"

FINAL_CHECK=true

# Vérifier le service
echo -n "  Service À Quai : "
if systemctl is-active --quiet dotation; then
    echo -e "${GREEN}✓ En cours d'exécution${NC}"
else
    echo -e "${RED}❌ Arrêté${NC}"
    FINAL_CHECK=false
fi

# Vérifier nginx
echo -n "  Reverse proxy nginx : "
if systemctl is-active --quiet nginx; then
    echo -e "${GREEN}✓ En cours d'exécution${NC}"
else
    echo -e "${RED}❌ Arrêté${NC}"
    FINAL_CHECK=false
fi

# Vérifier que l'app répond
echo -n "  Application web : "
if curl -s http://localhost/ > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Répond correctement${NC}"
else
    echo -e "${YELLOW}⚠️  Pas encore prête, patientez...${NC}"
    FINAL_CHECK=false
fi

echo ""

if [ "$FINAL_CHECK" = true ]; then
    echo "=================================================="
    echo -e "${GREEN}🌊 À Quai est prêt et fonctionnel !${NC}"
    echo "=================================================="
    echo ""
    echo "📍 Accédez à l'application :"
    APP_IP=$(hostname -I | awk '{print $1}')
    echo -e "   🌐 ${GREEN}http://${APP_IP}${NC}"
    echo ""
    echo "🔐 Identifiants par défaut :"
    echo "   📧 Utilisateur : ${GREEN}admin${NC}"
    echo "   🔑 Mot de passe : ${GREEN}admin${NC}"
    echo ""
    echo "⚠️  Changez le mot de passe admin immédiatement après la première connexion !"
    echo ""
else
    echo "=================================================="
    echo -e "${YELLOW}⚠️  Installation complétée mais l'app n'est pas encore prête${NC}"
    echo "=================================================="
    echo ""
    echo "Attendez quelques secondes et vérifiez les logs :"
    echo -e "   ${YELLOW}journalctl -u dotation -f${NC}"
    echo ""
    echo "En cas d'erreur, consultez :"
    echo -e "   ${YELLOW}journalctl -u dotation -n 50${NC}"
    echo ""
fi

echo "=================================================="
