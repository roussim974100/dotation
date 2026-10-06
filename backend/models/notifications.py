"""Notifications : « qui doit terminer cette action ».

Principe (cadrage du 06/10, voir docs/BACKLOG_PRODUIT.md) :
- une ressource est rattachee a un SERVICE du catalogue ; le lien est le libelle : le « service emetteur » de la ressource
  (`resource_catalog.issuer_service`) doit etre le libelle exact d'un service actif de `service_catalog` ;
- un service porte une liste de COMPTES titulaires (`service_referents`) : tous recoivent les taches du service ;
- les taches sont CALCULEES a partir des donnees (jamais un etat client copie a cote) : une tache disparait d'elle-meme
  quand la situation qui l'a produite est resolue. Aucune donnee personnelle dans une tache : type, ressource, service.

Lot 1 : une seule tache, pour les administrateurs — des ressources n'ont pas (ou plus) de service referent."""
import re
import unicodedata

from models.audit import insert_app_log
from utils import utc_now

# Droit qui donne acces a la gestion des services et des ressources (routes/admin.py) : il voit donc cette tache.
MANAGE_PERMISSION = "users.manage"

KIND_RESOURCES_MISSING_SERVICE = "resources_missing_service"

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


def can_manage(user):
    permissions = (user or {}).get("permissions") or []
    return "*" in permissions or MANAGE_PERMISSION in permissions


def open_tasks(connection, user):
    """Taches ouvertes visibles par cet utilisateur (calculees a l'instant)."""
    tasks = []
    if can_manage(user):
        task = missing_service_task(connection)
        if task:
            tasks.append(task)
    return tasks


def open_tasks_count(connection, user):
    """Nombre de taches ouvertes, sans le detail : lu a chaque contrôle de session (toutes les minutes)."""
    count = 0
    if can_manage(user):
        count += 1 if resources_missing_service(connection) else 0
    return count


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
