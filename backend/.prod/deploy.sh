#!/bin/bash
# Script de deploiement securise pour la production
# - Met a jour le code depuis git
# - Fusionne intelligemment users.json (preserve utilisateurs locaux, met a jour groupes/permissions)
# - Redémarre le service
# - Verifie que le service tourne

set -e

cd /opt/dotation || exit 1

# Recuperer la version actuelle
APP_VERSION=$(git describe --tags --always 2>/dev/null || echo "unknown")

echo "========================================="
echo "Deploiement en production (version: $APP_VERSION)"
echo "========================================="

# 1. Sauvegarder la config locale AVANT git reset
echo ""
echo "[1] Sauvegarde de la configuration locale..."
if [ -f "backend/users.json" ]; then
    cp "backend/users.json" "backend/users.json.backup.$(date +%Y%m%d_%H%M%S)"
    echo "    [OK] Config locale sauvegardée"
else
    echo "    [WARN] Aucune config locale trouvée"
fi

# 2. Recuperer les changements
echo ""
echo "[2] Mise a jour du code..."
git fetch origin
git reset --hard origin/main
echo "    [OK] Code a jour"

# 3. Fusionner les configurations users
echo ""
echo "[3] Fusion des configurations utilisateurs..."
python3 scripts/merge-users-config.py
if [ $? -ne 0 ]; then
    echo "    [ERROR] Erreur lors de la fusion - abandon"
    exit 1
fi
echo "    [OK] Fusion complete"

# 4. Redemarrer le service
echo ""
echo "[4] Redemarrage du service..."
systemctl restart dotation
sleep 2

# 5. Verifier que le service tourne
if systemctl is-active --quiet dotation; then
    echo "    [OK] Service redémarre avec succes"
else
    echo "    [ERROR] Erreur au redemarrage"
    exit 1
fi

echo ""
echo "========================================="
echo "[SUCCESS] Deploiement termine avec succes!"
echo "========================================="
echo ""
echo "Verifications :"
echo "  • Code : $(git log -1 --oneline)"
echo "  • Version : $(grep APP_BUILD_VERSION frontend/js/branding.js | grep -o '"[^"]*"' | tail -1)"
echo "  • Service : $(systemctl status dotation --no-pager | grep Active)"
echo ""
