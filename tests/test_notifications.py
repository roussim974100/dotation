"""Notifications, lot 1 : une ressource est rattachée à un service du catalogue (le lien est le libellé du « service émetteur »),
un service porte une liste de comptes titulaires, et les administrateurs reçoivent une tâche tant que des ressources n'ont pas
de service référent (avec une suggestion qu'ils valident ou changent). Base temporaire (tests/conftest.py)."""
import sqlite3
import time

import bcrypt
import pytest

from app import app
from auth import create_user, delete_user, update_user
from database import get_db
from migrations import MIGRATIONS, _m_service_referents
from models.notifications import (
    KIND_RESOURCES_MISSING_SERVICE, active_services, normalize_label, open_tasks, resources_missing_service, suggest_service_id,
)

H = {"X-CSRF-Token": "jeton"}


def uid():
    return str(time.time_ns())


def client_for(user="admin"):
    client = app.test_client()
    with client.session_transaction() as s:
        s["user"] = user
        s["csrf_token"] = "jeton"
    return client


def add_service(label):
    with get_db() as c:
        service_id = f"svc_{uid()}"
        c.execute("INSERT INTO service_catalog (id, label, is_active, is_builtin, created_at, updated_at) VALUES (?,?,1,0,'x','x')", (service_id, label))
    return service_id


def add_resource(label, issuer):
    with get_db() as c:
        resource_id = f"res_{uid()}"
        c.execute("INSERT INTO resource_catalog (id, code, label, category, issuer_service, created_at, updated_at) VALUES (?,?,?,?,?,'x','x')",
                  (resource_id, f"code_{resource_id}", label, "materiel", issuer))
    return resource_id


def issuer_of(resource_id):
    with get_db() as c:
        return c.execute("SELECT issuer_service FROM resource_catalog WHERE id = ?", (resource_id,)).fetchone()[0]


def my_tasks(client):
    return client.get("/api/notifications").get_json()


def group_for(tasks, resource_id):
    task = next((t for t in tasks["tasks"] if t["kind"] == KIND_RESOURCES_MISSING_SERVICE), None)
    if not task:
        return None
    return next((g for g in task["groups"] if any(r["id"] == resource_id for r in g["resources"])), None)


@pytest.fixture
def compte():
    name = f"notif_{uid()}"
    assert create_user(name, bcrypt.hashpw(b"Mot-2-Passe-Notif1!", bcrypt.gensalt()).decode(), ["lecture"])
    yield name
    delete_user(name)


# ---- libellés et suggestions ---------------------------------------------------------------------------------------

def test_normalize_label():
    assert normalize_label("  Services  Généraux ") == "services generaux"
    assert normalize_label("Bâtiment") == normalize_label("BATIMENT")


def test_suggestions():
    services = [{"id": "1", "label": "DSI"}, {"id": "2", "label": "DRH"}, {"id": "3", "label": "Services généraux et techniques"}]
    assert suggest_service_id("Informatique", services) == "1"          # appellation courante de la DSI
    assert suggest_service_id("Ressources humaines", services) == "2"
    assert suggest_service_id("dsi", services) == "1"                     # identique à la casse près
    assert suggest_service_id("Services generaux", services) == "3"      # un seul libellé contient celui-ci
    assert suggest_service_id("Cuisine", services) is None                # on ne devine pas
    assert suggest_service_id("", services) is None


# ---- tâche des administrateurs --------------------------------------------------------------------------------------

def test_ressource_sans_service_du_catalogue_devient_une_tache_avec_suggestion():
    marque = f"phoenix{uid()}"
    service_id = add_service(f"Direction {marque} et moyens")  # un seul libellé contient l'ancien nom : suggestion
    resource = add_resource("Imprimante test", marque.upper())
    group = group_for(my_tasks(client_for()), resource)
    assert group and group["legacy_service"] == marque.upper()
    assert group["suggested_service_id"] == service_id


def test_ressources_au_meme_ancien_nom_sont_regroupees_en_une_decision():
    ancien = f"Ancien regroupé {uid()}"
    first, second = add_resource("Groupée 1", ancien), add_resource("Groupée 2", ancien)
    tasks = my_tasks(client_for())
    group = group_for(tasks, first)
    assert group is group_for(tasks, second) or group == group_for(tasks, second)
    assert {r["id"] for r in group["resources"]} == {first, second}
    assert group["suggested_service_id"] is None


