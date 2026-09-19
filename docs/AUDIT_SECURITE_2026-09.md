# Audit cybersécurité — 19 septembre 2026

Périmètre : backend Flask (141 endpoints), mécanismes globaux (`app.py`, `auth.py`, `config.py`), uploads, signatures publiques, sauvegardes, module Parc (étapes 1 à 5). Audit **partiel** : voir « Non couvert ».

## Verdict

Aucune faille **critique** trouvée. 1 faille majeure (contournement de la limitation de connexion) et 7 points moyens ou mineurs corrigés ; 3 points acceptés ou à surveiller.

## Corrigé

| # | Gravité | Constat | Correctif |
|---|---|---|---|
| C1 | Moyen | `brand_logo_url` non validée : le serveur télécharge cette URL (`urlopen`, accepte `file://`, `ftp://`…). Réservé aux admins. | Seuls `http(s)://` acceptés (`save_app_settings`). |
| C2 | Moyen | Aucun `MAX_CONTENT_LENGTH` : upload géant lu sans plafond. | Plafond 100 Mo (`APP_MAX_UPLOAD_MB`). |
| C3 | **Majeur** | La limite de tentatives de connexion et les `@rate_limit` utilisaient le **premier `X-Forwarded-For`**, fourni par le client : contournement trivial en changeant l'en-tête à chaque essai, même derrière nginx. | Clé = `request.remote_addr` (`get_rate_limit_key`, corrigée par ProxyFix). L'IP déclarée reste utilisée pour les journaux seulement. |
| C4 | Moyen | `ProxyFix(x_for=1)` figé : si l'app est joignable sans proxy, IP falsifiable. | Confiance **automatique** (`backend/proxy.py`) : `X-Forwarded-*` n'est lu que si l'appelant direct est loopback/privé (reverse proxy local ou LAN) ; un accès direct depuis une IP publique l'ignore. Aucun réglage requis. Surcharge rare : `APP_TRUSTED_PROXIES=0` (jamais) ou `N` (forcer, ex. load balancer cloud à IP publique). |
| C5 | Mineur | `update_user(**fields)` insère les noms de colonnes dans le SQL (non exploitable aujourd'hui, fragile). | Liste blanche `UPDATABLE_USER_COLUMNS`. |
| C6 | Moyen | XSS stocké potentiel : `executive-dashboard.js` (nom, prénom, service, statut) et `app.js` (titre de dossier, libellé et clé des items de retrait) interpolés sans échappement. La CSP (`script-src` sans inline) limitait l'impact. | `escapeHtml` appliqué. |
| C7 | Moyen | Les exports (Excel, UNC, PDF par lots) ne sont pas masqués : un groupe à portée `masked` avec `forms.export` contournait le masquage RGPD. Configurable par l'admin (groupes par défaut tous en `full`). | Export refusé (403) si portée `masked` (`can_export_unmasked`). |
| C9 | Moyen | **Compteurs de limitation en mémoire, par processus** : avec `gunicorn -w 4`, 10 essais de connexion devenaient 40, et tout repartait à zéro au redémarrage. | Compteur **partagé** entre processus et persistant (`backend/rate_store.py`, table `rate_limit_hits` de `users.db`, verrou d'écriture atomique) ; repli en mémoire si la base est indisponible. Test multi-processus : 4 processus × 5 essais = 10 passages exactement. |
| C10 | Moyen | XSS stocké potentiel dans le rendu des retraits (`app.js`) : « Observations » et clé d'item insérées sans échappement dans des attributs. | `escapeHtml` appliqué. |
| C8 | Mineur : vulnérabilité connue PYSEC-2026-1845 (dépendance de test). | Passé en `9.0.3`. |

Tests : `tests/test_security_hardening.py` (9 tests). Suite complète : 202 passés.

## Accepté / à surveiller

| # | Gravité | Constat | Décision |
|---|---|---|---|
| A3 | Mineur | CSP `img-src https:` et `style-src 'unsafe-inline'`. | Conservé : l'aperçu du logo en Admin > Personnalisation charge l'URL distante saisie par l'admin. L'exploiter suppose déjà une XSS. Piste : passer l'aperçu par `/api/settings/logo`. |
| A4 | — | *(traité : voir C9)* | Compteurs désormais partagés entre processus. |
| A5 | Mineur | Ligne cliquable de `executive-dashboard.js` : `onclick=` inline bloqué par la CSP. | **Corrigé** : délégation d’événements (clic et clavier). |

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

- Relecture **outillée** des gabarits HTML : toutes les interpolations de données saisies dans `app.js`, `storage.js`, `admin.js`, `restitution.js`, `logs.js`, `parc*.js`, `dashboard-*.js`, `admin-backup*.js`, `admin-db.js` ont été passées en revue (20 fonctions de rendu) ; les cas trouvés sont corrigés (C6, C10). Un nouveau gabarit reste à relire à chaque ajout.
- Recherche globale : s'appuie sur `/api/forms`, déjà masqué pour les groupes à portée `masked`. Journaux : réservés au droit `users.manage`, aucun mot de passe enregistré.
- Vérification en conditions réelles du déploiement (proxy, HTTPS, permissions de `.app_secret_key` et `users.db`).
