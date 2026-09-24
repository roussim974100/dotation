# Historique des versions — À Quai

## [3.62.0] - 2026-09-24

### ✉️ E-mails depuis les écrans de restitution
- **Phase 1** : à la validation (« Valider et transmettre aux services »), l'application propose de préparer un e-mail informant la personne de la restitution (« Préparer l'e-mail » / « Plus tard »).
- **Phase 2** (et Phase 1 en consultation) : boutons « Télécharger le PDF » et « Envoyer par e-mail » dans la barre du bas, comme sur une attribution signée. L'e-mail joint le PDF de restitution ; sans droit d'export, c'est l'e-mail d'information (sans PDF) qui est préparé.
- **Après « Enregistrer la restitution »** : l'envoi par e-mail est proposé (« Envoyer par e-mail » / « Terminer ») ; un clic hors de la fenêtre vaut « Terminer ».
- Les deux écrans chargent désormais `storage.js`, qui porte déjà les fonctions d'e-mail et de PDF du tableau de bord (aucune duplication).

### 🐛 Correctif
- **Export PDF hors des listes** : `showExportLoader` supposait la présence du chargeur d'export, qui n'existe que sur les listes. Hors de celles-ci (fiche d'attribution, écrans de restitution), l'export échouait avant même d'appeler le serveur — ce qui cassait aussi « Télécharger le PDF » / « Envoyer par e-mail » sur la fiche d'une attribution signée. L'export fonctionne maintenant sans chargeur.

### 🧪 Tests
- `tests/browser/check_restitution_email.py` : parcours réel Phase 1 → Phase 2 → enregistrement, e-mail avec PDF depuis la fiche d'attribution, absence d'envoi sur clic hors fenêtre.

## [3.61.0] - 2026-09-23

Première étape du chantier « ajuster les ressources d'un dossier déjà actif » (plan cadré avec 3 experts — process métier, base de données, architecture — voir `docs` et la mémoire du projet).

### 🧩 Identifiant de personne stable
- Nouvelle colonne `dotation_forms.person_id`, indexée : elle ne fait qu'exposer une valeur déjà calculée à chaque enregistrement (`meta.personId`), jamais devinée ni fusionnée. Migration 5, appliquée sans incident sur la copie de production (34 dossiers, 47 fiches « personne » existantes — la duplication déjà présente est désormais visible et interrogeable, pas encore corrigée : ce sera un chantier à part, optionnel).
- **Le formulaire « Mise à jour de ressources » transmet maintenant l'identité de la personne du dossier source** : rechercher et choisir un dossier existant relie le nouveau dossier à la **même** fiche « personne » au lieu d'en créer une nouvelle à chaque mise à jour. Un dossier sans rapport (nouvelle arrivée) continue de créer sa propre fiche, normalement.

### 🧪 Tests
- `tests/test_person_id_migration.py` (backfill, idempotence, tolérance à un schéma minimal), scénario HTTP (même personne entre un dossier et sa mise à jour, personne différente pour un dossier sans rapport), `tests/browser/check_person_id.py` (parcours réel : recherche, transmission, bouton « Changer »).

## [3.60.2] - 2026-09-23

### 🐛 Correctif
- **Limiteur de tentatives de connexion : la limite globale pouvait être dépassée sous forte charge concurrente.** `rate_store.hit()` compte les tentatives dans une base partagée entre les processus (verrou d'écriture SQLite) ; si ce verrou échouait momentanément à cause d'un afflux de connexions simultanées, le code basculait silencieusement sur un compteur propre à chaque processus, qui ne voit pas les tentatives déjà comptées ailleurs — la limite pouvait alors être dépassée précisément quand elle sert le plus. Découvert lors du tout premier passage réel de la CI GitHub Actions (`.github/workflows/tests.yml`), jamais exécutée jusqu'ici.
- Corrigé en réessayant quelques fois le verrou d'écriture (quelques dixièmes de seconde au total) avant de considérer la base réellement indisponible ; le repli en mémoire reste en place pour les vraies pannes (disque plein, verrou prolongé).
- Vérifié par une charge plus forte que le test existant (8 processus × 10 tentatives) : comptage exact à chaque essai.

## [3.60.1] - 2026-09-23

### 🐛 Correctif
- **Retrait de ressource via un dossier « mise à jour » : le parc et le stock du dossier d'origine n'étaient jamais resynchronisés.** L'objet ou la quantité rendus restaient affichés comme toujours détenus dans Parc/Stock alors que le dossier disait « restitué ». `_apply_retraits_to_source` modifiait le dossier source directement, en dehors du chemin habituel (`persist_form`), sans jamais appeler la resynchronisation du parc (`sync_units_for_form`) ni du stock (`sync_stock_for_form`) sur ce dossier. Corrigé en appelant les deux, avec la même garde qu'ailleurs dans le projet : une resynchronisation impossible ne doit jamais empêcher l'enregistrement.
- Test ajouté (`tests/_http_scenarios.py`, `test_retrait_via_mise_a_jour_resynchronise_le_parc_du_dossier_source`) : un objet suivi par numéro de série redevient bien « disponible » après un retrait via ce mécanisme.

## [3.60.0] - 2026-09-20

Performance mesurée et sûreté des mises à jour / restaurations (`tools/load_test.py` : base synthétique de 3 000 dossiers).

### ⚡ Performance (mesurée)
- **Démarrage : 38 s → 1 s** et **contrôle de santé : 22 s → 0,3 s** sur 3 000 dossiers. Causes : une requête par ressource sur une table sans index (comparaison écart dossier / copie à plat) et un contrôle de santé synchrone au démarrage (désormais en arrière-plan uniquement).
- **Migration 4 : index de performance** sur les colonnes de jointure et de tri (éléments de dossier, statut/date des dossiers, mouvements de stock, parc, journal). Additive et idempotente.
- Limite connue, mesurée : l'affichage de la liste de tous les dossiers demande environ 1,7 ms par dossier (5 s pour 3 000, 6 Mo) ; sans effet à l'échelle d'usage habituelle (quelques dizaines à quelques centaines).

### 🛡️ Mises à jour et restaurations
- **Une migration en échec est annulée proprement** (point de sauvegarde SQLite : aucune modification partielle), consignée, retentée au démarrage suivant ; l'application démarre quand même et les migrations suivantes ne sont pas tentées.
- **Restauration tout-ou-rien** : si le remplacement d'une base échoue, celles déjà remplacées retrouvent leur état d'avant.
- **Restauration refusée** pour une base d'une version plus récente de l'application, ou une base de comptes vide (personne ne pourrait se connecter).
- **Déploiement** : les fichiers de base que le script root fait apparaître (journaux, copies) gardent le propriétaire du service ; attente de santé portée à 60 essais avec délai maximal par requête ; sauvegarde de `dotation.db` obligatoire avant toute modification.

### 🧪 Tests
- Migration en échec, index, restauration tout-ou-rien, refus de restauration, batterie de charge reproductible.

## [3.59.0] - 2026-09-20

Ressources personnalisées saines quel que soit leur schéma (pré-mortem du 20/09).

### 🧩 Rôles de champs explicites
- Chaque champ peut avoir un **rôle** dans le suivi : *identifiant de l'objet*, *quantité* (stock) ou *variante* (taille, pointure…), choisi dans l'éditeur de champs. Un seul champ par rôle. Avant, le stock et le parc devinaient ces champs d'après leur **nom** (« quantite », « taille »…) : une ressource dont le champ s'appelait « Nombre de pièces » ou « Qté » comptait 1 par remise, en silence.
- **Migration numéro 3** : pour les ressources existantes, le rôle actuellement déduit des noms est écrit explicitement (le comportement ne change pas), puis ne dépend plus des noms : renommer un champ ne fausse plus les stocks.
- **Stock** : la variante d'un article est celle de la **remise** ; un changement de taille après signature ne fausse plus les soldes par taille.

### 🩺 Contrôle de santé enrichi
- Invariants des stocks et du parc : soldes négatifs, mouvements ou objets d'une ressource inconnue, objets sans identifiant, ressource saisie sur plusieurs lignes dans un même dossier (risque de calcul de stock faussé). Ils apparaissent dans le contrôle général et dans le paquet de diagnostic.

### 🧪 Tests
- Batterie de propriétés : 200 descriptions de champs hostiles (unicode, emoji, doublons, types et rôles invalides, 200 champs…) sans erreur, normalisation idempotente, un seul champ par rôle ; 100 allers-retours du catalogue sans perte ni changement d'identifiant ; stock avec noms de champs libres ; migration des rôles (idempotente, schémas cassés tolérés) ; invariants de santé.

## [3.58.0] - 2026-09-20

Support à distance sans jamais recevoir la base d'un client.

### 🩺 Paquet de diagnostic (Administration > Base de données > Support technique)
- **Un clic, un zip** (`diagnostic.json` + `LISEZMOI.txt` + empreinte SHA-256), relisible avant envoi (aperçu du contenu), **rien n'est envoyé automatiquement**. Contenu : versions, migrations, schéma de la base et volumes, état de santé, structure des ressources (codes, clés techniques, types, drapeaux : jamais les libellés ni les options), statistiques d'usage sans valeur, paramètres non identifiants, système (espace disque, droits, fuseau), performances, derniers événements techniques.
- **Anonymisé par construction** : liste blanche de collecteurs + verrou final qui refuse de produire le paquet au moindre motif suspect (e-mail, chemin réseau, adresse IP, URL, chemin de fichier). Testé avec une base remplie de valeurs « sentinelles » (noms, e-mail, numéro de série, libellés, options, chemin UNC, nom de l'organisation) : aucune ne sort.
- **Base squelette** : `python tools/build_skeleton.py aquai_diagnostic.zip dossier` reconstruit une base synthétique (mêmes ressources, mêmes champs, volumes et anomalies comparables, données fictives) pour reproduire un problème chez soi.

### 🧭 Erreurs communicables
- Toute erreur inattendue renvoie un **code court et stable** (« E-4F2A9C », le même défaut donne le même code) et un identifiant de requête (`X-Request-ID`, accepte celui du proxy). Le client communique le code ; le journal fichier structuré (`logs/aquai.log`, rotation 5 × 5 Mo, niveau `APP_LOG_LEVEL`) ne contient que type d'exception, positions dans le code, route, statut et durée : jamais de valeur, de message brut ni de code source. Plus de message d'erreur brut renvoyé au navigateur sur l'export des retraits.

### 🧪 Tests
- Diagnostic sans donnée personnelle, verrou de sécurité, réservé aux administrateurs ; codes d'erreur (stabilité, absence de valeur, identifiant de requête invalide remplacé) ; base squelette reconstruite puis démarrée ; aperçu du paquet dans le navigateur.

## [3.57.0] - 2026-09-20

Pré-crise : l'application ne doit jamais être empêchée de démarrer ni de fonctionner par une donnée atypique chez un client (réunion de pré-mortem du 20/09).

### 🛡️ Démarrage et données
- **Un dossier ou une description de champs abîmés n'empêchent plus le démarrage** : JSON illisible, `null`, liste au lieu d'objet, droits de groupe illisibles sont ignorés et consignés au journal. Chaque correction de données historique s'exécute isolément : l'échec de l'une n'arrête ni l'application ni les suivantes.
- **Démarrage plus rapide et moins bloquant** : les dossiers ne sont réécrits que s'ils changent ; l'initialisation est verrouillée entre processus (plusieurs workers), attente des verrous SQLite portée à 30 s ; le contrôle de santé quotidien ne tourne que dans un seul worker.
- **Base plus récente que l'application refusée** avec un message clair (au lieu d'être abîmée par une version plus ancienne).
- **Copie de sécurité avant migration** : contrôle de l'espace disque, jamais bloquante (erreur consignée si impossible), purge automatique (5 copies conservées par famille).
- **Quantités illisibles** (« inf », « 1e999 ») : plus d'erreur, bornées.
- **Descriptions de champs hostiles** : libellé sans lettre latine (cyrillique, arabe, chinois, emoji) conservé avec une clé `champ_N` (avant : champ supprimé en silence) ; 60 champs, 120 caractères de libellé et 200 options maximum ; description mal formée = vide plutôt qu'erreur 500.
- **Routes `/api/debug/*` fermées** (404) sauf `APP_DEBUG_ENDPOINTS=1` ; la collecte de la console du navigateur n'est plus automatique en local (elle pouvait écrire des données personnelles dans des fichiers).

### 🧪 Tests
- `tests/test_startup_robustness.py` : démarrage sur base empoisonnée (dossiers illisibles, schémas `null`/objet, droits illisibles, migrations rejouées), refus d'une base du futur, quantités et schémas hostiles.

## [3.56.0] - 2026-09-20

Finitions du chantier « champs et personnalisation » (décisions D8, D11, D14, D15, D17).

### 🏷️ Types de bénéficiaires avec mandat
- Le type « élu » n'est plus câblé dans le code : un type porte un mandat s'il est déclaré avec `|mandat` (Personnalisation, ex. `conseiller:Conseiller municipal|mandat`). Le formulaire demande alors le mandat et l'affiche à la place du service (titre du dossier, synthèse par service, régularisation). Les bases existantes sont inchangées : sans drapeau, `elu` garde son mandat.

### 📦 Paramétrage exportable
- Administration > Base de données : **export du paramétrage** (réglages d'organisation, services, ressources et champs, sans aucun dossier ni donnée personnelle) et **import additif** avec aperçu : il crée ce qui manque, ne modifie jamais une ressource déjà présente, et peut être rejoué sans effet.

### 🩺 Contrôle quotidien
- Contrôle de santé de la base toutes les 24 h en arrière-plan (désactivable : `APP_HEALTH_INTERVAL_HOURS=0`), consigné au journal seulement en cas de point à examiner.

### 🧪 Tests
- Profil « données masquées » (écriture refusée, vrai nom jamais remplacé par une valeur masquée), rejeu de l'initialisation (`init_db`) sans effet sur le schéma ni les données, types à mandat en formulaire (`check_mandate_type.py`), export/import du paramétrage (`check_config_transfer.py`).

## [3.55.0] - 2026-09-20

### 🏷️ Vocabulaire configurable (décision D14 du comité, première étape)
- **Types de bénéficiaires** : tout type configuré dans Personnalisation est accepté par le serveur (avant, un dossier de régularisation ramenait tout type autre que « Élu » à « Agent ») et ses libellés sont utilisés dans les exports et PDF.
- **Libellés de statut** définis une seule fois côté serveur (`models/vocab.py`) et publiés au navigateur (`statusLabels` dans `/api/settings/public`) ; le tableau de bord les utilise (la liste locale ne sert plus que de secours).
- Reste à faire (chantier suivant) : le type « élu » (mandat) est encore traité à part dans le code ; les autres copies des libellés de statut dans les pages JS seront branchées progressivement.

## [3.54.0] - 2026-09-20

### 💾 Export / import de la base (décision D12 du comité)
- **Export** : copie cohérente par l'API de sauvegarde SQLite (lire le fichier brut d'une base en mode WAL pouvait omettre les écritures récentes).
- **Import** : copie de sécurité cohérente avant, puis remplacement **en place** (plus de fichier déplacé sous une base ouverte, plus de journal WAL ancien rejoué sur la nouvelle base).
- **Remise à niveau immédiate après restauration** (import simple ou archive chiffrée) : tables, colonnes et migrations numérotées sont rejouées tout de suite, sans attendre un redémarrage. Testé avec une base « ancienne » sans table de migrations ni identifiants de champs.

## [3.53.0] - 2026-09-20

Fondations (décisions D9 à D11 et D15 du comité).

### 🧱 Identifiant de champ immuable
- Chaque champ d'une ressource a un **identifiant interne** (`id`) indépendant de sa clé et de son libellé : attribué automatiquement aux champs existants (migration), conservé aux sauvegardes, **hérité** quand la clé change. Un dossier est relu par cet identifiant en priorité (correspondance certaine, même si le libellé a changé), puis par libellé, puis en dernier recours par ressemblance de noms.

### 🗂️ Migrations numérotées
- Table `schema_migrations` + `PRAGMA user_version` : chaque migration est appliquée une fois, dans l'ordre, avec une **copie de sécurité de la base avant** (API de sauvegarde SQLite, fiable en mode WAL) dès que la base contient des dossiers.

### 🩺 Contrôle de santé
- `GET /api/admin/health` et bouton « Contrôle général de la base » (Administration > Base de données) : intégrité SQLite, références cassées, version des migrations, valeurs de champs orphelines, écarts entre un dossier et sa copie à plat. Contrôle aussi fait au démarrage (avertissement au journal).
- Intégration continue GitHub Actions : la suite de tests tourne à chaque push et pull request.

## [3.52.0] - 2026-09-20

Suite du chantier « fiabiliser l'édition » (décisions D5 à D8 et D13 du comité, `docs/audit/DECISIONS_COMITE.md`).

### 🛡️ Fiabilité
- **Deux personnes ou deux onglets sur le même dossier** : le serveur refuse d'enregistrer une version périmée (`form_conflict`, HTTP 409) avec un message clair, au lieu d'écraser en silence le travail de l'autre.
- **Ressource désactivée ou retirée du catalogue** : ses valeurs restent dans les dossiers déjà saisis au lieu de disparaître au premier enregistrement.
- **Suppression d'une ressource utilisée par des dossiers refusée** (`resource_in_use`) : il faut la désactiver.
- **Profils « données masquées »** : ne peuvent plus enregistrer un dossier (ils renverraient les valeurs masquées à la place des vraies).

### 🧩 Éditeur de champs (Administration > Ressources)
- Types **« Liste de valeurs »** et **« Adresse e-mail avec domaine »** disponibles ; ils ne repassent plus en « Texte » à l'enregistrement.
- Aide à la saisie et anciens noms (alias) des champs conservés à l'aller-retour de l'éditeur.

### 🔐 Sécurité des exports
- Cellules qui ressemblent à une formule (`=`, `+`, `-`, `@`) neutralisées dans les exports CSV (accès UNC, services) ; guillemets et séparateurs protégés.
- Chemin du fichier du manifeste de sauvegarde réduit à un nom simple (plus de traversée de répertoire).

### 🧪 Tests
- `tests/browser/check_editor_and_lock.py` (éditeur, ressource hors catalogue, deux onglets, bouton Enregistrer sans faux conflit), verrou optimiste, suppression de ressource, CSV.

## [3.51.0] - 2026-09-20

Chantier « ne plus jamais perdre une valeur de champ » (audit et comité du 20/09 : `docs/audit/`).

### 🛡️ Données de dossiers
- **Le formulaire n'efface plus les valeurs qu'il ne reconnaît pas** : toute valeur dont le nom de champ n'existe plus dans le catalogue est affichée dans « Autres informations enregistrées » et renvoyée telle quelle à l'enregistrement (avant, elle disparaissait au premier enregistrement).
- **Correspondance exacte** : chaque dossier embarque la description de ses champs ; un champ actuel est rattaché à l'ancien champ de **même libellé**, sans deviner. La ressemblance de noms ne sert plus qu'en dernier recours.
- **Alias de champ** : quand la clé d'un champ change, l'ancienne devient un alias (libellé identique uniquement, jamais « par position ») ; les alias sont conservés aux sauvegardes suivantes.
- **Clés de champ** : une clé déjà valide est gardée telle quelle (fin de la mise en minuscules qui faisait dériver `numeroSerie`) ; un seul générateur de clés côté Python et JS.
- **Suggestions de saisie** pilotées aussi par le réglage « suggérer » des champs des ressources personnalisées.

### 🩺 Santé des champs (Administration > Base de données)
- Analyse des valeurs de dossiers sans champ correspondant, puis rattachement aux noms actuels : ajout seulement (rien n'est supprimé ni écrasé), dossier **et** copie à plat mis à jour, copie de sécurité de la base par l'API SQLite (fiable en mode WAL), entrée au journal.

### 🧪 Tests
- Ressource personnalisée de bout en bout (tous types de champs, libellés atypiques) : saisie, relecture, PUT(GET) idempotent, valeur orpheline conservée, renommage de clé, alias, masquage, PDF, export.
- `tests/browser/check_field_health.py` (formulaire d'ancien dossier + page Santé des champs), tests unitaires des alias et de la réparation.

## [3.50.2] - 2026-09-20

### 🐛 Correctifs
- **Formulaire d'un ancien dossier : e-mail et numéros de série affichés vides alors que le survol les montrait** : les valeurs étaient enregistrées sous d'anciens noms de champs (`nomPoste`, `numeroSerie`, `adresse`) que le catalogue actuel ne connaît plus. Le serveur les présente désormais aussi sous les noms actuels (rien n'est retiré ni écrasé).
- **Tableau de bord : un dossier « en attente de signature » sans restitution n'avait pas de bouton de signature** (et proposait à tort « Informer de la restitution »). Boutons renommés : « Envoyer le lien de signature » / « Renvoyer le lien de signature ».

## [3.50.1] - 2026-09-20

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