def test_ressource_au_service_du_catalogue_n_est_pas_une_tache():
    label = f"Service ok {uid()}"
    add_service(label)
    resource = add_resource("Ressource rattachée", label)
    assert group_for(my_tasks(client_for()), resource) is None
    with get_db() as c:
        assert resource not in {r["id"] for r in resources_missing_service(c)}


def test_service_vide_ou_inactif_est_une_tache():
    label = f"Service éteint {uid()}"
    service_id = add_service(label)
    with get_db() as c:
        c.execute("UPDATE service_catalog SET is_active = 0 WHERE id = ?", (service_id,))
    sans_service = add_resource("Sans service", "")
    service_inactif = add_resource("Service inactif", label)
    tasks = my_tasks(client_for())
    assert group_for(tasks, sans_service) is not None
    assert group_for(tasks, service_inactif) is not None


def test_la_tache_n_est_visible_que_de_ceux_qui_gerent_les_services(compte):
    add_resource("Pour la tâche", "Introuvable")
    assert my_tasks(client_for())["count"] >= 1
    assert my_tasks(client_for(compte)) == {"tasks": [], "count": 0}  # groupe « lecture » : rien
    assert client_for(compte).get("/api/session").get_json()["notifications_count"] == 0
    assert client_for().get("/api/session").get_json()["notifications_count"] >= 1


def test_anonyme_refuse():
    assert app.test_client().get("/api/notifications").status_code == 401


# ---- choix de l'administrateur --------------------------------------------------------------------------------------

def test_l_administrateur_choisit_le_service_et_la_tache_disparait():
    service_id = add_service(f"Choisi {uid()}")
    resources = [add_resource("A choisir 1", "Ancien nom"), add_resource("A choisir 2", "Ancien nom")]
    admin = client_for()
    resp = admin.post("/api/admin/resources/services", json={"assignments": [{"resource_ids": resources, "service_id": service_id}]}, headers=H)
    assert resp.status_code == 200 and resp.get_json()["assigned"] == 2
    with get_db() as c:
        label = c.execute("SELECT label FROM service_catalog WHERE id = ?", (service_id,)).fetchone()[0]
        journal = c.execute("SELECT details_json FROM app_logs WHERE action_type = 'resources_service_assigned' ORDER BY id DESC LIMIT 1").fetchone()[0]
    assert all(issuer_of(r) == label for r in resources)
    assert group_for(my_tasks(admin), resources[0]) is None
    assert "Ancien nom" in journal  # l'ancienne valeur est conservée au journal


def test_tout_ou_rien():
    service_id = add_service(f"Tout ou rien {uid()}")
    bonne = add_resource("Bonne", "Autre ancien nom")
    admin = client_for()
    resp = admin.post("/api/admin/resources/services", json={"assignments": [
        {"resource_ids": [bonne], "service_id": service_id}, {"resource_ids": ["res_inconnue"], "service_id": service_id}]}, headers=H)
    assert resp.status_code == 400 and resp.get_json()["error"] == "resource_unknown"
    assert issuer_of(bonne) == "Autre ancien nom"  # la première n'a pas été appliquée
    resp = admin.post("/api/admin/resources/services", json={"assignments": [{"resource_ids": [bonne], "service_id": "svc_inconnu"}]}, headers=H)
    assert resp.status_code == 400 and resp.get_json()["error"] == "service_unknown"
    resp = admin.post("/api/admin/resources/services", json={"assignments": [{"resource_ids": [], "service_id": service_id}]}, headers=H)
    assert resp.status_code == 400


def test_un_non_administrateur_ne_peut_pas_choisir(compte):
    service_id = add_service(f"Interdit {uid()}")
    resource = add_resource("Interdite", "X")
    resp = client_for(compte).post("/api/admin/resources/services", json={"assignments": [{"resource_ids": [resource], "service_id": service_id}]}, headers=H)
    assert resp.status_code == 403 and issuer_of(resource) == "X"


# ---- vie d'un service -----------------------------------------------------------------------------------------------

def test_renommer_un_service_fait_suivre_ses_ressources():
    ancien = f"Ancien nom {uid()}"
    service_id = add_service(ancien)
    resource = add_resource("Suit son service", ancien)
    nouveau = f"Nouveau nom {uid()}"
    resp = client_for().put(f"/api/admin/services/{service_id}", json={"label": nouveau}, headers=H)
    assert resp.status_code == 200
    assert issuer_of(resource) == nouveau
    assert group_for(my_tasks(client_for()), resource) is None  # toujours rattachée


