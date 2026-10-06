"""Notifications : « qui doit terminer cette action ».

Principe (cadrage du 06/10, voir docs/BACKLOG_PRODUIT.md) :
- une ressource est rattachee a un SERVICE du catalogue ; le lien est le libelle : le « service emetteur » de la ressource
  (`resource_catalog.issuer_service`) doit etre le libelle exact d'un service actif de `service_catalog` ;
- un service porte une liste de COMPTES titulaires (`service_referents`) : tous recoivent les taches du service ;
- les taches sont CALCULEES a partir des donnees (jamais un etat client copie a cote) : une tache disparait d'elle-meme
  quand la situation qui l'a produite est resolue. Aucune donnee personnelle dans une tache : type, ressource, service.

Lot 1 : une seule tache, pour les administrateurs — des ressources n'ont pas (ou plus) de service referent."""
import re
import time
import unicodedata

from models.audit import insert_app_log
from utils import utc_now

# Droit qui donne acces a la gestion des services et des ressources (routes/admin.py) : il voit donc cette tache.
MANAGE_PERMISSION = "users.manage"

KIND_RESOURCES_MISSING_SERVICE = "resources_missing_service"
KIND_BACKUP_FAILED = "backup_failed"
KIND_UPDATE_AVAILABLE = "update_available"
KIND_SIGNUPS_PENDING = "signups_pending"

_CACHE_SECONDS = 60
_cache = {}


def clear_cache():
    _cache.clear()


def _cached(key, compute, seconds=_CACHE_SECONDS):
    """Calcul mis en cache dans le processus : les taches sont recalculees a chaque controle de session (chaque minute,
    pour chaque administrateur connecte), et certaines lisent des fichiers (historique des sauvegardes)."""
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and now - hit[0] < seconds:
        return hit[1]
    value = compute()
    _cache[key] = (now, value)
    return value

# Services dont l'appellation courante differe du libelle du catalogue ; sert UNIQUEMENT a pre-remplir la suggestion
# (l'administrateur valide ou change : rien n'est rattache sans lui).
_SERVICE_ALIASES = {
    "informatique": ("dsi", "si", "systemes d information", "direction des systemes d information"),
    "dsi": ("informatique", "si"),
    "ressources humaines": ("drh", "rh", "direction des ressources humaines"),
    "drh": ("ressources humaines", "rh"),
    "rh": ("drh", "ressources humaines"),
    "services generaux": ("moyens generaux", "services techniques", "ctm"),
    "moyens generaux": ("services generaux",),
}


def normalize_label(value):
    """Libelle compare sans casse, sans accents, sans ponctuation ni espaces multiples."""
    text = unicodedata.normalize("NFD", str(value or "").lower())
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def active_services(connection):
    return [{"id": row[0], "label": row[1]} for row in connection.execute(
        "SELECT id, label FROM service_catalog WHERE is_active = 1 ORDER BY label COLLATE NOCASE")]


def find_service_by_label(services, label):
    wanted = normalize_label(label)
    return next((service for service in services if normalize_label(service["label"]) == wanted), None) if wanted else None


def suggest_service_id(legacy_text, services):
    """Service du catalogue le plus probable pour un ancien « service emetteur » ; None si on ne sait pas."""
    wanted = normalize_label(legacy_text)
    if not wanted:
        return None
    by_label = {normalize_label(service["label"]): service["id"] for service in services}
    if wanted in by_label:
        return by_label[wanted]
    for alias in _SERVICE_ALIASES.get(wanted, ()):
        if alias in by_label:
            return by_label[alias]
    if len(wanted) >= 4:
        contained = [service_id for label, service_id in by_label.items() if wanted in label or label in wanted]
        if len(contained) == 1:
            return contained[0]
    return None


def resources_missing_service(connection, services=None):
    """Ressources actives dont le service emetteur est vide ou n'est pas un service actif du catalogue."""
    services = active_services(connection) if services is None else services
    known = {normalize_label(service["label"]) for service in services}
    rows = connection.execute(
        "SELECT id, code, label, COALESCE(issuer_service, '') FROM resource_catalog WHERE is_active = 1 ORDER BY label COLLATE NOCASE").fetchall()
    return [{"id": row[0], "code": row[1], "label": row[2], "legacy_service": row[3].strip()}
            for row in rows if normalize_label(row[3]) not in known]


def missing_service_task(connection):
    """Tache « choisir le service de ces ressources », regroupee par ancien texte (une seule decision par groupe)."""
    services = active_services(connection)
    missing = resources_missing_service(connection, services)
    if not missing:
        return None
    groups = {}
    for resource in missing:
        groups.setdefault(resource["legacy_service"], []).append({"id": resource["id"], "label": resource["label"]})
    return {
        "kind": KIND_RESOURCES_MISSING_SERVICE,
        "count": len(missing),
        "groups": [
            {"legacy_service": legacy, "resources": resources, "suggested_service_id": suggest_service_id(legacy, services)}
            for legacy, resources in sorted(groups.items(), key=lambda item: normalize_label(item[0]))
        ],
        "services": services,
    }


def _has(user, permission):
    permissions = (user or {}).get("permissions") or []
    return "*" in permissions or permission in permissions


def can_manage(user):
    return _has(user, MANAGE_PERMISSION)


