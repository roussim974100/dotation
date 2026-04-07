#!/usr/bin/env python3
"""
Test de déploiement complet — Ministère de la Défense
Simule une installation neuve avec le profil "Administration publique"
et un workflow dossier complet (arrivée agent + arrivée contractuel + prestataire).

Usage : python3 scripts/test_deploiement_defense.py
"""

import io
import json
import os
import sys
import tempfile
import traceback
import bcrypt

# Force UTF-8 sur la sortie standard (Windows cp1252 sinon)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

PASS = "\033[92m[OK]\033[0m"
FAIL = "\033[91m[ERREUR]\033[0m"
WARN = "\033[93m[AVERT]\033[0m"
INFO = "\033[94m[INFO]\033[0m"

errors = []

def ok(msg):   print(f"  {PASS} {msg}")
def fail(msg): print(f"  {FAIL} {msg}"); errors.append(msg)
def warn(msg): print(f"  {WARN} {msg}")
def info(msg): print(f"  {INFO} {msg}")

def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

# ---------------------------------------------------------------------------
# Setup environnement isolé
# ---------------------------------------------------------------------------

tmp = tempfile.mkdtemp(prefix="test_defense_")
DB_PATH   = os.path.join(tmp, "defense.db")
USERS_PATH = os.path.join(tmp, "users.json")

def make_users_json():
    admin_hash = bcrypt.hashpw(b"Admin1234!", bcrypt.gensalt()).decode()
    config = {
        "groups": {
            "admin": {
                "label": "Administration",
                "permissions": ["*"],
                "data_scope": "full",
            }
        },
        "users": [{
            "username": "admin.defense",
            "password_hash": admin_hash,
            "groups": ["admin"],
            "is_active": True,
            "status": "active",
        }],
    }
    with open(USERS_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False)

make_users_json()

import database, auth
database.DB_PATH = DB_PATH
auth.USERS_FILE  = USERS_PATH

from app import app as flask_app, init_db
from models.settings import seed_app_settings, DEFAULT_APP_SETTINGS, build_public_settings_payload, _parse_beneficiary_types

flask_app.config["TESTING"] = True
flask_app.config["SECRET_KEY"] = "test-defense-secret"

with flask_app.app_context():
    init_db()
    with database.get_db() as conn:
        seed_app_settings(conn)

client = flask_app.test_client()

def csrf():
    r = client.get("/api/csrf-token")
    return r.get_json()["token"]

def login():
    t = csrf()
    client.post("/login", data={
        "username": "admin.defense",
        "password": "Admin1234!",
        "csrf_token": t,
    })

def api_post(path, body):
    t = csrf()
    return client.post(path, json=body, headers={"X-CSRF-Token": t})

def api_put(path, body):
    t = csrf()
    return client.put(path, json=body, headers={"X-CSRF-Token": t})

def api_get(path):
    return client.get(path)

# ---------------------------------------------------------------------------
# Phase 1 — Installation neuve
# ---------------------------------------------------------------------------
section("Phase 1 — Installation neuve (DB vierge)")

with flask_app.app_context():
    with database.get_db() as conn:
        row = conn.execute(
            "SELECT setting_value FROM app_settings WHERE setting_key='setup_completed'"
        ).fetchone()
        if row and row[0] == "0":
            ok("setup_completed = '0' au démarrage")
        else:
            fail(f"setup_completed attendu '0', obtenu {row[0] if row else 'absent'}")

        row2 = conn.execute(
            "SELECT setting_value FROM app_settings WHERE setting_key='org_name'"
        ).fetchone()
        val = row2[0] if row2 else ""
        if val == "" or val is None:
            ok("org_name vide (aucune référence en dur)")
        else:
            warn(f"org_name = '{val}' (devrait être vide pour une installation neuve)")

        row3 = conn.execute(
            "SELECT COUNT(*) FROM service_catalog"
        ).fetchone()
        if row3[0] == 0:
            ok("Catalogue services vide (seed conditionnel OK)")
        else:
            ok(f"Catalogue services pré-seedé ({row3[0]} services génériques)")

        # Vérifier absence de références à Publier
        rows_publier = conn.execute(
            "SELECT setting_key, setting_value FROM app_settings WHERE setting_value LIKE '%publier%' OR setting_value LIKE '%Publier%'"
        ).fetchall()
        if not rows_publier:
            ok("Aucune référence à 'Publier' dans les settings")
        else:
            for k, v in rows_publier:
                fail(f"Référence Publier trouvée : {k} = {v}")

