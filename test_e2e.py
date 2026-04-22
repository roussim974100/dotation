import requests
import json
import sys

BASE = "http://localhost:5000"
s = requests.Session()
PASS_COUNT = 0
FAIL_COUNT = 0

def ok(label):
    global PASS_COUNT
    PASS_COUNT += 1
    print(f"  OK  {label}")

def fail(label, detail=""):
    global FAIL_COUNT
    FAIL_COUNT += 1
    print(f"  KO  {label}" + (f" -- {detail}" if detail else ""))

def section(title):
    print(f"\n{'--'*30}")
    print(f"  {title}")
    print(f"{'--'*30}")

def get_csrf():
    r = s.get(f"{BASE}/api/csrf-token")
    return r.json()["token"]

def login(user="admin", pwd="admin"):
    csrf = get_csrf()
    r = s.post(f"{BASE}/login",
               data={"username": user, "password": pwd, "csrf_token": csrf},
               allow_redirects=False)
    return r.status_code in (200, 302)

def api(method, path, **kwargs):
    url = f"{BASE}{path}"
    csrf = get_csrf()
    headers = kwargs.pop("headers", {})
    headers["X-CSRF-Token"] = csrf
    headers["Content-Type"] = "application/json"
    r = getattr(s, method)(url, headers=headers, **kwargs)
    return r

# ----------------------------------------------------------
section("0. Connexion admin")
# ----------------------------------------------------------
logged = login("e2e.test", "E2eTest1234!")
if logged:
    ok("Login admin")
else:
    fail("Login admin")
    sys.exit(1)

# ----------------------------------------------------------
section("1. Dossier ARRIVEE - cycle complet avec signature")
# ----------------------------------------------------------

payload = {
    "meta": {"dossierType": "arrivee"},
    "beneficiaire": {
        "nom": "Durand", "prenom": "Marie",
        "service": "DSI", "fonction": "Developpeuse"
    },
    "dossier": {"serviceDestination": "Direction Informatique"},
    "workflow": {"status": "draft"}
}
r = api("post", "/api/forms", json=payload)
if r.status_code == 201:
    form_id = r.json()["summary"]["id"]
    ok(f"Creation dossier arrivee (id={form_id})")
else:
    fail("Creation dossier arrivee", f"status={r.status_code} {r.text[:200]}")
    sys.exit(1)

# Lecture
r = s.get(f"{BASE}/api/forms/{form_id}")
if r.status_code == 200:
    status = r.json()["summary"]["status"]
    ok(f"Lecture dossier (status={status})")
else:
    fail("Lecture dossier", str(r.status_code))

# Mise a jour
payload["meta"]["id"] = form_id
payload["validation"] = {"rgpdAccepted": True}
r = api("put", f"/api/forms/{form_id}", json=payload)
if r.status_code == 200:
    ok("Mise a jour dossier (RGPD accepte)")
else:
    fail("Mise a jour dossier", f"{r.status_code} {r.text[:200]}")

# Generer lien de signature attribution
r = api("post", f"/api/forms/{form_id}/signature-link", json={"validityDays": 3})
if r.status_code == 201:
    link_data = r.json()["link"]
    token_url = link_data.get("url", "")
    sig_token = token_url.rstrip("/").split("/")[-1]
    ok(f"Creation lien signature (status={link_data['status']})")
else:
    fail("Creation lien signature", f"{r.status_code} {r.text[:200]}")
    sig_token = None

# Signer via lien public (client sans session)
if sig_token:
    pub = requests.Session()
    r = pub.get(f"{BASE}/api/signature/{sig_token}")
    if r.status_code == 200:
        ok("GET lien signature public -> donnees recues")
    else:
        fail("GET lien signature public", str(r.status_code))

    sig_data = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    r = pub.post(
        f"{BASE}/api/signature/{sig_token}/submit",
        json={"signatureDataUrl": sig_data, "rgpdAccepted": True},
        headers={"Content-Type": "application/json"}
    )
    if r.status_code == 200 and r.json().get("success"):
        new_status = r.json()["summary"]["status"]
        ok(f"Signature publique OK (status={new_status})")
    else:
        fail("Signature publique", f"{r.status_code} {r.text[:200]}")

