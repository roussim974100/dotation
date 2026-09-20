#!/usr/bin/env bash
# Logique commune de deploy.sh (production) et deploy-dev.sh (version dev). Ne pas lancer directement.
# Attend : DEPLOY_BRANCH, APP_DIR, SERVICE, DEPLOY_SCRIPT ; les arguments du script appelant.
#   --force        écrase les modifications locales de fichiers suivis par git
#   --from-web     lancé par l'unité systemd de la mise à jour depuis le navigateur (même comportement, trace dans update/)
#   --no-rollback  ne rétablit PAS l'ancienne version en cas d'échec (pour diagnostiquer l'état cassé)
# Tout est dans main() : bash lit ainsi la fonction en entier AVANT d'exécuter quoi que ce soit, ce qui protège
# contre le remplacement de ce fichier par le « git reset » qu'il exécute lui-même.
#
# Retour arrière AUTOMATIQUE : si, après la mise à jour, l'application ne répond pas (ou si les dépendances ne s'installent
# pas), le code est remis dans l'état précédent et, si le service avait déjà redémarré sur le nouveau code (donc migré les
# bases), les bases sont restaurées depuis la sauvegarde faite juste avant. Les écritures faites pendant ces quelques minutes
# sont perdues : c'est le prix d'un retour à un état cohérent.
#
# Suivi : <données>/update/status.json (état, étape, message : lu par la page d'administration), update.log (sortie complète),
# lock.d (un seul déploiement à la fois).

main() {
UNIT="${DEPLOY_UNIT_PATH:-/etc/systemd/system/${SERVICE}.service}"
BRANCH="$DEPLOY_BRANCH"
FORCE=0
ROLLBACK=1
for arg in "$@"; do
    case "$arg" in
        --force) FORCE=1 ;;
        --from-web) ;;
        --no-rollback) ROLLBACK=0 ;;
        *) echo "Usage : sudo bash $DEPLOY_SCRIPT [--force] [--no-rollback]  (la branche déployée est toujours « $BRANCH »)" >&2; exit 2 ;;
    esac
done

STATUS_READY=0
say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
fail() {
    printf '\n\033[31mERREUR : %s\033[0m\n' "$*" >&2
    [ "$STATUS_READY" -eq 1 ] && write_status failed "" "$*"
    exit 1
}

# Le contrôle « root » n'est ignoré que pour les tests automatiques (DEPLOY_TEST=1), jamais en usage normal.
if [ "${DEPLOY_TEST:-}" != "1" ]; then
    [ "$(id -u)" -eq 0 ] || fail "à lancer en root : sudo bash $DEPLOY_SCRIPT"
fi
[ -d "$APP_DIR/.git" ] || fail "$APP_DIR n'est pas un dépôt git (installation non standard ?)"
[ -f "$UNIT" ] || fail "service $SERVICE introuvable ($UNIT)"

# Le venv, le port et le dossier de données sont lus dans le service : c'est ce que gunicorn utilise réellement.
EXEC_LINE="$(grep -m1 '^ExecStart=' "$UNIT")"
GUNICORN="$(printf '%s' "$EXEC_LINE" | sed -n 's/^ExecStart=\([^ ]*gunicorn\).*/\1/p')"
[ -x "$GUNICORN" ] || fail "gunicorn introuvable dans le service ($EXEC_LINE)"
VENV_BIN="$(dirname "$GUNICORN")"
PORT="$(printf '%s' "$EXEC_LINE" | sed -n 's/.*-b [^ ]*:\([0-9]\+\).*/\1/p')"
PORT="${PORT:-5000}"
BACKEND="$APP_DIR/backend"
DATA_DIR="$(sed -n 's/^Environment=.*APP_DATA_DIR=\([^" ]*\).*/\1/p' "$UNIT" | head -1)"
DATA_DIR="${DATA_DIR:-$BACKEND}"
UPDATE_DIR="$DATA_DIR/update"
mkdir -p "$UPDATE_DIR"
# La demande déposée par l'application est consommée tout de suite : sinon l'unité de surveillance relancerait ce script en boucle.
rm -f "$UPDATE_DIR/request.json"

