# Backlog produit — À Quai

Dernière revue : **23 septembre 2026** (daily scrum de fin de session, animé par le Scrum Master). Reprise prévue le **25 septembre 2026**.

Ce document est la vue d'ensemble ; le détail de chaque chantier vit dans le CHANGELOG, `docs/audit/` et la mémoire du projet.

## Version courante

`dev` = **3.62.1**, promue vers `preprod` par la PR #24 (ouverte, à fusionner par le propriétaire). `preprod` et `prod` sont à 3.60.2 tant que la #24 n'est pas fusionnée.

## Sprint en cours — « Ajuster les ressources d'un dossier déjà actif »

Cadré le 21-22/09 avec trois experts (process métier, base de données, architecture) : voir `docs/REPRISE_MAJ.md` et la mémoire `feature_ajustement_dossier_actif`.

**Fait** : 3.60.1 (bug parc/stock sur retrait), 3.60.2 (limiteur de connexion sous charge, trouvé par la CI), 3.61.0 (identifiant de personne stable), 3.62.0 (e-mails de restitution, inséré avant la suite du sprint).

**Reste, dans l'ordre** :

| # | Contenu | Effort | Priorité |
|---|---|---|---|
| ✅ 3.62.0 (fait le 24/09) | E-mails de restitution : voir « Demandes utilisateur » ci-dessous | S | P1 |
| 3.63.0 | Route unique `PATCH /api/forms/<id>/ajustement` (ajout + retrait + service en une transaction), permission dédiée assignée à Administrateur/Administration, statut de workflow distinct (ne pas réutiliser celui de la restitution finale), signature par geste en présentiel ou à distance, signature impossible → un responsable signe à la place | M/L | P0 |
| 3.64.0 | Migration de rattrapage sur les 34 dossiers « mise à jour » déjà en base (resynchronisation parc/stock historique) + invariant de santé associé | S | P0 |
| 3.65.0 | Interface : bouton « Ajuster les ressources / le service » sur un dossier actif, retrait de l'option « Mise à jour » du sélecteur de création (le type reste lisible pour les dossiers existants) | M | P1 |
| 3.66.0 (optionnel) | Écran de rapprochement/fusion de doublons de personnes — voir constat ci-dessous (47 fiches pour 34 dossiers) | L | P2 |

## Constats à traiter, issus de l'audit et de la pré-crise du 20/09 (non planifiés en version)

| Sujet | Détail | Priorité |
|---|---|---|
| Doublons de personnes | 47 fiches « personne » pour 34 dossiers sur la copie de production (trouvé en 3.61.0). La colonne `person_id` les rend maintenant visibles, mais aucune fusion n'a été faite. Se raccroche à 3.66.0 | P1 |
| Ancien modèle matériel/immatériel | 7 dossiers sur 34 (copie de prod) n'utilisent que ce format, ~150 références dans le code. Projet dédié, à mener sur une copie de production | P1 |
| Réparation des champs orphelins | La page Santé des champs signale 6 noms de champs rattachables sur la copie de production ; le bouton « Rattacher » n'a jamais été cliqué dessus | P1 |
| Déploiement réel | `setup/deploy-common.sh` n'a jamais tourné sur un vrai serveur Linux à plusieurs workers (validé par syntaxe et par ses tests seulement) | P1 |
| ✅ Identifiant saisi journalisé en clair lors d'un échec de connexion (trouvé le 24/09, corrigé en 3.62.1) | Corrigé : l'identifiant n'est conservé que s'il correspond à un compte ; migration 6 pour les entrées existantes. Reste à l'exploitation : faire changer le mot de passe concerné | P1 |
| Scan de vulnérabilités des dépendances | Jamais lancé (ex. `pip-audit` sur `backend/requirements.txt`) | P1 |
| Police PDF Unicode | Le cyrillique, l'arabe, le chinois sortent en « ? ». Nécessite d'embarquer une police libre (ex. DejaVu Sans) — décision de l'utilisateur en attente | P2 |
| Moteur de workflow déclaratif | Non commencé | P2 |
| Effet des formules CSV dans Excel | Neutralisation faite côté code (3.52.0), jamais vérifiée avec un vrai Excel | P2 |
| Pagination de `/api/forms` | Mesuré à ~1,7 ms/dossier (3000 dossiers synthétiques) : sans effet à l'échelle actuelle (34 dossiers), à surveiller si un client dépasse quelques centaines de dossiers | P2 |

## Demandes utilisateur (non planifiées en version)

| Sujet | Détail | Effort | Priorité |
|---|---|---|---|
| ✅ Bouton « Envoyer par e-mail » sur les écrans de restitution (demande du 24/09, fait le 24/09) | Phase 1 : à la validation, proposition d'un e-mail d'information. Phase 2 (et Phase 1 en consultation) : boutons « Télécharger le PDF » / « Envoyer par e-mail » dans la barre du bas (`renderRestitutionFollowUpActions`, `frontend/js/storage.js`, chargé désormais par les deux pages). Après « Enregistrer la restitution » : envoi proposé. Corrigé au passage : l'export PDF plantait hors des listes (chargeur d'export absent de `form.html` et des écrans de restitution), ce qui cassait aussi « Télécharger le PDF » / « Envoyer par e-mail » sur la fiche d'attribution signée. Scénario : `tests/browser/check_restitution_email.py` | S | P1 |
| ~~Menu e-mail pendant une restitution commencée~~ | Vérifié le 24/09 : pas de bug. L'enregistrement de la Phase 1 passe le dossier en `partial_return`, le menu propose donc bien les e-mails de restitution | — | — |
| Destinataires en copie | Le `.eml` ne vise que la personne (adresse de messagerie attribuée ou `beneficiaire.email`). Pour une restitution, le responsable de service et le service RH/informatique sont souvent concernés : à concevoir avec la case « Responsable de service » (voir plus bas). Sans adresse connue, le brouillon part sans destinataire et rien ne le signale | S | P2 |
| E-mail de la fiche de retraits | Le PDF de retraits (`/api/forms/<id>/retraits-pdf`) n'a pas d'équivalent « Envoyer par e-mail » ; à reprendre dans l'écran d'ajustement de 3.65.0 plutôt que sur l'ancien type « mise à jour » | S | P2 |

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