def backup_failed_task(user):
    """Sauvegarde automatique en echec (ou qui ne s'execute plus) : meme etat que le bandeau de l'administration de la base.
    Reserve au droit qui gere les sauvegardes (db.manage, ou son indicateur individuel)."""
    if not (_has(user, "db.manage") or (user or {}).get("db_manage")):
        return None

    def compute():
        import backup_schedule
        import backup_targets
        try:
            return backup_schedule.health(backup_targets.load_config())
        except Exception:  # noqa: BLE001 - une configuration illisible ne doit jamais empecher de lire le reste des notifications
            return {"level": "ok", "message": ""}

    state = _cached("backup_health", compute)
    if state.get("level") != "error":
        return None
    return {"kind": KIND_BACKUP_FAILED, "severity": "urgent", "message": state.get("message") or "", "link": "/admin-db.html"}


def update_available_task(user):
    """Nouvelle version disponible (cache disque, jamais de reseau ici). Reserve a ceux qui gerent les mises a jour."""
    if not can_manage(user):
        return None
    import update_check
    state = update_check.cached_status()
    if not state.get("available"):
        return None
    return {"kind": KIND_UPDATE_AVAILABLE, "current": state.get("current") or "", "latest": state.get("latest") or "", "link": "/admin.html"}


def signups_pending_task(user):
    """Demandes d'inscription a valider ou refuser (aucun nom dans la notification : seulement leur nombre)."""
    if not can_manage(user):
        return None
    from database import get_users_db
    try:
        with get_users_db() as users:
            count = users.execute("SELECT COUNT(*) FROM users WHERE status = 'pending'").fetchone()[0]
    except Exception:  # noqa: BLE001
        return None
    return {"kind": KIND_SIGNUPS_PENDING, "count": count, "link": "/admin-comptes.html"} if count else None


def open_tasks(connection, user):
    """Taches ouvertes visibles par cet utilisateur (calculees a l'instant), les plus urgentes d'abord."""
    tasks = [backup_failed_task(user), update_available_task(user), signups_pending_task(user)]
    if can_manage(user):
        tasks.append(missing_service_task(connection))
    return [task for task in tasks if task]


def open_tasks_count(connection, user):
    """Nombre de taches ouvertes : lu a chaque controle de session (toutes les minutes)."""
    return len(open_tasks(connection, user))


def apply_service_assignments(connection, assignments, actor):
    """Rattache des ressources a un service. `assignments` : [{"resource_ids": [...], "service_id": "..."}].
    Retourne (nombre de ressources rattachees, erreur ou None). Tout ou rien : une erreur n'applique rien."""
    services = {service["id"]: service for service in active_services(connection)}
    plan = []
    for item in assignments or []:
        service = services.get((item or {}).get("service_id"))
        if not service:
            return 0, "service_unknown"
        ids = [str(value) for value in ((item or {}).get("resource_ids") or [])]
        if not ids:
            return 0, "resources_required"
        for resource_id in ids:
            row = connection.execute("SELECT issuer_service FROM resource_catalog WHERE id = ?", (resource_id,)).fetchone()
            if not row:
                return 0, "resource_unknown"
            plan.append((resource_id, service, row[0] or ""))
    now = utc_now()
    for resource_id, service, previous in plan:
        connection.execute("UPDATE resource_catalog SET issuer_service = ?, updated_at = ? WHERE id = ?", (service["label"], now, resource_id))
    if plan:
        insert_app_log(connection, "admin", "resources_service_assigned", "Service referent choisi pour des ressources", "resource", None,
                       {"count": len(plan), "assignments": [{"resource": rid, "service": svc["label"], "previous": prev} for rid, svc, prev in plan]},
                       actor=actor)
    return len(plan), None


def rename_service(connection, old_label, new_label):
    """Un service renomme : ses ressources suivent (le lien est le libelle)."""
    if normalize_label(old_label) == normalize_label(new_label) and old_label == new_label:
        return 0
    return connection.execute(
        "UPDATE resource_catalog SET issuer_service = ?, updated_at = ? WHERE lower(trim(issuer_service)) = lower(trim(?))",
        (new_label, utc_now(), old_label)).rowcount


# ---- Titulaires d'un service --------------------------------------------------------------------------------------

def service_referents(connection, service_id):
    return [row[0] for row in connection.execute(
        "SELECT username FROM service_referents WHERE service_id = ? ORDER BY username COLLATE NOCASE", (service_id,))]


def all_referents(connection):
    result = {}
    for service_id, username in connection.execute("SELECT service_id, username FROM service_referents ORDER BY username COLLATE NOCASE"):
        result.setdefault(service_id, []).append(username)
    return result


def set_service_referents(connection, service_id, usernames, is_valid_account):
    """Remplace la liste des titulaires. `is_valid_account(username)` : le compte existe et est actif (users.db).
    Retourne (liste enregistree, erreur ou None)."""
    if not connection.execute("SELECT 1 FROM service_catalog WHERE id = ?", (service_id,)).fetchone():
        return [], "not_found"
    cleaned = []
    for username in usernames or []:
        username = str(username or "").strip()
        if not username or username in cleaned:
            continue
        if not is_valid_account(username):
            return [], "account_unknown"
        cleaned.append(username)
    connection.execute("DELETE FROM service_referents WHERE service_id = ?", (service_id,))
    now = utc_now()
    for username in cleaned:
        connection.execute("INSERT INTO service_referents (service_id, username, created_at) VALUES (?,?,?)", (service_id, username, now))
    return cleaned, None


def forget_account(connection, username):
    """Compte supprime : il quitte tous les services."""
    connection.execute("DELETE FROM service_referents WHERE username = ?", (username,))


def forget_service(connection, service_id):
    connection.execute("DELETE FROM service_referents WHERE service_id = ?", (service_id,))