VERSION_OF() { grep -o 'APP_BUILD_VERSION = "[^"]*"' "$APP_DIR/frontend/js/branding.js" 2>/dev/null | grep -o '"[^"]*"' | tr -d '"' || true; }
STARTED="$(date +%s)"
FROM_VERSION="$(VERSION_OF)"
TO_VERSION=""

write_status() {   # état (running|ok|failed|rolled_back)  étape  message
    "$VENV_BIN/python" - "$UPDATE_DIR/status.json" "$1" "$2" "$3" "$FROM_VERSION" "$TO_VERSION" "$STARTED" <<'PY' || true
import json, os, sys, time
path, state, step, message, source, target, started = sys.argv[1:8]
data = {"state": state, "step": step, "message": message, "from": source, "to": target, "started_at": float(started)}
if state != "running":
    data["finished_at"] = time.time()
temporary = path + ".tmp"
with open(temporary, "w", encoding="utf-8") as handle:
    handle.write(json.dumps(data, ensure_ascii=False))
os.replace(temporary, path)
try:
    os.chmod(path, 0o644)
except OSError:
    pass
PY
}

# Un seul déploiement à la fois (verrou portable : un dossier ; un verrou orphelin d'un processus mort est repris).
LOCK="$UPDATE_DIR/lock.d"
if ! mkdir "$LOCK" 2>/dev/null; then
    OTHER="$(cat "$LOCK/pid" 2>/dev/null || true)"
    if [ -n "$OTHER" ] && kill -0 "$OTHER" 2>/dev/null; then
        printf '\n\033[31mERREUR : un déploiement est déjà en cours (PID %s).\033[0m\n' "$OTHER" >&2
        exit 1
    fi
    rm -rf "$LOCK"
    mkdir "$LOCK" 2>/dev/null || { echo "ERREUR : verrou impossible ($LOCK)" >&2; exit 1; }
fi
echo "$$" > "$LOCK/pid"
trap 'rm -rf "$LOCK"' EXIT
# Environnement de ce serveur (dev, preprod ou prod) : lu par l'application pour la pastille et la version affichee.
# Le meme code est promu d'un environnement a l'autre, c'est donc le script de deploiement qui dit « je suis preprod ».
echo "$BRANCH" > "$DATA_DIR/environment" 2>/dev/null && chmod 644 "$DATA_DIR/environment" 2>/dev/null || true
exec > >(tee -a "$UPDATE_DIR/update.log") 2>&1
STATUS_READY=1

BEFORE="$(git -C "$APP_DIR" rev-parse --short HEAD)"
BEFORE_FULL="$(git -C "$APP_DIR" rev-parse HEAD)"
BRANCH_BEFORE="$(git -C "$APP_DIR" rev-parse --abbrev-ref HEAD)"
echo "=========================================="
echo "Déploiement de la branche $BRANCH (version actuelle : $FROM_VERSION, commit $BEFORE) - $(date '+%d/%m/%Y %H:%M:%S')"
echo "Venv du service : $VENV_BIN | port : $PORT | données : $DATA_DIR"
echo "=========================================="

# Le script tourne en root : tout fichier de base qu'il fait apparaitre (journal -wal, -shm, copies) doit rester lisible et inscriptible par
# l'utilisateur du service, sinon le service ne demarre plus. On aligne le proprietaire sur celui de la base principale (silencieux si impossible).
fix_ownership() {
    local ref="$DATA_DIR/dotation.db" f
    [ -e "$ref" ] || return 0
    for f in "$DATA_DIR"/dotation.db-wal "$DATA_DIR"/dotation.db-shm "$DATA_DIR"/users.db "$DATA_DIR"/users.db-wal "$DATA_DIR"/users.db-shm; do
        [ -e "$f" ] && chown --reference="$ref" "$f" 2>/dev/null || true
    done
    [ -d "$BACKEND/db_backups" ] && chown -R --reference="$ref" "$BACKEND/db_backups" 2>/dev/null || true
    [ -d "$DATA_DIR/db_backups" ] && chown -R --reference="$ref" "$DATA_DIR/db_backups" 2>/dev/null || true
    return 0
}

