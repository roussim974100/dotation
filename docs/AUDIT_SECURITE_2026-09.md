# Audit cybersécurité — 19 septembre 2026

Périmètre : backend Flask (141 endpoints), mécanismes globaux (`app.py`, `auth.py`, `config.py`), uploads, signatures publiques, sauvegardes, module Parc (étapes 1 à 5). Audit **partiel** : voir « Non couvert ».

## Verdict

Aucune faille **critique** trouvée. 2 points moyens corrigés dans ce commit, 3 points à traiter, le reste est conforme.

## Corrigé dans ce commit

| # | Gravité | Constat | Correctif |
|---|---|---|---|
| C1 | Moyen | `brand_logo_url` non validée : le serveur télécharge cette URL (`models/settings.py`, `urlopen`) qui accepte `file://`, `ftp://`… (lecture locale / SSRF, réservé aux admins `users.manage`). | Seuls `http://` et `https://` acceptés, sinon vidée (`save_app_settings`). Tests : `tests/test_security_hardening.py`. |
| C2 | Moyen | Aucun `MAX_CONTENT_LENGTH` : un upload géant (CSV, logo, restauration) était lu sans plafond, risque de saturation mémoire. | Plafond 100 Mo, réglable par `APP_MAX_UPLOAD_MB`. |

## À traiter

| # | Gravité | Constat | Recommandation |
|---|---|---|---|
| A1 | Moyen | Limitation des tentatives de connexion **en mémoire, par processus** (`auth.py`) et clé = IP. `ProxyFix(x_for=1)` fait confiance à `X-Forwarded-For` : si l'app est joignable sans reverse proxy, l'IP est falsifiable (contournement + fausses IP dans les logs). Avec plusieurs workers gunicorn, le compteur est multiplié. | Ne publier que derrière le reverse proxy (bind `127.0.0.1`), ou rendre `x_for` configurable (`0` par défaut hors proxy). Option : stocker les tentatives en base. |
| A2 | Mineur | `update_user(**fields)` construit `SET {cols}` à partir des clés reçues. Aujourd'hui les 2 appelants n'envoient que des clés fixes (`account_rules.build_self_update`, `admin.update_admin_user`), donc pas exploitable, mais fragile si un futur appelant passe des clés venant de la requête. | Liste blanche de colonnes dans `update_user`. |
| A3 | Mineur | CSP : `img-src` autorise `https:` (exfiltration par image possible en cas d'XSS) et `style-src 'unsafe-inline'`. `script-src` est bien strict (pas d'inline). | Restreindre `img-src` à `'self' data:` si le logo distant n'est plus nécessaire côté navigateur (il est servi par le backend). |

## Conforme

- **Mots de passe** : bcrypt. **Session** : cookie `HttpOnly`, `SameSite=Lax`, `Secure` automatique.
- **CSRF** : jeton `X-CSRF-Token` comparé en temps constant sur toute mutation `/api/` authentifiée ; exemptions limitées aux endpoints de signature publics et `/api/auth/`.
- **Signatures publiques** : jeton `token_urlsafe(32)` (256 bits), expiration 72 h recalculée à la lecture.
- **Injection** : requêtes paramétrées ; les seuls SQL dynamiques (`database.py`, `units_extra.py`) n'utilisent que des constantes du code. Aucun `subprocess`, `eval`, `exec`, `pickle`.
- **Uploads** : logo = extension `.png` + signature magique + 2 Mo ; sauvegardes lues par nom de membre (pas d'`extractall`, donc pas de zip-slip).
- **Contrôle d'accès** : sur 141 endpoints, seuls 6 sont sans garde (statiques et paramètres publics attendus). Parc : écriture = `parc.manage`, lecture = `login_required` + droits dossiers. Routes `debug` = `admin_required`.
- **En-têtes** : HSTS, `nosniff`, `X-Frame-Options`, CSP.
- **Secret** : `APP_SECRET_KEY` ou fichier généré (`secrets.token_hex(32)`).
- **XSS frontend** : `parc.js` échappe toutes les données (`parcEsc`).

## Non couvert (prochain audit)

- Échappement dans les autres fichiers à `innerHTML` (`app.js` 34, `storage.js` 23, `admin.js` 11, `global-search.js` 8…).
- Dépendances (`pip-audit` sur `requirements.txt`).
- Filtrage par `data_scope` endpoint par endpoint et contenu des logs (données personnelles).
- Vérification en conditions réelles du déploiement (proxy, HTTPS, permissions des fichiers `.app_secret_key` et `users.db`).