# ---------------------------------------------------------------------------
# Phase 2 — Setup wizard (API)
# ---------------------------------------------------------------------------
section("Phase 2 — Setup wizard Ministère de la Défense")

login()

r = api_get("/api/setup/status")
if r.status_code == 200:
    data = r.get_json()
    if not data["setupCompleted"]:
        ok("GET /api/setup/status -> setupCompleted=false")
    else:
        fail("setup déjà marqué complété alors que c'est une installation neuve")
else:
    fail(f"GET /api/setup/status -> HTTP {r.status_code}")

DEFENSE_CONFIG = {
    "org_context":       "public_administration",
    "org_name":          "Ministère de la Défense",
    "dpo_email":         "dpo@defense.gouv.fr",
    "beneficiary_types": "fonctionnaire:Fonctionnaire,contractuel:Contractuel(le),militaire:Militaire,prestataire:Prestataire",
    "support_name":      "DSI Défense",
    "support_role":      "Direction des Systèmes d'Information",
    "support_email":     "support-si@defense.gouv.fr",
}

r = api_post("/api/setup/complete", DEFENSE_CONFIG)
if r.status_code == 200:
    ok("POST /api/setup/complete -> 200")
else:
    fail(f"POST /api/setup/complete -> HTTP {r.status_code} : {r.get_data(as_text=True)[:200]}")

with flask_app.app_context():
    with database.get_db() as conn:
        row = conn.execute(
            "SELECT setting_value FROM app_settings WHERE setting_key='setup_completed'"
        ).fetchone()
        if row and row[0] == "1":
            ok("setup_completed = '1' en DB après wizard")
        else:
            fail("setup_completed non mis à '1' après wizard")

        for key, expected in [
            ("org_name",          "Ministère de la Défense"),
            ("org_context",       "public_administration"),
            ("dpo_email",         "dpo@defense.gouv.fr"),
        ]:
            row = conn.execute(
                "SELECT setting_value FROM app_settings WHERE setting_key=?", (key,)
            ).fetchone()
            val = row[0] if row else None
            if val == expected:
                ok(f"{key} = '{val}'")
            else:
                fail(f"{key} attendu '{expected}', obtenu '{val}'")

# ---------------------------------------------------------------------------
# Phase 3 — Branding et contexte organisationnel
# ---------------------------------------------------------------------------
section("Phase 3 — Branding public settings")

r = api_get("/api/settings/public")
if r.status_code == 200:
    ok("GET /api/settings/public -> 200")
    settings = r.get_json()

    if settings.get("orgName") == "Ministère de la Défense":
        ok(f"orgName = '{settings['orgName']}'")
    else:
        fail(f"orgName attendu 'Ministère de la Défense', obtenu '{settings.get('orgName')}'")

    if settings.get("orgContext") == "public_administration":
        ok(f"orgContext = '{settings['orgContext']}'")
    else:
        fail(f"orgContext attendu 'public_administration', obtenu '{settings.get('orgContext')}'")

    bt = settings.get("beneficiaryTypes", [])
    bt_values = [t["value"] for t in bt]
    bt_labels = [t["label"] for t in bt]

    for v, l in [
        ("fonctionnaire", "Fonctionnaire"),
        ("contractuel",   "Contractuel(le)"),
        ("militaire",     "Militaire"),
        ("prestataire",   "Prestataire"),
    ]:
        if v in bt_values:
            ok(f"Type bénéficiaire '{v}' ({l}) présent")
        else:
            fail(f"Type bénéficiaire '{v}' ABSENT de beneficiaryTypes")

    if "elu" not in bt_values:
        ok("Type 'elu' absent (correct pour une administration)")
    else:
        fail("Type 'elu' présent alors qu'on est en public_administration")

    if settings.get("setupCompleted") is True:
        ok("setupCompleted = true dans les settings publics")
    else:
        fail("setupCompleted devrait être true après wizard")