def test_supprimer_un_service_remet_ses_ressources_en_tache_et_vide_ses_titulaires(compte):
    label = f"A supprimer {uid()}"
    service_id = add_service(label)
    resource = add_resource("Orpheline", label)
    admin = client_for()
    assert admin.put(f"/api/admin/services/{service_id}/referents", json={"usernames": [compte]}, headers=H).status_code == 200
    assert admin.delete(f"/api/admin/services/{service_id}", headers=H).status_code == 200
    assert group_for(my_tasks(admin), resource) is not None
    with get_db() as c:
        assert c.execute("SELECT COUNT(*) FROM service_referents WHERE service_id = ?", (service_id,)).fetchone()[0] == 0


# ---- titulaires -----------------------------------------------------------------------------------------------------

def test_titulaires_d_un_service(compte):
    service_id = add_service(f"Avec titulaires {uid()}")
    admin = client_for()
    resp = admin.put(f"/api/admin/services/{service_id}/referents", json={"usernames": [compte, compte, "admin"]}, headers=H)
    assert resp.status_code == 200 and resp.get_json()["usernames"] == [compte, "admin"]  # sans doublon, ordre conservé
    assert sorted(admin.get(f"/api/admin/services/{service_id}/referents").get_json()["usernames"]) == sorted([compte, "admin"])
    listed = next(s for s in admin.get("/api/admin/services").get_json() if s["id"] == service_id)
    assert sorted(listed["referents"]) == sorted([compte, "admin"])
    # remplacement complet
    assert admin.put(f"/api/admin/services/{service_id}/referents", json={"usernames": []}, headers=H).get_json()["usernames"] == []


def test_titulaire_inconnu_ou_desactive_refuse(compte):
    service_id = add_service(f"Refus titulaires {uid()}")
    admin = client_for()
    assert admin.put(f"/api/admin/services/{service_id}/referents", json={"usernames": ["personne_xyz"]}, headers=H).status_code == 400
    update_user(compte, is_active=0, status="disabled")
    assert admin.put(f"/api/admin/services/{service_id}/referents", json={"usernames": [compte]}, headers=H).status_code == 400
    assert admin.put("/api/admin/services/svc_inconnu/referents", json={"usernames": []}, headers=H).status_code == 404
    assert admin.put(f"/api/admin/services/{service_id}/referents", json={"usernames": "pas une liste"}, headers=H).status_code == 400


def test_compte_supprime_quitte_ses_services(compte):
    service_id = add_service(f"Départ {uid()}")
    admin = client_for()
    admin.put(f"/api/admin/services/{service_id}/referents", json={"usernames": [compte]}, headers=H)
    assert admin.delete(f"/api/admin/users/{compte}", headers=H).status_code == 200
    assert admin.get(f"/api/admin/services/{service_id}/referents").get_json()["usernames"] == []
    create_user(compte, "x", ["lecture"])  # le fixture supprime le compte à la fin


def test_titulaires_reserves_a_ceux_qui_gerent_les_services(compte):
    service_id = add_service(f"Droits {uid()}")
    other = client_for(compte)
    assert other.get(f"/api/admin/services/{service_id}/referents").status_code == 403
    assert other.put(f"/api/admin/services/{service_id}/referents", json={"usernames": [compte]}, headers=H).status_code == 403


# ---- migration 9 ----------------------------------------------------------------------------------------------------

def test_migration_9_cree_la_table_et_rattache_les_noms_equivalents():
    connection = sqlite3.connect(":memory:")
    connection.executescript("""
        CREATE TABLE service_catalog (id TEXT PRIMARY KEY, label TEXT NOT NULL UNIQUE, is_active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE resource_catalog (id TEXT PRIMARY KEY, issuer_service TEXT);
        INSERT INTO service_catalog VALUES ('s1', 'Bâtiment', 1), ('s2', 'DSI', 1), ('s3', 'Fermé', 0);
        INSERT INTO resource_catalog VALUES ('r1', 'batiment'), ('r2', ' dsi '), ('r3', 'Informatique'), ('r4', 'Fermé'), ('r5', NULL), ('r6', 'DSI');
    """)
    _m_service_referents(connection)
    _m_service_referents(connection)  # idempotente
    issuers = dict(connection.execute("SELECT id, issuer_service FROM resource_catalog"))
    assert issuers["r1"] == "Bâtiment" and issuers["r2"] == "DSI" and issuers["r6"] == "DSI"   # ramenés au libellé exact
    assert issuers["r3"] == "Informatique"   # jamais devinée : l'administrateur choisit
    assert issuers["r4"] == "Fermé"          # service inactif : laissé tel quel
    assert issuers["r5"] is None
    assert connection.execute("SELECT COUNT(*) FROM service_referents").fetchone()[0] == 0