wait_healthy() {
    local attempt
    # 60 essais : sur une grosse base, le premier demarrage (migrations, verrous entre workers) peut depasser 25 s ; --max-time evite
    # qu'un curl suspendu bloque le script. Un faux echec declencherait un retour arriere inutile.
    for attempt in $(seq 1 "${DEPLOY_HEALTH_TRIES:-60}"); do
        sleep "${DEPLOY_SLEEP:-1}"
        if curl -fsS --max-time 5 -o /dev/null "http://127.0.0.1:$PORT/login"; then
            return 0
        fi
    done
    return 1
}

# Rétablit l'état d'avant : code, puis bases si le service avait déjà démarré sur le nouveau code.
rollback() {
    local reason="$1"
    write_status running "retour" "Échec ($reason) : retour à la version précédente..."
    say "RETOUR ARRIÈRE ($reason)"
    systemctl stop "$SERVICE" || true
    if [ "$RESTARTED" -eq 1 ] && [ -d "$SAVE_DIR" ]; then
        for name in dotation.db users.db; do
            if [ -f "$SAVE_DIR/$name" ]; then
                cp -f "$SAVE_DIR/$name" "$DATA_DIR/$name"
                rm -f "$DATA_DIR/$name-wal" "$DATA_DIR/$name-shm"
                echo "  base restaurée : $name"
            fi
        done
    fi
    git -C "$APP_DIR" checkout -q -f "$BRANCH_BEFORE" 2>/dev/null || true
    git -C "$APP_DIR" reset -q --hard "$BEFORE_FULL"
    echo "  code remis à : $BEFORE"
    "$VENV_BIN/pip" install --quiet -r "$BACKEND/requirements.txt" || echo "  (dépendances de l'ancienne version : vérification impossible)"
    systemctl reset-failed "$SERVICE" 2>/dev/null || true
    systemctl start "$SERVICE" || true
    TO_VERSION="$FROM_VERSION"
    if wait_healthy; then
        write_status rolled_back "" "La mise à jour a échoué ($reason) ; l'ancienne version ($FROM_VERSION) a été rétablie et répond."
        printf '\n\033[33mRetour arrière réussi : l'\''ancienne version répond de nouveau.\033[0m\n'
    else
        write_status failed "" "Échec ET retour arrière impossible ($reason) : intervention manuelle nécessaire. Sauvegarde : $SAVE_DIR"
        printf '\n\033[31mLe retour arrière n'\''a pas suffi : intervention manuelle nécessaire. Sauvegarde : %s\033[0m\n' "$SAVE_DIR" >&2
    fi
}

# Échec APRÈS modification du code : retour arrière automatique (sauf --no-rollback).
abort_after_change() {
    local reason="$1"
    echo
    echo "----- Dernières lignes du journal du service -----"
    journalctl -u "$SERVICE" -n 30 --no-pager 2>/dev/null | grep -v 'systemd\[1\]' || true
    if [ "$ROLLBACK" -eq 1 ]; then
        rollback "$reason"
    else
        write_status failed "" "$reason (retour arrière désactivé : --no-rollback)"
        printf '\nRetour arrière désactivé. Pour revenir en arrière a la main :\n  systemctl stop %s\n  cp %s/*.db %s/ && rm -f %s/*.db-wal %s/*.db-shm\n  git -C %s reset --hard %s\n  systemctl start %s\n' \
            "$SERVICE" "$SAVE_DIR" "$DATA_DIR" "$DATA_DIR" "$DATA_DIR" "$APP_DIR" "$BEFORE_FULL" "$SERVICE"
    fi
    exit 1
}

RESTARTED=0
SAVE_DIR=""

say "1/4 Sauvegarde des bases"
write_status running "1/4" "Sauvegarde des bases"
STAMP="$(date +%Y%m%d-%H%M%S)"
SAVE_DIR="$BACKEND/db_backups/avant_maj_$STAMP"
mkdir -p "$SAVE_DIR"
"$VENV_BIN/python" - "$DATA_DIR" "$SAVE_DIR" <<'PY' || fail "sauvegarde des bases impossible"
import os, sqlite3, sys
data_dir, target = sys.argv[1], sys.argv[2]
for name in ("dotation.db", "users.db"):
    source = os.path.join(data_dir, name)
    if not os.path.exists(source) or os.path.getsize(source) == 0:
        continue
    src = sqlite3.connect(source)
    dst = sqlite3.connect(os.path.join(target, name))
    src.backup(dst)  # copie cohérente, même si le service tourne (WAL compris)
    dst.close(); src.close()
    print("  sauvegarde :", name)
PY
fix_ownership
# Garde-fou : si la base principale existe et n'est pas vide, sa sauvegarde DOIT exister (sinon on ne poursuit pas : pas de retour arriere possible).
if [ -s "$DATA_DIR/dotation.db" ] && [ ! -s "$SAVE_DIR/dotation.db" ]; then
    fail "la sauvegarde de dotation.db est absente : mise à jour interrompue avant toute modification"
fi
echo "  -> $SAVE_DIR"

say "2/4 Récupération du code"
write_status running "2/4" "Récupération du code"
# On ignore le venv et les .pyc dans le contrôle : le venv est suivi par git et Python modifie ses .pyc en
# permanence, ce qui ne represente pas une modification locale de l'application.
DIRTY="$(git -C "$APP_DIR" status --porcelain --untracked-files=no -- . ':!backend/venv' ':!venv' ':!*.pyc')"
if [ "$FORCE" -eq 0 ] && [ -n "$DIRTY" ]; then
    printf '%s\n' "$DIRTY"
    fail "des fichiers suivis par git ont été modifiés localement (liste ci-dessus). Les conserver puis relancer, ou écraser avec : sudo bash $DEPLOY_SCRIPT --force"
fi
git -C "$APP_DIR" fetch origin "$BRANCH" || fail "impossible de joindre le dépôt distant (réseau ?) : rien n'a été modifie"
git -C "$APP_DIR" checkout -q "$BRANCH" 2>/dev/null || git -C "$APP_DIR" checkout -q -B "$BRANCH" FETCH_HEAD
git -C "$APP_DIR" reset --hard FETCH_HEAD || abort_after_change "mise à jour du code impossible"
AFTER="$(git -C "$APP_DIR" rev-parse --short HEAD)"
TO_VERSION="$(VERSION_OF)"
echo "  $BEFORE -> $AFTER"

say "3/4 Dépendances Python"
write_status running "3/4" "Dépendances Python"
"$VENV_BIN/pip" install --quiet -r "$BACKEND/requirements.txt" || abort_after_change "installation des dépendances impossible"

say "4/4 Redémarrage"
write_status running "4/4" "Redémarrage du service"
systemctl daemon-reload
systemctl reset-failed "$SERVICE" 2>/dev/null || true
RESTARTED=1
fix_ownership
systemctl restart "$SERVICE" || true
if wait_healthy; then
    write_status ok "" "Application redémarrée et vérifiée."
    printf '\n\033[32m[SUCCESS] Déploiement termine (%s -> %s, version %s). L'\''application répond sur le port %s.\033[0m\n' \
        "$BEFORE" "$AFTER" "$TO_VERSION" "$PORT"
    echo "  - Code : $(git -C "$APP_DIR" log -1 --oneline)"
    echo "  - Sauvegarde d'avant mise à jour : $SAVE_DIR"
    exit 0
fi
abort_after_change "l'application ne répond pas après le redémarrage"
}

main "$@"
