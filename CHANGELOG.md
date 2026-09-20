# Historique des versions — À Quai

## [Non publié : proposé 3.50.1]

### 🐛 Correctifs
- **Personnalisation : modifier uniquement le « Seuil d'alerte pilotage » (ou le délai de la phase 1, ou la conservation de l'historique du parc) n'enregistrait rien** : la page répondait « Aucune modification à enregistrer » (message affiché en haut, loin du bouton). Les trois réglages numériques sont désormais pris en compte, et le message « aucune modification » défile jusqu'à l'écran.
- Tests ajoutés : `tests/browser/check_personnalisation.py` (chaque champ de Personnalisation modifié seul, avec sauvegarde et remise en état des réglages quand il vise un serveur local), `tests/browser/check_admin_saves.py` (comptes, services, profil) et, côté serveur, le lien entre le seuil et l'état « En danger » des dossiers (la page Synthèse, elle, garde ses propres seuils).

## [3.50.0] - 2026-09-19

Chantier « Assistant d'organisation » : configuration de démarrage rejouable, adaptée à toute structure (y compris hors France : libellés dans toutes les langues, type « Autre / sur mesure », toutes les suggestions modifiables).

### 🧭 Assistant d'organisation (Administration > Personnalisation)
- **5 étapes** : type d'organisation, bénéficiaires, ressources à activer, réglages de départ, récapitulatif avec **aperçu exact** de ce qui sera modifié et confirmation.
- **Suggestions par type d'organisation** (collectivité, administration, entreprise, association, autre) : types de bénéficiaires, ressources recommandées, conservation. Ressources supplémentaires par modèle (vêtement, stock, accès…) ou **sur mesure**.
- **Ajout seulement** : rien de ce qui est utilisé n'est supprimé ni renommé ; une ressource déjà utilisée ne peut pas être masquée ; un type de bénéficiaire porté par des dossiers ne peut pas disparaître (seul son libellé change) ; une ressource équivalente existante n'est jamais recréée ; rejouer l'assistant sans rien changer ne fait rien.
- **Sécurité** : le serveur calcule le plan (`plan_org_wizard`) et n'applique que le plan aperçu (empreinte vérifiée) ; copie de sécurité de la base avant application ; une seule transaction ; entrée au journal d'audit ; droit `users.manage`, limitation de fréquence. API : `GET /api/admin/org-presets`, `POST /api/admin/org-wizard/preview` et `/apply`.
- **Checklist de démarrage** sur le portail admin (avancement calculé sur l'état réel : nom, assistant passé, ressources, DPO, sauvegarde automatique, support, domaines e-mail) ; l'installation initiale débouche sur l'assistant.

### 🧭 Navigation cohérente, moins de clics
- **Menu du compte identique sur toutes les pages**, généré par `ui.js` : Administration, Synthèse, Parc matériel et Base de données (selon les droits) puis Mon profil, Mode sombre, Changer le mot de passe, Aide générale, Déconnexion. Corrige les pages où « Administration » ou « Synthèse » manquaient (journal, corbeille, aide…).
- **Navigation d'administration commune** (`admin-nav.js`) : menu latéral groupé (Utilisateurs, Organisation, Apparence, Exploitation) identique sur toutes les sous-pages, ajouté au journal et à la corbeille ; page courante marquée ; **fil d'Ariane** Accueil › Administration › Page ; l'assistant d'organisation est accessible en un clic. Passer d'une sous-page à une autre : 1 clic au lieu de 2 ou 3.
- **Palette Ctrl+K étendue** : en plus des dossiers, on y trouve les **pages et actions** (Nouvelle attribution, Administration, Créer un compte, Ajouter une ressource, Assistant d'organisation, Sauvegarder maintenant, Restaurer une sauvegarde, Journal, Corbeille, Mon profil, Aide…), filtrées par droits, insensibles aux accents, avec des raccourcis dès l'ouverture. Ce sont de simples liens : aucune action sensible ne s'exécute depuis la palette. Toute tâche courante : 2 actions au clavier (Ctrl+K puis Entrée).
- **Portail d'administration regroupé** en trois sections identiques au menu latéral (Comptes et droits, Votre organisation, Suivi et exploitation), avec l'assistant d'organisation, le Parc, la Base de données, le Journal, la Corbeille et la Synthèse en cartes.
- **Personnalisation** : le bouton « Enregistrer la personnalisation », qui enregistre toute la page, n'est plus au milieu (sous la section Contact) mais dans une barre fixée en bas, toujours visible.
- **Mode sombre** : correction du menu latéral d'administration (titres blancs sur fond clair, illisibles) et du fil d'Ariane ; la liste de la palette Ctrl+K n'est plus écrasée par les filtres.
- **Comptes et droits en français simple** : chaque groupe est expliqué en une phrase, avec la liste de ce qu'il peut faire et de ce qu'il ne peut pas faire (fini les noms techniques comme `forms.read_list`) ; nouveau tableau « Qui peut faire quoi ? » qui compare tous les groupes ; formulaires reformulés (mot de passe, sauvegardes, accès réseau).
- Accessibilité : focus clavier visible, cibles de 44 px, onglets défilants sur mobile.

### 🔒 Sprint 1 : sécurité des réglages

### 🔒 Sécurité et robustesse des réglages
- Une mise à jour **partielle** des réglages n'efface plus les champs non envoyés (une valeur absente est conservée ; une chaîne vide vide bien le réglage). Les durées (restitution, alerte, conservation) ne se remettent plus à leur défaut quand elles sont absentes.
- **Types de bénéficiaires validés** côté serveur : identifiant `a-z 0-9 _ -`, libellé libre dans toutes les langues sauf la virgule, les deux-points, le point-virgule, `<`, `>`, `&`, les guillemets et l'antislash, doublons refusés, plus de retour silencieux sur Agent/Élu ; erreur 400 explicite.
- Textes de réglages limités à 200 caractères.
- L'**installation ne se rejoue plus** par mégarde : une fois terminée, `/api/setup/complete` répond 409 sauf confirmation explicite (`confirm_reconfigure`), tracée au journal.

## [3.49.1] - 2026-09-19

### 🗃️ Parc matériel
- Indicateurs simplifiés : « Objets dégradés » (nombre d'objets actuellement dégradés) remplace le pourcentage de restitutions dégradées, souvent trompeur sur un petit parc ; retrait de la durée moyenne de détention et des détentions de plus d'un an ; six cartes sur deux lignes de trois.
- Formulaire de dossier : rappel sous le champ identifiant — pour renuméroter un objet suivi, passer d'abord par Parc → Corriger l'identifiant afin d'éviter un doublon.

### 🎨 Interface
- Logo À Quai recadré sur son contenu (`a-quai-logo.png`) : il n'a plus de marge blanche et remplit son cadre dans les en-têtes.

## [3.49.0] - 2026-09-19

Cumul des versions 3.19 à 3.49 depuis la 3.18.3.

### 🗃️ Parc matériel et stocks
- **Assistant de création de ressource** en 5 étapes (mode de suivi, modèle, identité, champs, récapitulatif avec aperçu en direct) et écran « Qualité du catalogue ».
- **Suivi par objet** : historique de vie de chaque objet (attribué, restitué, dégradé, perdu, retrouvé, réparation, réformé, transféré), page *Parc matériel* avec frise chronologique, correction d'identifiant, fusion de doublons, réservation d'un objet choisi dans un brouillon (libérée après 30 jours), import CSV du parc initial, indicateurs.
- **Suivi par quantité** : stock par taille alimenté par les dossiers signés, réception / ajustement / perte, seuil d'alerte « Stock bas », historique des mouvements.
- Reprise d'un matériel déjà restitué dans le formulaire, avertissement de doublon de numéro de série.
- RGPD : anonymisation des anciens détenteurs après une durée réglable (5 ans par défaut). Nouveau droit `parc.manage`.

### 💾 Sauvegardes (Administration > Base de données)
- Sauvegarde multi-bases en une archive, **chiffrement par mot de passe** (AES-256-GCM), analyse avant restauration.
- Destinations réseau (partages SMB/NFS montés), test d'accès, envoi manuel, historique.
- **Sauvegarde automatique** planifiée (fréquence, jour, heure, rétention, alertes, script `backup_cli`).

### 👤 Comptes
- Adresse e-mail facultative, nom et prénom, page **Mon profil** (identifiant figé).

### ✍️ Signature et restitution
- « Enregistrer » séparé de la génération du lien de signature à distance, qui se fait depuis le tableau de bord.
- Restitution d'une personne **sans attribution enregistrée** (régularisation).
- Pages de signature publiques : plus d'informations internes (version, pied de page, pastille DEV).

### 🖥️ Interface
- Attributions et restitutions séparées, onglets à compteurs, tableaux compacts, actions de ligne + menu « Plus », actions groupées, édition des services et ressources en modale, tri par clic sur les en-têtes, raccourcis clavier, cibles tactiles de 44 px.
- Audit d'accessibilité outillé (axe-core) : correctifs sur ~18 pages.
- Seuil « En danger » configurable (Administration > Personnalisation).

### 🔒 Sécurité (audit du 19/09, voir `docs/AUDIT_SECURITE_2026-09.md`)
- **Limitation des tentatives de connexion non contournable** (elle reposait sur l'en-tête `X-Forwarded-For`, falsifiable) ; confiance dans les proxys **automatique** (`backend/proxy.py`).
- Exports refusés aux groupes à portée « masquée » ; alertes du tableau de bord masquées.
- Échappement HTML de données saisies, URL du logo limitée à http(s), plafond de taille des requêtes (`APP_MAX_UPLOAD_MB`), liste blanche de colonnes sur les comptes.

### 🚀 Déploiement
- `deploy.sh` (production, branche `prod` figée) et `deploy-dev.sh` (branche `dev`) : sauvegarde, code, dépendances dans le venv du service, redémarrage et **vérification que l'application répond**. Logique commune dans `setup/deploy-common.sh`.
- **Nouvelle version disponible** : bandeau dans l'administration (vérification toutes les 6 h, silencieuse sans Internet, désactivable).
- **Mise à jour depuis le navigateur** (facultative, désactivée par défaut) : l'application dépose une demande, une unité systemd lance le script en root (`setup/install-web-update.sh`) ; mot de passe exigé, journal d'audit, suivi de progression.
- **Retour arrière automatique** du code et des bases si la nouvelle version ne répond pas ; verrou contre les lancements simultanés.
- **Préproduction** : script `deploy-preprod.sh` (branche `preprod` figée), pastille **PREPROD** (version `-preprod`), et canal de mise à jour dédié.
- `cryptography` est importée à la demande : sans elle, l'application démarre (seules les sauvegardes chiffrées sont indisponibles).
- **Première mise à jour depuis une ancienne version : voir le README** (deux passages de `deploy.sh`, sauvegarde préalable).

## [3.18.3] - 2026-05-06

### 🐛 Bugfixes

#### Permissions manquantes dans les groupes
- **Problème** : Le groupe admin manquait permissions critiques (forms.delete, forms.edit, forms.restitution)
- **Cause** : Les groupes n'avaient pas toutes les permissions requises par les routes
- **Solution** : Audit complet + correction des permissions manquantes
- **Impact** : Admin et autres groupes (gestion, redaction) ont maintenant les bonnes permissions
- **Commit** : `0702f80`

#### Dossiers invisibles pour certains utilisateurs
- **Problème** : Les utilisateurs ne voyaient aucun dossier même avec les bonnes permissions
- **Cause** : Permissions `forms.read_list` et `forms.read_detail` manquantes
- **Solution** : Ajout de ces permissions à tous les groupes
- **Commit** : `00d7c87`

#### Visibilité inter-services
- **Problème** : Les utilisateurs de certains groupes ne voyaient pas les dossiers des autres services
- **Cause** : Permission `forms.view_all` manquante
- **Solution** : Ajout de `forms.view_all` à tous les groupes
- **Commit** : `a88fbc7`

### ✅ Validations

- ✅ Tous les dossiers visibles pour les administrateurs
- ✅ Permissions cohérentes entre groupes
- ✅ Routes critiques accessibles avec les bonnes permissions
- ✅ Audit complet des permissions effectué

---

## [3.18.2] - 2026-05-06

### 🐛 Bugfixes

#### Installation script — Permissions post-initialisation
- **Problème** : Le service ne démarrait pas avec l'erreur "Worker failed to boot"
- **Cause** : Les fichiers créés par `init_db()` (dotation.db, users.db, .app_secret_key) avaient les permissions root, empêchant www-data de les lire
- **Solution** : Ajouter une étape de correction des permissions immédiatement après l'initialisation de la base de données
- **Commit** : `e06b0cf`

### 📝 Modifications techniques

**Fichiers modifiés :**
- `setup/install-debian.sh` — Correction des permissions post-initialisation

### ✅ Validations

- ✅ Service démarre correctement après installation
- ✅ www-data a les permissions nécessaires pour lire/écrire les bases de données
- ✅ L'application Flask démarre sans erreur

---

## [3.18.1] - 2026-05-06

### 🐛 Bugfixes

#### Cases décochées non sauvegardées
- **Problème** : Les cases d'équipement décochées (Badge, Veste, etc.) reviendraient cochées après rechargement du dossier
- **Cause** : La fonction `extract_items()` ignorait complètement les items avec `selected: false`
- **Solution** : Modifier `extract_items()` pour persister TOUS les items avec leur état réel (`assigned: true/false`)
- **Commits** : `fe26203`, `3e6af34`, `b11f423`

#### Dossiers finalisés dégradés au redémarrage
- **Problème** : Après un redémarrage du service, les dossiers finalisés revenaient en "attribution en cours"
- **Cause** : La fonction de calcul de progression comptait TOUS les items au lieu de seulement ceux assignés
- **Solution** : Filtrer les items non assignés dans `summarize_assignment_progress()`
- **Commit** : `3e6af34`

#### Items décochés affichés dans les PDF
- **Problème** : Les PDFs de restitution affichaient les items décochés
- **Solution** : Ajouter un filtre pour exclure les items avec `assigned: false` du PDF
- **Commit** : `b11f423`

### 📝 Modifications techniques

**Fichiers modifiés :**
- `backend/models/workflow.py` — `extract_items()` et `summarize_assignment_progress()`
- `backend/pdf/restitution.py` — Filtrage des items assignés
- `frontend/js/branding.js` — Version 3.18.1-prod
- `tests/test_extract_items_fix.py` — Test unitaire pour les checkboxes

**Base de données :**
- Aucune migration requise
- Les items non assignés sont maintenant persistés avec `assigned = 0`

### ✅ Validations

- ✅ Checkboxes décochées se sauvegardent et se restituent correctement
- ✅ Les dossiers finalisés gardent leur statut après redémarrage
- ✅ Les PDFs n'affichent que les items assignés
- ✅ Tous les tests unitaires passent (3/3)
- ✅ Rétro-compatibilité : aucun changement API

---

## [3.18.0] - 2026-05-06

### ✨ Nouvelles fonctionnalités

#### Navigation restitution 5 onglets
- Phase 1 : Dates de restitution
- Phase 2 : État du matériel
- Signature électronique
- Vue récapitulative
- Archivage et audit

### 🔒 Sécurité

#### Signatures cachées avec authentification
- Les signatures sont maintenant protégées par authentification
- Auto-découverte des blueprints Flask
- Endpoints de signature sécurisés (dossiers + restitutions)

### 🐛 Bugfixes

- Correction des migrations SQLite avec idempotence garantie
- Fix: améliorer install-windows.ps1 avec vérifications robustes
- Fix: corriger install-debian.sh selon rapport de test

### 📚 Documentation

- Ajouter guide prochaines étapes pour validation tests installation
- Ajouter plans de test et synthèse améliorations installation

---

## [3.17.1] - 2026-04-20

### ✨ Améliorations UX

- Restitution Phase 1/Phase 2 split avec sécurité audit
- Amélioration du header de navigation
- Correctifs d'affichage et de responsivité

---

## [3.14.0] - 2026-03-15

### ✨ Nouvelles fonctionnalités

- Multi-sélection (Phases 1-4 complètes)
- Navigation 5 onglets pour restitutions
- Support ressources immatérielles
- Signatures protégées par authentification

---

## Politique de versionnement

À Quai suit [Semantic Versioning](https://semver.org/) :

- **MAJOR** (3.x.0) : Changements API ou fonctionnalités majeures
- **MINOR** (3.18.x) : Nouvelles fonctionnalités rétro-compatibles
- **PATCH** (3.18.1) : Bugfixes et corrections

### Suffixes de version

- `-dev` : Branche développement
- `-prod` : Release production

---

## Comment mettre à jour

### Debian / LXC (Automated)

```bash
cd /opt/dotation
git fetch origin
git checkout preprod
git pull origin preprod
sudo systemctl restart dotation
sudo systemctl status dotation
```

### Windows (Manual)

```powershell
cd C:\dotation
git fetch origin
git checkout preprod
git pull origin preprod
# Redémarrer l'application
```

---

## Support et signalements de bugs

Pour signaler un bug ou une suggestion :
1. Vérifiez le [CHANGELOG](CHANGELOG.md) (peut déjà être fixé)
2. Consultez les [Issues GitHub](https://github.com/roussim974100/dotation/issues)
3. Créez une nouvelle issue avec les détails du problème

---

**Dernière mise à jour :** 06 mai 2026
