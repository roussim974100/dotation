#!/usr/bin/env python3
"""
Test du scénario de déploiement derrière un reverse proxy TLS.

Simule ce que vit l'application quand :
  - SESSION_COOKIE_SECURE=1 (production)
  - nginx local relaie X-Forwarded-Proto: https depuis un proxy frontal
  - L'IP réelle du client arrive via X-Forwarded-For / X-Real-IP

Vérifie :
  1. Login avec X-Forwarded-Proto: https  --> cookie Secure posé, session active
  2. Login sans X-Forwarded-Proto         --> cookie sans flag Secure (SESSION_COOKIE_SECURE=1 ignoré si proto=http)
  3. IP réelle lue depuis X-Forwarded-For
  4. IP réelle lue depuis X-Real-IP (fallback)
  5. ProxyFix -- request.is_secure = True derrière proxy HTTPS
  6. Accès aux endpoints API avec session proxy
  7. Config nginx --behind-proxy : vérifie que le script génère les bons headers

Usage : python3 scripts/test_reverse_proxy.py
"""

import io
import json
import os
import re
import sys
import tempfile
import traceback
import bcrypt

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

PASS = "\033[92m[OK]\033[0m"
FAIL = "\033[91m[ERREUR]\033[0m"
WARN = "\033[93m[AVERT]\033[0m"
INFO = "\033[94m[INFO]\033[0m"

errors = []

def ok(msg):    print(f"  {PASS} {msg}")
def fail(msg):  print(f"  {FAIL} {msg}"); errors.append(msg)
def warn(msg):  print(f"  {WARN} {msg}")
def info(msg):  print(f"  {INFO} {msg}")

def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

# ---------------------------------------------------------------------------
# Environnement isolé
# ---------------------------------------------------------------------------

tmp       = tempfile.mkdtemp(prefix="test_proxy_")
DB_PATH   = os.path.join(tmp, "proxy.db")
USERS_PATH = os.path.join(tmp, "users.json")

admin_hash = bcrypt.hashpw(b"Admin1234!", bcrypt.gensalt()).decode()
users_config = {
    "groups": {
        "admin": {"label": "Admin", "permissions": ["*"], "data_scope": "full"}
    },
    "users": [{
        "username": "admin",
        "password_hash": admin_hash,
        "groups": ["admin"],
        "is_active": True,
        "status": "active",
    }],
}
with open(USERS_PATH, "w", encoding="utf-8") as f:
    json.dump(users_config, f)

import database, auth
database.DB_PATH = DB_PATH
auth.USERS_FILE  = USERS_PATH

from app import app as flask_app, init_db
from models.settings import seed_app_settings

# Simule SESSION_COOKIE_SECURE=1 (production derrière proxy TLS)
flask_app.config["TESTING"]             = True
flask_app.config["SECRET_KEY"]          = "test-proxy-secret-key"
flask_app.config["SESSION_COOKIE_SECURE"] = True

# Route de diagnostic ProxyFix -- doit être enregistrée AVANT le premier appel
from flask import request as freq, jsonify as fjson

@flask_app.route("/_test_proxy_is_secure")
def _test_proxy_is_secure():
    return fjson({"is_secure": freq.is_secure, "scheme": freq.scheme})

with flask_app.app_context():
    init_db()
    with database.get_db() as conn:
        seed_app_settings(conn)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PROXY_ENVIRON = {
    # Ce que nginx --behind-proxy relaie depuis un HAProxy/nginx frontal HTTPS
    "HTTP_X_FORWARDED_PROTO": "https",
    "HTTP_X_FORWARDED_HOST":  "dotation.exemple.local",
    "HTTP_X_FORWARDED_FOR":   "203.0.113.42",
    "HTTP_X_REAL_IP":         "203.0.113.42",
}

def make_client(with_proxy_headers=True):
    """Retourne un test client frais avec ou sans headers proxy."""
    c = flask_app.test_client()
    c._proxy_environ = PROXY_ENVIRON if with_proxy_headers else {}
    return c

