"""Tâches de service (notifications, lot 2) : ce qu'un service doit faire pour un dossier.

- « à fournir » : un élément attribué dans un dossier qui n'est pas encore (ou plus) en restitution — le service émetteur de la
  ressource prépare ou crée (compte, accès, matériel). Disparaît quand le dossier est annulé, restitué, ou que l'élément est retiré.
- « à fermer » : un dossier en restitution contient une ressource SANS retour physique (compte, accès : `requires_return` faux) —
  le service émetteur la désactive. (Le matériel à rendre est déjà suivi par la restitution elle-même.)

Une tâche est CALCULÉE à partir des éléments des dossiers (`dotation_items`) ; seule la décision « Fait » est enregistrée
(`service_task_done` : qui, quand), à part du contenu du dossier — aucune réécriture d'un dossier signé, aucun conflit de version.
La table est indépendante de `persist_form` (qui recrée les lignes d'éléments) : un « Fait » survit à un nouvel enregistrement.

Qui voit quoi : les titulaires du service de la ressource. Sans titulaire actif, les administrateurs (`users.manage`). Le nom de la
personne n'apparaît que pour un lecteur en portée « complète » (`data_scope`) : un profil masqué voit « dossier du jj/mm/aaaa »."""
from models.audit import insert_app_log
from models.notifications import active_services, all_referents, can_manage, find_service_by_label
from utils import utc_now

KIND_PROVISION = "service_provision"
KIND_DEPROVISION = "service_deprovision"
_DONE_KIND = {KIND_PROVISION: "provision", KIND_DEPROVISION: "deprovision"}

PROVISION_STATUSES = ("partial_assignment", "awaiting_signature", "active")
DEPROVISION_STATUSES = ("partial_return", "returned")
MAX_ITEMS_SHOWN = 200


def baseline_existing(connection):
    """Migration 10 : tout ce qui existe déjà est considéré comme traité (sinon les centaines d'attributions historiques
    deviendraient d'un coup des tâches). Les brouillons ne sont pas concernés : leurs éléments donneront des tâches à la validation."""
    now = utc_now()
    for done_kind in ("provision", "deprovision"):
        connection.execute(
            "INSERT OR IGNORE INTO service_task_done (kind, form_id, item_key, done_at, done_by, note) "
            "SELECT ?, i.form_id, i.item_key, ?, NULL, 'avant les notifications' FROM dotation_items i "
            "JOIN dotation_forms f ON f.id = i.form_id WHERE i.assigned = 1 AND f.status != 'draft'",
            (done_kind, now))


def _active_account_names():
    from database import get_users_db
    with get_users_db() as users:
        return {row[0] for row in users.execute(
            "SELECT username FROM users WHERE is_active = 1 AND status NOT IN ('pending', 'disabled')")}


def _candidate_rows(connection, kind):
    """Éléments qui appellent une action de ce type, sans « Fait » enregistré."""
    done_kind = _DONE_KIND[kind]
    if kind == KIND_PROVISION:
        condition = f"f.status IN ({','.join('?' * len(PROVISION_STATUSES))}) AND i.returned = 0"
        params = list(PROVISION_STATUSES)
    else:
        condition = f"f.status IN ({','.join('?' * len(DEPROVISION_STATUSES))}) AND COALESCE(r.requires_return, 1) = 0"
        params = list(DEPROVISION_STATUSES)
    return connection.execute(
        f"""SELECT i.form_id, i.item_key, i.label, f.status, f.nom, f.prenom, f.created_at, COALESCE(r.issuer_service, '')
            FROM dotation_items i
            JOIN dotation_forms f ON f.id = i.form_id
            LEFT JOIN resource_catalog r ON r.code = i.item_key
            WHERE i.assigned = 1 AND {condition}
              AND NOT EXISTS (SELECT 1 FROM service_task_done d WHERE d.kind = ? AND d.form_id = i.form_id AND d.item_key = i.item_key)
            ORDER BY f.created_at, i.label""", params + [done_kind]).fetchall()


def _responsible_for(connection, services, referents, active_names, issuer_service):
    """Comptes qui doivent traiter une ressource : titulaires actifs de son service ; None = service inconnu."""
    service = find_service_by_label(services, issuer_service)
    if not service:
        return None, set()
    return service, {name for name in referents.get(service["id"], []) if name in active_names}


def _display(row, user):
    """Libellé de la personne selon la portée du lecteur (aucune donnée personnelle pour un profil masqué)."""
    form_id, _key, _label, _status, nom, prenom, created_at, _issuer = row
    if (user or {}).get("data_scope") == "full":
        return f"{nom} {prenom}".strip() or "Dossier sans nom"
    return f"Dossier du {str(created_at or '')[:10]}"


def _can_open(user):
    permissions = (user or {}).get("permissions") or []
    return "*" in permissions or "forms.read_detail" in permissions


def service_tasks(connection, user):
    """Tâches de service visibles par cet utilisateur : liste de 0 à 2 tâches (« à fournir », « à fermer »)."""
    if not user:
        return []
    username = user.get("username")
    services = active_services(connection)
    referents = all_referents(connection)
    mine = {service["id"] for service in services if username in referents.get(service["id"], [])}
    fallback = can_manage(user)
    if not mine and not fallback:
        return []
    active_names = _active_account_names()
    tasks = []
    for kind in (KIND_PROVISION, KIND_DEPROVISION):
        items = []
        for row in _candidate_rows(connection, kind):
            service, responsible = _responsible_for(connection, services, referents, active_names, row[7])
            if service is None:
                continue  # ressource sans service : la tâche « choisir le service » des administrateurs s'en occupe
            visible = (service["id"] in mine) if responsible else fallback
            if not visible:
                continue
            items.append({
                "form_id": row[0], "item_key": row[1], "label": row[2], "service": service["label"],
                "who": _display(row, user), "can_open": _can_open(user), "since": str(row[6] or "")[:10],
                "unattended": not responsible,
            })
        if items:
            tasks.append({"kind": kind, "count": len(items), "items": items[:MAX_ITEMS_SHOWN], "truncated": len(items) > MAX_ITEMS_SHOWN})
    return tasks


def mark_done(connection, user, kind, form_id, item_key):
    """« Fait » : réservé à ceux à qui la tâche est adressée. Retourne (enregistré, erreur ou None)."""
    if kind not in _DONE_KIND:
        return False, "kind_unknown"
    visible = [item for task in service_tasks(connection, user) if task["kind"] == kind for item in task["items"]
               if item["form_id"] == str(form_id) and item["item_key"] == str(item_key)]
    if not visible:
        # inexistante, déjà faite, ou adressée à un autre service : on ne distingue pas (pas de fuite d'information)
        return False, "task_not_found"
    now = utc_now()
    connection.execute(
        "INSERT OR IGNORE INTO service_task_done (kind, form_id, item_key, done_at, done_by, note) VALUES (?,?,?,?,?, '')",
        (_DONE_KIND[kind], str(form_id), str(item_key), now, user.get("username")))
    insert_app_log(connection, "admin", "service_task_done", "Tâche de service terminée", "form", str(form_id),
                   {"kind": _DONE_KIND[kind], "resource": str(item_key), "service": visible[0]["service"]}, actor=user.get("username"))
    return True, None

