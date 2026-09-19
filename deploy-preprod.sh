#!/usr/bin/env bash
# Déploiement de la PRÉPRODUCTION (branche preprod, figée).
#
#   sudo bash deploy-preprod.sh            # déploie la branche « preprod »
#   sudo bash deploy-preprod.sh --force    # écrase les modifications locales de fichiers suivis par git
#
# La préproduction reçoit ce qui est PROMU depuis dev (Pull Request sur GitHub : base preprod, compare dev) et sert à valider une version, avec une copie
# de la base de production, avant qu'elle n'aille en production (deploy.sh).
#
# Ce que fait le script (voir setup/deploy-common.sh) :
#   1. sauvegarde cohérente des bases (backend/db_backups/avant_maj_<date>/)
#   2. récupère le code de origin/preprod (git fetch + reset ; refuse s'il y a des modifications locales)
#   3. installe les dépendances Python DANS LE VENV UTILISÉ PAR LE SERVICE, lu dans le fichier systemd
#   4. redémarre le service et vérifie qu'il RÉPOND ; sinon rétablit automatiquement l'ancienne version (code et bases).
# Les fichiers non suivis par git (bases .db, .app_secret_key, logos, sauvegardes) ne sont jamais touchés.
# Variables facultatives : APP_DIR (défaut : dossier du script), SERVICE (défaut : dotation).
set -euo pipefail

# Branche figée : ce script déploie TOUJOURS « preprod ».
DEPLOY_BRANCH="preprod"
DEPLOY_SCRIPT="deploy-preprod.sh"
APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
SERVICE="${SERVICE:-dotation}"
[ -f "$APP_DIR/setup/deploy-common.sh" ] || { echo "ERREUR : $APP_DIR/setup/deploy-common.sh introuvable" >&2; exit 1; }
source "$APP_DIR/setup/deploy-common.sh" "$@"
