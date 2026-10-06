"""Notifications, lot 2 : tâches de service (« à fournir » à l'attribution, « à fermer » à la restitution), adressées aux
titulaires du service de la ressource, « Fait » partagé, repli sur les administrateurs, aucune donnée personnelle pour un profil
masqué, historique existant considéré comme traité. Base temporaire (tests/conftest.py)."""
import sqlite3
import time

import bcrypt
import pytest

from app import app
from auth import create_user, delete_user, update_user
from database import get_db, get_users_db
from migrations import _m_service_tasks
from models import notifications as notif
from models.service_tasks import KIND_DEPROVISION, KIND_PROVISION, baseline_existing

H = {"X-CSRF-Token": "jeton"}
PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


def uid():
    return str(time.time_ns())


@pytest.fixture(autouse=True)
def sans_limiteur_de_creation(monkeypatch):
    """Ces tests créent plus de 30 dossiers à la minute (limite de /api/forms) : on neutralise le limiteur, pas la règle testée."""
    monkeypatch.setattr("auth._is_api_rate_limited", lambda *args, **kwargs: False)


def client_for(user):
    client = app.test_client()
    with client.session_transaction() as s:
        s["user"] = user
        s["csrf_token"] = "jeton"
    return client


def make_account(prefix, groups=("lecture",)):
    name = f"{prefix}_{uid()}"
    assert create_user(name, bcrypt.hashpw(b"Mot-2-Passe-Service1!", bcrypt.gensalt()).decode(), list(groups))
    return name


def make_service(label, referents=()):
    with get_db() as c:
        service_id = f"svc_{uid()}"
        c.execute("INSERT INTO service_catalog (id, label, is_active, is_builtin, created_at, updated_at) VALUES (?,?,1,0,'x','x')", (service_id, label))
        for name in referents:
            c.execute("INSERT INTO service_referents (service_id, username, created_at) VALUES (?,?,'x')", (service_id, name))
    notif.clear_cache()
    return service_id


def make_resource(issuer, requires_return, label=None):
    with get_db() as c:
        rid = f"res_{uid()}"
        code = f"code_{rid}"
        c.execute("INSERT INTO resource_catalog (id, code, label, category, issuer_service, requires_return, created_at, updated_at) VALUES (?,?,?,?,?,?, 'x','x')",
                  (rid, code, label or f"Ressource {code}", "materiel" if requires_return else "immateriel", issuer, int(requires_return)))
    return code


def make_dossier(codes, nom=None, status="active"):
    nom = nom or f"NOM{uid()}"
    resources = [{"id": index + 1, "code": code, "label": f"Libellé {code}", "category": "materiel", "requiresReturn": True, "selected": True,
                  "fields": {}, "details": "", "assignedAt": "2026-10-01T09:00:00"} for index, code in enumerate(codes)]
    body = {"dossier": {"type": "arrivee"}, "beneficiaire": {"nom": nom, "prenom": "Prénom", "qualite": "agent", "service": "DRH"},
            "resources": {"additional": resources}, "validation": {"signatureDataUrl": PNG, "rgpdAccepted": True},
            "workflow": {"status": status}, "meta": {}}
    created = client_for("admin").post("/api/forms", json=body, headers=H)
    assert created.status_code in (200, 201), created.get_data(as_text=True)[:300]
    form_id = created.get_json()["summary"]["id"]
    notif.clear_cache()
    return form_id, nom


def set_status(form_id, status):
    with get_db() as c:
        c.execute("UPDATE dotation_forms SET status = ? WHERE id = ?", (status, form_id))
    notif.clear_cache()


def tasks(user, kind):
    notif.clear_cache()
    task = next((t for t in client_for(user).get("/api/notifications").get_json()["tasks"] if t["kind"] == kind), None)
    return task


def keys(task):
    return {(item["form_id"], item["item_key"]) for item in (task or {"items": []})["items"]}


@pytest.fixture
def equipe():
    """Un service avec deux titulaires, un compte étranger, un compte désactivable."""
    titulaire, collegue, etranger = make_account("titulaire"), make_account("collegue"), make_account("etranger")
    label = f"Service équipe {uid()}"
    service_id = make_service(label, [titulaire, collegue])
    yield {"label": label, "id": service_id, "titulaire": titulaire, "collegue": collegue, "etranger": etranger}
    for name in (titulaire, collegue, etranger):
        delete_user(name)


# ---- à fournir -------------------------------------------------------------------------------------------------------

