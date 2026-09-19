#!/usr/bin/env bash
# Active (ou desactive) la mise a jour d'A Quai depuis le navigateur (Administration > « Mettre a jour »).
#
#   sudo bash setup/install-web-update.sh            # installe, puis demande confirmation avant de redemarrer le service
#   sudo bash setup/install-web-update.sh --yes      # sans question
#   sudo bash setup/install-web-update.sh --uninstall
#
# Ce que ca fait :
#   1. cree le dossier <donnees>/update, propriete de l'utilisateur du service (l'application y depose la demande) ;
#   2. installe deux unites systemd : dotation-update.path (surveille la demande) et dotation-update.service (lance
#      deploy.sh ou deploy-dev.sh selon la branche installee, en root, avec --from-web) ;
#   3. ajoute APP_ALLOW_WEB_UPDATE=1 au service dotation (fichier .d/web-update.conf) et le redemarre.
# L'application ne recoit AUCUN droit root : elle depose seulement un fichier ; c'est systemd qui agit.
# Variables facultatives : APP_DIR (defaut : dossier parent de ce script), SERVICE (defaut : dotation).
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SERVICE="${SERVICE:-dotation}"
UNIT_DIR="${INSTALL_UNIT_DIR:-/etc/systemd/system}"
TEMPLATES="$APP_DIR/setup/systemd"
YES=0
UNINSTALL=0
for arg in "$@"; do
    case "$arg" in
        --yes) YES=1 ;;
        --uninstall) UNINSTALL=1 ;;
        *) echo "Usage : sudo bash setup/install-web-update.sh [--yes] [--uninstall]" >&2; exit 2 ;;
    esac
done

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
fail() { printf '\n\033[31mERREUR : %s\033[0m\n' "$*" >&2; exit 1; }

# Le controle « root » n'est ignore que pour les tests automatiques (DEPLOY_TEST=1).
if [ "${DEPLOY_TEST:-}" != "1" ]; then
    [ "$(id -u)" -eq 0 ] || fail "a lancer en root : sudo bash setup/install-web-update.sh"
fi
SERVICE_FILE="$UNIT_DIR/$SERVICE.service"
[ -f "$SERVICE_FILE" ] || fail "service $SERVICE introuvable ($SERVICE_FILE)"
DROPIN_DIR="$UNIT_DIR/$SERVICE.service.d"

restart_service() {
    if [ "$YES" -eq 1 ]; then
        answer="o"
    else
        printf 'Redemarrer le service %s maintenant (indisponible quelques secondes) ? [o/N] ' "$SERVICE"
        read -r answer || answer="n"
    fi
    case "$answer" in
        o|O|y|Y) systemctl restart "$SERVICE" && echo "  service redemarre" ;;
        *) echo "  pense a redemarrer : systemctl restart $SERVICE" ;;
    esac
}

if [ "$UNINSTALL" -eq 1 ]; then
    say "Desactivation de la mise a jour depuis le navigateur"
    systemctl disable --now dotation-update.path 2>/dev/null || true
    rm -f "$UNIT_DIR/dotation-update.path" "$UNIT_DIR/dotation-update.service" "$DROPIN_DIR/web-update.conf"
    rmdir "$DROPIN_DIR" 2>/dev/null || true
    systemctl daemon-reload
    restart_service
    echo "Fait. Le bouton n'apparait plus ; le bandeau « nouvelle version » reste (desactivable : APP_UPDATE_CHECK=0)."
    exit 0
fi

# Utilisateur, dossier de donnees et branche : lus dans le service et dans le depot, pas devines.
APP_USER="$(sed -n 's/^User=\(.*\)$/\1/p' "$SERVICE_FILE" | head -1)"
APP_GROUP="$(sed -n 's/^Group=\(.*\)$/\1/p' "$SERVICE_FILE" | head -1)"
APP_USER="${APP_USER:-root}"
APP_GROUP="${APP_GROUP:-$APP_USER}"
DATA_DIR="$(sed -n 's/^Environment=.*APP_DATA_DIR=\([^" ]*\).*/\1/p' "$SERVICE_FILE" | head -1)"
DATA_DIR="${DATA_DIR:-$APP_DIR/backend}"
BRANCH="$(git -C "$APP_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo prod)"
if [ "$BRANCH" = "dev" ]; then DEPLOY_SCRIPT="deploy-dev.sh"; else DEPLOY_SCRIPT="deploy.sh"; fi
[ -f "$APP_DIR/$DEPLOY_SCRIPT" ] || fail "$APP_DIR/$DEPLOY_SCRIPT introuvable : mettez d'abord l'application a jour (git pull)"
[ -f "$TEMPLATES/dotation-update.path" ] && [ -f "$TEMPLATES/dotation-update.service" ] || fail "modeles systemd introuvables dans $TEMPLATES"

echo "Service : $SERVICE (utilisateur $APP_USER) | donnees : $DATA_DIR | script : $DEPLOY_SCRIPT (branche $BRANCH)"

say "1/3 Dossier de demande"
mkdir -p "$DATA_DIR/update"
chown "$APP_USER:$APP_GROUP" "$DATA_DIR/update"
chmod 755 "$DATA_DIR/update"
echo "  $DATA_DIR/update (proprietaire $APP_USER)"

say "2/3 Unites systemd"
render() { sed -e "s|@DATA_DIR@|$DATA_DIR|g" -e "s|@APP_DIR@|$APP_DIR|g" -e "s|@DEPLOY_SCRIPT@|$DEPLOY_SCRIPT|g" "$1" > "$2"; chmod 644 "$2"; }
render "$TEMPLATES/dotation-update.path" "$UNIT_DIR/dotation-update.path"
render "$TEMPLATES/dotation-update.service" "$UNIT_DIR/dotation-update.service"
mkdir -p "$DROPIN_DIR"
printf '[Service]\nEnvironment="APP_ALLOW_WEB_UPDATE=1"\n' > "$DROPIN_DIR/web-update.conf"
chmod 644 "$DROPIN_DIR/web-update.conf"
# git refuse d'operer en root dans un depot appartenant a un autre utilisateur : on l'autorise explicitement pour ce dossier.
git config --global --get-all safe.directory 2>/dev/null | grep -qxF "$APP_DIR" || git config --global --add safe.directory "$APP_DIR" 2>/dev/null || true
systemctl daemon-reload
systemctl enable --now dotation-update.path
echo "  dotation-update.path actif (surveille $DATA_DIR/update/request.json)"

say "3/3 Activation dans l'application"
restart_service
echo
echo "Termine. Dans Administration, le bouton « Mettre a jour maintenant » apparait quand une nouvelle version existe."
echo "Pour desactiver : sudo bash setup/install-web-update.sh --uninstall"