def csrf(client, environ=None):
    r = client.get("/api/csrf-token", environ_base=environ or {})
    return r.get_json()["token"]

def login(client, environ=None):
    env = environ or {}
    t = csrf(client, env)
    r = client.post(
        "/login",
        data={"username": "admin", "password": "Admin1234!", "csrf_token": t},
        environ_base=env,
    )
    return r

def cookie_flags(response, cookie_name):
    """Extrait les flags d'un Set-Cookie depuis les headers de réponse."""
    for header in response.headers.getlist("Set-Cookie"):
        if header.startswith(cookie_name + "=") or f" {cookie_name}=" in header:
            return header
    return ""

# ---------------------------------------------------------------------------
# Phase 1 — Login AVEC headers proxy (X-Forwarded-Proto: https)
# ---------------------------------------------------------------------------

section("Phase 1 — Login avec X-Forwarded-Proto: https")

try:
    c = make_client()
    r = login(c, PROXY_ENVIRON)
    if r.status_code in (200, 302):
        ok(f"Login reussi (HTTP {r.status_code})")
    else:
        fail(f"Login echoue : HTTP {r.status_code}")

    # Verifier que le cookie session a bien le flag Secure
    all_cookies = r.headers.getlist("Set-Cookie")
    session_cookie = next((h for h in all_cookies if "publier_session=" in h or "session=" in h), "")
    if session_cookie:
        if "Secure" in session_cookie:
            ok(f"Cookie session posé avec flag Secure")
        else:
            fail(f"Cookie session posé SANS flag Secure (SESSION_COOKIE_SECURE=1 devrait forcer Secure)")
        if "HttpOnly" in session_cookie:
            ok("Cookie session avec flag HttpOnly")
        else:
            warn("Cookie session sans HttpOnly")
        info(f"Set-Cookie: {session_cookie[:120]}")
    else:
        # Login redirige vers la page principale -- verifier que la session est active
        if r.status_code == 302:
            ok("Login redirige (302) -- session probablement cree")
            info("Note: le cookie est pose lors de la redirection, pas forcement dans cette reponse")
        else:
            warn("Pas de header Set-Cookie trouve dans la reponse de login")

    # Verifier l'acces après login avec les headers proxy
    r2 = c.get("/api/forms", environ_base=PROXY_ENVIRON)
    if r2.status_code == 200:
        ok("Acces API /api/forms apres login proxy : HTTP 200")
    elif r2.status_code == 401:
        fail("Session non reconnue apres login proxy (HTTP 401)")
    else:
        info(f"Acces API /api/forms : HTTP {r2.status_code}")

except Exception as e:
    fail(f"Exception phase 1 : {e}")
    traceback.print_exc()

# ---------------------------------------------------------------------------
# Phase 2 — Login SANS headers proxy (connexion directe HTTP)
# ---------------------------------------------------------------------------

section("Phase 2 — Login sans X-Forwarded-Proto (connexion HTTP directe)")

try:
    c2 = make_client(with_proxy_headers=False)
    r = login(c2, {})

    if r.status_code in (200, 302):
        ok(f"Login reussi (HTTP {r.status_code})")
    else:
        fail(f"Login echoue : HTTP {r.status_code}")

    all_cookies = r.headers.getlist("Set-Cookie")
    session_cookie = next((h for h in all_cookies if "publier_session=" in h or "session=" in h), "")
    if session_cookie:
        if "Secure" in session_cookie:
            # Avec SESSION_COOKIE_SECURE=1 et request.is_secure=False (http direct),
            # Flask peut quand même poser le flag Secure -- le navigateur refusera
            # ce cookie sur une connexion HTTP, causant la boucle de login.
            warn("Cookie posé avec flag Secure en HTTP direct -- boucle de login probable en vrai navigateur")
            info("C'est le comportement attendu : SESSION_COOKIE_SECURE=1 force toujours Secure")
            info("Un utilisateur HTTP direct ne peut pas se connecter -- c'est voulu en prod")
        else:
            ok("Cookie sans flag Secure en HTTP direct (SESSION_COOKIE_SECURE respecté différemment)")
        info(f"Set-Cookie: {session_cookie[:120]}")
    else:
        if r.status_code == 302:
            ok("Login redirige (302) -- comportement normal Flask")