def test_attribution_donne_une_tache_a_tous_les_titulaires_du_service(equipe):
    compte, materiel = make_resource(equipe["label"], False), make_resource(equipe["label"], True)
    form_id, nom = make_dossier([compte, materiel])
    for user in (equipe["titulaire"], equipe["collegue"]):
        task = tasks(user, KIND_PROVISION)
        assert keys(task) >= {(form_id, compte), (form_id, materiel)}
    assert tasks(equipe["etranger"], KIND_PROVISION) is None  # un autre service ne voit rien
    assert tasks(equipe["titulaire"], KIND_DEPROVISION) is None  # pas de restitution : rien à fermer


def test_les_administrateurs_ne_voient_pas_ce_qui_a_un_titulaire_actif(equipe):
    code = make_resource(equipe["label"], False)
    form_id, _ = make_dossier([code])
    assert (form_id, code) not in keys(tasks("admin", KIND_PROVISION))


def test_brouillon_annule_ou_restitue_ne_donnent_pas_de_tache_a_fournir(equipe):
    code = make_resource(equipe["label"], False)
    for status in ("draft", "cancelled", "returned", "partial_return"):
        form_id, _ = make_dossier([code], status=status)
        set_status(form_id, status)
        assert (form_id, code) not in keys(tasks(equipe["titulaire"], KIND_PROVISION)), status


def test_element_deja_rendu_n_est_pas_a_fournir(equipe):
    code = make_resource(equipe["label"], True)
    form_id, _ = make_dossier([code])
    with get_db() as c:
        c.execute("UPDATE dotation_items SET returned = 1 WHERE form_id = ? AND item_key = ?", (form_id, code))
    assert (form_id, code) not in keys(tasks(equipe["titulaire"], KIND_PROVISION))


def test_ressource_sans_service_du_catalogue_n_est_pas_une_tache_de_service(equipe):
    code = make_resource("Service inconnu du catalogue", False)
    form_id, _ = make_dossier([code])
    assert (form_id, code) not in keys(tasks(equipe["titulaire"], KIND_PROVISION))
    assert (form_id, code) not in keys(tasks("admin", KIND_PROVISION))


# ---- « Fait » ----------------------------------------------------------------------------------------------------------

def test_fait_est_partage_et_garde_qui_et_quand(equipe):
    compte, materiel = make_resource(equipe["label"], False), make_resource(equipe["label"], True)
    form_id, _ = make_dossier([compte, materiel])
    resp = client_for(equipe["titulaire"]).post("/api/service-tasks/done", json={"kind": KIND_PROVISION, "form_id": form_id, "item_key": compte}, headers=H)
    assert resp.status_code == 200 and resp.get_json()["done"] is True
    assert (form_id, compte) not in keys(tasks(equipe["collegue"], KIND_PROVISION))  # disparaît pour le collègue aussi
    assert (form_id, materiel) in keys(tasks(equipe["collegue"], KIND_PROVISION))     # le reste demeure
    with get_db() as c:
        row = c.execute("SELECT done_by, done_at FROM service_task_done WHERE kind = 'provision' AND form_id = ? AND item_key = ?", (form_id, compte)).fetchone()
        journal = c.execute("SELECT details_json FROM app_logs WHERE action_type = 'service_task_done' ORDER BY id DESC LIMIT 1").fetchone()[0]
    assert row[0] == equipe["titulaire"] and row[1]
    assert "NOM" not in journal and form_id not in journal.replace(f'"{form_id}"', "")  # aucun nom au journal


def test_fait_refuse_a_un_autre_service_et_si_deja_fait(equipe):
    code = make_resource(equipe["label"], False)
    form_id, _ = make_dossier([code])
    body = {"kind": KIND_PROVISION, "form_id": form_id, "item_key": code}
    assert client_for(equipe["etranger"]).post("/api/service-tasks/done", json=body, headers=H).status_code == 404
    assert client_for("admin").post("/api/service-tasks/done", json=body, headers=H).status_code == 404  # il y a des titulaires
    assert client_for(equipe["titulaire"]).post("/api/service-tasks/done", json=body, headers=H).status_code == 200
    assert client_for(equipe["collegue"]).post("/api/service-tasks/done", json=body, headers=H).status_code == 404  # déjà faite
    assert client_for(equipe["titulaire"]).post("/api/service-tasks/done", json={**body, "kind": "autre"}, headers=H).status_code == 400
    assert app.test_client().post("/api/service-tasks/done", json=body, headers=H).status_code == 401


