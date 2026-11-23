"""Tâches de service (notifications, lots 2 et 4) : ce qu'un service doit faire pour un dossier.

- « à fournir » : un élément attribué dans un dossier qui n'est pas encore (ou plus) en restitution — le service émetteur de la
  ressource prépare ou crée (compte, accès, matériel). Disparaît quand le dossier est annulé, restitué, ou que l'élément est retiré.
- « à fermer » : un dossier en restitution contient une ressource SANS retour physique (compte, accès : `requires_return` faux) —
  le service émetteur la désactive ; de même quand un AJUSTEMENT retire une telle ressource d'un dossier resté actif (l'élément est
  alors marqué rendu). (Le matériel à rendre est déjà suivi par la restitution elle-même.)

Une tâche est CALCULÉE à partir des éléments des dossiers (`dotation_items`) ; seule la décision « Fait » est enregistrée
(`service_task_done` : qui, quand), à part du contenu du dossier — aucune réécriture d'un dossier signé, aucun conflit de version.
La table est indépendante de `persist_form` (qui recrée les lignes d'éléments) : un « Fait » survit à un nouvel enregistrement.
Ces lignes ne sont PAS purgées avec le temps (elles sont la mémoire du « déjà fait » : les supprimer ferait réapparaître la tâche
tant que le dossier existe) ; seules celles d'un dossier supprimé le sont (`purge_orphans`). Un « Fait » par erreur se rouvre.

Retard (lot 4) : une tâche de plus de LATE_DAYS jours est « en retard » (visible comme telle) ; au-delà de ESCALATE_DAYS jours elle
est ESCALADÉE : elle apparaît aussi chez les administrateurs. L'ancienneté part de la création du dossier (à fournir) ou de la
date de restitution (à fermer). Pas d'e-mail : c'est un état visible dans la cloche et la page « Mes tâches ».

Qui voit quoi : les titulaires du service de la ressource. Sans titulaire actif, les administrateurs (`users.manage`). Le nom de la
personne n'apparaît que pour un lecteur en portée « complète » (`data_scope`) : un profil masqué voit « dossier du jj/mm/aaaa »."""
import os
from datetime import datetime, timedelta, timezone

from models.audit import insert_app_log
from models.notifications import active_services, all_referents, can_manage, find_service_by_label
from utils import utc_now

KIND_PROVISION = "service_provision"
KIND_DEPROVISION = "service_deprovision"
_DONE_KIND = {KIND_PROVISION: "provision", KIND_DEPROVISION: "deprovision"}

PROVISION_STATUSES = ("partial_assignment", "awaiting_signature", "active")
DEPROVISION_STATUSES = ("partial_return", "returned")
MAX_ITEMS_SHOWN = 200
RECENT_DAYS = 30
MAX_RECENT_SHOWN = 100
LATE_DAYS = int(os.environ.get("APP_TASK_LATE_DAYS", "3"))
ESCALATE_DAYS = int(os.environ.get("APP_TASK_ESCALATE_DAYS", "7"))


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


def purge_orphans(connection):
    """Supprime les « Fait » dont le dossier n'existe plus (suppression d'un dossier). Idempotent ; appelé au démarrage."""
    return connection.execute("DELETE FROM service_task_done WHERE form_id NOT IN (SELECT id FROM dotation_forms)").rowcount


def _active_account_names():
    from database import get_users_db
    with get_users_db() as users:
        return {row[0] for row in users.execute(
            "SELECT username FROM users WHERE is_active = 1 AND status NOT IN ('pending', 'disabled')")}