def test_la_migration_est_declaree_et_appliquee():
    assert (9, "titulaires_de_service") == next((m[0], m[1]) for m in MIGRATIONS if m[0] == 9)
    with get_db() as c:
        assert c.execute("SELECT 1 FROM schema_migrations WHERE version = 9").fetchone()
        assert c.execute("SELECT 1 FROM sqlite_master WHERE name = 'service_referents'").fetchone()


# ---- service obligatoire à la création d'une ressource ---------------------------------------------------------------

def resource_body(code, issuer, **extra):
    return {"code": code, "label": f"Ressource {code}", "description": "", "category": "materiel", "issuer_service": issuer,
            "requires_return": True, "has_assignment_date": True, "has_assignment_condition": True, "has_assignment_notes": True,
            "display_order": 900, "is_active": True, "tracking_mode": "none", "field_schema": [], **extra}


def test_creer_une_ressource_exige_un_service_du_catalogue():
    label = f"Service création {uid()}"
    add_service(label)
    admin = client_for()
    code = f"creation_{uid()}"
    assert admin.post("/api/admin/resources", json=resource_body(code, ""), headers=H).get_json()["error"] == "issuer_service_required"
    assert admin.post("/api/admin/resources", json=resource_body(code, "Service inventé"), headers=H).get_json()["error"] == "issuer_service_unknown"
    assert admin.post("/api/admin/resources", json=resource_body(code, label.upper()), headers=H).status_code in (200, 201)


def test_modifier_une_ressource_tolere_l_ancien_texte_inchange_mais_pas_un_nouveau_texte_libre():
    label = f"Service édition {uid()}"
    add_service(label)
    legacy = add_resource("Héritée", "Ancien texte libre")
    admin = client_for()
    with get_db() as c:
        code = c.execute("SELECT code FROM resource_catalog WHERE id = ?", (legacy,)).fetchone()[0]
    unchanged = admin.put(f"/api/admin/resources/{legacy}", json=resource_body(code, "Ancien texte libre"), headers=H)
    assert unchanged.status_code == 200, unchanged.get_data(as_text=True)
    assert admin.put(f"/api/admin/resources/{legacy}", json=resource_body(code, "Autre texte libre"), headers=H).get_json()["error"] == "issuer_service_unknown"
    assert admin.put(f"/api/admin/resources/{legacy}", json=resource_body(code, ""), headers=H).get_json()["error"] == "issuer_service_required"
    assert admin.put(f"/api/admin/resources/{legacy}", json=resource_body(code, label), headers=H).status_code == 200
    assert group_for(my_tasks(admin), legacy) is None


# ---- lot 3 : tâches des administrateurs (inscription, nouvelle version, sauvegarde) -------------------------------------

import update_check  # noqa: E402
from models import notifications as notif  # noqa: E402


@pytest.fixture(autouse=True)
def cache_vide():
    notif.clear_cache()
    yield
    notif.clear_cache()


def kinds(client):
    return [t["kind"] for t in my_tasks(client)["tasks"]]


def task_of(client, kind):
    return next((t for t in my_tasks(client)["tasks"] if t["kind"] == kind), None)


def test_inscription_en_attente_est_une_tache_sans_nom(compte):
    admin = client_for()
    before = (task_of(admin, notif.KIND_SIGNUPS_PENDING) or {"count": 0})["count"]
    pending = f"attente_{uid()}"
    assert create_user(pending, bcrypt.hashpw(b"Mot-2-Passe-Attente1!", bcrypt.gensalt()).decode(), ["lecture"], status="pending")
    try:
        task = task_of(admin, notif.KIND_SIGNUPS_PENDING)
        assert task["count"] == before + 1 and task["link"] == "/admin-comptes.html"
        assert pending not in str(task)  # seulement un nombre, aucun identifiant
        assert task_of(client_for(compte), notif.KIND_SIGNUPS_PENDING) is None  # réservé à ceux qui gèrent les comptes
        update_user(pending, status="active")  # validée : la tâche diminue d'elle-même
        assert (task_of(admin, notif.KIND_SIGNUPS_PENDING) or {"count": 0})["count"] == before
    finally:
        delete_user(pending)