def test_fait_survit_a_un_nouvel_enregistrement_du_dossier(equipe):
    """persist_form recrée les lignes d'éléments : le « Fait » est indépendant de ces lignes."""
    code = make_resource(equipe["label"], False)
    form_id, _ = make_dossier([code])
    client_for(equipe["titulaire"]).post("/api/service-tasks/done", json={"kind": KIND_PROVISION, "form_id": form_id, "item_key": code}, headers=H)
    with get_db() as c:
        row = c.execute("SELECT * FROM dotation_items WHERE form_id = ? AND item_key = ?", (form_id, code)).fetchone()
        c.execute("DELETE FROM dotation_items WHERE form_id = ?", (form_id,))
        c.execute("INSERT INTO dotation_items (form_id, item_key, category, label, assigned, returned, details_json) VALUES (?,?,?,?,1,0,'{}')",
                  (form_id, code, row["category"], row["label"]))
    assert (form_id, code) not in keys(tasks(equipe["titulaire"], KIND_PROVISION))


# ---- à fermer ----------------------------------------------------------------------------------------------------------

def test_restitution_donne_une_tache_a_fermer_pour_les_ressources_sans_retour_physique(equipe):
    compte, materiel = make_resource(equipe["label"], False), make_resource(equipe["label"], True)
    form_id, _ = make_dossier([compte, materiel])
    set_status(form_id, "partial_return")
    deprovision = tasks(equipe["collegue"], KIND_DEPROVISION)
    assert keys(deprovision) == {(form_id, compte)}  # le matériel à rendre est suivi par la restitution elle-même
    assert (form_id, compte) not in keys(tasks(equipe["collegue"], KIND_PROVISION))  # plus rien à fournir pour ce départ
    done = client_for(equipe["collegue"]).post("/api/service-tasks/done", json={"kind": KIND_DEPROVISION, "form_id": form_id, "item_key": compte}, headers=H)
    assert done.status_code == 200
    assert (form_id, compte) not in keys(tasks(equipe["titulaire"], KIND_DEPROVISION))
    set_status(form_id, "returned")
    assert (form_id, compte) not in keys(tasks(equipe["titulaire"], KIND_DEPROVISION))  # « Fait » conservé après la clôture


def test_a_fournir_et_a_fermer_sont_deux_decisions_distinctes(equipe):
    code = make_resource(equipe["label"], False)
    form_id, _ = make_dossier([code])
    client_for(equipe["titulaire"]).post("/api/service-tasks/done", json={"kind": KIND_PROVISION, "form_id": form_id, "item_key": code}, headers=H)
    set_status(form_id, "partial_return")
    assert (form_id, code) in keys(tasks(equipe["titulaire"], KIND_DEPROVISION))  # le compte créé doit maintenant être fermé


# ---- repli sur les administrateurs ------------------------------------------------------------------------------------

def test_service_sans_titulaire_actif_retombe_sur_les_administrateurs():
    label = f"Service vide {uid()}"
    make_service(label)
    code = make_resource(label, False)
    form_id, _ = make_dossier([code])
    task = tasks("admin", KIND_PROVISION)
    item = next(i for i in task["items"] if i["item_key"] == code)
    assert item["unattended"] is True
    done = client_for("admin").post("/api/service-tasks/done", json={"kind": KIND_PROVISION, "form_id": form_id, "item_key": code}, headers=H)
    assert done.status_code == 200


def test_titulaires_tous_desactives_les_administrateurs_reprennent(equipe):
    code = make_resource(equipe["label"], False)
    form_id, _ = make_dossier([code])
    assert (form_id, code) not in keys(tasks("admin", KIND_PROVISION))
    update_user(equipe["titulaire"], is_active=0, status="disabled")
    update_user(equipe["collegue"], is_active=0, status="disabled")
    assert (form_id, code) in keys(tasks("admin", KIND_PROVISION))
    update_user(equipe["collegue"], is_active=1, status="active")
    assert (form_id, code) not in keys(tasks("admin", KIND_PROVISION))


# ---- données personnelles ---------------------------------------------------------------------------------------------

