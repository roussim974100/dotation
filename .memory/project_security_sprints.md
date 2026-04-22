---
name: Sprints sécurité app.py
description: 6 sprints sécurité complétés et testés sur backend/app.py — état final
type: project
---

Tous les sprints sécurité sont terminés et testés avec curl sur localhost:5000.

**S1 — Headers sécurité** (app.py ~ligne 72)
Ajout de X-Content-Type-Options, X-Frame-Options, Referrer-Policy dans disable_frontend_cache().

**S2 — Rate limiting login** (app.py ~ligne 37 + route /login)
Implémentation maison (pas de lib externe) : 10 tentatives / 10 min par IP, thread-safe.
Fonctions : `_is_login_rate_limited()`, variables `_login_attempts`, `_LOGIN_MAX_ATTEMPTS=10`, `_LOGIN_WINDOW_SECONDS=600`.
Message frontend ajouté dans frontend/js/login.js : `rate_limited`.

**S3 — Upload logo sécurisé** (app.py route /api/admin/settings/logo-upload)
Validation magic bytes PNG (`\x89PNG\r\n\x1a\n`), limite 2 Mo avant écriture disque.
Idem pour téléchargement logo distant : `response.read(2 * 1024 * 1024)`.

**S4 — Open redirect + Content-Disposition**
- Open redirect : validation `re.match(r"^https?://", remote_url)` sur le logo URL.
- Content-Disposition : RFC 5987 avec `filename*=UTF-8''<encoded>` via `urllib.parse.quote`.
- Import ajouté : `import urllib.parse`.

**S5 — Whitelist tables SQL** (app.py fonctions table_columns/ensure_column)
Ajout de `_KNOWN_TABLES` set avec les 9 tables connues. ValueError si table inconnue.

**S6 — Protection CSRF** (login + signup)
- Backend : endpoint `GET /api/csrf-token` qui génère/retourne un token en session.
- Validation dans /login et /signup avec `secrets.compare_digest`.
- Frontend : champ hidden `csrf_token` dans login.html et signup.html.
- JS : `fetchCsrfToken()` dans login.js, `injectSignupCsrfToken()` dans signup.js, fetch avant soumission.

**Utilisateur de test créé** : `claude.test` / `ClaudeTest@2026!` (groupe admin) dans backend/users.json.

**Why:** Dette technique sécurité sur app.py monolithique de 5221 lignes.
**How to apply:** Ne pas refaire ces sprints. Reprendre à l'étape découpage de app.py.