else:
    fail(f"GET /api/settings/public -> HTTP {r.status_code}")

# ---------------------------------------------------------------------------
# Phase 4 — Création de dossiers avec les nouveaux types
# ---------------------------------------------------------------------------
section("Phase 4 — Création de dossiers")

def make_dossier(nom, prenom, qualite, service, fonction):
    return {
        "beneficiaire": {"nom": nom, "prenom": prenom, "qualite": qualite,
                         "service": service, "fonction": fonction},
        "dossier": {"type": "arrivee"},
        "workflow": {"status": "draft"},
        "validation": {"rgpdAccepted": True},
        "restitution": {},
        "meta": {},
    }

DOSSIERS = [
    {"desc": "Fonctionnaire — Jean Martin (arrivee)",
     "payload": make_dossier("Martin", "Jean", "fonctionnaire", "DSI", "Developpeur")},
    {"desc": "Contractuel — Sophie Dubois (arrivee)",
     "payload": make_dossier("Dubois", "Sophie", "contractuel", "RH", "Chargee RH")},
    {"desc": "Militaire — Col. Pierre Leroy (arrivee)",
     "payload": make_dossier("Leroy", "Pierre", "militaire", "Etat-major", "Colonel")},
    {"desc": "Prestataire — Marc Durand (arrivee)",
     "payload": make_dossier("Durand", "Marc", "prestataire", "DSI", "Consultant securite")},
]

created_ids = []
for d in DOSSIERS:
    r = api_post("/api/forms", d["payload"])
    if r.status_code == 201:
        data = r.get_json()
        form_id = (data.get("data") or {}).get("meta", {}).get("id") or data.get("id")
        created_ids.append(form_id)
        ok(f"{d['desc']} -> cree (id: {form_id[:8] if form_id else 'N/A'})")
    else:
        fail(f"{d['desc']} -> HTTP {r.status_code} : {r.get_data(as_text=True)[:150]}")

# Vérifier qu'aucun dossier n'a de mandat (pas public_collectivite)
if created_ids:
    with flask_app.app_context():
        with database.get_db() as conn:
            for form_id in created_ids:
                if not form_id:
                    continue
                row = conn.execute(
                    "SELECT mandat, beneficiary_type FROM dotation_forms WHERE id=?", (form_id,)
                ).fetchone()
                if row:
                    if not row[0]:
                        ok(f"Dossier {form_id[:8]}... mandat vide (correct, pas collectivite)")
                    else:
                        warn(f"Dossier {form_id[:8]}... mandat = '{row[0]}' (inattendu)")

# ---------------------------------------------------------------------------
# Phase 5 — Vérification absence du type "elu" dans le formulaire
# ---------------------------------------------------------------------------
section("Phase 5 — Tentative de créer un dossier avec type 'elu' (doit échouer ou être accepté tel quel)")

r = api_post("/api/forms", make_dossier("Test", "Elu", "elu", "DSI", "Test"))
# L'app accepte n'importe quelle qualite (pas de validation serveur sur les types)
# mais c'est un test de cohérence — dans un déploiement Défense ce type ne devrait pas être utilisé
if r.status_code == 201:
    warn("Dossier avec qualite='elu' accepté côté serveur (pas de validation des types côté API — comportement attendu, c'est au frontend de limiter)")
else:
    info(f"Dossier qualite='elu' rejeté HTTP {r.status_code}")

# ---------------------------------------------------------------------------
# Phase 6 — Workflow : liste, détail, statuts
# ---------------------------------------------------------------------------
section("Phase 6 — Workflow : lecture des dossiers")

r = api_get("/api/forms")
if r.status_code == 200:
    forms = r.get_json()
    total = len(forms) if isinstance(forms, list) else forms.get("total", "?")
    ok(f"GET /api/forms -> {total} dossiers accessibles")
else:
    fail(f"GET /api/forms -> HTTP {r.status_code}")