def test_le_nom_n_apparait_que_pour_une_portee_complete(equipe):
    code = make_resource(equipe["label"], False)
    form_id, nom = make_dossier([code], nom=f"DUPONT{uid()}")
    full_item = next(i for i in tasks(equipe["titulaire"], KIND_PROVISION)["items"] if i["form_id"] == form_id)
    assert nom in full_item["who"]
    with get_users_db() as users:
        users.execute("INSERT OR REPLACE INTO groups (key, label, description, permissions_json, data_scope, created_at, updated_at) "
                      "VALUES ('masque_service','Masqué','','[\"forms.read_list\"]','masked','x','x')")
        users.execute("DELETE FROM user_groups WHERE username = ?", (equipe["titulaire"],))
        users.execute("INSERT INTO user_groups (username, group_key) VALUES (?, 'masque_service')", (equipe["titulaire"],))
    masked_task = tasks(equipe["titulaire"], KIND_PROVISION)
    masked_item = next(i for i in masked_task["items"] if i["form_id"] == form_id)
    assert nom not in str(masked_task) and masked_item["who"].startswith("Dossier du ")
    assert masked_item["can_open"] is False  # pas de droit de lecture du dossier : pas de lien
    with get_users_db() as users:
        users.execute("DELETE FROM user_groups WHERE group_key = 'masque_service'")
        users.execute("DELETE FROM groups WHERE key = 'masque_service'")


# ---- compteur, migration -----------------------------------------------------------------------------------------------

def test_le_compteur_de_session_inclut_les_taches_de_service(equipe):
    code = make_resource(equipe["label"], False)
    make_dossier([code])
    assert client_for(equipe["titulaire"]).get("/api/session").get_json()["notifications_count"] >= 1
    assert client_for(equipe["etranger"]).get("/api/session").get_json()["notifications_count"] == 0


def test_migration_10_considere_l_existant_comme_traite_sauf_les_brouillons():
    connection = sqlite3.connect(":memory:")
    connection.executescript("""
        CREATE TABLE dotation_forms (id TEXT PRIMARY KEY, status TEXT);
        CREATE TABLE dotation_items (form_id TEXT, item_key TEXT, assigned INTEGER);
        INSERT INTO dotation_forms VALUES ('f_actif', 'active'), ('f_brouillon', 'draft'), ('f_retour', 'partial_return');
        INSERT INTO dotation_items VALUES ('f_actif', 'email', 1), ('f_actif', 'badge', 0), ('f_brouillon', 'email', 1), ('f_retour', 'vpn', 1);
    """)
    _m_service_tasks(connection)
    _m_service_tasks(connection)  # idempotente
    rows = set(connection.execute("SELECT kind, form_id, item_key FROM service_task_done"))
    assert rows == {("provision", "f_actif", "email"), ("deprovision", "f_actif", "email"), ("provision", "f_retour", "vpn"), ("deprovision", "f_retour", "vpn")}
    assert connection.execute("SELECT done_by FROM service_task_done LIMIT 1").fetchone()[0] is None


def test_migration_10_declaree_et_appliquee():
    with get_db() as c:
        assert c.execute("SELECT 1 FROM schema_migrations WHERE version = 10").fetchone()
        assert c.execute("SELECT 1 FROM sqlite_master WHERE name = 'service_task_done'").fetchone()
    assert baseline_existing  # importable


# ---- lot 4 : retard, escalade, réouverture, tâches récentes ---------------------------------------------------------------

from datetime import datetime, timedelta, timezone  # noqa: E402

from models import service_tasks as st  # noqa: E402


def days_ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def age_form(form_id, days, column="created_at"):
    with get_db() as c:
        c.execute(f"UPDATE dotation_forms SET {column} = ? WHERE id = ?", (days_ago(days), form_id))
    notif.clear_cache()


def item_of(user, kind, form_id, code):
    task = tasks(user, kind)
    return next((i for i in (task or {"items": []})["items"] if i["form_id"] == form_id and i["item_key"] == code), None)


def test_age_en_jours_et_dates_inconnues():
    now = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
    assert st.age_days("2026-10-05T09:00:00", now) == 5
    assert st.age_days("2026-10-05T09:00:00+00:00", now) == 5
    assert st.age_days("2026-10-05T09:00:00Z", now) == 5
    assert st.age_days("2026-12-01T00:00:00", now) == 0   # date future (départ planifié) : jamais en retard
    assert st.age_days(None, now) == 0 and st.age_days("n'importe quoi", now) == 0


def test_une_tache_recente_n_est_ni_en_retard_ni_escaladee(equipe):
    code = make_resource(equipe["label"], False)
    form_id, _ = make_dossier([code])
    item = item_of(equipe["titulaire"], KIND_PROVISION, form_id, code)
    assert item["late"] is False and item["escalated"] is False and item["age_days"] == 0
    assert tasks(equipe["titulaire"], KIND_PROVISION)["severity"] == "normal"


