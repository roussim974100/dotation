#!/usr/bin/env bash
# Mise à jour d'une installation À Quai sur Debian / Ubuntu.
#
#   sudo bash setup/update-debian.sh            # met à jour la branche actuellement installée
#   sudo bash setup/update-debian.sh main       # ou une branche précise
#
# Ce que fait le script (dans l'ordre) :
#   1. sauvegarde cohérente des bases (backend/db_backups/avant_maj_<date>/)
#   2. git pull de la branche
#   3. installe les dépendances Python DANS LE VENV UTILISÉ PAR LE SERVICE (lu dans le fichier systemd,
#      donc peu importe où il se trouve : /opt/dotation/venv ou /opt/dotation/backend/venv)
#   4. redémarre le service et vérifie qu'il répond ; sinon affiche l'erreur et la marche à suivre
#
# Variables facultatives : APP_DIR (défaut /opt/dotation), SERVICE (défaut dotation).
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/dotation}"
SERVICE="${SERVICE:-dotation}"
UNIT="/etc/systemd/system/${SERVICE}.service"

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
fail() { printf '\n\033[31mERREUR : %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "à lancer en root : sudo bash setup/update-debian.sh"
[ -d "$APP_DIR/.git" ] || fail "$APP_DIR n'est pas un dépôt git (installation non standard ?)"
[ -f "$UNIT" ] || fail "service $SERVICE introuvable ($UNIT)"

# Le venv et le port sont lus dans le service : c'est ce que gunicorn utilise réellement.
EXEC_LINE="$(grep -m1 '^ExecStart=' "$UNIT")"
GUNICORN="$(printf '%s' "$EXEC_LINE" | sed -n 's/^ExecStart=\([^ ]*gunicorn\).*/\1/p')"
[ -x "$GUNICORN" ] || fail "gunicorn introuvable dans le service ($EXEC_LINE)"
VENV_BIN="$(dirname "$GUNICORN")"
PORT="$(printf '%s' "$EXEC_LINE" | sed -n 's/.*-b [^ ]*:\([0-9]\+\).*/\1/p')"
PORT="${PORT:-5000}"
BACKEND="$APP_DIR/backend"
echo "Venv du service : $VENV_BIN | port : $PORT"

BRANCH="${1:-$(git -C "$APP_DIR" rev-parse --abbrev-ref HEAD)}"
BEFORE="$(git -C "$APP_DIR" rev-parse --short HEAD)"

say "1/4 Sauvegarde des bases"
STAMP="$(date +%Y%m%d-%H%M%S)"
SAVE_DIR="$BACKEND/db_backups/avant_maj_$STAMP"
mkdir -p "$SAVE_DIR"
"$VENV_BIN/python" - "$BACKEND" "$SAVE_DIR" <<'PY'
import os, sqlite3, sys
backend, target = sys.argv[1], sys.argv[2]
for name in ("dotation.db", "users.db"):
    source = os.path.join(backend, name)
    if not os.path.exists(source) or os.path.getsize(source) == 0:
        continue
    src = sqlite3.connect(source)
    dst = sqlite3.connect(os.path.join(target, name))
    src.backup(dst)  # copie cohérente, même si le service tourne (WAL compris)
    dst.close(); src.close()
    print("  sauvegardé :", name)
PY
echo "  -> $SAVE_DIR"

say "2/4 Récupération du code (branche $BRANCH)"
git -C "$APP_DIR" fetch origin
git -C "$APP_DIR" checkout "$BRANCH"
git -C "$APP_DIR" pull --ff-only origin "$BRANCH" || fail "git pull impossible (modifications locales ?). Voir : git -C $APP_DIR status"
AFTER="$(git -C "$APP_DIR" rev-parse --short HEAD)"
echo "  $BEFORE -> $AFTER"

say "3/4 Dépendances Python"
"$VENV_BIN/pip" install --quiet -r "$BACKEND/requirements.txt" || fail "installation des dépendances impossible (voir le message ci-dessus)"

say "4/4 Redémarrage"
systemctl daemon-reload
systemctl reset-failed "$SERVICE" 2>/dev/null || true
systemctl restart "$SERVICE"
for _ in $(seq 1 20); do
    sleep 1
    if curl -fsS -o /dev/null "http://127.0.0.1:$PORT/login"; then
        printf '\n\033[32mMise à jour réussie (%s -> %s). L'\''application répond sur le port %s.\033[0m\n' "$BEFORE" "$AFTER" "$PORT"
        echo "Sauvegarde d'avant mise à jour : $SAVE_DIR"
        exit 0
    fi
done

echo
echo "----- Dernières lignes du journal -----"
journalctl -u "$SERVICE" -n 30 --no-pager | grep -v 'systemd\[1\]' || true
cat <<EOF

L'application ne répond pas. Pour revenir en arrière :
  systemctl stop $SERVICE
  cp $SAVE_DIR/*.db $BACKEND/ && rm -f $BACKEND/*.db-wal $BACKEND/*.db-shm
  git -C $APP_DIR checkout $BEFORE
  systemctl start $SERVICE
EOF
exit 1
