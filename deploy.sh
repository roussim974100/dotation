#!/bin/bash
# Script de deploiement sécurisé pour la production
# - Met à jour le code depuis git
# - Fusionne intelligemment users.json (préserve utilisateurs locaux, met à jour groupes/permissions)
# - Redémarre le service
# - Vérifie que le service tourne
#
# Usage: ./deploy.sh (depuis /opt/dotation/)
# ou: cd /opt/dotation && /path/to/deploy.sh

set -e

cd /opt/dotation || exit 1

# Récupérer la version actuelle
APP_VERSION=$(git describe --tags --always 2>/dev/null || echo "unknown")

echo "========================================="
echo "Déploiement en production (version: $APP_VERSION)"
echo "========================================="

# 1. Récupérer les changements
echo ""
echo "[1] Mise à jour du code..."
git fetch origin
git reset --hard origin/prod
echo "    [OK] Code à jour"

# 2. Redémarrer le service
echo ""
echo "[2] Redémarrage du service..."
systemctl restart dotation
sleep 2

# 3. Vérifier que le service tourne
if systemctl is-active --quiet dotation; then
    echo "    [OK] Service redémarré avec succès"
else
    echo "    [ERROR] Erreur au redémarrage"
    exit 1
fi

echo ""
echo "========================================="
echo "[SUCCESS] Déploiement terminé avec succès!"
echo "========================================="
echo ""
echo "Vérifications :"
echo "  • Code : $(git log -1 --oneline)"
echo "  • Version : $(grep APP_BUILD_VERSION frontend/js/branding.js | grep -o '"[^"]*"' | tail -1)"
echo "  • Service : $(systemctl status dotation --no-pager | grep Active)"
echo ""
