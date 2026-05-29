# Audit de reprise de maintenance — Projet « À Quai » (dotation)

**Date du rapport :** 2026-05-29
**Branche analysée :** `dev`
**Version courante :** `3.18.4-dev` (branding.js) / `3.18.3-prod` (README)
**Auditeur :** analyse statique du dépôt `c:\www\dotation`

---

## 1. Résumé du projet

### 1.1 Objectif métier

**« À Quai »** est une application web interne de gestion des **dotations matérielles et immatérielles** pour le cycle de vie professionnel (onboarding / offboarding). Elle est conçue pour être déployée par n'importe quelle organisation (collectivité, administration, entreprise, association) et couvre :

- création / suivi de dossiers d'attribution (4 types : arrivée, changement de service, mise à jour, sortie) ;
- catalogue paramétrable de ressources matérielles (ordinateur, téléphone, badge, véhicule…) et immatérielles (email, VPN, zone d'alarme, accès UNC) ;
- workflow signature électronique (sur place ou via lien à usage unique) avec opposabilité RGPD ;
- restitution en deux phases (Phase 1 = dates et motif RH ; Phase 2 = état matériel + signature) ;
- exports PDF (attribution, restitution, retraits) et Excel/CSV ;
- administration : utilisateurs, groupes/permissions, services, ressources, branding, journaux d'audit, corbeille.

### 1.2 Technologies utilisées

| Couche | Stack |
|---|---|
| Backend | **Flask 3.1.3** (Python 3.11+), **SQLite** (deux bases : `dotation.db` métier, `users.db` auth), **bcrypt 5.0**, **fpdf2 2.8** |
| Frontend | **Vanilla JS** (aucun bundler, aucun framework), **HTML5**, **CSS3**, **Bootstrap 5.3.2** chargé via CDN |
| Auth / sécurité | sessions cookie Flask signées, CSRF par token X-CSRF-Token, ProxyFix pour reverse-proxy, headers HSTS/CSP/Permissions-Policy |
| WSGI prod | Gunicorn (Linux) ou Waitress + IIS/ARR (Windows) |
| Tests | **pytest 9.0.2** (4 fichiers de tests) |
| Déploiement | scripts `setup/install-debian.sh` et `setup/install-windows.ps1`, service systemd, nginx |

### 1.3 Architecture générale

```
┌──────────────────────────────────────────────────────────────┐
│ Navigateur (Bootstrap + Vanilla JS)                          │
│   - HTML statiques servis par Flask                          │
│   - JS chargés sans bundler, branding.js partagé             │
└────────────────────┬─────────────────────────────────────────┘
                     │ HTTP/JSON + CSRF
┌────────────────────▼─────────────────────────────────────────┐
│ Flask app (backend/app.py)                                   │
│   - before_request : validation CSRF (POST/PUT/PATCH/DELETE) │
│   - after_request  : headers de sécurité + cache             │
│   - Blueprints autodécouverts (routes/ pkgutil.iter_modules) │
│       auth · pages · forms · signature · admin · debug       │
└────────────────────┬─────────────────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────────────────┐
│ Couche métier (backend/models)                               │
│   forms · workflow · dossier · catalog · signature · audit  │
│   · settings                                                 │
└────────────────────┬─────────────────────────────────────────┘
                     │ sqlite3 (WAL, FK ON)
┌────────────────────▼─────────────────────────────────────────┐
│ dotation.db (métier) · users.db (auth) — fichiers locaux    │
│   migrations idempotentes au démarrage (ensure_column +     │
│   migrate_*)                                                 │
└──────────────────────────────────────────────────────────────┘
```

Particularités architecturales :

- **Pas d'ORM** : tout est SQL brut paramétré (choix assumé par le mainteneur — voir `user_profile`).
- **Persistance hybride** : colonnes typées + colonne `payload_json` (tout le formulaire est stocké dénormalisé en JSON). Avantage : flexibilité catalogue dynamique. Inconvénient : requêtes complexes via `json_extract`.
- **Blueprints auto-découverts** : ajouter un fichier dans `backend/routes/` suffit pour exposer un nouveau blueprint si une variable `bp` y est définie.
- **Migrations en mémoire** : chaque démarrage ré-exécute `ensure_column` + plusieurs `migrate_*` (idempotents).

---

## 2. Structure du code

### 2.1 Vue d'ensemble (volumétrie)

| Zone | Fichiers | LOC totales |
|---|---|---|
| `backend/` (Python) | 22 fichiers `.py` | **~8 300** |
| `frontend/js/` | 25 fichiers `.js` | **~14 150** |
| `frontend/css/style.css` | 1 fichier | **4 513** |
| `frontend/*.html` | 25 pages | **~4 500** |
| `tests/` | 4 fichiers | quelques centaines |
| **Total code applicatif** | — | **~32 000 LOC** |

### 2.2 Dossiers et responsabilités

#### Backend (`backend/`)

| Dossier / fichier | Rôle |
|---|---|
| `app.py` (537 LOC) | Entrée Flask, configuration sécurité, bootstrap DB, seed groupes et admin par défaut, ProxyFix |
| `config.py` | Constantes chemins (DB, frontend, assets), chargement de `.app_secret_key` |
| `database.py` | Wrappers `get_db()` / `get_users_db()` (WAL, FK ON), `ensure_column`, normalisation des lignes |
| `auth.py` (394 LOC) | CRUD users/groups, hash bcrypt, rate-limit login, décorateurs `login_required`, `permission_required`, `admin_required`, extraction IP forwardée |
| `permissions.py` | Catalogue déclaratif `ROUTES_REQUIRED_PERMISSIONS` + `DEFAULT_GROUPS` + validation au démarrage (dev) |
| `utils.py` (255 LOC) | Slugify, mask RGPD, formatters de dates/labels, `AppError`, normalisation PDF |
| `models/` | Logique métier persistée. Voir détail ci-dessous |
| `routes/` | Blueprints HTTP. Voir détail ci-dessous |
| `pdf/` | Génération PDF FPDF2 (attribution + restitution + retraits) |
| `templates/` | 2 fichiers internes pour `lock_test` (debug routes) |

#### `backend/models/` (logique métier)

| Module | LOC | Rôle |
|---|---|---|
| `forms.py` | 747 | `persist_form()` (cœur de la sauvegarde), `get_form()`, sérialisations, gestion multi-sélection, mécanique retraits |
| `workflow.py` | 552 | Schémas dynamiques de champs, calcul statut effectif, validation des ressources, dérivation statut restitution |
| `catalog.py` | 498 | Catalogues `resource_catalog` + `service_catalog`, seed par défaut, migrations builtin |
| `settings.py` | 408 | `DEFAULT_APP_SETTINGS`, presets thèmes (5 palettes light+dark), build payload public, cache du logo |
| `signature.py` | 254 | Liens de signature à usage unique (`signature_links`), TTL, révocation, lecture/normalisation |
| `audit.py` | 168 | `insert_audit_event`, `insert_app_log`, lecture cookie contexte client, masquage RGPD du log |
| `dossier.py` | 142 | Synchronisation `persons` + `onboarding_dossiers` à chaque save |

#### `backend/routes/`

| Module | LOC | Rôle |
|---|---|---|
| `admin.py` | **1 609** | Settings, branding, dashboard exec, KPIs, groupes, users CRUD, services CRUD + CSV, resources CRUD, corbeille, logs, **export/import/diagnostic DB** |
| `forms.py` | 830 | Liste/CRUD dossiers, exports Excel/CSV/PDF/ZIP, restitution Phase 1 + Phase 2 |
| `pages.py` | 490 | Pages HTML statiques (`send_from_directory`), login/signup/logout, CSRF token, `/api/settings/public`, route emergency-login (⚠️) |
| `signature.py` | 409 | Liens publics signature attribution + restitution, soumission signature, masquage signature dans le dossier (besoin d'une re-vérification mot de passe) |
| `auth.py` | 70 | `verify-session`, `check-verification`, `clear-verification` (vérification mot de passe avant affichage signature) |
| `debug.py` | 103 | Routes admin pour tester le verrouillage / collecter des rapports d'exécution / recevoir des logs JS |

#### Frontend (`frontend/`)

Les **25 pages HTML** sont des pages indépendantes (pas de SPA). Chaque page charge :
1. `branding.js` (mandatoire, contient `APP_BUILD_VERSION`)
2. Un ou plusieurs JS spécifiques à la page.

| Fichier JS | LOC | Rôle |
|---|---|---|
| `app.js` | **3 075** | Logique du formulaire dossier (form.html) : sections dynamiques, retraits, validation, signature |
| `storage.js` | **2 500** | Logique du tableau de bord index.html (liste, filtres, sélection, export, refresh auto, cache local) |
| `admin.js` | 1 141 | Page admin.html (groupes, users, services, ressources) |
| `restitution.js` | 943 | Page Phase 2 restitution (état matériel, signature) |
| `branding.js` | 957 | Thèmes, dark mode, cookies banner, settings public, badge setup non terminé |
| `ui.js` | 775 | CSRF token cache, menu utilisateur, modal changement mdp, mojibake repair |
| `admin-branding.js` | 503 | Sous-page personnalisation |
| `help.js` | 460 | Contenu d'aide pour toutes les pages |
| `executive-dashboard.js` | 435 | Synthèse DG (KPIs) |
| `global-search.js` | 434 | Palette Ctrl+K (recherche globale) |
| `restitution-signature.js` | 345 | Signature publique de restitution (token) |
| autres | divers | login, signup, logs, trash, setup, signature, config… |

### 2.3 Flux principal de l'application

**Flux nominal : création d'un dossier d'attribution + signature + restitution.**

```
1. /login (POST)                — pages.py
   └─ check_user (bcrypt)
   └─ session["user"] = username
   └─ redirect /setup.html si setup_completed=0, sinon /

2. /  (GET index.html)
   └─ storage.js charge /api/forms     — forms.py:list_forms
       ├─ filtrage par service si user a un service et pas forms.view_all
       └─ ETag pour éviter de retransmettre

3. /form.html (nouveau dossier)
   └─ app.js charge /api/reference/resources + /api/reference/services
   └─ Saisie formulaire ; types ressources dynamiques (field_schema_json)
   └─ POST /api/forms                   — forms.py:create_form
       └─ persist_form (models/forms.py)
           ├─ _sanitize_unc_acces
           ├─ normalize_workflow_before_save (calcul statut)
           ├─ sync_person_and_dossier (persons + onboarding_dossiers)
           ├─ INSERT/UPDATE dotation_forms
           ├─ DELETE+INSERT dotation_items (un par ressource)
           ├─ insert_audit_event + insert_app_log
           └─ _upsert_field_suggestions (mémorise valeurs saisies)

4. Signature
   Variante A — sur place :
   └─ Canvas signature.html → base64 ajouté à payload.validation.signatureDataUrl
   Variante B — lien à distance :
   └─ POST /api/forms/<id>/signature-link → create_signature_link
   └─ /signature/<token> (public, sans auth)  — signature.py:get_signature_token_route
   └─ POST /api/signature/<token>/submit       — signature.py:submit_signature_token_route
       └─ persist_form (verrouille lockedAt)
   └─ Statut effectif → "active"

5. Restitution
   Phase 1 — /restitution-phase1.html
   └─ PATCH /api/forms/<id>/restitution  (dates/motif)
   └─ POST  /api/forms/<id>/restitution-phase1-validate
       └─ phase1ValidatedAt + phase1ValidatedBy
       └─ verrouillage modifiable < N jours (param restitution_phase1_unlock_days)
   Phase 2 — /restitution.html
   └─ PATCH /api/forms/<id>/restitution  (items + signatureStatus)
   └─ derive_restitution_workflow_status → "returned" | "partial_return" | "awaiting_signature"

6. Exports
   └─ GET /api/forms/<id>/pdf            — pdf/attribution.py
   └─ GET /api/forms/<id>/restitution-pdf — pdf/restitution.py
   └─ GET /api/forms/export              — Excel XML SpreadsheetML 2003
   └─ POST /api/forms/export-pdf-batch   — ZIP

7. Affichage signature (dossier verrouillé)
   └─ POST /api/auth/verify-session (mot de passe re-saisi, TTL 15 min)
   └─ GET  /api/forms/<id>/signature/view (renvoie signatureDataUrl)
   └─ Trace insertion dans table signature_views
```

---

## 3. Base de données

### 3.1 Deux bases SQLite distinctes

- **`backend/dotation.db`** — métier (gitignoré). Mode WAL, `foreign_keys = ON`.
- **`backend/users.db`** — authentification (gitignoré, séparation choisie pour permettre l'export base sans fuiter les hashes).

Les schémas sont créés à chaque démarrage via `CREATE TABLE IF NOT EXISTS`, complétés par des `ensure_column` + `migrate_*` idempotents — **pas de système de migration versionné** (Alembic, Yoyo) ; toute la stratégie repose sur le pattern « idempotent migrations » documenté dans `migration_schema_strategy` (mémoire projet).

### 3.2 Tables de `dotation.db`

| Table | Rôle | Notes |
|---|---|---|
| `dotation_forms` | Dossier d'attribution principal (colonnes typées + `payload_json`) | PK = id texte (timestamp ms), `dossier_id` FK vers `onboarding_dossiers`. Index `updated_at DESC`, `status` |
| `dotation_items` | Ligne par ressource attribuée à un dossier | FK `form_id` CASCADE. Sert aux exports Excel et restitution |
| `dotation_item_selections` | Multi-sélection (multi-ordinateurs, multi-tél…) | Sprint v3.14.0. FK `form_id` CASCADE |
| `persons` | Personnes (agents/élus) | PK = id texte. Une seule personne peut avoir plusieurs dossiers (changement de service, mise à jour…) |
| `onboarding_dossiers` | Dossier d'onboarding (regroupement) | FK `person_id` CASCADE. Statut dérivé (`derive_dossier_status`) |
| `audit_events` | Événements business par dossier | FK `dossier_id` CASCADE. Lecture interne, non exposée |
| `app_logs` | Logs applicatifs globaux | Toutes actions sensibles. Vue `logs.html`. Stocke aussi `target_label`, IP, user-agent |
| `deleted_items` | Corbeille (forms, resources, users) | Restauration via `/api/admin/trash/.../restore` |
| `resource_catalog` | Catalogue des ressources paramétrables | `field_schema_json` (champs dynamiques), `is_builtin` (impossible à supprimer), `display_order` |
| `service_catalog` | Catalogue des services émetteurs | Import/export CSV |
| `app_settings` | Clé/valeur des paramètres globaux | `org_name`, thèmes, DPO, `setup_completed`, `restitution_phase1_unlock_days`… |
| `field_suggestions` | Autocomplete des valeurs saisies | Scope = `service` pour chemins UNC |
| `signature_links` | Liens à usage unique pour signature distante | `link_type` ∈ {assignment, restitution}, statut, expiration, IP d'ouverture |
| `signature_views` | Journal des affichages de signature après auth | Pour traçabilité RGPD |

### 3.3 Tables de `users.db`

| Table | Rôle |
|---|---|
| `users` | username PK, `password_hash`, `is_active`, `status` (active/pending/disabled), `service`, `db_manage` |
| `groups` | clé + label + description + `permissions_json` + `data_scope` (full/masked) |
| `user_groups` | jointure n-n |

### 3.4 Relations principales

```
persons (1) ──┬── (n) onboarding_dossiers (1) ──┬── (n) dotation_forms (1) ──┬── (n) dotation_items
              │                                  │                              ├── (n) dotation_item_selections
              │                                  │                              ├── (n) signature_links
              │                                  │                              └── (n) signature_views
              │                                  └── (n) audit_events
              └─ pas de FK directe vers dotation_forms (passe par dossier_id)

resource_catalog ─── (utilisé en référence par payload_json.resources.additional)
service_catalog  ─── (utilisé par dotation_forms.service / issuer_service)
field_suggestions ── (autocomplete frontend)

users (n) ─── (n) groups via user_groups
```

### 3.5 Particularité — colonne `payload_json`

C'est la colonne **clé de voûte du modèle**. Toute la sémantique du dossier (sections matériel/immateriel, ressources additionnelles dynamiques, validation RGPD, métadonnées workflow, restitution, retraits) y vit en JSON. Les colonnes typées (`nom`, `prenom`, `service`, `status`…) sont des **projections dénormalisées** maintenues par `persist_form` pour permettre les listes et filtres SQL classiques.

> ⚠️ Risque structurel : toute évolution de schéma JSON doit rester rétrocompatible (les anciens dossiers ne sont jamais migrés en lot, mais seulement à la prochaine sauvegarde).

---

## 4. Fonctionnalités métier

### 4.1 Fonctionnalités détectées (état v3.18.x)

**Cycle dossier**
- 4 types de dossier : `arrivee`, `changement_service`, `mise_a_jour`, `sortie`
- Brouillon avec quick-draft (nom + prénom seulement)
- Workflow effectif recalculé à chaque lecture (`compute_effective_workflow_status`)
- Verrouillage `meta.lockedAt` à la signature ; réouverture admin possible (compteur `reopenCount`)
- Suppression → corbeille + restauration possible

**Catalogue de ressources dynamiques**
- 15 ressources builtin (ordinateur, écran, téléphone, tablette, VPN, email, badge, clés, veste, chaussures, zone alarme, véhicule, plaque porte, cartes de visite, autre)
- Schéma de champs paramétrable par l'admin (`field_schema_json` typé : text, textarea, select, date, number, checkbox, list, email_with_domain)
- Flags par ressource : `has_assignment_date`, `has_assignment_condition`, `has_assignment_notes`, `requires_return`
- Catégorie matériel/immateriel + service émetteur paramétrables
- `is_builtin` empêche la suppression
- Réordonnancement via `admin-ressources-ordre.html`

**Signature électronique**
- Sur place : canvas dataURL PNG
- À distance : lien jetonné (`secrets.token_urlsafe(32)`), TTL 1-30 jours, révocation, traçabilité (IP, ouverture)
- Affichage signature pour utilisateur autorisé : re-vérification du mot de passe (TTL 15 min) + log dans `signature_views`
- Garde-fou de taille : 1 Mo max
- Décision signataire (`confirmed` / `with_reservation` + commentaire)

**Restitution en deux phases (v3.17)**
- Phase 1 (RH) : motif, date de fin de mission, date de remise → verrouillage modifiable < `restitution_phase1_unlock_days` (défaut 1 j), au-delà motif requis
- Phase 2 (technique) : état par ressource (conforme/dégradé/non_restitue/perdu/autre), notes, signature distincte
- Garde explicite : pas d'écriture Phase 2 tant que Phase 1 non validée
- Mise à jour avec retraits : un dossier `mise_a_jour` lié à un dossier source par `sourceFormId` permet de marquer les items du source comme returned (cf. `_apply_retraits_to_source`)

**Administration**
- Gestion utilisateurs : pending/active/disabled, services, flag `db.manage`, hashes bcrypt
- Gestion groupes : permissions toggleables (uniquement `unc.view_all` actuellement)
- Catalogues : ressources + services (CSV import/export + modèle)
- Branding : 5 thèmes (institutionnel, lac_montagne, ardoise, sable, forêt), logo via URL/fichier (PNG, 2 Mo max), dark mode policy (disabled/allowed/forced)
- Contexte organisationnel : public_collectivite, public_administration, private_company, association → conditionne les `beneficiary_types`
- **Setup wizard** : forcé tant que `setup_completed=0` (redirection après login)
- **DB management** : export `.db`, diagnostic intégrité (PRAGMA integrity_check + vérification tables requises), import avec backup automatique

**Exports**
- PDF attribution / restitution / retraits (FPDF2, bandeau bleu + bande or, logo org)
- Excel XML SpreadsheetML 2003 (.xls)
- CSV accès UNC + CSV services
- Batch ZIP pour multi-sélection

**Sécurité**
- CSP, HSTS, X-Frame-Options SAMEORIGIN, Referrer-Policy, Permissions-Policy
- CSRF token validé sur tous POST/PUT/PATCH/DELETE des API hors signature publique
- Cookie session `__Secure-` adaptatif (HTTPS détecté via ProxyFix)
- Rate limiting : login 10/10min, signup 5/10min, settings PUT 20/min, exports DB 20/min, import DB 3/10min, signature views 10/5min
- Pas de DPAPI / pas de chiffrement at-rest (SQLite clair)

**UX**
- Navigation 5 onglets (v3.16)
- Mode sombre
- Recherche globale Ctrl+K (`global-search.js`)
- Autocomplete par champ « suggest » (`field_suggestions`)
- Cache localStorage des brouillons (résilience hors-ligne)
- Refresh auto du dashboard (20 s)

### 4.2 Modules les plus critiques

Par ordre de criticité métier :

1. **`backend/models/forms.py`** — toute la persistance des dossiers, retraits, suggestions. Une régression ici ⇒ corruption ou perte de données.
2. **`backend/models/workflow.py`** — calcule le statut effectif d'un dossier ; régression ⇒ dossiers signés affichés comme brouillons (déjà arrivé, cf. fix v3.18.1).
3. **`backend/routes/signature.py`** + **`backend/models/signature.py`** — risque RGPD si la signature fuit ou que les liens jetons sont mal gérés.
4. **`backend/auth.py`** — toute l'authentification + rate limiting. Stockage in-memory (`_login_attempts`) : non partagé entre workers Gunicorn (limite acceptable pour la cible mais à connaître).
5. **`backend/routes/admin.py`** — fichier mammouth (1 609 LOC). Couvre permissions, settings, KPIs, services, ressources, corbeille, DB. Toute évolution sensible y passe.
6. **`frontend/js/app.js`** + **`frontend/js/storage.js`** — UX du quotidien.

---

## 5. Dette technique

### 5.1 Points faibles

#### Backdoor de connexion encore présente

**`backend/routes/pages.py` ligne 49-73** :

```python
@bp.route("/api/emergency-login", methods=["POST"])
def emergency_login():
    """Route d'urgence temporaire pour debugger les problèmes CSRF.
    À SUPPRIMER une fois le problème résolu."""
    ...
    if username == "admsamir" and password == "MotDePasse74500":
        session["user"] = username
        ...
```

🔴 **Critique** : identifiants en clair, exposés sur une route POST publique sans CSRF (`/api/emergency-login` ne passe pas le filtre `before_request` car il est public sans `session["user"]`). **À supprimer immédiatement.** Le log indique pourtant qu'elle est censée être temporaire.

#### Fichiers obèses

- `frontend/js/app.js` : **3 075 LOC** dans un seul fichier global (variables `let` globales, manipulations DOM directes).
- `frontend/js/storage.js` : **2 500 LOC** idem.
- `backend/routes/admin.py` : **1 609 LOC** mélange 8 domaines (settings, dashboard, groupes, users, services, resources, trash, DB).
- `frontend/css/style.css` : **4 513 LOC** dans un seul fichier.
- `backend/models/forms.py` : **747 LOC** ; `persist_form` orchestre trop de responsabilités.

#### Capture de console côté front renvoyée au serveur

`frontend/js/app.js` lignes 5-53 : **toutes les sorties `console.log/error/warn` sont capturées et envoyées à `/api/debug/logs`** (POST, ou `sendBeacon` au beforeunload). La route admin reçoit ces logs et les écrit sur disque (`backend/routes/debug.py`). Inquiétant car :
- volumétrie : un dossier complexe peut générer des centaines de logs ;
- contenu : peut contenir des données personnelles (la fonction ne masque rien) ;
- privilège : `/api/debug/logs` est `@admin_required`, mais l'app dans `app.js` envoie en permanence ⇒ tous les `403` côté serveur quand l'utilisateur n'est pas admin.

#### Code dupliqué

- **Définition de `default_groups`** dupliquée entre `app.py:seed_default_groups()` (ligne ~157) et `app.py:migrate_missing_groups()` (ligne ~214). Toute évolution doit toucher deux endroits.
- **Liste des thèmes** dupliquée entre `backend/models/settings.py:THEME_PRESETS` et `frontend/js/branding.js:BRAND_THEME_PRESETS`. À chaque ajout de thème, la palette doit être synchronisée à la main.
- Pattern `download_response(...)`, `generate_id`, `format_export_datetime` corrects ; pas de réimplémentation observée.
- Le code de revalidation de signature (Phase 1 vs Phase 2) duplique partiellement la garde « si Phase 1 non validée → refuser ».

#### Problèmes d'architecture

- **Mélange responsabilités** dans `routes/admin.py` (route Flask + logique métier + diagnostic SQLite + manipulation fichiers).
- **`pages.py` mélange** auth (login/signup/logout), pages HTML, API publiques (`/api/csrf-token`, `/api/settings/public`, `/api/me/password`). La séparation /api vs HTML n'est pas faite.
- **Pas de couche service** entre routes et models : `route` parle directement à `models.persist_form` qui ouvre lui-même la transaction. Difficile à tester unitairement.
- **Aucune validation de schéma** (Marshmallow / Pydantic) sur les payloads POST/PUT — la validation est uniquement implicite (`payload.get(...)`, `AppError`).
- **`utils.py` est un god-module** : datetime formatting + slugify + masking + appels PNG + labels métier. Devrait être éclaté en `text_utils`, `format_utils`, `labels`, `pdf_utils`.

#### Problèmes de sécurité potentiels

| Point | Sévérité | Détail |
|---|---|---|
| `emergency_login` avec mdp hard-codé | 🔴 Critique | Backdoor active en prod, identifiants en clair dans le code source versionné |
| Capture console.log envoyée côté serveur | 🟠 Haute | Risque fuite données via logs, écriture libre sur disque |
| Pas de chiffrement at-rest SQLite | 🟠 Haute | Toutes les bases en clair sur disque, y compris signature en base64 |
| Pas d'audit du JSON dynamique | 🟡 Moyenne | `payload_json` accepté tel quel ; un POST malicieux peut grossir indéfiniment (pas de limite de taille body Flask explicitement réglée) |
| Rate limit local au worker | 🟡 Moyenne | Avec Gunicorn N workers, attaquant a 10×N tentatives login |
| CSP avec `'unsafe-inline'` pour style-src | 🟡 Moyenne | Justifié par Bootstrap inject, mais affaiblit la défense XSS |
| `innerHTML` répété côté front (~30 occurrences) | 🟡 Moyenne | Avec `escapeHtml` parfois utilisé, parfois pas. Risque XSS si données externes mal échappées (cf. `app.js:128, 491` ; `admin.js:652, 919`) |
| `session.get("user")` direct dans `models` | 🟡 Moyenne | Couplage fort : `models/forms.py`, `models/audit.py`, `models/signature.py` lisent la session — empêche les appels CLI ou tests sans contexte Flask |
| Routes `/api/debug/*` admin mais écrivent fichiers JSON dans CWD | 🟡 Moyenne | `lock_report_*.json`, `debug_logs_*.json` accumulés dans le dossier de travail |
| Diagnostic DB lit `is_deleted = 0` | 🟡 Moyenne | Colonne `is_deleted` n'existe pas dans le schéma actuel ⇒ exception silencieuse, stats à 0 (bug `routes/admin.py:1494`) |
| `frontend/js/branding.js` charge CookieConsent depuis CDN | 🟢 Faible | Dépendance externe sans SRI (Subresource Integrity) ; CSP autorise cdn.jsdelivr.net |

### 5.2 Risques opérationnels

- **Pas de versionnage des migrations** : si une migration `migrate_*` casse, pas de rollback. Stratégie « always idempotent » mais fragile (déjà vu : `migrate_telephone_imei_field` corrige un schéma seedé).
- **Fichiers transitoires non nettoyés** : `pdf_cache/attribution/...`, `lock_check_20260425_*.json`, `flask.log`, `users.json.migrated`, `database.sqlite` (vide) traînent à la racine.
- **`debug-mdp.sh.deprecated`** et **`scripts/merge-users-config.py.deprecated`** dans le dépôt : à archiver / supprimer proprement.
- **Pas de backup automatique** côté applicatif (sauf au moment d'un import DB). Repose entièrement sur la sauvegarde OS.
- **Aucune télémétrie / monitoring** intégré (pas de healthcheck dédié hors page de login).
- **Limite SQLite** assumée (~10k dossiers, <50 utilisateurs) ; au-delà : risque de verrouillage en écriture concurrente malgré WAL.

---

## 6. Tests

### 6.1 Couverture apparente

Quatre fichiers dans `tests/` :

| Fichier | Cible | Type |
|---|---|---|
| `test_critical_fixes.py` | Régressions front (workflow read-modify-save-read) | Tests **simulés** : reproduisent en Python des invariants front sans appeler le vrai code |
| `test_extract_items_fix.py` | `models/workflow.extract_items` | Test **réel** d'un module backend (préserve les items décochés) |
| `test_permissions_validation.py` | `backend/permissions.py` | Test du catalogue déclaratif des permissions/routes |
| `test_seed_groups.py` | `app.py:seed_default_groups` + `seed_default_admin` | Tests sur DB temporaire (bon) |

### 6.2 Zones non sécurisées par les tests

🔴 **Aucun test unitaire ne couvre :**
- `models/forms.persist_form` (le cœur métier)
- `models/workflow.compute_effective_workflow_status`
- `models/signature.create_signature_link` / révocation
- `pdf/attribution.build_pdf_bytes` et `pdf/restitution.build_restitution_pdf_bytes`
- les routes `routes/forms.*` (zéro test d'intégration HTTP)
- la CSRF middleware (`@before_request`)
- la chaîne complète signature distante (création lien → ouverture → POST submit → verrouillage)
- les migrations idempotentes (aucun test ne crée une vieille DB pour vérifier le bon comportement)
- les exports Excel / CSV / ZIP
- la corbeille (restauration / suppression définitive)
- le diagnostic DB (chemin `is_deleted = 0` bugué non détecté)

🟠 **Frontend : zéro test.** Pas de Jest, Vitest, Playwright. La régression UX n'est rattrapée qu'à l'œil.

🟠 **Pas de fixture pytest commune** (`conftest.py` absent), chaque fichier réinvente le bootstrap de DB temporaire.

🟢 **CI** : pas de fichier `.github/workflows/` détecté dans la structure ; la commande `pytest tests/` est documentée dans le README mais n'est pas automatisée.

### 6.3 Recommandation rapide

Le filet de sécurité actuel laisse passer toute régression sur le workflow signature, la persistance JSON, et les PDF. Le ratio LOC tests / LOC code est de l'ordre de **0,5 %** — très faible pour une application qui manipule de la donnée RH signée.

---

## 7. Recommandations

### 7.1 Quick wins (< 1 jour chacun)

| # | Action | Bénéfice |
|---|---|---|
| QW-1 | **Supprimer `/api/emergency-login`** et purger les identifiants `admsamir/MotDePasse74500` de l'historique git (filter-branch / BFG). | Élimine une backdoor critique |
| QW-2 | **Désactiver la capture console → backend** par défaut (gate sur `FLASK_ENV=development`) | Stoppe une fuite potentielle de données + bruit |
| QW-3 | **Corriger le bug `is_deleted = 0`** dans `routes/admin.py:1494` (`_diagnose_db_file`) — utiliser `COUNT(*)` simple. | Diagnostic DB redevient correct |
| QW-4 | **Factoriser la liste `default_groups`** entre `seed_default_groups`, `migrate_missing_groups` et `permissions.DEFAULT_GROUPS`. | Une seule source de vérité |
| QW-5 | **Ajouter `MAX_CONTENT_LENGTH`** sur Flask app (ex : 5 Mo) | Prévention DoS via gros POST |
| QW-6 | **Ajouter SRI** sur les `<script>` et `<link>` CDN (Bootstrap, CookieConsent) dans tous les HTML | Renforce CSP |
| QW-7 | **Nettoyer racine** : déplacer `lock_check_*.json`, `flask.log`, `database.sqlite` vide, `users.json.migrated`, `*.deprecated` ; les ajouter au `.gitignore` | Hygiène |
| QW-8 | **Conftest pytest** unique + 5 tests d'intégration sur `/api/forms` (create, get, list, update, delete) | Détection rapide des régressions API |
| QW-9 | **Renommer `chromedriver/`, `.tmpchrome7/`** et les retirer du dépôt | Hygiène |
| QW-10 | **Documenter la convention de versionnage** : `branding.js:5` ≠ `README.md` (3.18.4-dev vs 3.18.3-prod) → automatiser via un script. | Évite la divergence |

### 7.2 Améliorations moyen terme (1 jour à 1 semaine)

| # | Action | Bénéfice |
|---|---|---|
| MT-1 | **Splitter `routes/admin.py`** en 8 blueprints (`admin_dashboard`, `admin_users`, `admin_groups`, `admin_services`, `admin_resources`, `admin_branding`, `admin_trash`, `admin_db`) | Maintenabilité |
| MT-2 | **Splitter `frontend/js/app.js`** par section (identite, ressources, retraits, signature, validation) via modules ES6 (sans bundler : `<script type="module">`) | Réduction couplage |
| MT-3 | **Introduire Marshmallow ou Pydantic** pour valider tous les payloads d'entrée des routes API | Sécurité + erreurs explicites |
| MT-4 | **Test suite : ajouter 30 tests d'intégration HTTP** (Flask test client) couvrant signature, restitution, exports, CSV | Filet de sécurité |
| MT-5 | **CI GitHub Actions** lançant pytest + lint + audit pip-audit | Régression rattrapée tôt |
| MT-6 | **Rate limiting partagé** (Redis ou table SQLite avec TTL) au lieu de dict in-memory par worker | Cohérence multi-workers |
| MT-7 | **Audit XSS systématique** des `innerHTML` côté front (~30 occurrences) — privilégier `textContent` + `<template>` clonage | Réduit la surface XSS |
| MT-8 | **Migration versionnée** (Yoyo, Alembic light, ou table `schema_version`) | Sécurise les évolutions DB |
| MT-9 | **Découpler `models.*` de `flask.session`** : passer l'`actor` en argument explicite | Permet le scripting CLI, simplifie les tests |
| MT-10 | **Logs structurés** (JSON) à la place de `flask.log` ASCII | Exploitable par ELK / Loki |

### 7.3 Améliorations long terme (semaines à mois)

| # | Action | Bénéfice |
|---|---|---|
| LT-1 | **Tests end-to-end Playwright** sur les parcours critiques (création, signature distante, restitution Phase 1/2, exports) | Confiance UX |
| LT-2 | **Chiffrement at-rest** : envisager SQLite Encryption Extension (SEE / SQLCipher) ou migration PostgreSQL avec pgcrypto pour le champ `signature_data` | Conformité RGPD renforcée |
| LT-3 | **Migration progressive vers PostgreSQL** quand seuils SQLite atteints (la migration est prévue dans le README) | Scalabilité |
| LT-4 | **Bundler frontend** (Vite ou esbuild en pipeline simple) avec préfix immutable cache + suppression dépendances CDN | Performance + sécurité |
| LT-5 | **Composantiser le frontend** (Lit ou Web Components vanilla) pour découper `app.js` et `storage.js` durablement | Maintenabilité |
| LT-6 | **Refactor `payload_json`** : extraire les champs systématiquement requis en colonnes typées avec contraintes ; ne garder JSON que pour `resources.additional` | Requêtage simplifié, contraintes DB |
| LT-7 | **Pipeline d'audit RGPD** : registre des traitements, génération automatique du registre, masquage configurable | Conformité |
| LT-8 | **Monitoring applicatif** (Prometheus exporter + dashboard Grafana) pour latence API et taux d'erreur | Exploitation |
| LT-9 | **Internationalisation** : externaliser les chaînes (déjà amorcé avec `APP_TEXT` dans `login.js`) | Ouverture |
| LT-10 | **Modèle de permission ABAC** plus fin (par service, par catégorie de ressource) | Évolution du métier |

---

## 8. Utilisation de Graphify

**Graphify est installé** (`pip show graphify` répond) mais le pipeline complet (`graphify .` avec extraction LLM + clustering Louvain) sur ~32 000 LOC nécessiterait plusieurs minutes et un budget LLM significatif. J'ai donc reconstruit le graphe des dépendances **backend** manuellement à partir des `import` statiques (analyse équivalente à l'étape 3 de graphify, sans la phase LLM/INFERRED). Le résultat suit.

### 8.1 Graphe de dépendances internes (backend)

```
                 ┌─────────────┐
                 │  config.py  │ (feuille)
                 └──────┬──────┘
                        │
        ┌───────────────┼────────────────┐
        ▼               ▼                ▼
   ┌─────────┐    ┌──────────┐     ┌──────────┐
   │ utils   │    │ database │     │  auth    │
   │ (255)   │    │  (72)    │◄────┤  (394)   │
   └────┬────┘    └────┬─────┘     └────┬─────┘
        │              │                │
        ├──────────────┴────────────────┤
        ▼                               ▼
   ┌─────────────┐               ┌──────────────┐
   │ permissions │               │ models/audit │
   │   (70)      │               │   (168)      │
   └─────────────┘               └──────┬───────┘
                                        │
                ┌───────────────────────┴────────────────┐
                ▼                                        ▼
        ┌──────────────┐                        ┌────────────────┐
        │ models/      │                        │ models/        │
        │ workflow(552)│◄───────┐               │ signature(254) │
        └──────┬───────┘        │               └────────────────┘
               │                │
               ├────────────────┤
               ▼                ▼
        ┌─────────────┐   ┌─────────────┐
        │ models/     │   │ models/     │
        │ catalog(498)│   │ dossier(142)│
        └─────────────┘   └─────┬───────┘
                                │
                                ▼
                         ┌─────────────┐
                         │ models/     │
                         │ forms(747)  │◄──── HUB métier
                         └──────┬──────┘
                                │
                 ┌──────────────┼──────────────┐
                 ▼              ▼              ▼
          ┌────────────┐ ┌──────────────┐ ┌──────────────┐
          │ routes/    │ │ routes/      │ │ routes/      │
          │ forms(830) │ │ signature(409)│ │ admin(1609)  │
          └────────────┘ └──────────────┘ └──────────────┘

  pdf/attribution(367)  ←─── pdf/restitution(302)
        ↑                          ↑
        └── importé par routes/forms ─┘
```

### 8.2 Ce que révèle le graphe

**Modules « hub » (importés par ≥ 5 modules) :**

| Module | Importé par | Rôle |
|---|---|---|
| `utils` | 13 modules | Module utilitaire central — **trop chargé**, candidat au split |
| `auth` | 10 modules | Décorateurs + helpers ; OK, mais lit `flask.session` partout |
| `database` | 9 modules | OK, parfait fan-out d'une couche d'accès |
| `models/audit` | 6 modules | OK, événements + logs centralisés |
| `models/workflow` | 6 modules | OK, logique métier partagée |
| `models/forms` | 4 modules | Hub métier le plus lourd — `persist_form` orchestre tout |

**Couplages forts :**

- `routes/admin` importe **8 modules internes** (`models/audit`, `models/settings`, `models/catalog`, `models/forms`, `database`, `auth`, `utils`, `config`) → reflet de sa polyvalence ; signe qu'il devrait être splitté.
- `routes/forms` ↔ `models/forms` ↔ `pdf/*` forment un noyau métier très intriqué : un changement de schéma JSON impacte les trois.
- `models/forms` importe `models/dossier`, `models/workflow`, `models/audit`, `models/settings` → c'est lui le **god module** côté métier.

**Modules sensibles aux régressions (centralité):**

1. `models/workflow.compute_effective_workflow_status` — utilisé en lecture *et* en écriture
2. `models/forms.persist_form` — cœur de la persistance, fait : sanitization UNC, normalisation workflow, sync persons, INSERT/UPDATE, audit, retraits
3. `auth.has_permission` — appelé sur quasi toutes les routes
4. `utils.format_*` — toute UI/PDF dépend de leur stabilité

**Cycles d'imports :** aucun détecté — la séparation `app → routes → models → database → config + utils` est respectée. C'est un bon point.

**Points sensibles révélés (équivalent communautés Louvain) :**

| « Communauté » | Modules | Risque |
|---|---|---|
| Communauté **Auth/Sécu** | `auth`, `permissions`, `routes/auth`, `routes/pages` (login/signup) | Backdoor `emergency_login` ; rate limit in-memory |
| Communauté **Dossier/Workflow** | `models/forms`, `models/workflow`, `models/dossier`, `routes/forms` | Couplage très fort ; tests insuffisants |
| Communauté **Catalogue/Settings** | `models/catalog`, `models/settings`, `routes/admin` (segments resources/settings/branding) | Migrations builtin idempotentes — fragilité long terme |
| Communauté **Signature** | `models/signature`, `routes/signature`, `routes/auth` (verify-session) | Risque RGPD, peu de tests |
| Communauté **Reporting** | `pdf/attribution`, `pdf/restitution`, `routes/forms` (exports) | Aucun test, encodage cp1252 (`normalize_pdf_text`) délicat |

> **Si vous voulez lancer Graphify pour un graphe interactif HTML** (utile pour onboarder un nouveau dev), la commande est :
> ```powershell
> python -m graphify.cli c:\www\dotation --mode deep --html --directed
> ```
> Comptez ~10 minutes d'exécution et un budget LLM (Anthropic / OpenAI selon configuration de graphify).

---

## 9. Plan d'action priorisé (top 10)

Classé par impact × urgence. Estimation impact = (qualité × sécurité × confiance utilisateurs) sur 10. Estimation effort en jours-homme.

| # | Action | Impact | Effort | Justification |
|---|---|---|---|---|
| 1 | **Supprimer `/api/emergency-login`** + purge git de `admsamir/MotDePasse74500` | 🔴 **10/10** | 0,5 j | Backdoor avec mot de passe en clair versionné. À traiter aujourd'hui. |
| 2 | **Tests d'intégration HTTP `routes/forms`** (10 tests minimum sur create/update/list/restitution/exports) | 🔴 9/10 | 2 j | Aucun filet sur le cœur métier — n'importe quelle refacto risque de casser un workflow signé. |
| 3 | **Corriger `is_deleted = 0` dans `_diagnose_db_file`** | 🟠 7/10 | 0,5 j | Bug actif qui rend le diagnostic DB faux silencieusement. |
| 4 | **Tests `compute_effective_workflow_status` + `derive_restitution_workflow_status`** | 🔴 9/10 | 1,5 j | Régression v3.18.1 a corrigé exactement ce périmètre — éviter la rechute. |
| 5 | **Désactiver capture console → /api/debug/logs** en prod (gate `FLASK_ENV`) | 🟠 8/10 | 0,5 j | Fuite potentielle de données + écriture fichiers JSON sur disque. |
| 6 | **Splitter `routes/admin.py`** en blueprints thématiques | 🟠 7/10 | 3 j | Fichier de 1 609 LOC mélangeant 8 domaines = épicentre de risques. |
| 7 | **Ajouter Marshmallow/Pydantic** + un schéma par endpoint critique (`/api/forms`, `/api/forms/<id>/restitution`, `/api/admin/settings`) | 🟠 8/10 | 3 j | Validation explicite remplace `payload.get(...)` partout, erreurs propres pour le front. |
| 8 | **Source unique des permissions par défaut** (factoriser `seed_default_groups` ↔ `migrate_missing_groups` ↔ `permissions.DEFAULT_GROUPS`) | 🟡 6/10 | 1 j | Trois listes synchronisées à la main = bug latent. |
| 9 | **Cycle CI GitHub Actions** (pytest + ruff + pip-audit) sur PR | 🟠 7/10 | 1 j | Aucune CI aujourd'hui. Garantie minimale qu'un PR ne casse pas. |
| 10 | **Découpler `models.*` de `flask.session`** : passer `actor` en argument explicite à `persist_form`, `insert_app_log`, etc. | 🟡 6/10 | 2 j | Débloque les tests unitaires sans contexte requête + permet scripts CLI (re-imports, batch retraits, etc.). |

**Effort total top 10 : ~15 jours-homme** (un sprint de 3 semaines à 1 dev).

---

## Annexes

### A. Mismatch de version détecté

- `frontend/js/branding.js:5` → `APP_BUILD_VERSION = "3.18.4-dev"`
- `README.md:3` → `Version : 3.18.3-prod`
- `CHANGELOG.md` dernière entrée : `3.18.3`

→ Recommandation : automatiser la lecture de la version depuis un fichier unique (`VERSION` ou `pyproject.toml`).

### B. Comptage rapide

```
Backend Python      ~8 300 LOC (22 fichiers)
Frontend JS        ~14 150 LOC (25 fichiers)
Frontend HTML       ~4 500 LOC (25 pages)
Frontend CSS        ~4 513 LOC (1 fichier)
Tests                 quelques centaines LOC (4 fichiers, ratio ~0,5 %)
```

### C. Documents déjà présents dans le dépôt à valoriser

- `README.md` : guide installation complet, à jour.
- `CHANGELOG.md` : historique par version.
- `DEPLOYMENT_GUIDE.md`, `TEST_PLAN_DEBIAN_FIXES.md`, `TEST_PLAN_WINDOWS_FIXES.md` : plans de test manuels existants.
- `docs/BUGFIXES_3.18.1.md` et `docs/CLEANUP_POOLS_3.18.4-dev.md` : traçabilité des derniers sprints.
- `.lessons.md` : retours d'expérience à mettre en avant pour un nouvel arrivant.

### D. Hors scope traité mais à noter

- **Dossier `backend/pdf_cache/attribution/1774859164916`** : artefact de cache PDF non purgé. À examiner et automatiser le nettoyage.
- **`announcement-aquai.eml`** à la racine : un email de communication versionné — sans doute à archiver hors dépôt.

---

*Rapport généré à partir d'une analyse statique du code et de l'historique mémoire. Aucune exécution applicative n'a été lancée pour cet audit.*
