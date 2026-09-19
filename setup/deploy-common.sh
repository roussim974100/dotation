#!/usr/bin/env bash
# Logique commune de deploy.sh (production) et deploy-dev.sh (version dev). Ne pas lancer directement.
# Attend : DEPLOY_BRANCH, APP_DIR, SERVICE ; les arguments du script appelant (--force).
# Tout est dans main() : bash lit ainsi la fonction en entier AVANT d'exécuter quoi que ce soit, ce qui protège
# contre le remplacement de ce fichier par le « git reset » qu'il exécute lui-même.

main() {
UNIT="/etc/systemd/system/${SERVICE}.service"
BRANCH="$DEPLOY_BRANCH"
FORCE=0
for arg in "$@"; do
    case "$arg" in
        --force) FORCE=1 ;;
        *) echo "Usage : sudo bash $DEPLOY_SCRIPT [--force]  (la branche déployée est toujours « $BRANCH »)" >&2; exit 2 ;;
    esac
done

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
fail() { printf '\n\033[31mERREUR : %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "à lancer en root : sudo bash $DEPLOY_SCRIPT"
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

BEFORE="$(git -C "$APP_DIR" rev-parse --short HEAD)"
VERSION_OF() { grep -o 'APP_BUILD_VERSION = "[^"]*"' "$APP_DIR/frontend/js/branding.js" 2>/dev/null | grep -o '"[^"]*"' | tr -d '"' || true; }
echo "=========================================="
echo "Déploiement de la branche $BRANCH (version actuelle : $(VERSION_OF), commit $BEFORE)"
echo "Venv du service : $VENV_BIN | port : $PORT"
echo "=========================================="

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

say "2/4 Récupération du code"
# On ignore le venv et les .pyc dans le contrôle : le venv est suivi par git et Python modifie ses .pyc en
# permanence, ce qui ne représente pas une modification locale de l'application.
DIRTY="$(git -C "$APP_DIR" status --porcelain --untracked-files=no -- . ':!backend/venv' ':!venv' ':!*.pyc')"
if [ "$FORCE" -eq 0 ] && [ -n "$DIRTY" ]; then
    printf '%s
' "$DIRTY"
    fail "des fichiers suivis par git ont été modifiés localement (liste ci-dessus). Les conserver puis relancer, ou écraser avec : sudo bash $DEPLOY_SCRIPT --force"
fi
git -C "$APP_DIR" fetch origin "$BRANCH"
git -C "$APP_DIR" checkout -q "$BRANCH" 2>/dev/null || git -C "$APP_DIR" checkout -q -B "$BRANCH" FETCH_HEAD
git -C "$APP_DIR" reset --hard FETCH_HEAD
AFTER="$(git -C "$APP_DIR" rev-parse --short HEAD)"
echo "  $BEFORE -> $AFTER"

say "3/4 Dépendances Python"
"$VENV_BIN/pip" install --quiet -r "$BACKEND/requirements.txt" || fail "installation des dépendances impossible (voir le message ci-dessus)"

say "4/4 Redémarrage"
systemctl daemon-reload
systemctl reset-failed "$SERVICE" 2>/dev/null || true
systemctl restart "$SERVICE"
for _ in $(seq 1 25); do
    sleep 1
    if curl -fsS -o /dev/null "http://127.0.0.1:$PORT/login"; then
        printf '\n\033[32m[SUCCESS] Déploiement terminé (%s -> %s, version %s). L'\''application répond sur le port %s.\033[0m\n' \
            "$BEFORE" "$AFTER" "$(VERSION_OF)" "$PORT"
        echo "  • Code : $(git -C "$APP_DIR" log -1 --oneline)"
        echo "  • Sauvegarde d'avant mise à jour : $SAVE_DIR"
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
  git -C $APP_DIR reset --hard $BEFORE
  systemctl start $SERVICE
EOF
exit 1
}

main "$@"
