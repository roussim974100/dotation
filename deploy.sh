#!/usr/bin/env bash
# Déploiement de la PRODUCTION (branche prod, figée).
#
#   sudo bash deploy.sh            # déploie la branche « prod »
#   sudo bash deploy.sh --force    # écrase les modifications locales de fichiers suivis par git
#
# Ce que fait le script (voir setup/deploy-common.sh) :
#   1. sauvegarde cohérente des bases (backend/db_backups/avant_maj_<date>/)
#   2. récupère le code de origin/prod (git fetch + reset ; refuse s'il y a des modifications locales)
#   3. installe les dépendances Python DANS LE VENV UTILISÉ PAR LE SERVICE, lu dans le fichier systemd
#   4. redémarre le service et vérifie qu'il RÉPOND ; sinon affiche l'erreur et les commandes de retour arrière.
# Les fichiers non suivis par git (bases .db, .app_secret_key, logos, sauvegardes) ne sont jamais touchés.
# Variables facultatives : APP_DIR (défaut : dossier du script), SERVICE (défaut : dotation).
set -euo pipefail

# Branche figée : ce script déploie TOUJOURS « prod ».
DEPLOY_BRANCH="prod"
DEPLOY_SCRIPT="deploy.sh"
APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
SERVICE="${SERVICE:-dotation}"
[ -f "$APP_DIR/setup/deploy-common.sh" ] || { echo "ERREUR : $APP_DIR/setup/deploy-common.sh introuvable" >&2; exit 1; }
source "$APP_DIR/setup/deploy-common.sh" "$@"
