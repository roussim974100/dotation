#!/bin/bash
# Script de déploiement sécurisé pour la production
# - Met à jour le code depuis git
# - Fusionne intelligemment users.json (préserve utilisateurs locaux)
# - Redémarre le service

set -e  # Arrêter sur erreur

cd /opt/dotation || exit 1

echo "========================================="
echo "Déploiement v3.11.2+ en production"
echo "========================================="

# 1. Récupérer les changements
echo ""
echo "[1] Mise a jour du code..."
git fetch origin
git reset --hard origin/main
echo "    [OK] Code a jour"

# 2. Fusionner les configurations users
echo ""
echo "[2] Fusion des configurations utilisateurs..."
python3 scripts/merge-users-config.py
if [ $? -ne 0 ]; then
    echo "    [ERROR] Erreur lors de la fusion - abandon"
    exit 1
fi

# 3. Redémarrer le service
echo ""
echo "[3] Redemarrage du service..."
systemctl restart dotation
sleep 2

# 4. Vérifier que le service tourne
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
echo "Vérifications :"
echo "  • Code : $(git log -1 --oneline)"
echo "  • Version : $(grep APP_BUILD_VERSION frontend/js/branding.js | grep -o '"[^"]*"' | tail -1)"
echo "  • Service : $(systemctl status dotation --no-pager | grep Active)"
echo ""