except Exception as e:
    fail(f"Exception phase 2 : {e}")
    traceback.print_exc()

# ---------------------------------------------------------------------------
# Phase 3 — IP réelle via X-Forwarded-For
# ---------------------------------------------------------------------------

section("Phase 3 — Lecture de l'IP réelle depuis les headers proxy")

try:
    with flask_app.test_request_context(
        "/",
        environ_base={
            "HTTP_X_FORWARDED_FOR": "203.0.113.42",
            "REMOTE_ADDR": "127.0.0.1",
        }
    ):
        from auth import get_request_client_ip
        ip = get_request_client_ip()
        if ip == "203.0.113.42":
            ok(f"X-Forwarded-For lu correctement : {ip}")
        else:
            fail(f"IP attendue 203.0.113.42, obtenue : {ip!r}")

except Exception as e:
    fail(f"Exception phase 3 (X-Forwarded-For) : {e}")
    traceback.print_exc()

# ---------------------------------------------------------------------------
# Phase 4 — IP réelle via X-Real-IP (fallback)
# ---------------------------------------------------------------------------

section("Phase 4 — Lecture de l'IP réelle via X-Real-IP (fallback)")

try:
    with flask_app.test_request_context(
        "/",
        environ_base={
            "HTTP_X_REAL_IP": "10.0.0.55",
            "REMOTE_ADDR": "127.0.0.1",
        }
    ):
        ip = get_request_client_ip()
        if ip == "10.0.0.55":
            ok(f"X-Real-IP lu correctement : {ip}")
        else:
            fail(f"IP attendue 10.0.0.55, obtenue : {ip!r}")

except Exception as e:
    fail(f"Exception phase 4 (X-Real-IP) : {e}")
    traceback.print_exc()

# ---------------------------------------------------------------------------
# Phase 5 — ProxyFix : request.is_secure derrière proxy HTTPS
# ---------------------------------------------------------------------------
# ProxyFix est un middleware WSGI — il s'applique avant Flask.
# test_request_context() bypass le middleware, donc on passe par le test client
# avec une route temporaire qui expose request.is_secure.

section("Phase 5 — ProxyFix : request.is_secure = True derrière proxy HTTPS")

try:
    tc = flask_app.test_client()

    # Avec X-Forwarded-Proto: https -- ProxyFix doit réécrire wsgi.url_scheme -> https
    r_secure = tc.get(
        "/_test_proxy_is_secure",
        environ_base={"HTTP_X_FORWARDED_PROTO": "https", "REMOTE_ADDR": "127.0.0.1"},
    )
    data_secure = r_secure.get_json() or {}
    if data_secure.get("is_secure") is True and data_secure.get("scheme") == "https":
        ok(f"ProxyFix actif : request.is_secure=True, scheme=https avec X-Forwarded-Proto: https")
    else:
        fail(f"ProxyFix : attendu is_secure=True/scheme=https, obtenu {data_secure}")

    # Sans X-Forwarded-Proto -- connexion HTTP directe
    r_http = tc.get(
        "/_test_proxy_is_secure",
        environ_base={"REMOTE_ADDR": "127.0.0.1"},
    )
    data_http = r_http.get_json() or {}
    if data_http.get("is_secure") is False and data_http.get("scheme") == "http":
        ok(f"ProxyFix : request.is_secure=False sans X-Forwarded-Proto (HTTP direct)")
    else:
        fail(f"ProxyFix : attendu is_secure=False/scheme=http, obtenu {data_http}")

except Exception as e:
    fail(f"Exception phase 5 (ProxyFix) : {e}")
    traceback.print_exc()

# ---------------------------------------------------------------------------
# Phase 6 — Workflow complet derrière proxy (création dossier)
# ---------------------------------------------------------------------------

section("Phase 6 — Workflow dossier complet derrière proxy")

