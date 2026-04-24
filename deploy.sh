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

# 1. Sauvegarder la config locale AVANT git reset
echo ""
echo "[1] Sauvegarde de la configuration locale..."
if [ -f "backend/users.json" ]; then
    cp "backend/users.json" "backend/users.json.backup.$(date +%Y%m%d_%H%M%S).pre-reset"
    echo "    [OK] Config locale sauvegardée (pre-reset)"
else
    echo "    [WARN] Aucune config locale trouvée"
fi

# 2. Récupérer les changements
echo ""
echo "[2] Mise à jour du code..."
git fetch origin
git reset --hard origin/main
echo "    [OK] Code à jour"

# 3. Fusionner les configurations users
echo ""
echo "[3] Fusion des configurations utilisateurs..."
python3 scripts/merge-users-config.py
if [ $? -ne 0 ]; then
    echo "    [ERROR] Erreur lors de la fusion - abandon"
    exit 1
fi
echo "    [OK] Fusion complète"

# 4. Redémarrer le service
echo ""
echo "[4] Redémarrage du service..."
systemctl restart dotation
sleep 2

# 5. Vérifier que le service tourne
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