# Statut post-signature
r = s.get(f"{BASE}/api/forms/{form_id}")
if r.status_code == 200:
    status = r.json()["summary"]["status"]
    if status in ("active", "partial_assignment"):
        ok(f"Statut post-signature correct ({status})")
    else:
        fail("Statut post-signature inattendu", status)

# Tenter reutilisation lien signe
if sig_token:
    pub2 = requests.Session()
    r = pub2.post(
        f"{BASE}/api/signature/{sig_token}/submit",
        json={"signatureDataUrl": sig_data, "rgpdAccepted": True},
        headers={"Content-Type": "application/json"}
    )
    if r.status_code == 410:
        ok("Reutilisation lien signature -> 410 used (correct)")
    else:
        fail("Reutilisation lien", f"{r.status_code} {r.text[:100]}")

# ----------------------------------------------------------
section("2. Restitution - cycle complet avec signature distance")
# ----------------------------------------------------------

restitution_payload = {
    "returnedAt": "2026-04-21T10:00:00Z",
    "reason": "depart",
    "notes": "RAS, tout rendu.",
    "items": {}
}
r = api("patch", f"/api/forms/{form_id}/restitution", json=restitution_payload)
if r.status_code == 200:
    ok("PATCH restitution (save)")
else:
    fail("PATCH restitution", f"{r.status_code} {r.text[:200]}")

# Creer lien signature restitution
r = api("post", f"/api/forms/{form_id}/restitution-signature-link", json={"validityDays": 3})
if r.status_code == 201:
    rest_link = r.json()["link"]
    rest_token_url = rest_link.get("url", "")
    rest_token = rest_token_url.rstrip("/").split("/")[-1]
    ok(f"Creation lien signature restitution (status={rest_link['status']})")
else:
    fail("Creation lien restitution", f"{r.status_code} {r.text[:200]}")
    rest_token = None

# Signer restitution via lien public
if rest_token:
    pub3 = requests.Session()
    r = pub3.get(f"{BASE}/api/restitution-signature/{rest_token}")
    if r.status_code == 200:
        ok("GET lien restitution public -> donnees recues")
    else:
        fail("GET lien restitution public", str(r.status_code))

    r = pub3.post(
        f"{BASE}/api/restitution-signature/{rest_token}/submit",
        json={
            "signatureDataUrl": sig_data,
            "signataireDecision": "confirmed"
        },
        headers={"Content-Type": "application/json"}
    )
    if r.status_code == 200 and r.json().get("success"):
        final_status = r.json()["summary"]["status"]
        ok(f"Signature restitution publique OK (status={final_status})")
    else:
        fail("Signature restitution publique", f"{r.status_code} {r.text[:200]}")

# Reutilisation lien restitution -> 410
if rest_token:
    pub4 = requests.Session()
    r = pub4.post(
        f"{BASE}/api/restitution-signature/{rest_token}/submit",
        json={"signatureDataUrl": sig_data, "signataireDecision": "confirmed"},
        headers={"Content-Type": "application/json"}
    )
    if r.status_code == 410:
        ok("Reutilisation lien restitution -> 410 used (correct)")
    else:
        fail("Reutilisation lien restitution", f"{r.status_code}")

# Nouveau lien pour signer avec reserve
r = api("post", f"/api/forms/{form_id}/restitution-signature-link", json={"validityDays": 1})
if r.status_code == 400 and r.json().get("error") == "already_signed":
    ok("Nouveau lien post-signature -> already_signed (correct)")
elif r.status_code == 201:
    token_reserve = r.json()["link"]["url"].rstrip("/").split("/")[-1]
    pub5 = requests.Session()
    r2 = pub5.post(
        f"{BASE}/api/restitution-signature/{token_reserve}/submit",
        json={
            "signatureDataUrl": sig_data,
            "signataireDecision": "with_reservation",
            "signataireComment": "Clavier manquant"
        },
        headers={"Content-Type": "application/json"}
    )
    if r2.status_code == 200:
        ok("Signature restitution avec reserve OK")
    else:
        fail("Signature avec reserve", f"{r2.status_code} {r2.text[:100]}")

