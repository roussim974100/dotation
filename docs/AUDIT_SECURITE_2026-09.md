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
| C4 | Moyen | `ProxyFix(x_for=1)` figé : si l'app est joignable sans proxy, IP falsifiable. | Nombre de proxys de confiance configurable : `APP_TRUSTED_PROXIES` (défaut 1, mettre 0 sans proxy). |
| C5 | Mineur | `update_user(**fields)` insère les noms de colonnes dans le SQL (non exploitable aujourd'hui, fragile). | Liste blanche `UPDATABLE_USER_COLUMNS`. |
| C6 | Moyen | XSS stocké potentiel : `executive-dashboard.js` (nom, prénom, service, statut) et `app.js` (titre de dossier, libellé et clé des items de retrait) interpolés sans échappement. La CSP (`script-src` sans inline) limitait l'impact. | `escapeHtml` appliqué. |
| C7 | Moyen | Les exports (Excel, UNC, PDF par lots) ne sont pas masqués : un groupe à portée `masked` avec `forms.export` contournait le masquage RGPD. Configurable par l'admin (groupes par défaut tous en `full`). | Export refusé (403) si portée `masked` (`can_export_unmasked`). |
| C8 | Mineur | `pytest 9.0.2` : vulnérabilité connue PYSEC-2026-1845 (dépendance de test). | Passé en `9.0.3`. |

Tests : `tests/test_security_hardening.py` (6 tests). Suite complète : 199 passés.

## Accepté / à surveiller

| # | Gravité | Constat | Décision |
|---|---|---|---|
| A3 | Mineur | CSP `img-src https:` et `style-src 'unsafe-inline'`. | Conservé : l'aperçu du logo en Admin > Personnalisation charge l'URL distante saisie par l'admin. L'exploiter suppose déjà une XSS. Piste : passer l'aperçu par `/api/settings/logo`. |
| A4 | Mineur | Compteurs de limitation **en mémoire, par processus** : multipliés par le nombre de workers gunicorn, remis à zéro au redémarrage. | À stocker en base si plusieurs workers. |
| A5 | Mineur | `executive-dashboard.js` ligne ~425 : `onclick=` inline sur les lignes de service. La CSP bloque les handlers inline, donc le clic sur une ligne est probablement sans effet (défaut fonctionnel, pas de faille). | À remplacer par une délégation d'événements. |

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

- Échappement : scan **heuristique** des interpolations d'objets ; les cas de gabarits construits autrement (concaténations, `insertAdjacentHTML`) n'ont pas été relus un par un.
- `data_scope` : vérifié sur formulaires, parc et exports ; pas sur `/api/admin/dashboard-stats` (protégé par `forms.view_all`, renvoie noms et prénoms des alertes) ni sur la recherche globale.
- Contenu des journaux (données personnelles) et rotation.
- Vérification en conditions réelles du déploiement (proxy, HTTPS, permissions de `.app_secret_key` et `users.db`).