def test_en_retard_apres_trois_jours_visible_du_service_seulement(equipe):
    code = make_resource(equipe["label"], False)
    form_id, _ = make_dossier([code])
    age_form(form_id, 4)
    item = item_of(equipe["collegue"], KIND_PROVISION, form_id, code)
    assert item["late"] is True and item["escalated"] is False and item["age_days"] == 4
    task = tasks(equipe["collegue"], KIND_PROVISION)
    assert task["severity"] == "late" and task["late_count"] >= 1
    assert item_of("admin", KIND_PROVISION, form_id, code) is None  # pas encore escaladée : les administrateurs ne la voient pas


def test_escaladee_apres_sept_jours_chez_les_administrateurs(equipe):
    code = make_resource(equipe["label"], False)
    form_id, _ = make_dossier([code])
    age_form(form_id, 8)
    assert item_of(equipe["titulaire"], KIND_PROVISION, form_id, code)["escalated"] is True
    admin_item = item_of("admin", KIND_PROVISION, form_id, code)
    assert admin_item and admin_item["escalated"] is True and admin_item["unattended"] is False
    # un administrateur peut la terminer
    resp = client_for("admin").post("/api/service-tasks/done", json={"kind": KIND_PROVISION, "form_id": form_id, "item_key": code}, headers=H)
    assert resp.status_code == 200
    assert item_of(equipe["titulaire"], KIND_PROVISION, form_id, code) is None


def test_les_seuils_sont_reglables(monkeypatch, equipe):
    code = make_resource(equipe["label"], False)
    form_id, _ = make_dossier([code])
    age_form(form_id, 2)
    assert item_of(equipe["titulaire"], KIND_PROVISION, form_id, code)["late"] is False
    monkeypatch.setattr(st, "LATE_DAYS", 1)
    monkeypatch.setattr(st, "ESCALATE_DAYS", 2)
    item = item_of(equipe["titulaire"], KIND_PROVISION, form_id, code)
    assert item["late"] is True and item["escalated"] is True
    assert item_of("admin", KIND_PROVISION, form_id, code) is not None


def test_l_anciennete_d_une_tache_a_fermer_part_de_la_restitution(equipe):
    code = make_resource(equipe["label"], False)
    form_id, _ = make_dossier([code])
    age_form(form_id, 30)  # dossier ancien...
    set_status(form_id, "partial_return")
    with get_db() as c:
        c.execute("UPDATE dotation_forms SET returned_at = ? WHERE id = ?", (days_ago(1), form_id))  # ...mais restitué hier
    notif.clear_cache()
    item = item_of(equipe["titulaire"], KIND_DEPROVISION, form_id, code)
    assert item["age_days"] == 1 and item["late"] is False
    age_form(form_id, 5, column="returned_at")
    assert item_of(equipe["titulaire"], KIND_DEPROVISION, form_id, code)["late"] is True


def test_rouvrir_un_fait_par_erreur(equipe):
    code = make_resource(equipe["label"], False)
    form_id, _ = make_dossier([code])
    body = {"kind": KIND_PROVISION, "form_id": form_id, "item_key": code}
    client_for(equipe["titulaire"]).post("/api/service-tasks/done", json=body, headers=H)
    recent = client_for(equipe["collegue"]).get("/api/service-tasks/recent").get_json()["items"]
    entry = next(i for i in recent if i["form_id"] == form_id and i["item_key"] == code)
    assert entry["done_by"] == equipe["titulaire"] and entry["service"] == equipe["label"]
    assert not any(i["form_id"] == form_id for i in client_for(equipe["etranger"]).get("/api/service-tasks/recent").get_json()["items"])
    assert client_for(equipe["etranger"]).post("/api/service-tasks/reopen", json=body, headers=H).status_code == 404
    resp = client_for(equipe["collegue"]).post("/api/service-tasks/reopen", json=body, headers=H)
    assert resp.status_code == 200 and resp.get_json()["reopened"] is True
    assert item_of(equipe["titulaire"], KIND_PROVISION, form_id, code) is not None  # la tâche est revenue pour tous
    assert client_for(equipe["collegue"]).post("/api/service-tasks/reopen", json=body, headers=H).status_code == 404  # déjà rouverte
    with get_db() as c:
        assert c.execute("SELECT COUNT(*) FROM app_logs WHERE action_type = 'service_task_reopened'").fetchone()[0] >= 1