# ----------------------------------------------------------
section("3. Dossier SORTIE - restitution directe sans lien")
# ----------------------------------------------------------

payload2 = {
    "meta": {"dossierType": "sortie"},
    "beneficiaire": {"nom": "Martin", "prenom": "Paul", "service": "RH"},
    "workflow": {"status": "draft"}
}
r = api("post", "/api/forms", json=payload2)
if r.status_code == 201:
    form2_id = r.json()["summary"]["id"]
    ok(f"Creation dossier sortie (id={form2_id})")
else:
    fail("Creation dossier sortie", f"{r.status_code} {r.text[:200]}")
    form2_id = None

if form2_id:
    r = api("patch", f"/api/forms/{form2_id}/restitution", json={
        "returnedAt": "2026-04-21T09:00:00Z",
        "reason": "retraite",
        "notes": "",
        "items": {}
    })
    if r.status_code == 200:
        ok("Restitution directe (sans lien) OK")
    else:
        fail("Restitution directe", f"{r.status_code} {r.text[:100]}")

# ----------------------------------------------------------
section("4. Dossier CHANGEMENT DE SERVICE")
# ----------------------------------------------------------

payload3 = {
    "meta": {"dossierType": "changement_service"},
    "beneficiaire": {"nom": "Bernard", "prenom": "Sophie", "service": "Finance"},
    "dossier": {"serviceDestination": "Direction Generale"},
    "workflow": {"status": "draft"}
}
r = api("post", "/api/forms", json=payload3)
if r.status_code == 201:
    form3_id = r.json()["summary"]["id"]
    ok(f"Creation dossier changement service (id={form3_id})")
else:
    fail("Creation dossier changement service", f"{r.status_code} {r.text[:200]}")
    form3_id = None

# ----------------------------------------------------------
section("5. Dossier MISE A JOUR")
# ----------------------------------------------------------

payload4 = {
    "meta": {"dossierType": "mise_a_jour"},
    "beneficiaire": {"nom": "Petit", "prenom": "Luc", "service": "Batiment"},
    "workflow": {"status": "draft"}
}
r = api("post", "/api/forms", json=payload4)
if r.status_code == 201:
    form4_id = r.json()["summary"]["id"]
    ok(f"Creation dossier mise a jour (id={form4_id})")
else:
    fail("Creation dossier mise a jour", f"{r.status_code}")
    form4_id = None

# ----------------------------------------------------------
section("6. Exports")
# ----------------------------------------------------------

r = s.get(f"{BASE}/api/forms/export")
if r.status_code == 200 and b"Workbook" in r.content:
    ok(f"Export Excel sans filtre ({len(r.content)} bytes)")
else:
    fail("Export Excel sans filtre", f"status={r.status_code}")

r = s.get(f"{BASE}/api/forms/export?status=draft")
if r.status_code == 200:
    in_xls = b"Bernard" in r.content or b"Petit" in r.content
    ok(f"Export Excel status=draft (dossiers draft presents: {in_xls})")
else:
    fail("Export Excel status=draft", str(r.status_code))

r = s.get(f"{BASE}/api/forms/export?service=DSI")
if r.status_code == 200 and b"Durand" in r.content:
    ok("Export Excel service=DSI (Durand present)")
else:
    fail("Export Excel service=DSI", f"Durand={'oui' if r.status_code == 200 and b'Durand' in r.content else 'non'}")

r = s.get(f"{BASE}/api/forms/export?date_from=2026-04-01&date_to=2026-04-30")
if r.status_code == 200:
    ok("Export Excel filtre date_from + date_to")
else:
    fail("Export Excel filtre date", str(r.status_code))

# PDF attribution
r = s.get(f"{BASE}/api/forms/{form_id}/pdf")
if r.status_code == 200 and r.content[:5] == b"%PDF-":
    ok(f"Export PDF attribution ({len(r.content)} bytes)")
else:
    fail("Export PDF attribution", f"status={r.status_code}")

