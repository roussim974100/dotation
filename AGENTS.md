# AGENTS.md — point d'entrée pour un assistant de code (IA)

Ce fichier dit **où trouver l'information** dans ce dépôt, pour reprendre le travail sans relire tout le code. Il vaut pour
n'importe quel assistant (Claude, Codex, Cursor, Copilot, Gemini…). À lire en premier, puis ouvrir seulement ce qui sert
la tâche. Langue du projet : **français** (interface, commits, documentation, commentaires).

> Mettre ce fichier à jour quand une règle, un emplacement ou un piège change. Le reste (état, historique, décisions)
> vit dans les documents cités ci-dessous, pas ici.

## 1. L'application en deux phrases

**À Quai** gère les ressources remises aux agents et élus d'une organisation (collectivité, administration, entreprise,
association) : attribution (matériel, accès, comptes), signature, puis restitution au départ. Pile : **Flask + SQLite**
côté serveur, **HTML + JavaScript sans framework** côté navigateur, PDF générés par le serveur.

## 2. Par quoi commencer, selon la question

| Question | Où regarder |
|---|---|
| Où en est le projet, qu'est-ce qui reste à faire ? | `docs/BACKLOG_PRODUIT.md` (vue d'ensemble, priorités, sprint en cours) |
| Qu'est-ce qui a changé, version par version ? | `CHANGELOG.md` (le plus récent en haut) |
| Pourquoi les données sont organisées ainsi (dossier, champs, parc, stock) ? | `docs/ARCHITECTURE_DONNEES.md` — **à lire avant de toucher aux ressources ou aux champs** |
| Circuit de mise en production, tests, diagnostic | `docs/REPRISE_MAJ.md` (§2 à §6 ; son §1 « où on en est » date du 20/09, l'état courant est dans le backlog) |
| Audit et décisions de conception | `docs/audit/` (`DECISIONS_COMITE.md`, `AUDIT_SIMPLIFIE.md`, `AUDIT_DETAILLE.md`), `docs/AUDIT_SECURITE_2026-09.md` |
| Installation, déploiement, variables d'environnement | `README.md`, `setup/README.md`, `DEPLOYMENT_GUIDE.md` |
| Utilisation fonctionnelle (côté utilisateur) | `GUIDE_UTILISATEUR.md`, pages d'aide `frontend/help.html` |

Version courante : `APP_BUILD_VERSION` dans `frontend/js/branding.js` (identique à l'entête du `README.md`, vérifié par
`tests/test_version_consistency.py`).

## 3. Carte du code

**Recherche rapide** : sur le poste de développement, le dépôt est indexé par *graft* (dossier `graft/`) et *graphify*
(`graphify-out/GRAPH_REPORT.md`). Ces index sont **générés localement et non versionnés** : s'ils sont présents, un
`grep` d'un nom de fonction dans `graft/` donne le fichier et les lignes ; sinon, partir des tableaux ci-dessous.

### Serveur (`backend/`)

| Fichier | Rôle |
|---|---|
| `app.py` | création de l'application, en-têtes (cache, sécurité), enregistrement automatique des blueprints |
| `routes/forms.py` | API des dossiers : création, mise à jour, restitution (`PATCH /api/forms/<id>/restitution`), Phase 1, régularisation, exports Excel/PDF |
| `routes/pages.py` | pages HTML, connexion, `/api/session` (utilisateur courant, permissions, `data_scope`) |
| `routes/admin.py` | administration (comptes, services, ressources, personnalisation, base de données) |
| `routes/signature.py` | liens de signature à distance (attribution, restitution, **ajustement**) ; `models/signature.py` (`signature_link_*`) pour ajouter un 4ᵉ type |
| `routes/units.py`, `routes/stock.py`, `routes/inventory.py` | parc (objets suivis), stock, inventaire |
| `models/forms.py` | `persist_form` : **chemin unique d'enregistrement d'un dossier** (resynchronise parc et stock) |
| `models/workflow.py` | calcul des statuts (attribution, restitution) |
| `models/dossier.py` | personne ↔ dossier (`sync_person_and_dossier`) |
| `models/adjustment.py` | ajustement d'un dossier actif (ajouts, retraits, service, signature par geste) : fonctions pures ; routes `PATCH /api/forms/<id>/ajustement` dans `routes/forms.py` |
| `models/units.py`, `models/stock.py` | projections parc/stock (`sync_units_for_form`, `sync_stock_for_form`) |
| `models/vocab.py` | libellés de statuts et types de bénéficiaires (source unique, publiés au navigateur) |
| `models/settings.py` | paramètres de l'organisation |
| `auth.py`, `permissions.py` | comptes, groupes, permissions, portée des données (`data_scope`) ; toutes les permissions sont éditables par groupe dans Admin > Comptes (`routes/admin.py`, `TOGGLEABLE_PERMISSIONS`), avec garde-fou anti-verrouillage sur `users.manage`/`db.manage` |
| `app.py` (`PERMISSION_BACKFILLS`) | rattrape une fois pour toutes un droit ajouté après coup sur des groupes déjà en service (ex. `forms.adjust`), sans jamais réajouter un droit retiré volontairement — ajouter une ligne ici plutôt que de modifier `DEFAULT_GROUPS` pour un nouveau droit sur l'existant |
| `migrations.py` | migrations de schéma numérotées, idempotentes, avec copie de sécurité avant application (8 migrations à ce jour) |
| `pdf/attribution.py`, `pdf/restitution.py` | génération des PDF |
| `config.py`, `environment.py` | chemins de données (`APP_DATA_DIR`), environnement (dev/preprod/prod) écrit par le script de déploiement |

### Navigateur (`frontend/`)

Scripts **classiques** (pas de modules, pas de build) : les fonctions sont globales et partagées entre fichiers chargés
sur une même page. Chaque page HTML liste ses scripts en bas ; `?v=AAAAMMJJx` sert à forcer le rechargement — **mettre à
jour la version sur TOUTES les pages qui chargent ce fichier** (voir piège ci-dessous).

| Fichier | Rôle |
|---|---|
| `js/storage.js` | appels API, listes des dossiers (**4 tableaux de bord, regroupés par personne** — `groupDraftsByPerson`, une ligne par personne avec historique dépliable, dossiers toujours distincts en base), menus d'actions, exports, **e-mails `.eml`** et PDF |
| `js/app.js` | formulaire d'un dossier (`form.html`) : saisie, ressources (dont reprise de matériel restitué, `openReuseResourceModal`), signature, actions d'un dossier signé |
| `js/restitution-phase1.js`, `js/restitution.js` | restitution en deux phases : dates (`restitution-phase1.html`), état du matériel et signature (`restitution.html`) |
| `js/signature-qr.js`, `js/vendor/qrcode-generator.js` | QR code d'un lien de signature (fenêtre, générateur embarqué MIT, aucun CDN) ; actions `showAssignmentSignatureQr` / `showRestitutionSignatureQr` / `showAdjustmentSignatureQr` dans `storage.js` |
| `js/adjustment.js` | ajustement d'un dossier actif : fenêtre (retirer / ajouter — avec reprise de matériel restitué, `openAdjustmentReuseModal` / changer le service / signature), signature d'un ajustement en attente, historique ; chargé après `storage.js` (listes et fiche) |
| `adjustment-signature.html`, `js/adjustment-signature.js` | page publique de signature à distance d'un ajustement (lien + QR) |
| `js/ui.js` | composants partagés : `showToast`, `askConfirm`, dialogues de workflow (`askWorkflowDialog`), menu du compte |
| `js/branding.js` | version, logo, pied de page, pastille d'environnement |
| `js/admin*.js` | écrans d'administration |
| `css/style.css` | feuille unique (mode sombre via `[data-color-mode="dark"]`) |

Pages de liste : `index.html` (attributions en cours), `assignments-completed.html`, `restitutions-pending.html`,
`restitutions-completed.html`.

### Tests (`tests/`)

- `python -m pytest tests -q` : suite complète (~2 min).
- `RUN_BROWSER_TESTS=1 python -m pytest tests -q` : avec navigateur (~5 à 8 min).
- `python tests/browser/check_<nom>.py` : scénarios navigateur isolés (serveur temporaire, base vierge, port 5055) ;
  `tests/browser/browser_harness.py` (`Instance(copy_db=...)` pour travailler sur une **copie** d'une base).
- Scénarios HTTP : `tests/_http_scenarios.py`, lus par `tests/test_http_endpoints.py`.

## 4. Notions à connaître avant de modifier

- **Un dossier est la source de vérité** (`dotation_forms.payload_json`). Parc, stock et éléments sont des projections
  recalculées par `persist_form`. Tout enregistrement de dossier passe par là (voir `docs/ARCHITECTURE_DONNEES.md`).
- **Statuts** (`models/vocab.py`) : `draft`, `partial_assignment`, `awaiting_signature`, `active`, `partial_return`,
  `returned`, `cancelled`. Un dossier « en restitution » est `partial_return` dès l'enregistrement de la Phase 1.
- **Types de dossier** : `arrivee`, `mise_a_jour` (ancien type, retiré du sélecteur de création depuis 3.65.0 — voir
  **ajustement** ci-dessous), `changement_service`, `sortie` (dont la **régularisation** : restitution d'une personne
  sans attribution enregistrée).
- **Ajustement d'un dossier actif** (`models/adjustment.py`, `PATCH /api/forms/<id>/ajustement`) : ajouter/retirer des
  ressources ou changer le service **sans créer un nouveau dossier** — le dossier reste `active`, chaque geste a sa
  propre signature. « Nouvelle attribution pour cette personne » ne doit plus être utilisée sur un dossier actif (menu
  masqué depuis 3.67.2) : c'est justement le cas qui créait des doublons.
- **Regroupement par personne** (`groupDraftsByPerson`, `storage.js`) : les 4 tableaux de bord n'affichent qu'une ligne
  par personne (fusion par `personId` **et** par identité nom+prénom+service, en secours pour les dossiers créés avant
  qu'une action ne reprenne le `personId`). Les dossiers restent des documents distincts et immuables ; seul
  l'affichage fusionne. Pour qu'un nouveau dossier reste bien rattaché à la même personne, reprendre son `personId`
  via le champ caché `#retraitsSourcePersonId` (déjà fait pour « mise à jour », « nouvelle attribution » et
  « changement de service »).
- **Portée des données** : un groupe `data_scope = "masked"` (RGPD) voit des données masquées et **ne peut générer aucun
  PDF ni export**, même avec `forms.export`. Serveur : `can_export_unmasked()` (`routes/forms.py`). Navigateur :
  `canExportUnmasked(user)` (`storage.js`). Garder les deux alignés.
- **Permissions** : `forms.create`, `forms.edit`, `forms.delete`, `forms.export`, `forms.restitution`,
  `forms.adjust`, `forms.read_list`, `forms.read_detail`, `forms.view_all`, `parc.manage`, `unc.view_all`, `users.manage`, `db.manage`
  (`permissions.py`).
- **Signatures** : jamais exposées sans authentification ; affichage protégé par mot de passe.
- **E-mails** : l'application ne les envoie pas ; elle prépare un fichier `.eml` que l'utilisateur ouvre dans sa
  messagerie (fonctions `prepare*Email` de `storage.js`).
- **Préférence d'interface** : éviter le HTML dupliqué ou codé en dur ; décrire les éléments répétés par des objets
  JavaScript et les générer (ex. `DASHBOARD_COLUMNS`, `REGULARISATION_FIELDS`, listes `actions` des barres de boutons).

## 5. Règles de travail (validées par le propriétaire du dépôt)

1. Travailler sur la branche **`dev`**. Promotion `dev` → `preprod` → `prod` **par Pull Request** ; le propriétaire
   fusionne lui-même. La production se déploie depuis la branche **`prod`** (pas `main`).
2. **Ne jamais utiliser `git add -A` ni `git add .`** : ajouter les fichiers un par un. Une base de production a déjà été
   publiée par erreur (le dépôt est public). Ne jamais committer de base (`*.db`), de journal ni de secret.
3. **Demander avant de changer le numéro de version** (`branding.js`, entête du `README.md`, `CHANGELOG.md`).
   Correctif = x.y.**Z**, fonctionnalité = x.**Y**.0.
4. Commits **en français**, un commit par lot cohérent, message qui dit ce qui change et pourquoi.
5. Présenter un plan et attendre l'accord avant une fonctionnalité qui touche plus de 3 fichiers.
6. La base locale (`http://127.0.0.1:5000`, `backend/dotation.db`) est **une copie de la production** : ne pas la
   nettoyer ni la modifier pour tester ; utiliser `browser_harness.Instance(copy_db=...)` ou une base vierge.
7. Vérifier dans un vrai navigateur ce qui touche l'interface, pas seulement les tests.
8. Le dossier `scripts/` est ignoré par git : les outils versionnés vont dans `tools/`.
9. Tenir à jour `CHANGELOG.md` et `docs/BACKLOG_PRODUIT.md` à chaque lot livré.

## 6. Lancer l'application en local

```
cd backend && python app.py        # http://127.0.0.1:5000 ; relancer après toute modification du serveur
```

Les fichiers du navigateur sont lus directement depuis `frontend/` (un simple rechargement suffit).
Variables utiles : `APP_DATA_DIR`, `APP_LOG_LEVEL`, `APP_DEBUG_ENDPOINTS=1`, `APP_HEALTH_INTERVAL_HOURS=0`,
`APP_UPDATE_CHECK=0` (détail : `README.md`, section « Variables d'environnement »). Journal : `<APP_DATA_DIR>/logs/aquai.log`.

## 7. Pièges déjà rencontrés

- `storage.js` est aussi chargé par `form.html` et les deux écrans de restitution. Ceux-ci redéclarent `requestJson`,
  `getDraftById` et `escapeHtml` : la version **chargée en dernier** l'emporte pour toute la page.
- Tout ce qui dépend d'un élément présent seulement sur les listes (ex. `#exportLoader`) doit tolérer son absence.
- Le cadre des listes (`.content-card`) a un `backdrop-filter` : un élément en `position: fixed` placé dedans reste
  piégé dans le cadre. Le menu « ⋯ » est donc rattaché au `<body>` quand il est ouvert (`placeActionMenuPanel`).
- Dans les dialogues `askWorkflowDialog`, un clic hors de la fenêtre renvoie `"secondary"` : ne jamais mettre une
  action à effet (envoi, suppression) sur le bouton secondaire.
- Flask : impossible d'ajouter une route après la première requête ; relancer le serveur après une modification.
- GitHub : l'outil `gh` n'est pas installé sur le poste de développement ; les PR sont ouvertes par le navigateur.
- **Cache-busting incomplet** (trouvé le 28/09) : `admin.js` et `app.js` n'avaient *aucun* `?v=...` sur leurs pages,
  `adjustment.js` était resté sur une version périmée. Un navigateur déjà ouvert peut exécuter du code obsolète
  indéfiniment, même après un rechargement simple (F5) — seul un rechargement forcé (Ctrl+F5) ou la navigation privée
  le contourne à coup sûr. **Toujours vérifier que le `?v=` a bien été mis à jour sur CHAQUE page qui charge le
  fichier modifié**, pas seulement celle qu'on teste.
- **Régularisation et unité de parc bloquée** (`models/units.py`, `derive_state`) : un dossier de régularisation
  (`assigned_at` rétrodaté avant la création réelle du brouillon) peut produire un événement `reserved` daté *après*
  son `assigned`. `derive_state` traite les événements triés par date : sans `_FORM_RELATIONSHIP_SETTLED`, la
  réservation de ce dossier n'était jamais levée et l'unité restait affichée « réservée » pour toujours, même après
  restitution (corrigé en 3.66.1, migration 8 pour rattraper l'existant).