def test_un_administrateur_voit_et_rouvre_tout(equipe):
    code = make_resource(equipe["label"], False)
    form_id, _ = make_dossier([code])
    body = {"kind": KIND_PROVISION, "form_id": form_id, "item_key": code}
    client_for(equipe["titulaire"]).post("/api/service-tasks/done", json=body, headers=H)
    assert any(i["form_id"] == form_id for i in client_for("admin").get("/api/service-tasks/recent").get_json()["items"])
    assert client_for("admin").post("/api/service-tasks/reopen", json=body, headers=H).status_code == 200


def test_l_historique_d_avant_les_notifications_et_les_vieux_fait_ne_sont_pas_listes(equipe):
    code = make_resource(equipe["label"], False)
    form_id, _ = make_dossier([code])
    with get_db() as c:
        c.execute("INSERT OR REPLACE INTO service_task_done (kind, form_id, item_key, done_at, done_by, note) VALUES ('provision', ?, ?, ?, NULL, 'avant les notifications')",
                  (form_id, code, days_ago(1)))
    assert not any(i["form_id"] == form_id for i in client_for(equipe["titulaire"]).get("/api/service-tasks/recent").get_json()["items"])  # baseline : pas d'auteur
    with get_db() as c:
        c.execute("UPDATE service_task_done SET done_by = ?, done_at = ? WHERE form_id = ?", (equipe["titulaire"], days_ago(45), form_id))
    assert not any(i["form_id"] == form_id for i in client_for(equipe["titulaire"]).get("/api/service-tasks/recent").get_json()["items"])  # plus de 30 jours


def test_le_nom_est_masque_dans_les_taches_recentes_pour_un_profil_masque(equipe):
    code = make_resource(equipe["label"], False)
    form_id, nom = make_dossier([code], nom=f"DURAND{uid()}")
    client_for(equipe["titulaire"]).post("/api/service-tasks/done", json={"kind": KIND_PROVISION, "form_id": form_id, "item_key": code}, headers=H)
    full = next(i for i in client_for(equipe["collegue"]).get("/api/service-tasks/recent").get_json()["items"] if i["form_id"] == form_id)
    assert nom in full["who"]
    with get_users_db() as users:
        users.execute("INSERT OR REPLACE INTO groups (key, label, description, permissions_json, data_scope, created_at, updated_at) VALUES ('masque_recent','M','','[]','masked','x','x')")
        users.execute("DELETE FROM user_groups WHERE username = ?", (equipe["collegue"],))
        users.execute("INSERT INTO user_groups (username, group_key) VALUES (?, 'masque_recent')", (equipe["collegue"],))
    try:
        masked = next(i for i in client_for(equipe["collegue"]).get("/api/service-tasks/recent").get_json()["items"] if i["form_id"] == form_id)
        assert nom not in str(masked) and masked["who"].startswith("Dossier du ")
    finally:
        with get_users_db() as users:
            users.execute("DELETE FROM user_groups WHERE group_key = 'masque_recent'")
            users.execute("DELETE FROM groups WHERE key = 'masque_recent'")


def test_les_fait_d_un_dossier_supprime_sont_purges_les_autres_gardes(equipe):
    code = make_resource(equipe["label"], False)
    form_id, _ = make_dossier([code])
    client_for(equipe["titulaire"]).post("/api/service-tasks/done", json={"kind": KIND_PROVISION, "form_id": form_id, "item_key": code}, headers=H)
    with get_db() as c:
        c.execute("INSERT INTO service_task_done (kind, form_id, item_key, done_at, done_by, note) VALUES ('provision', 'form_disparu', 'x', 'x', 'y', '')")
        assert st.purge_orphans(c) >= 1
        assert c.execute("SELECT COUNT(*) FROM service_task_done WHERE form_id = 'form_disparu'").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM service_task_done WHERE form_id = ?", (form_id,)).fetchone()[0] == 1  # le « Fait » d'un dossier existant reste : il est la mémoire du déjà fait
        assert st.purge_orphans(c) == 0  # idempotent


def test_les_routes_de_reouverture_exigent_une_session():
    anonymous = app.test_client()
    assert anonymous.get("/api/service-tasks/recent").status_code == 401
    assert anonymous.post("/api/service-tasks/reopen", json={}, headers=H).status_code == 401
    assert client_for("admin").post("/api/service-tasks/reopen", json={"kind": "autre"}, headers=H).status_code == 400


def test_la_page_mes_taches_exige_une_session():
    assert app.test_client().get("/tasks.html").status_code == 302  # renvoyée vers la connexion
    page = client_for("admin").get("/tasks.html")
    assert page.status_code == 200 and "Mes tâches" in page.get_data(as_text=True)