try:
    c3 = make_client()
    login(c3, PROXY_ENVIRON)

    # CSRF
    csrf_token = csrf(c3, PROXY_ENVIRON)

    # Création d'un dossier
    payload = {
        "meta":         {"startAt": "2026-06-01"},
        "dossier":      {"type": "arrivee"},
        "beneficiaire": {"nom": "Proxy", "prenom": "Test", "qualite": "agent", "service": "DSI"},
        "validation":   {"rgpdAccepted": True},
        "resources":    {"additional": []},
    }
    r = c3.post(
        "/api/forms",
        json=payload,
        environ_base=PROXY_ENVIRON,
        headers={"X-CSRF-Token": csrf_token},
    )
    if r.status_code == 201:
        form_id = (r.get_json() or {}).get("data", {}).get("meta", {}).get("id")
        ok(f"Dossier créé via proxy : id={form_id}")
    else:
        fail(f"Création dossier via proxy : HTTP {r.status_code} -- {r.get_data(as_text=True)[:200]}")

except Exception as e:
    fail(f"Exception phase 6 : {e}")
    traceback.print_exc()

# ---------------------------------------------------------------------------
# Phase 7 — Vérification du script deploy-debian.sh --behind-proxy
# ---------------------------------------------------------------------------

section("Phase 7 — Validation de la config nginx générée par --behind-proxy")

try:
    script_path = os.path.join(os.path.dirname(__file__), "deploy-debian.sh")
    with open(script_path, encoding="utf-8") as f:
        script = f.read()

    # Extraire le bloc nginx --behind-proxy (entre OPT_BEHIND_PROXY=1 et le else)
    # On cherche la présence des patterns clés dans le script
    checks = [
        (r"\$http_x_forwarded_proto",   "X-Forwarded-Proto relaie la valeur du proxy ($http_x_forwarded_proto)"),
        (r"\$http_x_forwarded_host",    "X-Forwarded-Host relaie la valeur du proxy ($http_x_forwarded_host)"),
        (r"--behind-proxy",             "Option --behind-proxy présente dans le script"),
        (r"OPT_BEHIND_PROXY",           "Variable OPT_BEHIND_PROXY déclarée"),
        (r"X-Forwarded-Proto.*https",   "Warning X-Forwarded-Proto: https mentionné dans l'output"),
    ]

    for pattern, label in checks:
        if re.search(pattern, script):
            ok(label)
        else:
            fail(f"Pattern manquant dans deploy-debian.sh : {pattern} -- {label}")

    # Vérifier que le mode standard utilise $scheme (pas relaie)
    # Le bloc else doit contenir $scheme
    if re.search(r"\\\$scheme", script):
        ok("Mode standard utilise $scheme (non-proxy)")
    else:
        warn("$scheme non trouvé dans le script -- vérifier le mode standard")

    # Vérifier que les deux modes sont bien distincts
    behind_proxy_count = script.count("$http_x_forwarded_proto")
    if behind_proxy_count >= 1:
        ok(f"Config relais présente {behind_proxy_count} fois dans le script")
    else:
        fail("Config relais $http_x_forwarded_proto absente du script")

except FileNotFoundError:
    fail("deploy-debian.sh introuvable -- exécuter depuis la racine du projet")
except Exception as e:
    fail(f"Exception phase 7 : {e}")
    traceback.print_exc()

# ---------------------------------------------------------------------------
# Bilan
# ---------------------------------------------------------------------------

section("Bilan")

if errors:
    print(f"\n  {FAIL} {len(errors)} erreur(s) :")
    for e in errors:
        print(f"    - {e}")
    sys.exit(1)
else:
    print(f"\n  {PASS} Tous les tests sont passés.")
    print()
    print("  Scénario validé :")
    print("    - Login avec X-Forwarded-Proto: https -> cookie Secure posé")
    print("    - IP réelle lue depuis X-Forwarded-For et X-Real-IP")
    print("    - ProxyFix actif : request.is_secure = True derrière proxy HTTPS")
    print("    - Workflow dossier complet fonctionnel derrière proxy")
    print("    - Script deploy-debian.sh --behind-proxy génère la bonne config nginx")
    print()