def _parse(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def age_days(value, now=None):
    """Jours entiers écoulés depuis `value` (0 si date inconnue ou future : un départ planifié n'est pas en retard)."""
    start = _parse(value)
    if not start:
        return 0
    return max(0, ((now or datetime.now(timezone.utc)) - start).days)


def _candidate_rows(connection, kind, form_id=None):
    """Éléments qui appellent une action de ce type, sans « Fait » enregistré."""
    done_kind = _DONE_KIND[kind]
    if kind == KIND_PROVISION:
        condition = f"f.status IN ({','.join('?' * len(PROVISION_STATUSES))}) AND i.returned = 0"
        params = list(PROVISION_STATUSES)
        since = "f.created_at"
    else:
        # Dossier en restitution, OU élément retiré par un ajustement (le dossier reste actif, l'élément est marqué rendu).
        condition = (f"(f.status IN ({','.join('?' * len(DEPROVISION_STATUSES))}) "
                     f"OR (f.status IN ({','.join('?' * len(PROVISION_STATUSES))}) AND i.returned = 1)) AND COALESCE(r.requires_return, 1) = 0")
        params = list(DEPROVISION_STATUSES) + list(PROVISION_STATUSES)
        since = "COALESCE(i.returned_at, f.returned_at, f.updated_at)"
    only_form = "AND i.form_id = ?" if form_id is not None else ""
    return connection.execute(
        f"""SELECT i.form_id, i.item_key, i.label, f.status, f.nom, f.prenom, f.created_at, COALESCE(r.issuer_service, ''), {since}
            FROM dotation_items i
            JOIN dotation_forms f ON f.id = i.form_id
            LEFT JOIN resource_catalog r ON r.code = i.item_key
            WHERE i.assigned = 1 AND {condition} {only_form}
              AND NOT EXISTS (SELECT 1 FROM service_task_done d WHERE d.kind = ? AND d.form_id = i.form_id AND d.item_key = i.item_key)
            ORDER BY f.created_at, i.label""", params + ([str(form_id)] if form_id is not None else []) + [done_kind]).fetchall()


def _responsible_for(services, referents, active_names, issuer_service):
    """Service de la ressource et titulaires actifs ; (None, set()) si le service n'est pas au catalogue."""
    service = find_service_by_label(services, issuer_service)
    if not service:
        return None, set()
    return service, {name for name in referents.get(service["id"], []) if name in active_names}


def _display(form_id, nom, prenom, created_at, user):
    """Libellé de la personne selon la portée du lecteur (aucune donnée personnelle pour un profil masqué)."""
    if (user or {}).get("data_scope") == "full":
        return f"{nom} {prenom}".strip() or "Dossier sans nom"
    return f"Dossier du {str(created_at or '')[:10]}"


def _can_open(user):
    permissions = (user or {}).get("permissions") or []
    return "*" in permissions or "forms.read_detail" in permissions


def service_tasks(connection, user, now=None):
    """Tâches de service visibles par cet utilisateur : liste de 0 à 2 tâches (« à fournir », « à fermer »)."""
    if not user:
        return []
    username = user.get("username")
    services = active_services(connection)
    referents = all_referents(connection)
    mine = {service["id"] for service in services if username in referents.get(service["id"], [])}
    admin = can_manage(user)
    if not mine and not admin:
        return []
    active_names = _active_account_names()
    tasks = []
    for kind in (KIND_PROVISION, KIND_DEPROVISION):
        items = []
        for row in _candidate_rows(connection, kind):
            service, responsible = _responsible_for(services, referents, active_names, row[7])
            if service is None:
                continue  # ressource sans service : la tâche « choisir le service » des administrateurs s'en occupe
            age = age_days(row[8], now)
            escalated = age >= ESCALATE_DAYS
            if responsible:
                # titulaires du service ; les administrateurs seulement quand la tâche est escaladée
                visible = service["id"] in mine or (admin and escalated)
            else:
                visible = admin  # service sans titulaire actif : les administrateurs reprennent
            if not visible:
                continue
            items.append({
                "form_id": row[0], "item_key": row[1], "label": row[2], "service": service["label"],
                "who": _display(row[0], row[4], row[5], row[6], user), "can_open": _can_open(user), "since": str(row[6] or "")[:10],
                "unattended": not responsible, "age_days": age, "late": age >= LATE_DAYS, "escalated": escalated,
            })
        if items:
            late = sum(1 for item in items if item["late"])
            tasks.append({"kind": kind, "count": len(items), "late_count": late, "escalated_count": sum(1 for item in items if item["escalated"]),
                          "severity": "late" if late else "normal", "items": items[:MAX_ITEMS_SHOWN], "truncated": len(items) > MAX_ITEMS_SHOWN,
                          "late_days": LATE_DAYS, "escalate_days": ESCALATE_DAYS})
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


def _done_rows(connection, since_iso):
    return connection.execute(
        """SELECT d.kind, d.form_id, d.item_key, d.done_at, d.done_by, COALESCE(i.label, d.item_key), f.nom, f.prenom, f.created_at,
                  COALESCE(r.issuer_service, '')
           FROM service_task_done d
           JOIN dotation_forms f ON f.id = d.form_id
           LEFT JOIN dotation_items i ON i.form_id = d.form_id AND i.item_key = d.item_key
           LEFT JOIN resource_catalog r ON r.code = d.item_key
           WHERE d.done_by IS NOT NULL AND d.done_at >= ?
           ORDER BY d.done_at DESC""", (since_iso,)).fetchall()


def _may_reopen(user, service, mine):
    return can_manage(user) or (service is not None and service["id"] in mine)


def recently_done(connection, user, now=None):
    """Ce qui a été terminé ces RECENT_DAYS derniers jours dans les services de l'utilisateur (tous pour un administrateur) :
    sert à vérifier un « Fait » et à le rouvrir s'il était une erreur."""
    if not user:
        return []
    services = active_services(connection)
    referents = all_referents(connection)
    mine = {service["id"] for service in services if user.get("username") in referents.get(service["id"], [])}
    since = ((now or datetime.now(timezone.utc)) - timedelta(days=RECENT_DAYS)).isoformat()
    reverse = {value: key for key, value in _DONE_KIND.items()}
    result = []
    for kind, form_id, item_key, done_at, done_by, label, nom, prenom, created_at, issuer in _done_rows(connection, since):
        service = find_service_by_label(services, issuer)
        if not _may_reopen(user, service, mine):
            continue
        result.append({"kind": reverse.get(kind, kind), "form_id": form_id, "item_key": item_key, "label": label,
                       "service": service["label"] if service else issuer, "who": _display(form_id, nom, prenom, created_at, user),
                       "done_at": done_at, "done_by": done_by})
        if len(result) >= MAX_RECENT_SHOWN:
            break
    return result


def reopen(connection, user, kind, form_id, item_key):
    """Rouvre un « Fait » enregistré par erreur : la tâche revient chez tous les titulaires. Réservé aux titulaires du service
    et aux administrateurs. Retourne (rouvert, erreur ou None)."""
    if kind not in _DONE_KIND:
        return False, "kind_unknown"
    allowed = [item for item in recently_done(connection, user) if item["kind"] == kind and item["form_id"] == str(form_id) and item["item_key"] == str(item_key)]
    if not allowed:
        return False, "task_not_found"
    connection.execute("DELETE FROM service_task_done WHERE kind = ? AND form_id = ? AND item_key = ?", (_DONE_KIND[kind], str(form_id), str(item_key)))
    insert_app_log(connection, "admin", "service_task_reopened", "Tâche de service rouverte", "form", str(form_id),
                   {"kind": _DONE_KIND[kind], "resource": str(item_key), "service": allowed[0]["service"]}, actor=user.get("username"))
    return True, None


def form_service_tasks(connection, form_id, now=None):
    """Tâches de service d'UN dossier, pour sa fiche : ce qui reste à faire (service, ancienneté, retard) puis ce qui est fait
    (par qui, quand). Aucune donnée sur la personne : seulement des ressources, des services et des noms de comptes. Les « Fait »
    d'avant les notifications (sans auteur) ne sont pas listés."""
    services = active_services(connection)
    referents = all_referents(connection)
    active_names = _active_account_names()
    entries = []
    for kind in (KIND_PROVISION, KIND_DEPROVISION):
        for row in _candidate_rows(connection, kind, form_id=form_id):
            service, responsible = _responsible_for(services, referents, active_names, row[7])
            if service is None:
                continue
            age = age_days(row[8], now)
            entries.append({"state": "open", "kind": kind, "label": row[2], "service": service["label"], "age_days": age,
                            "late": age >= LATE_DAYS, "escalated": age >= ESCALATE_DAYS, "unattended": not responsible})
    reverse = {value: key for key, value in _DONE_KIND.items()}
    done_rows = connection.execute(
        """SELECT d.kind, d.item_key, d.done_at, d.done_by, COALESCE(i.label, d.item_key), COALESCE(r.issuer_service, '')
           FROM service_task_done d
           LEFT JOIN dotation_items i ON i.form_id = d.form_id AND i.item_key = d.item_key
           LEFT JOIN resource_catalog r ON r.code = d.item_key
           WHERE d.form_id = ? AND d.done_by IS NOT NULL ORDER BY d.done_at DESC""", (str(form_id),)).fetchall()
    for kind, item_key, done_at, done_by, label, issuer in done_rows:
        service = find_service_by_label(services, issuer)
        entries.append({"state": "done", "kind": reverse.get(kind, kind), "label": label, "service": service["label"] if service else issuer,
                        "done_at": done_at, "done_by": done_by})
    return entries