# PDF restitution
r = s.get(f"{BASE}/api/forms/{form_id}/restitution-pdf")
if r.status_code == 200 and r.content[:5] == b"%PDF-":
    ok(f"Export PDF restitution ({len(r.content)} bytes)")
else:
    fail("Export PDF restitution", f"status={r.status_code} {r.text[:100]}")

# ----------------------------------------------------------
section("7. Operations admin")
# ----------------------------------------------------------

r = s.get(f"{BASE}/api/admin/logs")
if r.status_code == 200 and isinstance(r.json(), list):
    ok(f"Logs admin ({len(r.json())} entrees)")
else:
    fail("Logs admin", str(r.status_code))

r = s.get(f"{BASE}/api/admin/unc-stats")
if r.status_code == 200:
    ok(f"UNC stats (agents={r.json().get('agents', '?')})")
else:
    fail("UNC stats", str(r.status_code))

r = s.get(f"{BASE}/api/forms")
if r.status_code == 200:
    ok("Dashboard liste OK")
else:
    fail("Dashboard liste", str(r.status_code))

# Suppression -> corbeille -> restauration
if form3_id:
    r_del = api("delete", f"/api/forms/{form3_id}")
    if r_del.status_code == 200:
        ok("Suppression dossier -> corbeille")
        # Récupérer l'id de la corbeille (différent du form_id)
        r_trash = s.get(f"{BASE}/api/admin/trash")
        trash_id = None
        if r_trash.status_code == 200:
            entry = next((t for t in r_trash.json() if t.get("item_key") == form3_id), None)
            trash_id = entry["id"] if entry else None
        if trash_id:
            r_restore = api("post", f"/api/admin/trash/{trash_id}/restore")
            if r_restore.status_code == 200:
                ok("Restauration depuis corbeille")
            else:
                fail("Restauration", f"{r_restore.status_code} {r_restore.text[:100]}")
        else:
            fail("Restauration", "trash_id introuvable dans la corbeille")
    else:
        fail("Suppression", f"{r_del.status_code} {r_del.text[:100]}")

# ----------------------------------------------------------
section("8. Cas limites et erreurs")
# ----------------------------------------------------------

# Reopen dossier signe
r = api("post", f"/api/forms/{form_id}/reopen")
if r.status_code in (200, 403, 400):
    ok(f"Reopen dossier signe -> {r.status_code} ({r.json().get('error', 'ok')})")
else:
    fail("Reopen", f"{r.status_code} {r.text[:100]}")

# Formulaire inexistant
r = s.get(f"{BASE}/api/forms/inexistant-999")
if r.status_code == 404:
    ok("GET dossier inexistant -> 404")
else:
    fail("GET dossier inexistant", str(r.status_code))

# Lien signature inexistant
anon = requests.Session()
r = anon.get(f"{BASE}/api/signature/token-invalide-xyz")
if r.status_code == 404:
    ok("GET lien signature invalide -> 404")
else:
    fail("GET lien signature invalide", str(r.status_code))

# Sans auth
anon2 = requests.Session()
r = anon2.get(f"{BASE}/api/forms")
if r.status_code == 401:
    ok("Sans auth -> 401")
else:
    fail("Sans auth", str(r.status_code))

# Conflict-check beneficiary_types
r = s.get(f"{BASE}/api/admin/settings/conflict-check?beneficiary_types=agent:Agent,elu:Elu")
if r.status_code == 200:
    ok(f"Conflict-check types (hasConflicts={r.json().get('hasConflicts')})")
else:
    fail("Conflict-check types", str(r.status_code))

# CSV template
r = s.get(f"{BASE}/api/admin/services/csv-template")
if r.status_code == 200 and b"label" in r.content:
    ok("CSV template services OK")
else:
    fail("CSV template services", str(r.status_code))

# ----------------------------------------------------------
print(f"\n{'='*60}")
print(f"  RESULTAT : {PASS_COUNT} OK  |  {FAIL_COUNT} KO")
print(f"{'='*60}\n")
if FAIL_COUNT > 0:
    sys.exit(1)