def fake_check_file(monkeypatch, tmp_path, latest, age=0, enabled=True):
    path = tmp_path / "check.json"
    path.write_text('{"latest": "%s", "checked_at": %s, "error": null}' % (latest, time.time() - age), encoding="utf-8")
    monkeypatch.setattr(update_check, "CHECK_FILE", str(path))
    monkeypatch.setenv("APP_UPDATE_CHECK", "1" if enabled else "0")
    calls = []
    monkeypatch.setattr(update_check, "_refresh_in_background", lambda: calls.append(1))
    return calls


def test_nouvelle_version_est_une_tache_pour_les_administrateurs(monkeypatch, tmp_path, compte):
    fake_check_file(monkeypatch, tmp_path, "99.0.0")
    task = task_of(client_for(), notif.KIND_UPDATE_AVAILABLE)
    assert task["latest"] == "99.0.0" and task["link"] == "/admin.html"
    assert task_of(client_for(compte), notif.KIND_UPDATE_AVAILABLE) is None


def test_pas_de_tache_si_a_jour_ou_verification_desactivee(monkeypatch, tmp_path):
    fake_check_file(monkeypatch, tmp_path, "0.0.1")
    assert task_of(client_for(), notif.KIND_UPDATE_AVAILABLE) is None
    fake_check_file(monkeypatch, tmp_path, "99.0.0", enabled=False)
    assert task_of(client_for(), notif.KIND_UPDATE_AVAILABLE) is None


def test_la_verification_de_version_ne_bloque_jamais_et_ne_fait_aucun_appel_reseau(monkeypatch, tmp_path):
    """Lu à chaque contrôle de session : une vérification périmée part en arrière-plan, sans jamais attendre le réseau."""
    calls = fake_check_file(monkeypatch, tmp_path, "99.0.0", age=update_check.CHECK_TTL_SECONDS + 60)
    monkeypatch.setattr(update_check, "fetch_latest_version", lambda *a, **k: pytest.fail("appel réseau synchrone"))
    assert task_of(client_for(), notif.KIND_UPDATE_AVAILABLE) is not None  # la valeur en cache sert en attendant
    assert calls == [1]  # et une vérification est lancée en arrière-plan


def fake_backup_health(monkeypatch, level, message="Dernière sauvegarde automatique en échec : disque plein."):
    import backup_schedule
    calls = []
    monkeypatch.setattr(backup_schedule, "health", lambda config, now=None: calls.append(1) or {"level": level, "message": message})
    notif.clear_cache()
    return calls


def test_sauvegarde_en_echec_est_une_tache_urgente(monkeypatch, compte):
    fake_backup_health(monkeypatch, "error")
    task = task_of(client_for(), notif.KIND_BACKUP_FAILED)
    assert task["severity"] == "urgent" and "disque plein" in task["message"] and task["link"] == "/admin-db.html"
    assert task_of(client_for(compte), notif.KIND_BACKUP_FAILED) is None  # réservé au droit de gestion des sauvegardes


@pytest.mark.parametrize("level", ["ok", "info", "warning"])
def test_sauvegarde_en_bonne_sante_n_est_pas_une_tache(monkeypatch, level):
    fake_backup_health(monkeypatch, level)
    assert task_of(client_for(), notif.KIND_BACKUP_FAILED) is None


def test_la_sante_des_sauvegardes_est_mise_en_cache(monkeypatch):
    calls = fake_backup_health(monkeypatch, "error")
    admin = client_for()
    for _ in range(3):
        my_tasks(admin)
    assert len(calls) == 1  # un seul calcul pour trois lectures rapprochées (le fichier d'historique peut être gros)


def test_la_sauvegarde_en_echec_passe_avant_le_reste(monkeypatch, tmp_path):
    fake_backup_health(monkeypatch, "error")
    fake_check_file(monkeypatch, tmp_path, "99.0.0")
    add_resource("Pour l'ordre", "Introuvable ordre")
    order = kinds(client_for())
    assert order[0] == notif.KIND_BACKUP_FAILED
    assert order.index(notif.KIND_UPDATE_AVAILABLE) < order.index(notif.KIND_RESOURCES_MISSING_SERVICE)


def test_le_compteur_de_session_compte_toutes_les_taches(monkeypatch, tmp_path):
    fake_backup_health(monkeypatch, "error")
    fake_check_file(monkeypatch, tmp_path, "99.0.0")
    admin = client_for()
    assert admin.get("/api/session").get_json()["notifications_count"] == len(my_tasks(admin)["tasks"]) >= 2
