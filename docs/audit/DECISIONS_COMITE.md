# Décisions du comité — data management × full stack × qualité (20 septembre 2026)

Statut initial : propositions du comité. **Mise à jour du 20/09/2026 (fin de journée) : les décisions D1 à D15 sont appliquées sur `dev` (versions 3.51.0 à 3.60.0) ; D16 (ancien modèle matériel / immatériel), la police PDF Unicode et le moteur de workflow ne sont pas faits.** État détaillé, suite et reprise : `docs/REPRISE_MAJ.md`. Une réunion de pré-crise (démarrage insensible aux données, support à distance, rôles de champs, performance, restauration) a ajouté les versions 3.57.0 à 3.60.0.

## Où les équipes convergent (adopté)
- Cause racine unique : la clé technique du champ sert à la fois de nom, d'identifiant et de clé de stockage, et elle peut changer.
- Le dossier doit garder toute valeur qu'il ne reconnaît pas ; jamais de reconstruction du dossier depuis le seul schéma courant.
- La correspondance « au jugé » (ressemblance de noms, position) doit disparaître au profit d'une correspondance exacte.

## Décisions

| # | Sujet | Décision | Version | Priorité |
|---|---|---|---|---|
| D1 | Valeurs sans champ correspondant | Conservées et affichées dans « Autres informations enregistrées » ; renvoyées telles quelles à l'enregistrement | 3.51.0 | P0 |
| D2 | Alias de champ | Suppression de l'appariement **par position** (risque de rattacher au mauvais champ). Seul le **libellé identique** rattache. Les alias existants sont **conservés** à chaque sauvegarde. *Appliqué dans le code non commité.* | 3.51.0 | P0 |
| D3 | Réparation des données | **Ne pas livrer l'interface tant que** la réparation ne met pas aussi à jour `dotation_items.details_json` et les suggestions, et que la copie de sécurité n'utilise pas l'API de sauvegarde SQLite (base en WAL). Toujours ajout seulement, jamais de suppression | 3.51.0 | P0 |
| D4 | Un seul générateur de clés | Un slugifieur unique (Python et JS) avec test de parité ; la clé d'un champ existant est **immuable côté serveur** (jamais re-slugifiée) | 3.51.0 | P0 |
| D5 | Éditeur de champs (admin) | Types « liste » et « e-mail avec domaine » disponibles ; alias et aide à la saisie renvoyés au serveur | 3.52.0 | P0 |
| D6 | Modifications simultanées | Numéro de version sur le dossier ; refus (avec message clair) si quelqu'un l'a modifié entre-temps | 3.52.0 | P0 |
| D7 | Ressource désactivée / hors catalogue | Reste visible et conservée dans les dossiers existants ; la suppression du catalogue est refusée si la ressource est utilisée | 3.52.0 | P0 |
| D8 | Profils « masqués » | L'écriture d'un dossier ne peut pas écraser des valeurs masquées ; champs des ressources personnalisées masqués comme les autres | 3.52.0 | P0 |
| D9 | Identifiant de champ | **Tranché** : on n'introduit pas un `field_id` en urgence. D1–D4 + D5 apportent l'essentiel. Le `field_id` immuable arrive avec le **registre de schéma versionné** (le dossier référence une version au lieu de copier le schéma) | 3.53.0 | P1 |
| D10 | Migrations | Table de versions + migrations numérotées avec sauvegarde automatique avant chacune ; regroupe les 16 `ensure_column` dispersés | 3.53.0 | P1 |
| D11 | Copies multiples des valeurs | `payload_json` = source de vérité ; `dotation_items` et parc = projections recalculées par une seule fonction | 3.53.0 | P1 |
| D12 | Import/export de base « ancien » | À refondre (lecture d'une base en WAL, déplacement sur la base vivante, pas de migration après restauration). **Pas dans un lot correctif** : chantier dédié | 3.54.0 | P1 |
| D13 | Sécurité | Contrôle du chemin du manifeste de sauvegarde ; neutralisation des formules et guillemets dans les exports CSV ; plafonds de taille par route | 3.52.0 | P1 |
| D14 | Vocabulaires configurables | Statuts, types de dossier, états servis par le serveur (`/api/vocab`) au lieu d'être recopiés ; type de bénéficiaire « élu » remplacé par un **attribut** de type ; types personnalisés acceptés à l'enregistrement | 3.55.0 | P1 |
| D15 | Tests et contrôle continu | Tests « contrat de données » (saisir → enregistrer → relire → exporter sans perte, PUT(GET) idempotent) ; contrôle quotidien de santé des champs ; CI | en continu | P1 |
| D16 | Ancien modèle matériel / immatériel | Migration en dernier (risque élevé, effort L) | ≥ 3.56 | P2 |
| D17 | Divers P2 | Police PDF Unicode, moteur de workflow déclaratif, export/import du paramétrage, dictionnaire de données généré | plus tard | P2 |

## Arbitrages entre équipes
- **field_id maintenant ou plus tard ?** La data le voulait en P0, le full stack en P1 : retenu P1 (D9), car des correctifs plus petits suppriment déjà le risque immédiat.
- **Appariement des alias** : la qualité a démontré le risque de l'appariement par position, la data l'avait proposé : retenu « libellé identique seulement » (D2).
- **Import ancien de base** : la qualité le voulait P0, retenu P1 dans un lot séparé pour ne pas mélanger un correctif de données et un chantier sur la restauration (D12).
- **Réparation des données existantes** : la data voulait la lancer tout de suite ; retenu de la conditionner à D3, car elle laisserait sinon `details_json` incohérent.

## Points à confirmer par test (non vérifiés par les équipes)
Effet réel des formules CSV dans Excel ; existence en production d'un groupe « masqué » avec droit de modification ; comportement des listes/nombres/dates avec une valeur hors liste ; cause des écarts entre `payload_json` et `dotation_items` (égalité stricte seulement dans 7 dossiers sur 34).

## Données locales à nettoyer (après sauvegarde, sur accord)
51 lignes de sélection sans correspondance, 20 liens `source_form_id` vers des dossiers supprimés, 2 fichiers `.db` vides parasites, 3 tables de parcs mutualisés vides.