if created_ids:
    r = api_get(f"/api/forms/{created_ids[0]}")
    if r.status_code == 200:
        detail = r.get_json()
        qualite = detail.get("beneficiaire", {}).get("qualite", "?")
        ok(f"GET /api/forms/{created_ids[0][:8] if created_ids[0] else 'N/A'}... -> detail OK (qualite={qualite})")
    else:
        fail(f"GET détail dossier -> HTTP {r.status_code}")

# ---------------------------------------------------------------------------
# Phase 7 — Changer settings : vérifier que les dossiers existants survivent
# ---------------------------------------------------------------------------
section("Phase 7 — Modification des settings après création de dossiers")

r = api_put("/api/admin/settings", {
    "org_name":          "Ministère de la Défense — DIRISI",
    "org_context":       "public_administration",
    "beneficiary_types": "fonctionnaire:Fonctionnaire,contractuel:Contractuel(le),militaire:Militaire,prestataire:Prestataire",
    "dpo_email":         "dpo@defense.gouv.fr",
    "brand_logo_mode":   "none",
    "theme_id":          "institutionnel",
    "dark_mode_policy":  "auto",
})
if r.status_code == 200:
    ok("PUT /api/admin/settings -> 200")
else:
    fail(f"PUT /api/admin/settings -> HTTP {r.status_code}")

r2 = api_get("/api/settings/public")
if r2.status_code == 200:
    s = r2.get_json()
    if s.get("orgName") == "Ministère de la Défense — DIRISI":
        ok(f"orgName mis à jour : '{s['orgName']}'")
    else:
        fail(f"orgName non mis à jour : '{s.get('orgName')}'")

# Les dossiers créés avant la modif doivent toujours être accessibles
if created_ids:
    r3 = api_get(f"/api/forms/{created_ids[2]}")
    if r3.status_code == 200:
        ok(f"Dossier militaire toujours accessible après modif settings")
    else:
        fail(f"Dossier militaire inaccessible après modif settings : HTTP {r3.status_code}")

# ---------------------------------------------------------------------------
# Phase 8 — Logs d'audit
# ---------------------------------------------------------------------------
section("Phase 8 — Logs d'audit")

r = api_get("/api/admin/logs?scope=admin")
if r.status_code == 200:
    logs = r.get_json()
    entries = logs if isinstance(logs, list) else logs.get("logs", [])
    setup_logs = [l for l in entries if "setup" in (l.get("action_type") or "").lower()
                  or "setup" in (l.get("action_label") or "").lower()]
    if setup_logs:
        ok(f"Log setup wizard trouvé ({len(setup_logs)} entrée(s))")
    else:
        warn("Aucun log d'audit pour le setup wizard")
    ok(f"{len(entries)} log(s) d'administration au total")
else:
    warn(f"GET /api/admin/logs -> HTTP {r.status_code} (endpoint peut-être différent)")

# ---------------------------------------------------------------------------
# Phase 9 — Régression : tests existants
# ---------------------------------------------------------------------------
section("Phase 9 — Régression (tests pytest)")

import subprocess
result = subprocess.run(
    [sys.executable, "-m", "pytest", "backend/tests/", "-q", "--tb=short"],
    capture_output=True, text=True, encoding="utf-8", errors="replace",
    cwd=os.path.join(os.path.dirname(__file__), ".."),
    timeout=300,
)
last_lines = result.stdout.strip().split("\n")[-3:]
for line in last_lines:
    if line.strip():
        info(line)
if result.returncode == 0:
    ok("Tous les tests pytest passent")
else:
    fail("Des tests pytest ont échoué")
    print(result.stdout[-500:])

# ---------------------------------------------------------------------------
# Rapport final
# ---------------------------------------------------------------------------
section("Rapport final")

if errors:
    print(f"\n  {FAIL} {len(errors)} ERREUR(S) DÉTECTÉE(S) :")
    for e in errors:
        print(f"     • {e}")
    sys.exit(1)
else:
    print(f"\n  {PASS} Test de déploiement Ministère de la Défense : SUCCÈS COMPLET")
    print(f"  DB temporaire : {DB_PATH}")
    print()
