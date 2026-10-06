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
