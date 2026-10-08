# Backlog produit — À Quai

Dernière revue : **6 octobre 2026**, fin de journée (série 3.67.3 → 3.71.0 ; 3.67.4 : déconnexion immédiate de l'onglet ouvert ; P0 « sécurité des sessions » ajouté puis terminé : 3.67.3 ; précédente : 29 septembre, chantier « regroupement des dossiers par personne », versions 3.66.1 à 3.67.2 ; voir CHANGELOG pour le détail).

Ce document est la vue d'ensemble ; le détail de chaque chantier vit dans le CHANGELOG, `docs/audit/` et la mémoire du projet.

## 🔁 Reprise — où on en est (6 octobre 2026, fin de journée)

**État des branches (fin de journée du 06/10)** : `dev` = **3.72.0** (`preprod` = 3.71.0) (PR n°36 puis n°37 `dev` → `preprod` fusionnées par le propriétaire) ; **`prod` = `main` = 3.67.1**. La série 3.67.3 → 3.71.0 (sécurité des sessions puis notifications 3.68.0 à 3.71.0) est donc en préprod, **pas en production**. Reste au propriétaire : tester la préprod (checklist ci-dessous), puis PR `preprod` → `prod`, puis déploiement.

**`main` (branche par défaut de GitHub, affiche le README)** : elle ne sert à rien au déploiement (la production se déploie depuis `prod`) ; elle sert à afficher le bon README. Une PR `preprod` → `main` peut exister : **ne la fusionner qu'après la mise en production**, sinon GitHub affiche « 3.71.0 » alors que la production est en 3.67.1. Ordre voulu : `dev` → `preprod` → test → `prod` → déploiement → alignement de `main`. L'historique des trois branches est relié par des commits « ours » (voir `docs/REPRISE_MAJ.md`).

**À tester en préprod (propriétaire)** : (1) deux navigateurs, changement de mot de passe dans l'un → l'autre est déconnecté en moins d'une minute ; (2) `admin/admin` encore en place → fenêtre de changement obligatoire ; (3) cloche → « N ressources sans service référent » → choisir les services (Informatique = DSI proposé) ; (4) Admin > Services → ajouter les **titulaires** de chaque service ; (5) attribuer une ressource d'un service → la tâche « à fournir » apparaît chez les titulaires → « Fait » ; (6) restituer → « à fermer » pour un compte ; (7) page « Mes tâches », « Rouvrir ». Migrations 9 et 10 au premier démarrage (copie de sécurité automatique).

**Avant la mise en production** : sauvegarde de la base ; prévenir les utilisateurs qu'ils devront **se reconnecter une fois** ; rattacher les ressources aux services et saisir les titulaires **avant** de compter sur les notifications (sans titulaire, tout retombe sur les administrateurs) ; faire changer les mots de passe `admin` restants.

**Suite conseillée, dans l'ordre**
1. ✅ **Retrait d'une ressource par un ajustement → tâche « à fermer »** (3.72.0, 07/10).
2. ✅ **« Tâches des services » avec « Fait par X le … » dans la fiche du dossier** (3.72.0, 07/10).
3. ✅ **Scénarios navigateur** remis au vert (07/10) : 28 `check_*` passent ; `inspect_*` = outils d'inspection sur copie de base.
4. 🟡 **Sécurité P2** : ✅ changement forcé après création / réinitialisation par un administrateur (3.72.0). **Verrouillage temporaire par compte : codé mais DÉSACTIVÉ par défaut, reporté** (décision du propriétaire le 08/10 : un verrouillage permet de bloquer volontairement un compte ; à reprendre plus tard, p. ex. avec un délai croissant entre les essais plutôt qu'un blocage dur ; activable par `APP_LOGIN_ACCOUNT_MAX_FAILURES=5`). **MFA : écarté pour le moment** (décision du 08/10). Reste possible : liste des sessions actives (registre de sessions côté serveur).
5. **Reste de l'ajustement** : ✅ PDF de l'ajustement et ✅ e-mail (3.72.0, 08/10). Reste : QR code sur les restitutions après « Enregistrer en attente » — **à cadrer avec le propriétaire**.
6. ✅ **Heures des PDF en heure locale** (3.72.0, 08/10) : réglage « Fuseau horaire » de l'organisation (Europe/Paris par défaut), conversion des heures enregistrées en UTC, en-tête des PDF compris. Reste possible : afficher aussi l'heure locale dans les e-mails `.eml` générés côté navigateur (ils utilisent déjà l'heure du navigateur).
7. P1 déjà listés plus bas (doublons de personnes, ancien modèle matériel, champs orphelins, déploiement réel) — **sur une copie de la base de production**, jamais sur `backend/dotation.db`.

**Pièges appris pendant cette série** (détail dans `AGENTS.md` §4 et §7) : ne jamais lancer `tests/_http_scenarios.py` à la main (il a écrasé la base locale le 06/10) ; les sessions posées à la main dans un test passent par `tests/_stamped_client.py` ; le harnais navigateur donne à `admin` un autre mot de passe (sinon `admin/admin` est reflaggé) ; `/api/forms` est limité à 30 créations par minute (neutraliser dans un test qui en crée beaucoup) ; une ressource ne se crée plus sans service du catalogue ; les scénarios qui modifient la base directement règlent `APP_NOTIFICATIONS_CACHE_SECONDS=1`.

**Méthode** : explorer avec `graft` (`ask`, `callers` avant de modifier une fonction partagée, `grep`) et `graphify` (hook de commit déjà installé) plutôt qu'avec des lectures de fichiers entiers ; skill `token-thrift` en début de tâche ; un seul outil par besoin.

## Version courante

`dev` à **3.72.0**, `preprod`/`prod` en cours de promotion (voir CHANGELOG). `forms.adjust` se rattrape désormais automatiquement au démarrage sur les installations existantes (3.66.1) — ne demande plus d'action manuelle.

## ✅ P0 — Sécurité des sessions (trouvé le 06/10, terminé le 06/10 en 3.67.3)

**Constat** : après un changement de mot de passe, une session ouverte avant (ex. `admin/admin` par défaut) reste valide et garde tous les droits. Cause : le cookie de session ne contient que `session["user"]` ; `login_required` (`auth.py`) ne relit rien en base, et ni `/api/me/password` (`routes/pages.py`) ni la modification d'un compte par l'admin (`routes/admin.py`) n'invalident les sessions existantes. La désactivation et la suppression d'un compte sont très probablement touchées aussi (à vérifier par test).

| Lot | Contenu | Effort | Priorité |
|---|---|---|---|
| ✅ 1 (code fait le 06/10, 3.67.3) | **Empreinte de session** : au lieu d'une colonne (donc sans migration), le cookie porte un HMAC du hash du mot de passe (`pwd_fp`), comparé à chaque requête par `enforce_session_validity` (`auth.py`, `before_request` dans `app.py`). Mot de passe changé (par l'utilisateur ou un admin), compte désactivé, en attente ou supprimé → session vidée, 401, entrée `session_revoked` au journal de sécurité. La session de celui qui change son propre mot de passe est réalignée (`realign_session_password`). Les cookies émis avant le correctif (sans empreinte) sont refusés : **tout le monde devra se reconnecter une fois à la mise à jour**. Limite connue : un compte désactivé puis réactivé avant toute requête de la session ancienne la ressuscite | M | P0 |
| ✅ 2 (code fait le 06/10, 3.67.3) | **Cycle de vie** : `start_session` vide la session avant la connexion (pas de fixation) ; durée absolue 12 h et inactivité 60 min, réglables par `APP_SESSION_MAX_HOURS` / `APP_SESSION_IDLE_MINUTES` | S | P0 |
| ✅ 3 (fait le 06/10, 3.67.3) | **Compte par défaut** : `must_change_password` posé sur `admin` au seed et au démarrage tant que son mot de passe est `admin` ; le serveur ne répond plus qu'au changement de mot de passe, fenêtre non fermable côté navigateur. Le flag cookie `Secure` est déjà posé automatiquement en HTTPS (`_AutoSecureSessionInterface`). Scénario navigateur : `tests/browser/check_password_obligatoire.py` | S | P0 |
| ✅ Tests (`tests/test_session_validity.py`, 11 tests) | Changement par un admin, par l'utilisateur (sa session reste ouverte), désactivation, suppression, mutation avec jeton CSRF valide, expiration absolue et par inactivité, cookie ancien, remplacement de session à la connexion. `tests/_stamped_client.py` complète les sessions posées à la main par les autres tests | S | P0 |
| Plus tard | Limitation des tentatives de connexion (à vérifier), MFA TOTP pour les admins, liste des sessions actives, forcer le changement après une réinitialisation par un administrateur | M | P2 |

À livrer en correctif (x.y.Z) : version à confirmer avec le propriétaire avant tout changement. Bonnes pratiques de référence : OWASP Session Management, ASVS §3.

## Sprint terminé le 26/09 — « Ajuster les ressources d'un dossier déjà actif »

Cadré le 21-22/09 avec trois experts (process métier, base de données, architecture) : voir `docs/REPRISE_MAJ.md` et la mémoire `feature_ajustement_dossier_actif`.

**Fait** : 3.60.1 (bug parc/stock sur retrait), 3.60.2 (limiteur de connexion), 3.61.0 (identifiant de personne stable), 3.62.0 (e-mails de restitution), 3.62.1 (journal de connexion), 3.63.0 à 3.65.0 (ajustement), 3.66.0 (QR code de signature).

**Détail des versions** (les lignes « Reste » de chaque version restent à traiter) :

| # | Contenu | Effort | Priorité |
|---|---|---|---|
| ✅ 3.62.0 (fait le 24/09) | E-mails de restitution : voir « Demandes utilisateur » ci-dessous | S | P1 |
| ✅ 3.63.0 (fait le 26/09, complété le 28-29/09) | Route `PATCH /api/forms/<id>/ajustement` + signature par geste + permission `forms.adjust` + statut d'événement distinct + lien public de signature à distance (`adjustment-signature.html`, 3.66.1) + `forms.adjust` rattrapé automatiquement sur les groupes existants (`PERMISSION_BACKFILLS`, 3.66.1) | M | P1 |
| ✅ 3.64.0 (fait le 26/09) | Migration 7 de rattrapage + invariant de santé « retrait non répercuté ». Sur la copie de la base de production : 2 dossiers sources, aucun changement (rien à annoncer) | S | P0 |
| ✅ 3.65.0 (fait le 26/09, complété le 28-29/09) | Interface d'ajustement (fenêtre, signature manuscrite, à distance puis recueillie, historique, reprise de matériel restitué), « Mise à jour » retiré du sélecteur de création, plus « Gérer les ressources » à côté de « Restituer » (3.67.2). **Reste** : PDF de l'ajustement, e-mail de la fiche de retraits (voir « Demandes utilisateur ») | M | P1 |
| ✅ 3.67.1 (fait le 28/09) | Regroupement des dossiers par personne dans les 4 tableaux de bord (`groupDraftsByPerson`) — répond au symptôme visible des doublons (voir constat ci-dessous), mais ne fusionne pas les fiches « personne » elles-mêmes | M | P2 |

**Demande du 26/09, faite en 3.66.0** : QR code du lien de signature (personne présente) — menu « Signature en face à face » et bannière. **Reste** : QR code sur les écrans de restitution après « Enregistrer en attente ».

## 🟡 Notifications — « qui doit terminer cette action » (lot 1 livré en 3.68.0 le 06/10, lot 3 livré en 3.69.0 le 06/10, lot 2 livré en 3.70.0 le 06/10, lot 4 livré en 3.71.0 le 06/10)

Idée du propriétaire : prévenir la personne en charge d'une action (ex. créer un compte dotelec), et les administrateurs (nouvelle version, sauvegarde en échec). Étudiée le 06/10 par un groupe de trois experts (métier, architecture/données, interface/sécurité/RGPD).

**Lot 1 ✅ (3.68.0, 06/10)** : titulaires par service (Admin > Services), service obligatoire sur une ressource, migration 9, cloche + panneau, tâche des administrateurs « ressources sans service référent » avec suggestion validée par l'administrateur. **Lot 3 ✅ (3.69.0, 06/10)** : tâches des administrateurs (nouvelle version, sauvegarde en échec, inscriptions en attente). **Lot 2 ✅ (3.70.0, 06/10)** : tâches de service « à fournir » / « à fermer », « Fait » partagé (table `service_task_done`, pas dans le contenu du dossier), repli sur les administrateurs, migration 10 qui considère l'existant comme traité. **Reste** : retrait d'une ressource par un ajustement → « à fermer » ; « Fait par X le … » dans la fiche du dossier ; lot 4 (relance J+3, escalade J+7, page « Mes tâches », rétention 90 jours).

**Décisions du propriétaire (06/10)** : tâche **partagée** par service (un seul état, elle disparaît pour tous dès qu'un titulaire la fait) ; **toutes les ressources** concernées, pas seulement dotelec ; **le même service** est prévenu d'un compte à fermer au départ d'un agent ; l'administrateur garde la main sur le rattachement des ressources existantes (Informatique = DSI proposé, validé par lui).

**Décision du propriétaire (06/10, remplace la précédente)** : *on rattache chaque ressource à un **service**, et le service porte une **liste de comptes** (ses titulaires)*. **Tous les membres du service reçoivent la notification** (ex. une création de compte AD part à tous les membres de la DSI). Conséquences à cadrer :
- table `service_referents` (service du catalogue `service_catalog` ↔ comptes) + section « Titulaires » dans l'édition d'un service (Admin > Services) ;
- le « service émetteur » d'une ressource (`resource_catalog.issuer_service`, texte libre : `DSI` et `Informatique`, `DRH` et `Ressources humaines` coexistent) doit devenir une vraie référence au catalogue des services, avec migration qui propose la correspondance et signale les cas ambigus ; **obligatoire** à la création d'une ressource ;
- une tâche est **partagée par service** (un seul état) : visible chez tous les titulaires, elle disparaît pour tous dès que l'un la termine ; repli sur les administrateurs si le service n'a aucun titulaire actif ;
- plus tard, si besoin : référent propre à une ressource (non prévu en V1).

**Consensus des experts** : cloche dans l'application (sondage de 60 s déjà en place), pas d'e-mail en V1, aucune donnée personnelle dans le texte d'une notification (type + ressource + n° de dossier ; un profil « masqué » ne voit aucun nom), tâches visibles jusqu'à l'action, relance à J+3 puis escalade aux administrateurs à J+7, rétention 90 jours. Piège central : aucun marqueur « compte créé / à créer » n'existe dans les dossiers — c'est le vrai chantier. Architecture conseillée : tâches **calculées** à partir des dossiers + petite table de suivi (`notifications`, migration 9, `dotation.db`) ; événements ponctuels (version, sauvegarde) en `INSERT OR IGNORE` à clé unique ; nouveau droit `notifications.view` rattrapé par `PERMISSION_BACKFILLS`.

**V1 proposée** : 4 sources — compte/accès à créer à l'attribution, compte à fermer à la restitution, inscription en attente, nouvelle version ou sauvegarde en échec. **Questions ouvertes** : seul dotelec ou aussi messagerie/badges/clés ; la création bloque-t-elle la signature ; qui est prévenu d'un compte à fermer ; un simple « Fait » ou la saisie de l'identifiant créé.

## Constats à traiter, issus de l'audit et de la pré-crise du 20/09 (non planifiés en version)

| Sujet | Détail | Priorité |
|---|---|---|
| Doublons de personnes | 47 fiches « personne » pour 34 dossiers sur la copie de production (trouvé en 3.61.0). Le regroupement par personne dans les tableaux de bord (3.67.1) masque le symptôme visible (une personne = une ligne, même avec plusieurs `personId`, grâce au repli par identité), mais aucune fusion des fiches « personne » elles-mêmes n'a été faite | P1 |
| Ancien modèle matériel/immatériel | 7 dossiers sur 34 (copie de prod) n'utilisent que ce format, ~150 références dans le code. Projet dédié, à mener sur une copie de production | P1 |
| Réparation des champs orphelins | La page Santé des champs signale 6 noms de champs rattachables sur la copie de production ; le bouton « Rattacher » n'a jamais été cliqué dessus | P1 |
| Déploiement réel | `setup/deploy-common.sh` n'a jamais tourné sur un vrai serveur Linux à plusieurs workers (validé par syntaxe et par ses tests seulement) | P1 |
| ✅ Identifiant saisi journalisé en clair lors d'un échec de connexion (trouvé le 24/09, corrigé en 3.62.1) | Corrigé : l'identifiant n'est conservé que s'il correspond à un compte ; migration 6 pour les entrées existantes. Reste à l'exploitation : faire changer le mot de passe concerné | P1 |
| ✅ Scan de vulnérabilités des dépendances (fait le 26/09) | `pip-audit` : aucune vulnérabilité connue (détail dans `docs/AUDIT_SECURITE_2026-09.md`). À relancer avant chaque mise en production ; les bibliothèques chargées par CDN (Bootstrap, cookieconsent) restent à revoir à la main | P1 |
| Défilement horizontal du tableau « Restitutions en cours » à 1100 px (constaté le 26/09) | `tests/browser/test_no_horizontal_scroll.py` échoue sur la copie de la base de production (tableau de 869 px dans un cadre de 852 px), **y compris avant les travaux du 24-26/09** : lié aux lignes « Sortie (régularisation) » ajoutées depuis la dernière mesure du 19/09. À reprendre avec les colonnes secondaires (`DASHBOARD_COLUMNS.secondary`) | P2 |
| Police PDF Unicode | Le cyrillique, l'arabe, le chinois sortent en « ? ». Nécessite d'embarquer une police libre (ex. DejaVu Sans) — décision de l'utilisateur en attente | P2 |
| Moteur de workflow déclaratif | Non commencé | P2 |
| Effet des formules CSV dans Excel | Neutralisation faite côté code (3.52.0), jamais vérifiée avec un vrai Excel | P2 |
| Pagination de `/api/forms` | Mesuré à ~1,7 ms/dossier (3000 dossiers synthétiques) : sans effet à l'échelle actuelle (34 dossiers), à surveiller si un client dépasse quelques centaines de dossiers | P2 |

## Demandes utilisateur (non planifiées en version)

| Sujet | Détail | Effort | Priorité |
|---|---|---|---|
| ✅ Reprise de matériel restitué dans l'ajustement (demande du 29/09, fait le 29/09) | « Reprendre un matériel déjà restitué » propose désormais, quand on ajoute une ressource via « Gérer les ressources », les unités disponibles en stock (`/api/catalog/available/<id>`) — même mécanisme que la création de dossier, réimplémenté dans `frontend/js/adjustment.js` (`openAdjustmentReuseModal`) car ce fichier est aussi chargé sur des pages sans `app.js`. Scénario : `tests/browser/check_adjustment_reuse_stock.py` (12/12) | M | P1 |
| ✅ Bouton « Envoyer par e-mail » sur les écrans de restitution (demande du 24/09, fait le 24/09) | Phase 1 : à la validation, proposition d'un e-mail d'information. Phase 2 (et Phase 1 en consultation) : boutons « Télécharger le PDF » / « Envoyer par e-mail » dans la barre du bas (`renderRestitutionFollowUpActions`, `frontend/js/storage.js`, chargé désormais par les deux pages). Après « Enregistrer la restitution » : envoi proposé. Corrigé au passage : l'export PDF plantait hors des listes (chargeur d'export absent de `form.html` et des écrans de restitution), ce qui cassait aussi « Télécharger le PDF » / « Envoyer par e-mail » sur la fiche d'attribution signée. Scénario : `tests/browser/check_restitution_email.py` | S | P1 |
| ~~Menu e-mail pendant une restitution commencée~~ | Vérifié le 24/09 : pas de bug. L'enregistrement de la Phase 1 passe le dossier en `partial_return`, le menu propose donc bien les e-mails de restitution | — | — |
| Destinataires en copie | Le `.eml` ne vise que la personne (adresse de messagerie attribuée ou `beneficiaire.email`). Pour une restitution, le responsable de service et le service RH/informatique sont souvent concernés : à concevoir avec la case « Responsable de service » (voir plus bas). Sans adresse connue, le brouillon part sans destinataire et rien ne le signale | S | P2 |
| E-mail de la fiche de retraits | Le PDF de retraits (`/api/forms/<id>/retraits-pdf`) n'a pas d'équivalent « Envoyer par e-mail » ; à reprendre dans l'écran d'ajustement (livré en 3.65.0) plutôt que sur l'ancien type « mise à jour » | S | P2 |

## Backlogs plus anciens : où ils en sont

**Terminés depuis, pas à rouvrir :**
- Revue de code v3.8.x (`backlog_code_review`) : les ~10 points restants ont reçu leur test cette session.
- Audit cybersécurité (`backlog_next_sprints`, point 2) : couvert par l'audit du 20/09 (reste seulement le scan de dépendances ci-dessus).
- UX signature à distance (`backlog_next_sprints`, point 1) : déjà refaite avant le 18/09.
- Sauvegarde multi-bases chiffrée, destinations SMB/NFS, planification (`feature_sauvegarde_multibases`) : livrée en v3.36-3.38.
- Resélection d'un matériel restitué (`feature_reprise_materiel_restitue`) : livrée en v3.41 ; son point « UI admin pour marquer le champ identifiant » est couvert par les rôles de champs de 3.59.0.
- Ergonomie/boutons (`backlog_ergonomie_sprints`) : sprints S1 à S7 faits. Ne restent que deux micro-points (voir ci-dessous).
- Mode sombre (`dark_mode_not_tech_debt`) : **ne pas relancer de chantier**, ce n'est pas de la dette.

**Vraiment encore ouverts, non planifiés :**
- Toast « Annuler » après suppression d'un dossier (`backlog_ergonomie_sprints`).
- Cartes empilées sur mobile (`backlog_ergonomie_sprints`) — jamais pu être testé par l'automatisation du navigateur (le redimensionnement de fenêtre ne change pas la largeur perçue).
- Historique/cycle de vie du parc + assistant de création de ressource (`backlog_historique_parc`) : plan validé, rien codé.
- Cohérence de la navigation, moins de clics (`backlog_navigation_audit`) : audit fait le 19/09, rien codé.
- Case « Responsable de service » sur les comptes, pour de futurs e-mails automatiques (`feature_reprise_materiel_restitue`) : recoupe le signataire de substitution décidé pour le chantier en cours (3.63.0) — à concevoir ensemble plutôt que séparément.
- Blocage d'une saisie manuelle d'un n° de série déjà attribué ailleurs (`feature_reprise_materiel_restitue`).
- Typage progressif (`@ts-check` + JSDoc) sur `storage.js`/`admin.js` (`backlog_typage_typescript`) : backlog de version future, faible priorité.

## Repères

- Comment reprendre : `docs/REPRISE_MAJ.md`.
- Pourquoi le code est fait ainsi : `docs/ARCHITECTURE_DONNEES.md`.
- Audit et décisions du 20/09 : `docs/audit/`.
