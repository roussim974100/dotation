# Audit détaillé — À Quai (20 septembre 2026)

Trois équipes, en lecture seule : **data management**, **full stack**, **qualité / sécurité / tests**. Chaque point est marqué vérifié [V] ou supposé [S] dans les rapports. Les décisions du comité sont dans `DECISIONS_COMITE.md`.

---

# PARTIE 1 — Données et bases
# Audit data — « À Quai » (modélisation, qualité des données, cycle de vie des champs)

Date : 20/09/2026. Périmètre : lecture seule (SQLite ouvert en `mode=ro`, aucun fichier du dépôt modifié).
Légende : **[V]** = vérifié (requête ou lecture de code) ; **[H]** = hypothèse / non vérifié.
Aucune donnée personnelle n'est citée : uniquement des comptes.

---

## 1. Inventaire des bases

Chemins (`backend/config.py:11-15`) : `DATA_DIR` = `backend/` par défaut (ou `APP_DATA_DIR`), `DB_PATH=dotation.db`, `DB_USERS_PATH=users.db`.

| Fichier | Taille | Contenu | Remarque |
|---|---|---|---|
| `backend/dotation.db` (+ `-wal` 3,8 Mo, `-shm`) | 2,2 Mo | base métier, 23 tables | WAL actif, `integrity_check=ok`, `foreign_key_check` vide [V] |
| `backend/users.db` | 28 Ko | `users` 14, `groups` 7, `user_groups` 14, `rate_limit_hits` 19 | |
| `backend/app.db`, `./dotation.db` | 0 octet | fichiers vides résiduels | à supprimer (risque de confusion) [V] |
| `backend/db_backups/` | 6 Mo | 4 zip « avant étape », 1 backup `.db`, 1 paire `avant_restauration_*` | sauvegardes manuelles/pré-opération [V] |

Volumes `dotation.db` [V] : `dotation_forms` 34 · `dotation_items` 349 · `persons` 47 · `onboarding_dossiers` 47 · `audit_events` 548 · `app_logs` 1052 · `deleted_items` 28 · `resource_catalog` 25 · `service_catalog` 21 · `signature_links` 24 · `signature_views` 12 · `app_settings` 18 · `field_suggestions` 59 · `dotation_item_selections` 51 · `resource_units` 18 · `resource_unit_events` 31 · `resource_unit_aliases` 1 · `parc_meta` 1 · `shared_pools*` 0/0/0 · `resource_stock_movements` 0 · `resource_stock_thresholds` 0.
Poids du JSON : `payload_json` = 576 Ko cumulés (max 37 Ko/dossier) ; `signature_data` (base64) = 446 Ko cumulés, stockée **dans** la table principale.

Index [V] : seulement 7 index explicites (`dotation_forms.status`, `updated_at`, `dotation_item_selections(form_id,returned_at)`, `stock`×2, `unit_events`, `units`). **Aucun index** sur `dotation_items(form_id)`, `dotation_items(item_key)`, `onboarding_dossiers(person_id)`, `audit_events(dossier_id)`, `signature_links(form_id)`, `dotation_forms(dossier_id)`, `app_logs(created_at)`. Sans conséquence à 349 lignes ; à corriger avant montée en charge.

Clés étrangères [V] : déclarées pour `audit_events→onboarding_dossiers`, `onboarding_dossiers→persons`, `dotation_items→dotation_forms`, `dotation_item_selections→dotation_forms`, `signature_*→dotation_forms`, `resource_unit_events→resource_units` (PRAGMA `foreign_keys=ON` posé par `database.py:22`). **Non déclarées** : `dotation_forms.dossier_id`, `dotation_forms.source_form_id`, `dotation_items.item_key→resource_catalog.code`, `resource_units.resource_code`, `resource_units.holder_form_id`, `resource_unit_events.form_id`, `resource_stock_movements.form_id/resource_code`, `resource_unit_aliases.unit_id`. Intégrité assurée uniquement par le code applicatif.

Migrations [V] : pas de numéro de version (`PRAGMA user_version = 0`), pas de table `schema_migrations`. Schéma initial dans `app.py:334` (`init_db`, `CREATE TABLE IF NOT EXISTS`) + 16 `ensure_column` (`database.py:41`) + 23 `CREATE TABLE IF NOT EXISTS` répartis dans `app.py`, `models/units.py:127`, `models/stock.py:39`. Migrations de données idempotentes par « marqueur » dans `parc_meta` (seul marqueur présent : `field_alignment_v1`, posé le 19/09 à 18:48 ; `models/units.py:380`) et par re-exécution à chaque démarrage (`migrate_builtin_resource_schemas` `models/catalog.py:328`, `migrate_telephone_imei_field` `:423`). `users.db` : `ensure_users_schema` (`database.py:50`).

Sauvegarde [V] : export/import/diagnostic chiffré, destinations SMB/NFS, planification (`routes/db_backup.py`, `backup*.py`). Un dossier `db_backups/` local existe. [H] non vérifié : test de restauration périodique et rétention.

---

## 2. Audit de modélisation

### 2.1 JSON vs relationnel
| Colonne JSON | Table | Contenu | Risque |
|---|---|---|---|
| `payload_json` | `dotation_forms` | dossier **entier** : bénéficiaire, `resources.additional[]` (valeurs `fields`, **`fieldSchema` embarqué**, libellé, flags), restitution, workflow, sections legacy `materiel`/`immateriel` (7 dossiers sur 34), `unc_*` | source de vérité de fait pour les valeurs ; schéma non contraint |
| `details_json` | `dotation_items` | copie de l'entrée de ressource (clés `assignedAt, category, code, conditionAttribution…` + `fields` ou champs à plat) — renseignée pour 349/349 | 2ᵉ copie des valeurs |
| `field_schema_json` | `resource_catalog` | liste de champs `{key,label,type,required,options,suggest,identifier,hidden,aliases}` | **clé = slug du libellé**, pas d'identifiant immuable |
| `fields_json` | `resource_units` | valeurs de champs de l'unité de parc (18 lignes) | 3ᵉ copie, clés alignées sur le catalogue au resync |
| `details_json` | `app_logs`, `audit_events` | traces | ok (journal) |
| `payload_json` | `deleted_items` | corbeille (28) | fige un ancien format de clés : à la restauration, dérive possible |
| `setting_value` | `app_settings` | JSON libre (`beneficiary_types`, `org_context`) | non typé |

Colonnes relationnelles mortes ou faussées [V] :
- `dotation_items.serial_number` : **0/253** lignes matériel renseignées (colonne morte ; la vraie valeur est dans `details_json`).
- `dotation_items.resource_type` : dupliquée avec `item_key`.
- `dotation_item_selections` (51 lignes) : `item_id INTEGER` contient en réalité des **identifiants texte `resource_…`** (jamais un `dotation_items.id`) → **51/51 lignes sans correspondance** ; reliquat de la fonctionnalité « parcs mutualisés » supprimée le 7 mai (les 3 tables `shared_pool*` sont vides et toujours créées). Le `is_pool_resource` du catalogue est aussi un reliquat (`database.py:88` le retire à la lecture).
- `resource_catalog.is_pool_resource` : colonne toujours présente.

### 2.2 Duplication et risque de divergence
Une même valeur de champ peut exister à 4 endroits : `payload_json` → `dotation_items.details_json` → `resource_units.fields_json` → (PDF/export recalculés). Mesures [V] :
- Nombre d'entrées `additional` par dossier = nombre de lignes `dotation_items` dans seulement **7/34 dossiers** ; nombre de `selected` = nombre de `assigned` dans **27/34**. Écarts attendus en partie (lignes non sélectionnées écrites en `dotation_items` avec `assigned=0`), mais le contrôle automatique n'existe pas [H sur la cause exacte].
- `onboarding_dossiers` : **13 dossiers sans aucun formulaire** (47 contre 34 formulaires) ; les statuts sont mappés (form `active`→`actif`, `returned`→`en_restitution`, etc., 34/34 cohérents), mais le vocabulaire diffère (`draft` vs `a_preparer`) : deux machines d'état.
- Identité de la personne dupliquée dans `persons` et `dotation_forms.nom/prenom` (0 divergence sur 34) mais **6 groupes de personnes en doublon** (même nom+prénom insensible à la casse) dans `persons` : pas de clé naturelle ni de contrainte d'unicité.
- `dotation_forms.source_form_id` (chaînage mise à jour → dossier d'origine) : 34 lignes, 22 renseignées, **20 pointent vers un dossier inexistant** (supprimés → corbeille). Pas de FK, pas de `ON DELETE SET NULL`.
- `dotation_forms` mélange identité, statut, signature base64, payload : table « fourre-tout » (colonnes `nom, prenom, service, fonction, mandat, assigned_at, returned_at` = copies de valeurs du payload).

### 2.3 Clés naturelles instables
- Clé de champ = `slugify_field_key(libellé)` (`utils.py:57`, doublon JS `admin.js:67`) ; la clé est figée à la création côté formulaire admin (`admin.js:696-697`) mais **pas contrainte côté serveur** : un PUT API peut changer une clé.
- `resource_catalog.code` : clé de liaison de `dotation_items.item_key`, `resource_units.resource_code`, stock, et payload. Verrouillé si déjà utilisé (`routes/admin.py:1275`, `code_locked`), bon garde-fou, mais **ni FK ni cascade** : les tables filles ne sont pas protégées si le verrou est contourné (import, SQL).
- Clés mélangées camelCase / snake_case dans le catalogue et l'historique : `nomPoste`, `numeroSerie`, `nomTelephone`, `adresse` (anciens) vs `nom_du_poste`, `numero_de_serie`, `n_de_serie_sn`, `adresse_email`. Cas particulier [V] : téléphone = `n_de_serie_sn` alors que les autres = `numero_de_serie` ; plaque de porte et cartes de visite réutilisent des clés génériques (`nom`, `prenom`, `fonction`, `telephone`, `email`) qui collisionnent conceptuellement avec les champs du bénéficiaire.
- Le catalogue ne contient **aucun** champ `hidden`, **aucun** `id`/`fieldId` (clés présentes : `options, required, suggest, type, label, key, placeholder` — `identifier`/`aliases` apparaissent après normalisation côté code) [V]. 25 ressources ; 6 sans champ (`veste`, `chaussuresSecurite`, `souris`, `dotelec_*`, `bl_gestion_financiere`, `signature_email`) → valeurs impossibles à ranger, tout passe par « détails ».

### 2.4 Versionnement de schéma
Absent : ni version de schéma de base, ni **version de schéma de champ**. Le `fieldSchema` embarqué dans chaque entrée de dossier joue le rôle de « snapshot de schéma », mais il est **différent du catalogue dans 33 des 72 entrées** [V] (clés `nomPoste`… vs `nom_du_poste`…) : c'est la preuve qu'un snapshot existe, sans registre d'historique ni identifiant reliant l'ancien et le nouveau champ.

---

## 3. Qualité des données réelles (chiffres [V])

| Contrôle | Résultat |
|---|---|
| Dossiers (`dotation_forms`) | 34 : active 23, draft 5, returned 4, partial_return 1, awaiting_signature 1 ; types arrivée 16 / mise à jour 15 / sortie 2 / changement de service 1 ; bénéficiaires agent 24 / élu 10 |
| Entrées de ressource `additional` | 72 (0 code inconnu du catalogue ; 0 sans `fieldSchema` embarqué) |
| **Entrées dont les clés `fields` sont absentes du catalogue (orphelines)** | **31/72 (43 %)** dans **21/34 dossiers (62 %)** |
| Clés orphelines distinctes | `email.adresse` ×10, `ordinateur.nomPoste` ×10, `ordinateur.numeroSerie` ×10, `telephone.numeroSerie` ×10, `telephone.nomTelephone` ×9, `ecran.numeroSerie` ×1 (6 couples, 50 valeurs) |
| Entrées dont le `fieldSchema` embarqué diffère du catalogue | 33/72 |
| Champs requis vides **avant** alignement | 49 |
| Champs requis vides **après** alignement alias/schéma embarqué (logique de `align_payload_field_names`) | **18**, tous dans des dossiers `draft` (ordinateur_fixe 4, tablette 6, plaque de porte 3, clés 2, badge 1, zone d'alarme 1, photo 1) : légitimes (brouillons en cours), pas de la dérive. Donc **31 des 49 vides étaient de la dérive de clé et sont désormais résolus à la lecture** |
| Entrées avec `fields` vide alors que le catalogue en définit | 9 |
| Valeurs orphelines de `resource_units.fields_json` | 0 (alignées au resync) |
| Doublons d'identifiant en unités (`resource_code`, `identifier_norm`) | 0 (UNIQUE) |
| Doublons de n° de série entre dossiers (parmi 21 identifiants matériel sélectionnés) | 2 : ordinateur et téléphone, chacun dans 1 dossier `returned` + 1 `active` → cas normal de réattribution (vérifié : pas d'affectation simultanée) |
| `dotation_items` sans catalogue | 0 ; sans formulaire | 0 ; formulaires sans lignes | 0 |
| Statut `dotation_forms` vs colonnes de dates | cohérent (signature présente sur 23 active + 4 returned + 1 partial ; `returned_at` rempli pour tous les statuts, y compris draft = **5/5 draft avec `returned_at` non nul**, à expliquer [H : valeur par défaut ou date prévisionnelle]) |
| Statut `dotation_forms` ↔ `onboarding_dossiers` | 34/34 cohérents, mais 13 `onboarding_dossiers` orphelins de formulaire |
| `resource_units` | 18 : ordinateur 11 (assigned 8, degraded 1, in_stock 1, reserved 1), badge 4, ordinateur_fixe 1, écran 1, scanner 1 ; 0 unité sans dossier détenteur existant, 0 code hors catalogue |
| `source_form_id` orphelin | 20/22 |
| `dotation_item_selections` sans `dotation_items` | 51/51 |
| `field_suggestions` | 59 lignes, clés `modele` 19, `nomPoste` 10, `nomTelephone` 10, `marque` 8, `unc_chemin` 6, `zones` 6 : **`nomPoste` et `nomTelephone` sont les anciens noms** → les suggestions de saisie ne sont plus alimentées/retrouvées sous les nouvelles clés (`nom_du_poste`, `nom_du_telephone`) |
| Persons en doublon | 6 groupes |
| Bases vides parasites | 2 fichiers 0 octet |

Limite [H] : `dotation_items.details_json` n'a pas été analysé champ par champ (mélange de formats à plat / `fields`) ; le compte d'orphelins y est donc probablement du même ordre (≈ 30-50 lignes) mais non mesuré précisément.

Chiffres de la base : la vue de la base reflète l'état à la lecture (WAL inclus). Le correctif applicatif « alignement à la lecture » (`models/forms.py:437`) masque la dérive **sans réécrire** la base : les 31 entrées restent orphelines en stockage tant que `repair_orphan_fields` (`models/field_health.py:70`, exposé `routes/admin.py:1686-1707`) n'est pas exécuté.

---

## 4. Cycle de vie d'un champ de ressource et points de dérive

```
Admin (admin.js:660-700)          Catalogue                      Dossier                          Parc / stock              Export / PDF
libellé saisi ──slugify──> key ──> resource_catalog.field_schema_json ─> resources.additional[].fields{key:val}
 (clé figée à l'ouverture)          (normalize_resource_field_schema      + fieldSchema embarqué (copie)     │
                                     workflow.py:15 ; aliases,            + dotation_items.details_json      ├─> resource_units.fields_json
                                     hidden, identifier)                  (copie)                            │    (units.py sync_units_for_form:271)
                                                                                                             └─> stock (par code)
```

Points de dérive identifiés :
1. **Création** : clé = slug du libellé, donc le libellé détermine l'identité. Deux champs de même libellé donnent la même clé [H : non testé côté serveur]. Le slug est calculé à deux endroits (JS `admin.js:67`, Python `utils.py:57`), risque de divergence de règle d'accents/caractères.
2. **Renommage de libellé** : sans effet si l'UI garde `data-field-key` (`admin.js:696`). **Renommage de clé** (import, API, migration `migrate_builtin_resource_schemas` `catalog.py:328`, migration IMEI `:423`) : `carry_over_field_aliases` (`catalog.py:175`) devine l'appariement par libellé identique ou par position « en cas d'égalité de nombre » : heuristique, **pas d'identité**, et ne s'applique qu'à l'édition d'une ressource existante (`catalog.py:220`).
3. **Suppression de champ** : la valeur reste dans le payload des dossiers (orpheline), disparaît de l'affichage/PDF. Alternative « masquage » (`hidden`, `workflow.py:35`) existante mais **facultative** ; aucun champ masqué en base aujourd'hui.
4. **Snapshot embarqué** : `fieldSchema` recopié dans chaque entrée de dossier à chaque enregistrement ; fait foi pour l'affichage historique mais la lecture revient au catalogue actuel (source de la panne d'origine).
5. **Duplication dans `dotation_items.details_json`** et `resource_units.fields_json` : clés recalculées au resync (`units.py:380` `field_alignment_v1`), mais `dotation_items` non.
6. **Identifiant du parc** : `resolve_identifier_key` (`inventory.py:17`) choisit le champ identifiant parmi les clés ; verrou `identifier_locked` (`admin.py:1289`) empêche de changer/masquer/supprimer le champ identifiant s'il est utilisé. Bon garde-fou, mais il repose sur la clé (instable) et non sur un id.
7. **Suggestions** (`field_suggestions.field_key`) : indexées par clé brute → orphelines après renommage (constaté : 20 lignes sous d'anciens noms).
8. **Corbeille** (`deleted_items.payload_json`) : restauration réinjecte d'anciennes clés (13 formulaires + 1 ressource concernés) [H : chemin de restauration non audité].
9. **Import de sauvegarde** : restaure schémas et données d'un ancien état ; `ensure_users_schema` est rejoué mais pas de vérification catalogue/payload après import.
10. **Export/PDF** : dépendent de `fieldSchema` embarqué ou catalogue selon le chemin [H : non audité exhaustivement] ; toute clé absente du schéma disparaît silencieusement.

Ce qui existe déjà (non commité / récent) : `aliases` par champ + `align_fields`/`align_with_embedded_schema` (`inventory.py:34-90`), `align_payload_field_names` (`forms.py:437`), écran santé des champs (`models/field_health.py`, routes admin), verrous `code_locked`/`identifier_locked`. C'est une couche de **rattrapage** ; il manque la **cause racine** (identité de champ).

---

## 5. Recommandations (priorisées)

| # | Prio | Recommandation | Effort | Risque si non fait / risque du changement |
|---|---|---|---|---|
| 1 | **P0** | **`field_id` immuable** (UUID court généré à la création, jamais modifié) ajouté à chaque champ du catalogue ; `key` devient un simple « nom technique » modifiable. Migration : attribuer un `field_id` à chaque champ existant ; à l'enregistrement d'un dossier, écrire aussi `fieldIds` ou stocker `fields` par `field_id` (lecture double : `field_id` puis `key`/alias). Rejet côté serveur de toute modification/suppression d'un `field_id` existant. | M-L | Sans : dérive récurrente à chaque renommage. Changement : format de payload à double lecture, à tester sur les 34 dossiers |
| 2 | **P0** | **Réparer les données existantes** : exécuter `repair_orphan_fields` après sauvegarde (31 entrées / 21 dossiers), puis vérifier `scan_orphan_fields` = 0. Réaligner `dotation_items.details_json` et `field_suggestions` (migrer `nomPoste`→`nom_du_poste`, `nomTelephone`→`nom_du_telephone`). Poser un marqueur `parc_meta`. | S | Faible (idempotent, additif) ; à faire avec la sauvegarde d'abord |
| 3 | **P0** | **Interdire la suppression dure** d'un champ utilisé : forcer `hidden=true` (déjà supporté) côté serveur si `count_resource_field_usage > 0`, avec message clair ; conserver l'entrée dans le schéma. | S | Perte silencieuse de valeurs |
| 4 | **P1** | **Registre de schéma versionné** : table `resource_field_versions(resource_code, version, schema_json, created_at, actor)` alimentée à chaque modification du catalogue ; chaque dossier stocke `schemaVersion` au lieu (ou en plus) du `fieldSchema` complet. Lecture historique = schéma de la version, puis mapping vers le courant par `field_id`. | M | Réduit la taille des payloads (576 Ko dont fieldSchema répété) et supprime la classe de bug |
| 5 | **P1** | **Migrations formelles** : `PRAGMA user_version` ou table `schema_migrations(id, applied_at, checksum)` ; numéroter les migrations (fichiers `migrations/NNN_*.py`), toujours précédées d'une sauvegarde automatique ; sortir les 16 `ensure_column` et 23 `CREATE IF NOT EXISTS` d'`app.py`. | M | Aujourd'hui l'état de la base est déduit par introspection |
| 6 | **P1** | **Contrôle d'intégrité planifié** (tâche quotidienne + bouton admin, réutilisant le planificateur de sauvegarde) : `PRAGMA integrity_check/foreign_key_check`, clés orphelines (`scan_orphan_fields`), écarts `payload↔dotation_items↔resource_units`, champs requis vides sur dossiers non-draft, `source_form_id` orphelins, `onboarding_dossiers` sans formulaire, personnes en doublon ; résultat dans `app_logs` + alerte sur la page qualité. Ces 8 contrôles reprennent les constats du §3 (chiffres de référence). | M | Détection précoce |
| 7 | **P1** | **FK et nettoyage** : `source_form_id` avec `ON DELETE SET NULL` ; nettoyage des 20 liens morts ; supprimer `dotation_item_selections`, `shared_pool*`, `is_pool_resource`, `dotation_items.serial_number/resource_type` (après sauvegarde et vérification qu'aucun code ne les lit) ; supprimer les 2 fichiers `.db` vides. | S-M | Réduit les faux signaux |
| 8 | **P1** | **Source de vérité unique des valeurs** : `payload_json` reste maître ; `dotation_items.details_json` et `resource_units.fields_json` deviennent des projections recalculées (fonction unique de « resync » appelée à l'enregistrement, au restore et au démarrage), avec test de cohérence. | M | Divergence |
| 9 | **P1** | **Clés de suggestion** : indexer `field_suggestions` par `(resource_code, field_id)` au lieu de `field_key` brut. | S | Suggestions perdues après renommage |
| 10 | **P2** | **Dictionnaire de données** généré (page admin + fichier `docs/`) : table, colonne, type, source de vérité, propriétaire, règle de rétention (schéma JSON documenté pour `payload_json`, `details_json`, `field_schema_json`). Le générer depuis un schéma JSON unique validé (jsonschema) à l'écriture. | M | Onboarding, audit |
| 11 | **P2** | **Validation à l'écriture** : valider `payload_json` contre un schéma (jsonschema) et refuser les clés hors schéma (ou les classer en `extras`) ; empêcher la collision de clés (deux champs même slug) au niveau serveur ; centraliser `slugify_field_key` (une seule règle, JS appelle l'API ou table de test partagée). | M | Dette de règles doublées |
| 12 | **P2** | **Index** sur `dotation_items(form_id)`, `dotation_items(item_key)`, `dotation_forms(dossier_id)`, `onboarding_dossiers(person_id)`, `audit_events(dossier_id)`, `signature_links(form_id)`, `app_logs(created_at)`. | S | Perf à 10× le volume |
| 13 | **P2** | **Personnes** : contrainte/règle d'unicité (nom, prénom, service ou identifiant externe) + outil de fusion ; sortir `signature_data` base64 dans une table dédiée. | M | Doublons, poids |
| 14 | **P2** | **Sauvegarde** : test de restauration automatique (restaurer dans un fichier temporaire + `integrity_check` + contrôles §6), rétention documentée, sauvegarde automatique avant toute migration de données. | M | Confiance dans la restauration |

### Stratégie d'évolution du schéma sans perte (proposée)
1. Toute modification du catalogue = nouvelle **version** immuable dans le registre (rec. 4).
2. Champ identifié par `field_id` ; renommage = modification de `label` et/ou `key` avec conservation automatique de l'ancienne clé en alias (déjà en place) **et** rattachement par `field_id` (plus d'heuristique).
3. Suppression = passage en `hidden` (jamais d'effacement de valeur) ; purge réelle uniquement via un outil admin explicite, journalisé, après export.
4. Changement de type (texte → liste) = nouveau champ + migration assistée, ancien masqué.
5. Migration de données : script numéroté, idempotent, précédé d'une sauvegarde, suivi de `scan_orphan_fields = 0` et du contrôle de cohérence ; échec = rollback fichier.
6. Restauration (corbeille/import) : repasser par le même alignement avant écriture.

## 6. Limites de cet audit
- Base lue à l'instant T (WAL inclus, serveur en fonctionnement) ; chiffres susceptibles d'évoluer.
- Non audité : `details_json` champ par champ, chemins d'export PDF/Excel (`backend/pdf`), restauration corbeille, `users.db` au-delà des volumes, conformité RGPD des durées de rétention.
- Les causes exactes des écarts `payload↔dotation_items` (27/34 égalité sélectionnés/assignés, 7/34 égalité totale) et des `returned_at` non nuls sur draft sont des hypothèses.

---

# PARTIE 2 — Full stack et personnalisation
# Audit full stack : personnalisation « de bout en bout » de À Quai

Périmètre : `C:\www\dotation` (branche `dev`, arbre de travail avec correctifs non commités sur `models/inventory.py`, `models/forms.py`, `models/catalog.py`, `models/field_health.py`, etc.). Audit en **lecture seule**. Seules deux commandes Python pures et sans effet de bord ont été exécutées (`slugify_field_key`, `carry_over_field_aliases`) pour confirmer deux comportements.

Légende : **[V]** = vérifié (lu dans le code, ou exécuté quand c'est précisé) ; **[S]** = supposé / non exécuté de bout en bout.

---

## 1. Cartographie

### 1.1 Couches

| Couche | Fichiers principaux | Rôle |
|---|---|---|
| Routes Flask | `backend/routes/{admin,forms,units,stock,inventory,signature,org_wizard,pages,db_backup,...}.py` | API JSON + pages |
| Modèles | `models/catalog.py` (seed + normalisation catalogue), `workflow.py` (schéma de champs, items, statuts), `forms.py` (persistance dossier), `inventory.py` (clés, alignement), `units.py` / `units_extra.py` (parc), `stock.py` (quantités), `resource_rules.py` (règles catalogue), `settings.py` (réglages, thèmes, types de bénéficiaires), `org_presets.py` / `org_wizard.py` (assistant), `field_health.py` (réparation), `dossier.py` (personne + dossier) | Métier |
| Utilitaires | `backend/utils.py` (libellés statuts, types de dossier, slug), `permissions.py`, `auth.py` | Transverse |
| Frontend | `form.html` + `js/app.js` (3408 l.), `admin*.html` + `js/admin*.js`, `restitution*.html/js`, `parc*.js`, `storage.js` (3073 l., liste/tableau de bord), `executive-dashboard.js`, `global-search.js` | UI en JS vanilla |

### 1.2 Flux d'une ressource personnalisée

1. **Admin** (`admin.js` ~l.552-717, `admin-resource-wizard.js`) : édition du schéma. La clé technique d'un champ est **figée dans le DOM** (`data-field-key`, `admin.js:552,697`) ; seule une création dérive la clé du libellé.
2. **API** `POST/PUT /api/admin/resources` (`routes/admin.py:1180,1247`) : `normalize_resource_catalog_payload` (`catalog.py:202`) → `normalize_resource_field_schema` (`workflow.py:15`) → `validate_resource` (`resource_rules.py:26`). Garde-fous : `code_locked`, `identifier_locked` (`admin.py:1274-1289`). Stockage : `resource_catalog.field_schema_json`.
3. **Catalogue** exposé par `GET /api/reference/resources` (`admin.py:691`, enrichi par `database.py:75-82` : `field_schema`, `identifier_key`, `effective_tracking_mode`).
4. **form.html / app.js** : rendu 100 % piloté par `resource.field_schema` (`app.js:923-956`, `buildDynamicFieldInput` ~l.500-530). Champs masqués → `<input hidden>`. Collecte `buildAdditionalResourcesPayload` (`app.js:1085-1120`) : `fields` = orphelins conservés + valeurs du schéma courant ; le dossier **embarque `fieldSchema`** (instantané).
5. **Enregistrement** `persist_form` (`models/forms.py:257`) : le serveur stocke le payload **tel qu'envoyé** dans `dotation_forms.payload_json`, **aplatit** en `dotation_items` (`workflow.py:extract_items` l.251-…, `details_json`), puis appelle `sync_units_for_form` (parc), `sync_stock_for_form` (quantités), `_upsert_field_suggestions`. Aucune validation serveur des `fields` contre le schéma.
6. **Lecture** `get_form` → `align_payload_field_names` (`forms.py:437`, appelé l.564) : ajoute les valeurs sous les noms courants (jamais retirer/écraser).
7. **Parc / unités** : `unit_identifier_keys` (`units.py:176`) + `align_fields`; identité = valeur normalisée du champ identifiant ; tables `resource_units`, `resource_unit_aliases`, journal d'événements.
8. **Restitution** : `extract_items` (états par `item_key`), `derive_restitution_workflow_status` (`workflow.py:473`), PDF `pdf/restitution.py`, signature.
9. **Exports** : Excel XML `routes/forms.py:55-175`, PDF `pdf/attribution.py` / `restitution.py`, CSV services/parc. Le détail des ressources passe par `summarize_dynamic_resource` (`workflow.py:~55`) qui utilise **le `fieldSchema` embarqué** dans le dossier (libellé d'époque).
10. **Dashboard / synthèse** : `admin.py:101` (`dashboard-stats`), `executive-dashboard.js`, `storage.js` : agrégats sur `dotation_forms.status`, `beneficiary_type`, `dossier_type`.

### 1.3 Duplication de la donnée d'un champ (3 à 4 copies) [V]

| Copie | Où | Mise à jour |
|---|---|---|
| Payload dossier | `dotation_forms.payload_json` (`resources.additional[].fields` + `fieldSchema`) | à chaque save |
| Vue à plat | `dotation_items.details_json` | reconstruite à chaque save (`forms.py` DELETE+INSERT) |
| Résumé texte | `details` (JS `summarizeDynamicResource`, `app.js:675`, valeurs sans libellé) | à chaque save, figé |
| Parc | `resource_units` (identifiant + champs) | `sync_units_for_form` |

`repair_orphan_fields` (`field_health.py:_walk`, l.~55-60) ne met à jour **que** `payload_json`, pas `dotation_items.details_json` : les deux copies divergent jusqu'au prochain enregistrement du dossier [V par lecture].

---

## 2. Inventaire du codé en dur (à rendre configurable)

Couplage : **fort** = casse si on change la valeur ; **moyen** = comportement dégradé ; **faible** = cosmétique.

### 2.1 Codes de ressources spéciaux et modèle « legacy »

| Élément | Emplacement | Couplage | Commentaire |
|---|---|---|---|
| Liste figée de 13 ressources « statiques » (`ordinateur`, `ecran`, `telephone`, `tablette`, `vehicule`, `badge`, `cles`, `veste`, `chaussuresSecurite`, `autre`, `vpn`, `email`, `zoneAlarme`) avec libellés | `workflow.py:251-263` (`extract_items`) | **Fort** | Second modèle de données (`payload.materiel.*` / `payload.immateriel.*`) parallèle à `resources.additional`. Toute ressource ajoutée est « additional ». |
| Règles de complétude par ressource legacy (champs requis en dur, `cles.values`, `zoneAlarme.zones`) | `workflow.py:386-442` (`collect_resource_validation_errors`) | **Fort** | Duplique les `required` du catalogue. |
| `CORE_RESOURCE_CODES` | `catalog.py:7-23` | Moyen | Sert d'ensemble « intouchable ». |
| Seed catalogue avec clés camelCase (`nomPoste`, `numeroSerie`, `nomTelephone`…) | `catalog.py:30-160` | **Fort** (origine de la dérive, voir §3) | |
| 5 migrations ad hoc par code de ressource (`migrate_telephone_imei_field`, `migrate_suggest_flags`, `migrate_cartes_visite_quantite`…) | `catalog.py:354-525` | Moyen | Aucune numérotation de version ; rejouées à chaque démarrage [S : appelées depuis `app.py`, non relu]. |
| Presets par code builtin (`vpn`, `email`, `vehicule`) | `org_presets.py:9-64` | Moyen | |
| Assistant ressources JS : gabarits `telephone`, `badge`, `cles` | `admin-resource-wizard.js:9-40` | Faible | Gabarits légitimes mais dupliqués côté JS et `org_presets.py`. |
| Code mort JS `clesRows` / `zoneAlarmeRows` (aucun élément dans `form.html`) | `app.js:1528-1535` | Faible | Reliquat du modèle legacy. |

### 2.2 Champs spéciaux (identifiant, quantité, variante)

| Élément | Emplacement | Couplage |
|---|---|---|
| `PREFERRED_IDENTIFIER_KEYS = ("numeroSerie","numeroserie","numero_de_serie","immatriculation","numero","identifiant")` : repli devinette de l'identifiant | `inventory.py:11` | **Fort** |
| `QUANTITY_KEYS`, `VARIANT_KEYS` (`quantite/quantity/nombre`, `taille/pointure/variante`) : repli par nom de clé | `stock.py:26-27`, `resource_rules.py:~63` | **Fort** |
| **Les drapeaux `quantity` et `variant` n'existent pas dans le schéma** : `normalize_resource_field_schema` (`workflow.py:15-45`) ne les conserve pas alors que `_pick_key(schema,"quantity",…)` (`stock.py:67`) et `resource_rules.py` les lisent [V] | | **Fort** : le repli par nom de clé est donc la seule voie ; un champ « Nombre de cartes » ne sera jamais la quantité. |
| Suggestions : ensembles de clés `{"marque","modele","nomPoste","nomTelephone","nomTablette"}` et `{"zones"}` alors que `field.suggest` existe déjà | `forms.py:26-27` | **Fort** : la table `field_suggestions` n'est alimentée que si la clé est camelCase historique ; les clés slugifiées (`nom_du_poste`) sont ignorées [V par lecture]. |
| Types de champs autorisés (8) | `workflow.py:16` ; rendu switch JS `app.js:~500-560` ; `list` et `email_with_domain` codés à part `app.js:2073-2086` | Moyen |
| Heuristique « loose » de correspondance (préfixe, `numero`→`n`) | `inventory.py:93-98` | Moyen : devinette, uniquement en affichage, mais peut rattacher la mauvaise valeur si deux champs partagent un préfixe (ambiguïtés ignorées, `len(candidates)==1`). |

### 2.3 Statuts, types de dossier, états

| Élément | Emplacement | Couplage |
|---|---|---|
| Statuts de workflow (`draft`, `partial_assignment`, `awaiting_signature`, `active`, `partial_return`, `returned`, `cancelled`) : machine d'états impérative | `workflow.py:473-575` | **Fort** |
| Statuts dossier dérivés (`a_preparer`, `en_preparation`, `en_signature`, `actif`, `partiellement_complete`, `en_restitution`, `clos`) | `workflow.py:539-570` | **Fort** |
| Libellés de statut **dupliqués** : 1 fois Python (`utils.py:198`) + au moins 8 fois JS : `app.js:1637,2576`, `executive-dashboard.js:10-37` (libellés + 2 palettes), `global-search.js:15,105`, `parc-check.js:5`, `restitution.js:654`, `restitution-phase1.js:113`, `storage.js:37,2926` | | **Moyen** (dérive garantie à chaque nouveau statut) |
| Types de dossier (`arrivee`, `changement_service`, `mise_a_jour`, `sortie`) : `utils.py:108`, `utils.py:130-140` (mapping qui **renvoie `arrivee` pour toute valeur inconnue**), `app.js:63`, `form.html:92-94` (options HTML en dur), `executive-dashboard.js:18`, `admin.py:56` | | **Fort** |
| États de restitution (`pending`, `returned`, `returned_damaged`, `missing`, `transferred`, `conforme`, `degrade`, `non_restitue`, `perdu`, `autre`) — trois vocabulaires qui se chevauchent | `utils.py:211`, `workflow.py:~150` (`returned` = ensemble en dur), `inventory.py:12-13` (`READY_CONDITIONS`, `DEGRADED_CONDITIONS`) | **Fort** : la définition du « rendu réutilisable » est en dur. |
| États à la remise (`neuf`, `bon_etat`, `etat_usage`, `degrade`) | `utils.py:248` + `<select>` HTML/JS | Moyen |
| Statuts de parc `PARC_STATUS` (réservé, attribué, réparation…) | `parc.js:4-9` + `units.py` | Moyen |
| Accès UNC (`lecture`, `lecture_ecriture`, `refuse`, statuts `demande/en_cours/provisionne`) | `forms.py:162-163`, `admin-home.js:56` | Faible |
| Motifs de sortie (ex. `fin_de_mandat`) | `app.js:1671` | Faible |

### 2.4 Bénéficiaires

| Élément | Emplacement | Couplage |
|---|---|---|
| Types de bénéficiaires configurables **mais stockés en chaîne « valeur:Libellé,… »** (séparateurs interdits dans les libellés) | `settings.py:34,44-54,238-263` | Moyen : format fragile, pas d'attributs par type. |
| **`"elu"` spécial** : titre = mandat, bloc Mandat, mandat requis | `utils.py:123`, `forms.py:507`, `routes/forms.py:595,618`, `admin.py:169`, `app.js:210-213,1552-1604,2803`, `form.html:152-161` | **Fort** : un type personnalisé ne peut pas porter un champ supplémentaire. |
| **`routes/forms.py:595`** : `qualite = "elu" if … else "agent"` → tout type personnalisé enregistré par cette route (brouillon rapide) est **rétrogradé en `agent`** [V par lecture] | | **Fort** (bug de perte) |
| `format_beneficiary_label` : uniquement `agent`/`elu`, ignore les types configurés | `utils.py:190-195` | Moyen : exports Excel/PDF affichent l'identifiant brut pour un type personnalisé [V]. |
| Options de mandat en dur (Maire, Adjoint(e)…) | `form.html:156-159` | Moyen (HTML dupliqué, contre la préférence utilisateur) |
| Préréglages métier par contexte d'organisation | `org_presets.py`, `settings.py:41` (`VALID_ORG_CONTEXTS`) | Faible (déjà des données) |

### 2.5 Seuils, durées, catégories

| Élément | Emplacement | État |
|---|---|---|
| `restitution_phase1_unlock_days`, `timing_warning_days`, `parc_retention_years` | `settings.py:36-38` | **Déjà configurables** (bon modèle) |
| `RESERVATION_DAYS = 30` (libération des réservations) | `units.py:24`, repris par `stock.py:190` | **En dur** |
| Seuil de stock bas | par ressource (`threshold` dans `stock.py:249`) | Configurable |
| Catégories `materiel` / `immateriel` (2 valeurs, avec règles : pas d'état à la remise pour l'immatériel, restitution réservée au matériel) | `catalog.py:213-214,236-237`, `workflow.py:is_restitution_eligible_material_details`, `resource_rules.py` | **Fort** |
| Modes de suivi `unit/none/access/quantity` | `resource_rules.py:14`, `catalog.py:242` | Moyen (bien centralisé) |
| Ordre des statuts pour tri | `storage.js:37` | Faible |

### 2.6 Permissions, groupes, textes

| Élément | Emplacement | Couplage |
|---|---|---|
| `DEFAULT_GROUPS` (7 groupes) et 12 permissions ; `ROUTES_REQUIRED_PERMISSIONS` n'est qu'un contrôle de cohérence | `permissions.py:4-30` | Moyen : groupes livrés en dur, mais stockés (`user_groups`, `/api/admin/groups`) donc partiellement modifiables. Les décorateurs `@permission_required("users.manage")` sont en dur par route (normal). |
| Textes d'e-mails : aucun envoi SMTP trouvé (`grep smtplib/Subject` négatif) ; seuls des `mailto:` / e-mails de support/DPO configurables | [V] | Rien à extraire côté serveur ; les gabarits `docs/emails/` sont hors application. |
| Textes de PDF (titres, mentions RGPD, sections) | `pdf/attribution.py`, `pdf/restitution.py`, `forms.py:144-210` | Moyen : pas de libellés éditables (titre « DOSSIER D'ATTRIBUTION DE RESSOURCES », « Ressources attribuees »…). |
| Libellés de la navigation et des aides | `help.js` (460 l.), `admin-nav.js` | Faible |
| Thèmes | `settings.py:56-…` (`THEME_PRESETS`) + `branding.js` | **Déjà en données** ; pas de thème personnalisé importable. |
| i18n | Aucune infrastructure : libellés français en dur partout (~JS et Python) | Moyen |

---

## 3. Utilisation des clés de champ et risque de dérive

### 3.1 Cause racine [V, exécuté]

- Le seed écrit des clés camelCase brutes (`catalog.py:30-160`, insertion sans normalisation `catalog.py:258-285`).
- Au premier `PUT /api/admin/resources/<id>`, `normalize_resource_field_schema` applique `slugify_field_key` (`utils.py:57`) qui **passe en minuscules** : `slugify_field_key("numeroSerie")` → `numeroserie` ; `nom_du_poste` reste identique. Donc **une simple sauvegarde du catalogue change silencieusement la clé** (`numeroSerie` → `numeroserie`) sans que l'utilisateur ait touché au champ.
- La **fonction de slug existe en deux versions divergentes** : Python `slugify_field_key("N° de série")` → `n__de_serie` (double soulignement) ; JS `slugifyFieldKey` (`admin.js:67`) → `n_de_serie` (collapse `[^a-z0-9]+`). Un champ créé par l'assistant JS et normalisé par Python peut donc obtenir deux clés différentes selon le chemin (l'API réenregistre `key` fourni, donc la clé JS gagne quand elle est envoyée, mais l'assistant et l'import n'envoient pas toujours la clé) [V pour la divergence, S pour l'impact selon chemin].
- La réparation actuelle (`canonical_key`, alias, `align_with_embedded_schema`) est une **couche de rattrapage à la lecture**, non une clé stable.

### 3.2 Bug vérifié : les alias sont perdus à la sauvegarde suivante

`carry_over_field_aliases` (`catalog.py:175-198`) ne reporte les alias que pour des paires « champ retiré / champ ajouté ». L'éditeur admin n'envoie pas `aliases` (`admin.js:707-716`). Test exécuté : ancien schéma `{key: nom_du_poste, aliases:[nomPoste]}`, nouveau schéma identique sans `aliases` → résultat `aliases: []`. **Les alias déclarés disparaissent dès qu'on enregistre à nouveau la ressource sans toucher à ce champ** ; les dossiers dépendant de l'alias redeviennent illisibles (sauf repli `loose`/libellé embarqué). Sévérité P0 (perte silencieuse du filet de sécurité).

### 3.3 Matrice étape par étape

| Étape | Code | Mécanisme de clé | Risque de dérive / perte | Statut |
|---|---|---|---|---|
| **Création de champ** | `admin.js:697`, `workflow.py:15` | slug JS puis re-slug Python | Deux slugifieurs divergents (§3.1) | Moyen [V] |
| **Renommage libellé** | `admin.js:552` | clé figée côté UI | OK côté UI ; l'API accepte une clé différente n'importe quand (aucun contrôle serveur d'immuabilité) | Moyen [V] |
| **Renommage de clé (via API/JSON)** | `catalog.py:175` | alias auto si appariement libellé/position | Devinette par position si autant d'ajouts que de retraits ; alias perdus ensuite (§3.2) | Élevé [V] |
| **Seed camelCase → slug** | `catalog.py` + `workflow.py:31` | minuscules | Changement de clé silencieux à la première sauvegarde | Élevé [V] |
| **Suppression de champ** | UI d'usage `admin.py:1383` + `count_resource_field_usage` (`workflow.py:180`) | compare `k.lower() == field_key.lower()` | Compte sous-estimé : ne connaît ni alias ni forme canonique (`nomPoste` vs `nom_du_poste`) ; `is_dynamic…` | Élevé [V] |
| **Masquage** | `hidden` (`workflow.py:36`), input hidden (`app.js:928`) | clé conservée | Bonne pratique. Risque : identifiant masqué → parc muet (couvert par `resource_rules`) | Faible |
| **Lecture dossier** | `align_payload_field_names` (`forms.py:437`) | canonique + alias + libellé embarqué + loose | Additive, correcte ; `loose` devine | Faible/Moyen |
| **Formulaire (population)** | `app.js:1120-1200` | `FIELD_LEGACY_KEYS = {imei:"numeroSerie"}` **en dur** dans le JS ; orphelins conservés | Logique d'alignement **dupliquée JS / Python** (deux implémentations différentes) ; le JS ne connaît ni alias ni canonique | Moyen [V] |
| **Écriture dossier** | `persist_form` (`forms.py:257`) | aucune validation des clés côté serveur | Un client obsolète / un import peut écrire n'importe quelles clés ; c'est désormais le client qui préserve les orphelins ; **aucune garantie serveur** | Élevé [V] |
| **Aplatissement** | `extract_items` | recopie `details` | Copies désynchronisées après réparation (§1.3) | Moyen [V] |
| **Parc/unités** | `units.py:176,278-298,417`, `align_fields` non `loose` | identifiant par `resolve_identifier_key` + canonique | Si l'identifiant est renommé et que l'alias est perdu (§3.2), l'unité perd son identité ; `identifier_locked` protège seulement le retrait | Élevé [V] |
| **Stock quantité/variante** | `stock.py:26-27,67` | noms de clés `quantite/taille…` | Fonctionne seulement si le champ porte un de ces noms ; drapeaux absents du schéma | Élevé [V] |
| **Suggestions** | `forms.py:26-27,30-66` | clés camelCase en dur | Silencieusement inactif pour les clés slugifiées (route catalogue `admin.py:617` lit bien `suggest`, deux implémentations) | Moyen [V] |
| **Exports Excel/PDF** | `summarize_dynamic_resource` | schéma **embarqué** + comparaison minuscule | Robuste (libellé d'époque). Valeurs hors schéma rendues sans libellé. Aucun export « par colonne de champ » : rien à casser, mais pas d'export structuré non plus | Faible [V] |
| **Import CSV parc** | `units_extra.py:100-135` | mappe colonnes → clés via libellé / clé nue | Correct, dépend des libellés | Moyen [S] |
| **Import/export base** | `admin.py:1637-1750` | copie brute SQLite | Pas de vérification de version de schéma de champs | Moyen [S] |
| **Assistant d'organisation** | `org_wizard.py:158-217` | génère clés à partir des libellés | Ajout seulement (bon) ; même slugifieur Python | Faible |
| **Restitution** | `restitution.js:75`, `extract_items` | `item_key = code` ressource | Le **code** de ressource est verrouillé après usage (`code_locked`) : bon | Faible |
| **Réparation** `field_health` | `field_health.py` | additive, sauvegarde préalable | Ne met pas à jour `dotation_items` ; `loose` peut réparer sur une mauvaise cible | Moyen [V] |

### 3.4 Tests existants sur ce thème [V]

`tests/test_field_aliases.py` (5), `tests/test_form_legacy_fields.py` (6), `tests/test_inventory.py`, `test_resource_rules.py`, `test_units.py`, `test_stock.py`, `_http_scenarios.py`. **Manquent** : (a) idempotence « lecture → sauvegarde » d'un dossier sans perte de clé ; (b) sauvegarde du catalogue deux fois de suite conserve clés + alias ; (c) parité slug Python/JS ; (d) suggestions avec clés slugifiées ; (e) type de bénéficiaire personnalisé de bout en bout (brouillon rapide, export, titre) ; (f) tous les seeds passent `normalize_resource_field_schema` sans changer leurs clés.

---

## 4. Dette et robustesse

| Sujet | Constat | Réf. |
|---|---|---|
| **Validation serveur vs client** | Le catalogue est bien validé côté serveur (`resource_rules.validate_resource`, types autorisés, unicité). En revanche le **contenu des dossiers n'est pas validé** (clés, types, `required`, options `select`) : la règle « champ requis » n'existe que dans le JS (`app.js:724-729`) et, pour les ressources legacy, en Python (`workflow.py:386-442`). | `forms.py:257`, `workflow.py:386` |
| **Duplication de règles JS/Python** | slug (2 versions) ; alignement de clés (JS `FIELD_LEGACY_KEYS` vs Python `align_fields`) ; résumé de ressource (`app.js:675` sans libellés vs `workflow.py` avec libellés) ; complétude (`is_dynamic_resource_complete` Python vs `app.js:724`) ; libellés statuts (9 copies) ; types de dossier (6 copies) ; titre de dossier (`utils.py:build_title` vs `forms.py:507` : logique `elu` copiée). | voir §2 |
| **Versions de schéma** | Aucun `schema_version` sur les champs ni les dossiers ; aucun `PRAGMA user_version` ; migrations = fonctions idempotentes rejouées au démarrage sans registre (`catalog.py:354-525`). Le dossier embarque `fieldSchema` (instantané utile) mais sans identifiant de version ni identifiant de champ stable. | grep négatif [V] |
| **Identifiants de champ** | Clé = slug du libellé (donc lisible, modifiable, dépendant de la casse et du slugifieur). Pas d'ID technique immuable (`fld_xxx`) distinct de la clé d'affichage. | `workflow.py:26` |
| **Modèle de données double** | `payload.materiel/immateriel` vs `resources.additional` ; `persist_form` supprime les anciennes clés si `additional` a du contenu (`forms.py:~262-273`) ; `derive_dossier_status` lit encore `materiel`/`immateriel` (`workflow.py:539-560`). | |
| **Base de données** | Configuration sous forme de chaînes (types de bénéficiaires), de JSON dans des colonnes (`field_schema_json`) ; pas de contrainte d'intégrité entre `dotation_items.item_key` et `resource_catalog.code` (garde-fou applicatif seulement). | `settings.py:34`, `admin.py:1274` |
| **Extensibilité** | Aucun mécanisme de hooks/plugins/événements ; les blueprints Flask sont auto-découverts (`routes/__init__.py`) mais les règles métier sont impératives. API REST propre mais non versionnée (`/api/…` sans `v1`) et sans schéma OpenAPI. | [V] |
| **Types de champs** | 8 types, ajout d'un type = modifier `workflow.py:16`, `app.js:~500-560`, l'éditeur admin, l'export, la complétude (5 endroits). Pas de registre. | |
| **Thèmes** | Bon : presets en données + jetons de couleur, audit de contraste (tests navigateur). Pas de thème utilisateur importable/validé. | `settings.py:56` |
| **i18n** | Français en dur, accents dans le code Python et JS ; libellés de champs et de ressources déjà en base (bon), mais tout le chrome et les messages d'erreur non. | |
| **Tests** | 318 tests Python d'après le rapport de nuit ; **aucun test JS unitaire** (pas de runner) ; tests navigateur par scripts ad hoc (`tests/browser/*.py`, certains sont des sondes GitHub à ne pas laisser dans la suite). | |
| **Suppression de données** | Suppression de ressource et corbeille existent (`admin.py:1347,793`) ; suppression de champ bloquée par comptage faux (§3.3). | |

---

## 5. Recommandations priorisées

Effort : S ≤ 1 jour, M ≤ 1 semaine, L > 1 semaine. Risque = risque de régression de la mesure.

| # | Priorité | Recommandation | Effort | Risque | Justification |
|---|---|---|---|---|---|
| 1 | **P0** | **Ne plus perdre les alias** : `normalize_catalog_payload` doit toujours fusionner les alias de l'ancien schéma par clé identique (`aliases` = ancien ∪ nouveau) ; l'éditeur admin doit renvoyer `aliases` ; test « 2 sauvegardes consécutives ». | S | Faible | Bug vérifié §3.2. |
| 2 | **P0** | **Figer les clés existantes côté serveur** : à la mise à jour, une clé déjà présente dans l'ancien schéma est immuable (si le payload propose une autre clé pour le même champ, la refuser ou l'ignorer). Ne plus re-slugifier une clé déjà valide (conserver la casse du seed). | S | Faible | Supprime la cause racine §3.1 (camelCase → minuscules). |
| 3 | **P0** | **Une seule fonction de slug** (Python) exposée au JS (endpoint `/api/util/slug` ou constante partagée) + test de parité ; corriger le double `_`. | S | Faible | §3.1 |
| 4 | **P0** | **`routes/forms.py:595` et `format_beneficiary_label`** : accepter tout type de bénéficiaire configuré (valider contre `beneficiary_types`), libellés issus de la configuration ; remplacer le test `== "elu"` par un attribut de type (`requires_mandate`). | S-M | Faible | Perte/rétrogradation de type personnalisé. |
| 5 | **P0** | **Corriger le comptage d'usage** `count_resource_field_usage` pour utiliser `align_fields` (alias + canonique) et propager le même filtre à l'API d'usage ; test. | S | Faible | Risque de suppression de valeurs en croyant le champ inutilisé. |
| 6 | **P1** | **Validation serveur des dossiers** (clés connues ou alias, `required`, types, options) en mode « avertissement journalisé » puis « refus », avec conservation explicite des orphelins dans `fields_extra`. | M | Moyen | Le serveur redevient garant de l'intégrité au lieu du client. |
| 7 | **P1** | **Identifiants de champ immuables (`field_id`)** : ajouter `id` (ex. `fld_` + UUID court) à chaque champ ; les valeurs des dossiers restent indexées par `key` mais l'appariement passe par `id` via le `fieldSchema` embarqué (qui contiendrait l'id). Migration : attribuer un id à chaque champ existant (par code + clé) et l'écrire dans le schéma. | M-L | Moyen | Remplace tout le dispositif canonique/alias/loose par une correspondance exacte. |
| 8 | **P1** | **Drapeaux `quantity` / `variant` (et `identifier`) conservés dans le schéma** : les ajouter à `normalize_resource_field_schema`, à l'éditeur admin, et supprimer les listes `QUANTITY_KEYS`, `VARIANT_KEYS`, `PREFERRED_IDENTIFIER_KEYS` (migration qui pose les drapeaux depuis les noms actuels). | M | Moyen | §2.2 |
| 9 | **P1** | **Suggestions pilotées par `field.suggest`** dans `_upsert_field_suggestions` (au lieu de `_SUGGEST_*`). | S | Faible | §2.2/3.3 |
| 10 | **P1** | **Registre de types de champs** (Python + un JSON exposé au JS) : `{type, label, valider, rendre, résumer, vide?}`. Un seul point d'ajout d'un type. Côté JS : table `FIELD_RENDERERS` (préférence utilisateur pour des définitions objet). | M | Moyen | §4 |
| 11 | **P1** | **Vocabulaires en données servis par l'API** (`/api/vocab`) : statuts, types de dossier, états de restitution/parc, états à la remise, motifs de sortie, mandats — libellé, couleur, ordre, drapeaux (`terminal`, `réutilisable`, `compte comme rendu`). Le JS et `utils.py` en dérivent ; suppression des 9+6 copies. | M | Faible-Moyen | §2.3 |
| 12 | **P1** | **Tests de contrat** : schéma JSON des payloads (dossier, catalogue), test « aller-retour » (charger un dossier ancien → sauvegarde → aucune clé perdue), test « chaque seed traverse `normalize` intact », tests JS avec un runner léger (Vitest/`node --test`) sur la logique pure (résumé, alignement, complétude). | M | Faible | §3.4 |
| 13 | **P1** | **Synchroniser `field_health.repair`** avec `dotation_items` (recalcul via l'aplatissement) ; supprimer la copie `details` stockée ou la régénérer à la lecture. | S | Faible | §1.3 |
| 14 | **P2** | **Migration du modèle legacy** : convertir `materiel/immateriel` en `resources.additional` (une passe versionnée, sauvegarde préalable), puis supprimer `extract_items` legacy, `collect_resource_validation_errors` par code, et le JS mort. | L | Élevé | Le plus gros gain de simplification, mais touche l'historique. |
| 15 | **P2** | **Moteur de workflow déclaratif** : états, transitions, gardes (`signature présente`, `toutes ressources complètes`), dérivé du statut de dossier — défini en JSON (avec un jeu par défaut identique à aujourd'hui) et évalué côté serveur uniquement ; le JS lit l'état et les actions autorisées. | L | Élevé | §2.3 ; à faire après 11 et 14. |
| 16 | **P2** | **Types de bénéficiaires structurés** (table ou JSON : `id`, `libellé`, `champs supplémentaires`, `requires_mandate`) remplaçant la chaîne `valeur:Libellé`. Mandats = liste d'options du type. | M | Moyen | §2.4 |
| 17 | **P2** | **Versionnement de schéma** : `PRAGMA user_version` + table `schema_migrations`, migrations numérotées ; `schema_version` dans le payload dossier ; refus/avertissement à l'import d'une base plus récente. | M | Faible | §4 |
| 18 | **P2** | **Paramétrage exportable/importable** (JSON signé : catalogue, services, bénéficiaires, thèmes, libellés) pour reproduire un environnement (déjà noté « non fait » dans le rapport de nuit). | M | Faible | |
| 19 | **P2** | **Gabarits de documents (PDF/e-mail)** en données (titres, mentions, ordre des sections) avec variables ; textes RGPD éditables et versionnés. | M | Moyen | §2.6 |
| 20 | **P2** | **i18n** : extraire les libellés Python/JS vers un catalogue par langue (`fr` par défaut) après les vocabulaires (11). | L | Moyen | |
| 21 | **P2** | **Extensibilité** : bus d'événements interne (`form_saved`, `unit_synced`, `resource_updated`) + points d'extension documentés ; versionner l'API (`/api/v1`) et publier un schéma OpenAPI. | L | Moyen | |
| 22 | **P2** | Externaliser les constantes restantes (`RESERVATION_DAYS`) vers `app_settings` (déjà le modèle utilisé pour trois autres seuils). | S | Faible | §2.5 |

### Ordre d'exécution conseillé
1. P0 n°1, 2, 3, 5 (un seul lot correctif, tests inclus) puis n°4.
2. n°8, 9, 13 (drapeaux et suggestions, petits gains).
3. n°6 + 12 (validation et filet de tests) avant toute refonte.
4. n°7 (identifiants immuables) pour rendre les rattrapages (canonical/alias/loose) supprimables.
5. n°11, 10, 16 (vocabulaires, registre de types, bénéficiaires) : rendu piloté par définitions objet, conforme à la préférence utilisateur.
6. n°14, 15, 17 en dernier (impact sur l'historique).

---

## 6. Limites de l'audit

- **Non relu en détail** [S] : `storage.js` (3073 l.), `restitution.js`, `signature*.js`, `pdf/attribution.py`, `units.py` (tables du parc), `backup*.py`, imports CSV, l'ordre d'appel des migrations dans `app.py`.
- **Non exécuté** : aucune requête HTTP, aucun test, serveur :5000 non touché. Deux fonctions pures Python ont été appelées pour confirmer les constats §3.1 et §3.2.
- Les correctifs non commités de l'arbre de travail (alias, `field_health`, alignement) ont été lus dans leur état actuel ; ils améliorent la lecture mais n'ont pas de garantie d'écriture (§3.3).
- Aucun nom de personne issu des données n'est cité dans ce rapport.

---

# PARTIE 3 — Qualité, fiabilité, tests, sécurité
# Audit qualité, fiabilité des données, tests et sécurité — « À Quai »

Périmètre : dépôt `C:\www\dotation` (branche `dev`, arbre de travail avec modifications non commitées, dont `backend/models/field_health.py` et `tests/test_field_aliases.py`). Lecture seule : aucun fichier du dépôt modifié, serveur :5000 non touché, aucun test exécuté.

Légende : **[V]** = vérifié par lecture du code (fichier:ligne cités) ; **[S]** = supposé / dépend du comportement navigateur ou d'une configuration, à confirmer par un test.

---

## 0. Synthèse exécutive

Le socle est sain (transactions `with get_db()`, CSRF sur toutes les mutations `/api`, CSP sans `unsafe-inline` pour les scripts, échappement HTML systématique dans les rendus de champs personnalisés, export PDF sans interprétation de balisage). Le risque principal n'est pas l'injection mais la **perte silencieuse de données par reconstruction de payload** : le frontend reconstruit tout le dossier depuis le DOM et le serveur remplace `payload_json` en bloc, sans fusion ni version. Toute donnée absente du DOM à l'instant de l'enregistrement disparaît.

Points les plus graves (détails aux sections 2 à 4) :

1. **[V] L'éditeur de champs de l'admin détruit silencieusement des métadonnées** : aucun choix `list` / `email_with_domain` dans le sélecteur de type (`frontend/js/admin.js:570-575`), donc un champ liste (Zone alarme) ou e-mail repasse en « Texte » à la sauvegarde ; `aliases` et `placeholder` ne sont jamais renvoyés (`admin.js:705-716`).
2. **[V] Une ressource désactivée ou supprimée du catalogue disparaît des dossiers ouverts puis réenregistrés** (`app.js:1083-1120` ne parcourt que le catalogue actif ; `models/forms.py:257` remplace tout).
3. **[V] Un utilisateur de portée « masquée » qui enregistre un dossier réécrit les noms masqués (`J**n`) par-dessus les vrais** (`models/forms.py:566-568` masque en lecture ; `routes/forms.py:657-668` n'interdit pas l'écriture). Dépend de l'existence d'un groupe `masked` avec `forms.edit` **[S]**.
4. **[V] Association d'alias « par position »** (`models/catalog.py:184-190`) : supprimer un champ et en ajouter un autre dans la même sauvegarde rattache les anciennes valeurs au mauvais champ, puis les réécrit sous le nouveau nom à l'enregistrement suivant.
5. **[V] Import / export de base « legacy »** (`routes/admin.py:1637-1750`) : lecture brute d'une base en mode WAL, déplacement d'un fichier par-dessus la base vivante, aucune migration après import ; en parallèle du mécanisme correct `backup.py`.
6. **[V] Traversée de chemin dans l'archive de sauvegarde** (`backup.py:253`, `301`) : `entry["file"]` du manifeste est joint sans contrôle.
7. **[V] Aucune intégration continue, aucun test JS, aucun endpoint santé** ; les tests de personnalisation existants couvrent des fonctions pures, pas le cycle de vie complet.

---

## 1. Audit des tests existants

### 1.1 Inventaire (vérifié)

`tests/` : environ 4 000 lignes, 35 fichiers, ~330 fonctions de test. Isolation correcte (`tests/conftest.py` pose `APP_DATA_DIR` temporaire avant tout import ; `test_http_endpoints.py` lance `_http_scenarios.py` en sous-processus sur base temporaire). Aucun `.github/`, aucun `package.json`, aucun `tox`/`pytest.ini` : **pas de CI, pas de test unitaire JavaScript**. `tests/browser/*` sont des scripts Selenium exécutés à la main (`check_*.py`, `audit_dark.py`…), non collectés par pytest (à confirmer : le nom `test_no_horizontal_scroll.py` est le seul collectable **[S]**).

Couverture utile pour la personnalisation :
- `test_field_aliases.py` (5 tests) : logique pure de `carry_over_field_aliases` / `align_fields`.
- `test_form_legacy_fields.py` (6 tests) : alignement d'anciens noms, fonctions pures.
- `test_http_endpoints.py::test_legacy_field_names_are_shown_under_the_current_catalog_names`, `::test_field_health_scan_and_repair_only_adds_current_names` : seul vrai test de bout en bout du sujet.
- `test_resource_rules.py` (10), `test_inventory.py` (16), `test_units.py` (62), `test_stock.py` (18) : règles de suivi et parc.
- `test_backup_archive.py` (9) : création, diagnostic, restauration, copie de sécurité (module `backup.py` uniquement, pas la route).
- `test_security_hardening.py` (10), `test_http_endpoints.py::test_no_private_endpoint_answers_an_anonymous_visitor`.

### 1.2 Trous de couverture (vérifiés par absence de test correspondant)

| # | Flux de personnalisation | Couvert ? | Commentaire |
|---|---|---|---|
| T1 | Créer une ressource personnalisée puis créer un dossier avec elle (POST resource → POST form → GET form → export) | Non | Aucun test du chemin POST `/api/admin/resources` + `/api/forms` |
| T2 | Renommer le libellé d'un champ puis relire d'anciens dossiers | Partiel | Fonctions pures seulement, pas de PUT catalogue réel |
| T3 | Masquer / réafficher un champ et enregistrer un dossier existant | Non | Rien ne vérifie que la valeur du champ masqué survit à un PUT |
| T4 | Supprimer un champ ayant des valeurs | Non | La route `usage` n'est pas testée |
| T5 | Désactiver / supprimer une ressource utilisée puis rouvrir + réenregistrer un dossier | Non | Le trou correspond au défaut n°2 |
| T6 | Changer le type d'un champ (texte vers liste / nombre / date / liste déroulante) avec données existantes | Non | Défauts §2.3 à §2.5 |
| T7 | Éditeur admin : lecture puis réécriture du schéma sans modification (aller-retour identique) | Non | Défaut n°1 : aucun test JS/navigateur ne compare `field_schema` avant/après |
| T8 | Round-trip dossier complet : POST, GET, PUT sans changement, GET, égalité des `payload_json` | Non | Aucun test d'idempotence de `persist_form` |
| T9 | Exports (Excel, PDF, CSV UNC) avec libellés/valeurs hostiles ou non latins | Non | Voir §4 |
| T10 | Import de base / restauration puis migrations, puis lecture des dossiers | Partiel | `restore_archive` testé, mais pas la route `/api/admin/backup/import`, pas la restauration d'un ancien schéma, pas l'ancien import `/api/admin/db/import` |
| T11 | Deux écritures concurrentes du même dossier | Non | Aucun contrôle de version n'existe |
| T12 | Portée de données « masquée » : lecture puis écriture | Non | Défaut n°3 |
| T13 | Codes de ressource hostiles (guillemets, espaces, majuscules) | Non | §2.6 |
| T14 | `field_health` : réparation puis cohérence de `dotation_items.details_json` | Non | §2.7 |
| T15 | Tests du frontend `get*Data` / `populate*` | Non | Aucun harnais JS |

### 1.3 Matrice proposée : tests « contrat de données »

Principe : pour chaque combinaison **(type de champ) x (opération de personnalisation) x (état du dossier)**, vérifier l'invariant central :

> **Invariant I1 (aucune perte)** : toute valeur non vide saisie dans un dossier reste retrouvable (sous son nom courant ou, à défaut, visible en « valeur orpheline ») après : ouverture dans le formulaire, réenregistrement sans modification, export Excel/PDF, sauvegarde/restauration.
> **Invariant I2 (aucune invention)** : aucune valeur n'apparaît sous un champ auquel elle n'a jamais été saisie (cf. alias par position).
> **Invariant I3 (idempotence)** : `PUT(GET(x))` donne un `payload_json` égal au champ près (hors `savedAt`).
> **Invariant I4 (schéma stable)** : `GET` catalogue puis `PUT` du même contenu ne change rien (types, `aliases`, `placeholder`, `hidden`, `identifier`).

Matrice (chaque ligne est un test paramétré ; « P » = pytest HTTP sur base temporaire, « B » = navigateur, « J » = test JS) :

| Opération sur le catalogue | Types de champ | États de dossier | Niveau | Invariants |
|---|---|---|---|---|
| Renommer le libellé (clé figée) | text, textarea, select, date, number, checkbox, list, email_with_domain | brouillon, en attente, actif verrouillé | P | I1, I3 |
| Changer la clé (via API) avec libellé identique / différent / 2 retirés + 2 ajoutés | text, list | idem | P | I1, I2 |
| Masquer, sauvegarder un dossier, réafficher | tous | brouillon | P + B | I1, I3 |
| Supprimer un champ (avec / sans valeurs) | tous | idem | P | I1 (valeur en orphelin visible) |
| Changer le type text vers list / date / number / select / checkbox et l'inverse | 7 x 7 | brouillon | P + B | I1 |
| Retirer une option d'une liste déroulante utilisée | select | brouillon | B | I1 |
| Désactiver puis supprimer la ressource | ressource entière | brouillon, mise à jour, restitution | P | I1 |
| Éditeur admin sans modification : GET schéma, éditeur, PUT, GET | tous les types, dont builtin `zoneAlarme` et `email` | n/a | B | I4 |
| Ressource personnalisée créée puis utilisée (dossier, restitution, parc, PDF, Excel, signature distante) | mode unit, quantity, access, none | cycle complet | P | I1, I3 |
| Export Excel / PDF / CSV UNC | libellés et valeurs : `=1+1`, `<b>`, `"`, `;`, saut de ligne, cyrillique, arabe, emoji | n/a | P | contenu échappé, pas de « ? » à la place de texte valide |
| Sauvegarde archive puis restauration sur base vierge puis migrations puis GET | base ancienne (schéma d'une version antérieure) | n/a | P | I1 |
| Ancien import `/api/admin/db/import` | base issue de l'export | n/a | P | export = import (aller-retour identique) |
| Portée masquée : GET puis PUT | groupe `masked` avec `forms.edit` | brouillon | P | les vrais noms ne sont jamais écrasés |
| Deux PUT concurrents (mêmes `savedAt`) | n/a | brouillon | P | le second est refusé (conflit), ou fusion |
| Code de ressource `a"b`, `Ordi 1`, `ORDINATEUR` (collision avec builtin) | n/a | n/a | P | refus 400 ou normalisation |
| Réparation `field_health` puis `parc` | anciens noms | actif | P | `dotation_items.details_json` aligné |

Tests de propriété (Hypothesis, à ajouter aux dépendances de test) : générer un schéma aléatoire (types, clés, alias, masqué) et un dossier aléatoire, appliquer une séquence aléatoire d'opérations de personnalisation, vérifier I1 à I4. C'est l'outil le plus efficace contre la classe de bugs « dérive de clés ».

Côté JS : extraire `getAdditionalResourcesData` / `populateAdditionalResources` / `readResourceFieldSchema` dans un module testable (Node + jsdom, ou Playwright) et tester l'aller-retour `populate(get(x)) == x`.

---

## 2. Points de perte silencieuse de données

Cause structurelle **[V]** : `getFormData` (`frontend/js/app.js:2309-2371`) fabrique un payload complet depuis le DOM ; `update_form` (`backend/routes/forms.py:657-668`) le transmet à `persist_form` (`backend/models/forms.py:257-436`) qui écrit `payload_json = json.dumps(payload)` sans lire ni fusionner l'ancien contenu (l'ancien n'est lu que pour tester `lockedAt`, `forms.py:352-356`). Tout champ non reconstruit par le DOM est perdu.

### 2.1 Frontend, formulaire de dossier

| # | Fichier:ligne | Scénario de perte | Statut |
|---|---|---|---|
| L1 | `app.js:1083-1120` (`getAdditionalResourcesData` mappe `dynamicResourceReferences`) ; `routes/admin.py:691-703` (`/api/reference/resources` filtre `is_active = 1`) | Ressource désactivée ou supprimée du catalogue : son entrée `resources.additional` du dossier n'a pas de case DOM, elle n'est plus émise, le PUT la supprime, `dotation_items` la perd aussi (`extract_items`, `workflow.py:268-274`). | [V] |
| L2 | `app.js:1223` (`field.value = String(value)`) | Champ `select` dont l'option enregistrée a été retirée du catalogue : `select.value` n'a pas de correspondance, la valeur devient vide, puis n'est plus émise (`getDynamicResourceFieldValue` renvoie `""` et `.filter(([, value]) => value)` de `app.js:1107` l'écarte). Idem `type="number"` avec « 12 pcs » et `type="date"` avec « 12/03/2026 » après changement de type. | [S] (standard DOM, à tester) |
| L3 | `app.js:1193-1206` (`listContainer && Array.isArray(value)`) | Champ passé de texte à liste : la valeur est une chaîne, la branche liste est ignorée, aucun élément DOM ne correspond ensuite, valeur perdue à l'écran et à l'enregistrement. Inverse (liste vers texte) : `String(["a","b"])` donne `"a,b"`, altération. | [V] |
| L4 | `app.js:1155-1162` (`FIELD_LEGACY_KEYS = { imei: "numeroSerie" }`) et `2039-2050` (`LEGACY_FIELD_RENAMES`) | Table d'alias codée en dur, seulement pour `imei`, redondante avec `aliases`/`align_fields` côté serveur : deux mécanismes concurrents, résultat dépendant de l'ordre. | [V] |
| L5 | `app.js:1099-1112` (`details: … \|\| summarizeDynamicResource(resource)`) | Ressource sans schéma ayant un détail libre, puis ajout de champs au catalogue : `#dynamic_resource_details_*` n'existe plus, `details` vide est remplacé par un résumé des champs : le texte libre d'origine est écrasé. | [V] |
| L6 | `app.js:2309-2371` | `validation.signedAt`, `meta.dossierId`, `meta.createdAt`, `meta.resourceValidationErrors` ne sont pas renvoyés ; `signedAt` disparaît si un dossier signé à distance est réenregistré (reste théorique tant que `lockedAt` bloque la mise à jour, `forms.py:352-356`). `get_signature_datetime` (`utils.py:166-176`) retombe alors sur `lockedAt` : date de signature modifiée. | [S] |
| L7 | `app.js:224-234` | Un champ **obligatoire et masqué** bloque la validation du dossier (`getDynamicResourceFieldValue` lit l'input caché vide) et l'utilisateur ne peut pas le saisir : impasse fonctionnelle (et incitation à contourner). Aucune règle serveur n'interdit « masqué + obligatoire » (`validate_resource`, `resource_rules.py:35-75`). | [V] |

### 2.2 Éditeur de schéma admin

| # | Fichier:ligne | Scénario | Statut |
|---|---|---|---|
| A1 | `admin.js:566-577` (options du sélecteur de type : text, textarea, select, date, number, checkbox seulement) contre `models/workflow.py:16` (types acceptés : + `list`, `email_with_domain`) | Ouvrir puis enregistrer une ressource contenant un champ `list` (builtin `zoneAlarme`) ou `email_with_domain` : aucune `<option selected>`, le navigateur sélectionne la première (« Texte »), le type est écrasé. Les valeurs déjà saisies (tableaux) sont alors relues comme texte (voir L3). Même absence dans `admin-resource-wizard.js` (`WIZARD_FIELD_TYPES`) **[S]** pour ce dernier. | [V] pour l'éditeur, [S] pour l'effet navigateur |
| A2 | `admin.js:705-716` | `aliases` non renvoyés : les alias déjà enregistrés d'un champ sont effacés à chaque sauvegarde depuis l'interface (`normalize_resource_field_schema` reconstruit `aliases` depuis le seul payload, `workflow.py:44`). `carry_over_field_aliases` (`catalog.py:175-198`) ne réinjecte que pour les couples retiré/ajouté. | [V] |
| A3 | `admin.js:709` (`placeholder: ""` forcé) | Les aides à la saisie des ressources intégrées (« Ex: Renault, Citroen », `catalog.py`) sont vidées à la première sauvegarde. `quantity` (indicateur de champ quantité, `resource_rules.py:56`) n'est pas renvoyé non plus. | [V] |
| A4 | `admin.js:717` (`.filter((field) => field.label && field.key)`) et `workflow.py:21-22` (`if not label or not key: continue`) | Un champ dont le libellé est vide, ou dont le libellé ne contient que des symboles (« ??? » donne une clé vide), est supprimé sans message, alors que l'utilisateur pense l'avoir ajouté. | [V] |

### 2.3 Backend

| # | Fichier:ligne | Scénario | Statut |
|---|---|---|---|
| B1 | `models/catalog.py:184-190` | Appariement par position quand `len(removed) == len(added)` mais libellés différents : « Marque » retiré et « Couleur » ajouté deviennent alias l'un de l'autre ; `align_payload_field_names` (`forms.py:437-465`) copie alors la marque dans « Couleur » à chaque lecture, et le réenregistrement la fige. Contredit la promesse « en cas de doute, on ne devine pas » de la docstring. | [V] |
| B2 | `models/forms.py:437-465` + `models/field_health.py:20-56` | L'alignement (`get_form`) et la réparation modifient `payload_json` mais jamais `dotation_items.details_json`, alors que le parc (`inventory.py:139-200`), les restitutions (`build_restitution_signature_public_payload`, `forms.py:648-651`) et l'export Excel des lignes (`routes/forms.py:~125`) lisent la vue à plat. Après réparation, l'identifiant de parc reste introuvable jusqu'au prochain `persist_form`. | [V] |
| B3 | `models/forms.py:298-303` (nettoyage `materiel`/`immateriel` dès qu'une ressource `additional` a du contenu) | Suppression définitive et sans copie des clés `materiel` / `immateriel` d'anciens dossiers dès qu'un enregistrement contient une ressource dynamique (« CRITICAL FIX #3 »). Une donnée d'ancien format non migrée par `migrateLegacyResourcesToAdditional` (ex. `legacyData.values`, cas spéciaux, `app.js:2058-2090`) est détruite. | [V] |
| B4 | `models/forms.py:395-405` | `sync_units_for_form` / `sync_stock_for_form` lèvent une exception : elle est journalisée puis avalée, mais les écritures partielles déjà faites dans la même transaction sont validées au `with` (pas de `SAVEPOINT`). Parc ou stock potentiellement à moitié synchronisé. | [V] pour le code, [S] pour la fréquence |
| B5 | `models/workflow.py:15-46` | `field.get(...)` sans contrôle de type : un élément non-objet dans `field_schema` produit une exception 500 (pas de 400). Aucune borne sur le nombre de champs, d'options, ni sur la longueur des libellés. | [V] |
| B6 | `models/workflow.py:268-274` | `item_key` = `code` fourni par le client dans le payload ; un `code` égal à un identifiant intégré (`ordinateur`, `email`…) crée une seconde ligne de même `item_key` pour un même dossier. Le libellé et la catégorie enregistrés dans `dotation_items` viennent du client, pas du catalogue. | [V] |
| B7 | `routes/admin.py:1347-1380` (`DELETE /api/admin/resources/<id>`) | Suppression d'une ressource utilisée par des dossiers sans aucun contrôle (le PUT, lui, verrouille `code`, `routes/admin.py:1263-1268`). La ligne est conservée dans `deleted_items`, mais les dossiers ouverts perdent la ressource (L1). | [V] |

### 2.4 Migrations, import, exports

| # | Fichier:ligne | Scénario | Statut |
|---|---|---|---|
| M1 | `utils.py:66-78` (`text.encode("cp1252", "replace")`) et `pdf/attribution.py` (tout le texte passe par `normalize_pdf_text`) | Tout caractère hors cp1252 (cyrillique, arabe, grec, CJK, emoji, certains guillemets) devient `?` dans les PDF : perte de fidélité pour une exigence de « souplesse internationale » (`feature_org_wizard`). | [V] |
| M2 | `routes/forms.py:359`, `373`, `355-381` | Export CSV UNC assemblé par `";".join(...)` sans guillemets : `nom`, `prenom`, `service`, `fonction`, `chemin` ne sont pas nettoyés (seuls `unc_ref_ad` et `commentaire` le sont) ; un `;` ou un saut de ligne dans ces champs décale les colonnes. | [V] |
| M3 | `routes/admin.py:1637-1650` | `db_export` lit le fichier `.db` brut alors que la base est en WAL : les écritures récentes encore dans `-wal` sont absentes de l'export (le module `backup.py` utilise, lui, l'API de sauvegarde SQLite, `backup.py:82-91`). | [V] pour le code, [S] pour l'effet (dépend du dernier checkpoint) |
| M4 | `routes/admin.py:1735-1736` | Import legacy : `shutil.copy2` (copie brute) puis `shutil.move` par-dessus la base ouverte ; les fichiers `-wal` / `-shm` de l'ancienne base restent ; sous Windows le remplacement d'un fichier ouvert échoue ; les connexions ouvertes continuent sur l'ancien inode sous Linux. Aucune migration (`init_db`, `ensure_column`) exécutée après import. | [V] |
| M5 | `routes/db_backup.py:121-134` | Après `restore_archive`, seul `ensure_users_schema()` est rappelé ; le schéma de la base « dotation » restaurée (colonnes ajoutées, `migrate_*` du catalogue) n'est mis à niveau qu'au prochain redémarrage : une archive ancienne restaurée à chaud peut produire des 500 (`tracking_mode`, `field_schema_json`…). | [V] pour l'absence d'appel, [S] pour les 500 |
| M6 | `backup.py:279-310` | Restauration de deux bases non atomique : si la seconde échoue, la première est déjà remplacée ; les copies de sécurité existent mais aucun retour arrière automatique. | [V] |
| M7 | `routes/admin.py:1702-1706` (`field_health_repair`) | Copie de sécurité par `shutil.copy2` de la base vivante en WAL (incohérente possible) au lieu de `backup.snapshot_sqlite`. | [V] |
| M8 | `backup.py:253` et `301` | `os.path.join(workdir, entry["file"])` avec `entry["file"]` issu du manifeste de l'archive téléversée : un manifeste `"file": "../../x.db"` (entrée de même nom dans le zip, empreinte cohérente) écrit hors du dossier temporaire. Nécessite le droit `db.manage`. | [V] |

---

## 3. Robustesse

### 3.1 Validations serveur

- **[V] Aucune validation de structure sur `POST/PUT /api/forms`** (`routes/forms.py:642-668`) : le corps est passé tel quel ; les seuls contrôles sont nom/prénom (`forms.py:258`). Un `resources.additional` mal formé (élément non-objet) déclenche `AttributeError` (`workflow.py:268-274`, `forms.py:262-266`) donc HTTP 500. Le plafond de taille est `APP_MAX_UPLOAD_MB=100` par défaut (`app.py:37`) pour **toutes** les routes : un JSON de dossier de 100 Mo est accepté (charge mémoire, base gonflée). Proposer un plafond par route (ex. 2 Mo pour les dossiers, 1 Mo pour les schémas).
- **[V] `code` de ressource non validé** (`models/catalog.py:201-210`, `routes/admin.py:1180-1190`) : seule la non-vacuité est vérifiée. Or `code` sert de clé dans `item_key`, dans le motif `LIKE '%"code"%'` de `count_resource_field_usage` (`workflow.py:193`), dans des sélecteurs CSS construits par concaténation (`app.js:2320-2325`, `data-item-key="${itemKey}"`) et dans des `id` DOM. Un code contenant un guillemet ou un espace casse les sélecteurs (le formulaire lève une exception JavaScript **[S]**).
- **[V] Les règles métier de la ressource viennent du client** : `requiresReturn`, `hasAssignment*`, `fieldSchema`, `category` sont embarqués dans le payload du dossier (`app.js:1088-1103`) et jamais confrontés au catalogue par `persist_form`.
- **[V] `field_schema` sans plafonds** : nombre de champs, longueur des libellés, nombre d'options (`workflow.py:15-46`).
- **[V]** Règle « masqué + obligatoire » non interdite (voir L7) ; règle « `identifier` masqué » couverte (`resource_rules.py:53-55`).

### 3.2 Erreurs avalées

Occurrences `except … : pass` dans le code applicatif (hors `venv`) : `app.py:330-331`, `models/settings.py:438-439`, `465-466`, `routes/pages.py:171-172`, `routes/admin.py:1676-1677`, `1740-1741`, `models/catalog.py:221-222`, `backup_schedule.py:81,88,103,210`, `backup_targets.py:164`, `config.py:32,39`, `rate_store.py:72`, `update_check.py:124`, `utils.py:155`. Environ 350 `except Exception` au total. Les plus sensibles pour les données :
- `models/catalog.py:221` (`except (TypeError, JSONDecodeError): pass`) : un `field_schema_json` ancien corrompu désactive silencieusement le calcul d'alias au lieu d'alerter.
- `routes/db_backup.py:56-65` (`_log`) : un échec d'écriture du journal d'audit est ignoré sans trace (intention documentée, mais aucune journalisation applicative de secours).
- `models/forms.py:395-405` : voir B4.
- `models/field_health.py:28-31` (`continue` sur JSON invalide d'un dossier) : un dossier au JSON corrompu est simplement ignoré, sans être compté ni signalé dans le rapport.

### 3.3 Transactions et connexions

- **[V]** `with get_db() as connection` valide/annule la transaction mais **ne ferme pas** la connexion (comportement de `sqlite3`) ; `get_db()` n'a pas de fermeture explicite. Pire, certaines routes appellent `get_db().execute(...)` sans jamais fermer (`routes/forms.py:185, 207, 211, 347` ; `routes/admin.py:67`). Effet : fuite de descripteurs jusqu'au ramasse-miettes, verrous WAL retardés **[S]**.
- **[V]** `PRAGMA journal_mode = WAL` est rejoué à chaque connexion (`database.py:20-21`), sans `busy_timeout` explicite ni `synchronous=NORMAL` : correct mais coûteux.
- **[V]** `persist_form` : lecture de l'existant puis écriture dans la même connexion, sans `BEGIN IMMEDIATE` : deux écritures simultanées entrent en concurrence sur le verrou de fin de transaction (délai de 10 s, `database.py:15`, puis `database is locked`, HTTP 500 non rattrapé **[S]**).

### 3.4 Concurrence (deux onglets, deux utilisateurs)

**[V] Pas de contrôle de version optimiste** : `savedAt` est envoyé par le client (`app.js:2326`) mais jamais comparé à `updated_at` en base (`persist_form` ne lit que `lockedAt`). Scénario : onglet A et onglet B ouvrent le dossier 12 ; A ajoute une ressource et enregistre ; B, qui ne connaît pas cette ressource, enregistre : la ressource de A disparaît (dernier écrivain gagnant, remplacement total). Le même scénario s'applique à une modification du catalogue faite entre l'ouverture et l'enregistrement (L1, L2). Recommandation : `expectedUpdatedAt` dans le PUT, `409 conflict` si différent, et fusion côté serveur pour les entrées `additional` non touchées.

### 3.5 Import / restauration / migrations / sauvegardes

- Bien : `backup.py` utilise l'API de sauvegarde SQLite, vérifie signature, `integrity_check`, tables attendues, empreintes SHA-256, borne la taille décompressée (`backup.py:194-196`), chiffre en AES-GCM (scrypt N = 2^15), écrit des copies « avant restauration ».
- À corriger : M4 à M8, plus :
  - **[V]** `diagnose_sqlite` ne fait ni `PRAGMA foreign_key_check`, ni contrôle de version de schéma, ni analyse de la santé des champs (`field_health`) ; une archive « valide » peut contenir des dossiers à noms de champs orphelins.
  - **[V]** Deux mécanismes parallèles (`routes/db_backup.py` correct, `routes/admin.py:1637-1750` legacy) exposés simultanément par `frontend/admin-db.html:279` et `admin-db.js:102` : risque de confusion utilisateur et de perte (M3, M4).
  - **[V]** Migrations idempotentes : `ensure_column`, `INSERT OR IGNORE`, `migrate_*` du catalogue (`models/catalog.py:290-513`) et `ensure_users_schema` (`database.py:47-66`) sont conçues idempotentes (lecture) ; aucune table `schema_version` ni test « appliquer deux fois » **[V pour l'absence]**.
  - **[V]** Pas de migration exécutée après `restore` d'une base « dotation » (M5).

---

## 4. Sécurité applicative (périmètre personnalisation)

### 4.1 Résultats vérifiés positifs

- **XSS dans les rendus de champs personnalisés : non exploitable dans les chemins examinés.** `buildDynamicFieldInput` (`app.js:452-590`) échappe `field.label`, `field.key`, `option`, `placeholder` (`escapeHtml` / `escapeAttribute`) ; l'éditeur admin échappe `field.key`, `label`, options (`admin.js:562-584`) ; listes et tableaux d'admin (`admin.js:1255-1266`, `admin-backup-targets.js:34-58`) ; sélecteur « reprendre un matériel » (`app.js:379-385`) idem. Les seuls `innerHTML` non échappés relevés injectent des libellés statiques (`admin-branding.js:282`) ou `btn.textContent` (`app.js:2832-2834`, sûr tant que le libellé du bouton est statique). CSP `script-src 'self' https://cdn.jsdelivr.net` sans `unsafe-inline` (`app.py:125-135`) limite l'impact d'un oubli.
- **Clés de champ** : `slugify_field_key` (`utils.py:57-63`) ne laisse passer que des caractères alphanumériques et `_` : pas de clé `__proto__` (le préfixe `_` est supprimé), pas de guillemet.
- **CSRF** : jeton vérifié pour toute mutation `/api/` d'une session authentifiée (`app.py:55-76`), comparaison à temps constant. Exceptions légitimes : routes publiques de signature, `/api/auth/`.
- **PDF** : bibliothèque `fpdf`, texte posé par `self.text(...)` sans balisage interprété (pas de `Paragraph` ReportLab) : pas d'injection de balisage. Le seul défaut est la fidélité (M1).
- **Excel** : `spreadsheet_cell` (`routes/forms.py:46-52`) émet `ss:Type="String"` avec `xml_escape` : les formules ne sont pas évaluées par Excel pour ce format XML 2003 (vérifier en pratique avec un fichier `=1+1` **[S]**).
- **Accès admin** : toutes les routes du catalogue, des utilisateurs, de `field-health` portent `@login_required` + `@permission_required` (`users.manage` ou `db.manage`) (`routes/admin.py:1169-1391`, `1683-1707`) ; test d'accès anonyme automatique (`test_http_endpoints.py:26`).
- **Exports** réservés aux portées complètes (`can_export_unmasked`, `routes/forms.py:17-22`).

### 4.2 Défauts et risques vérifiés

| # | Constat | Fichier:ligne | Gravité | Statut |
|---|---|---|---|---|
| S1 | Traversée de chemin dans l'archive de sauvegarde (M8). Exemple : manifeste avec `"file":"../evil.db"` | `backup.py:253`, `301` | Moyenne (droit `db.manage` requis) | [V] |
| S2 | Injection de formule CSV : `commentaire`, `chemin`, `nom` commençant par `=`, `+`, `-`, `@` sont écrits tels quels dans `acces_unc_export.csv`, ouvert dans Excel : `=HYPERLINK("http://x","clic")` ou DDE. Exemple : commentaire UNC `=cmd|' /C calc'!A0`. | `routes/forms.py:355-381` | Moyenne | [V] pour l'absence de neutralisation, [S] pour l'effet dans Excel |
| S3 | Même absence de préfixe d'échappement dans `services.csv` (libellés modifiables par l'admin) | `routes/admin.py:1094-1106` | Faible | [V] |
| S4 | Portée « masquée » : lecture masquée (`get_form`, `forms.py:566-568`) mais écriture non contrôlée : `PUT /api/forms/<id>` accepte le payload masqué et écrase nom/prénom (voir défaut n°3). Le masque ne couvre par ailleurs que quelques champs en dur (`utils.py:37-53` : `immateriel.email.adresse`, `materiel.badge.numero`, `telephone.numeroSerie`, `vehicule.immatriculation`) : **les champs des ressources personnalisées (`resources.additional[*].fields`, e-mails, immatriculations, numéros de série) ne sont pas masqués**. | `utils.py:37-53`, `routes/forms.py:657-668` | Élevée (RGPD) | [V] |
| S5 | Fuite via lien de signature publique : la page publique renvoie nom, prénom, service, fonction, mandat et le détail des ressources, y compris identifiants matériels (`build_signature_public_payload`, `models/forms.py:591-633`) à toute personne détenant le lien ; jeton `secrets.token_urlsafe(32)` (fort, `signature.py:41-42`) mais **stocké en clair** (`get_signature_link_by_token`, `signature.py:107-111`) : une fuite de base (ou une sauvegarde non chiffrée, `allow_unencrypted`) donne des liens actifs. Recommandation : stocker un hachage du jeton. | `models/signature.py:41-42`, `107-111` | Faible à moyenne | [V] |
| S6 | Limite de taille globale de 100 Mo pour toutes les routes JSON (`app.py:37`) | `app.py:37` | Moyenne (déni de service) | [V] |
| S7 | Code de ressource non validé (caractères, longueur) : chaînes destinées à des sélecteurs CSS et à un `LIKE` (voir §3.1). Le `LIKE` est paramétré, donc pas d'injection SQL ; le risque est la casse du formulaire et les jokers `%`/`_` faussant `count_resource_field_usage`. | `routes/admin.py:1180-1190`, `models/workflow.py:193` | Faible | [V] |
| S8 | Contenu de la sauvegarde : `users.db` (hachages bcrypt) est inclus ; le chiffrement est optionnel (`allow_unencrypted`, `routes/db_backup.py:135-150`) | `backup.py:38-52` | Faible | [V] |
| S9 | `img-src 'self' data: https:` autorise le chargement d'images depuis n'importe quel site HTTPS : canal d'exfiltration si une injection HTML est un jour trouvée (défense en profondeur) | `app.py:130` | Faible | [V] |
| S10 | Journal d'audit sans « avant/après » : voir §5 | `routes/admin.py:1305-1316` | Moyenne | [V] |

Exposition des e-mails : `email` des comptes utilisateurs renvoyé par `/api/admin/users` (réservé `users.manage`) ; pas d'anomalie constatée. Signatures : masquées hors droit `can_export_signature_assets` (`auth.py`) ; les PDF affichent « Signature masquée dans cet export » (`pdf/attribution.py:197-206`) [V].

---

## 5. Observabilité

État actuel **[V]** :
- `app_logs` (via `insert_app_log`, `models/audit.py:150-168`) : acteur, portée, action, cible, détails JSON ; `audit_events` par dossier. Le journal est consultable (`routes/admin.py:765-768`) mais **non purgé** (aucune rétention) et **sans intégrité** (pas de chaînage).
- Diagnostics : `db_diagnose` (fichier), `diagnose_archive`, `/api/admin/field-health` (scan des valeurs orphelines, non commité), `/api/admin/catalog/quality` (ressources actives à problèmes), `backup_schedule.health`.
- Manques : **pas d'endpoint `/health`** (grep des routes : seul `routes/debug.py` expose des tests de verrou) ; **pas de CI** ; journaux de mise à jour de schéma sans diff (`resource_updated` ne consigne que `field_count`, `routes/admin.py:1305-1316` ; `resource_deleted` n'indique pas combien de dossiers l'utilisaient) ; `form_updated` ne consigne que statut et titre (`models/forms.py:411-427`), donc impossible d'établir a posteriori quelle donnée a disparu.

### 5.1 Contrôles automatiques proposés

1. **Endpoint `GET /api/admin/health`** (droit `db.manage`, JSON) : `PRAGMA integrity_check` rapide + `foreign_key_check`, version de schéma, nombre de dossiers dont `payload_json` est illisible, nombre de valeurs orphelines (`scan_orphan_fields`), écart `payload_json` contre `dotation_items` (ressources présentes d'un côté et pas de l'autre), ressources actives avec problèmes (`catalog_quality_report`), ressources référencées par des dossiers mais absentes/inactives du catalogue, dernière sauvegarde réussie (`backup_schedule.health`). Renvoyer `ok | warning | error`.
2. **Endpoint public minimal `GET /healthz`** (sans données, `{"status":"ok"}`, vérification `SELECT 1`) pour les sondes du reverse proxy (Traefik en préproduction).
3. **Journal d'audit enrichi** : à chaque `resource_updated`, enregistrer le diff du schéma (clés ajoutées, retirées, changements de type, masquées, alias) ; à `resource_deleted` / désactivation, le nombre de dossiers et de lignes `dotation_items` concernés ; à `form_updated`, la liste des `item_key` ajoutés/retirés et le nombre de champs non vides avant/après (alerte « diminution de contenu »).
4. **Garde-fou de perte à l'écriture** : dans `persist_form`, comparer l'ancien et le nouveau `resources.additional` ; si un champ non vide disparaît sans que le client l'ait explicitement supprimé, refuser (409) ou conserver l'ancienne valeur dans `payload.meta.orphans` (comme le fait déjà le frontend via `orphanFieldValues`, `app.js:1154-1175`, mais côté serveur).
5. **Job planifié** (`backup_cli.py` déjà présent) : exécution quotidienne du scan de santé des champs + rapport dans `app_logs` (niveau `warning` si valeurs orphelines > 0) ; alerte à l'administrateur dans le tableau de bord.
6. **CI** (GitHub Actions) : `pytest` + le futur test de contrat + `python -m compileall backend` + lint (`ruff`), plus un job navigateur (Playwright/Selenium sur instance isolée, comme `check_personnalisation.py` lance déjà « instance isolée, port 5055 ») pour les scénarios d'éditeur.
7. **Test de schéma de base** : reconstruire une base vierge via `init_db` et comparer au schéma d'une base ancienne migrée (détecte les dérives de migration).
8. **Rétention du journal** : purge paramétrable (> 1 an) après export.

---

## 6. Recommandations priorisées

Effort : S = moins d'une demi-journée, M = 1 à 3 jours, L = plus de 3 jours. Risque = risque de la modification elle-même.

### P0 — à traiter avant toute autre évolution

| ID | Action | Effort | Risque | Référence |
|---|---|---|---|---|
| P0-1 | Éditeur de champs : ajouter les types `list` et `email_with_domain` au sélecteur (et à l'assistant), renvoyer `aliases`, `placeholder`, `quantity`, et **conserver tout attribut inconnu** du champ (copier l'objet d'origine puis surcharger) au lieu de reconstruire ; test « GET, éditer sans changer, PUT, GET identique » | S | Faible | A1-A3 |
| P0-2 | Ne jamais perdre une ressource au réenregistrement : le frontend doit renvoyer les entrées `additional` connues du dossier mais absentes du catalogue actif (les garder en « lecture seule, ressource retirée du catalogue »), et le serveur doit fusionner (union par `code`) plutôt que remplacer | M | Moyen (touche `persist_form`) | L1, B7 |
| P0-3 | Interdire l'écriture des dossiers à un utilisateur de portée masquée (ou refuser tout PUT dont nom/prénom correspondent au masque), et masquer aussi `resources.additional[*].fields` (au moins les champs `identifier`/e-mail) | S | Faible | S4 |
| P0-4 | Supprimer l'appariement d'alias par position (`catalog.py:184-190`) : n'apparier que par libellé identique, ou exiger une confirmation explicite côté API (`renames: {ancien: nouveau}`) | S | Faible | B1 |
| P0-5 | Contrôle de version optimiste sur `PUT /api/forms/<id>` (`expectedSavedAt`, réponse 409) et garde-fou « pas de diminution de contenu non demandée » côté serveur | M | Moyen | §3.4, §5.1-4 |
| P0-6 | Retirer (ou réaligner sur `backup.py`) `db_export` / `db_import` legacy ; à défaut, `snapshot_sqlite` pour l'export et `restore_sqlite` pour l'import, puis exécuter les migrations (`init_db`) après toute restauration à chaud | M | Moyen | M3-M5 |

### P1

| ID | Action | Effort | Risque | Référence |
|---|---|---|---|---|
| P1-1 | Valider `entry["file"]` du manifeste (`basename` unique, liste blanche `dotation.db` / `users.db`) | S | Faible | M8, S1 |
| P1-2 | Échapper les champs CSV (`csv.writer`, préfixe `'` devant `= + - @` tab CR) pour l'export UNC et `services.csv` | S | Faible | M2, S2, S3 |
| P1-3 | Aligner `dotation_items.details_json` lors de la réparation `field_health` et lors de `align_payload_field_names` (ou recalculer `extract_items` après alignement) | S | Faible | B2 |
| P1-4 | Valider `code` de ressource (`^[a-zA-Z0-9_-]{1,40}$`, insensible à la casse pour l'unicité, interdit les codes intégrés) ; plafonds sur `field_schema` (nombre de champs, options, longueurs) ; 400 sur éléments non-objets | S | Faible | §3.1, B5, B6 |
| P1-5 | Refuser « masqué + obligatoire » (ou ignorer l'obligation d'un champ masqué dans la validation frontend/backend) | S | Faible | L7 |
| P1-6 | Changements de type de champ : avertissement + `usage` (nombre de dossiers) ; conversion sûre à l'ouverture (chaîne vers liste = un élément ; liste vers texte = jointure sans perte) ; conserver la valeur non convertible en orpheline | M | Moyen | L2, L3 |
| P1-7 | Journal d'audit enrichi (diff de schéma, comptages, avant/après du contenu) | M | Faible | §5.1-3 |
| P1-8 | Plafond de taille par route (dossiers 2 Mo, schémas 1 Mo, uploads 100 Mo seulement pour la restauration) | S | Faible | S6 |
| P1-9 | CI GitHub Actions (pytest, ruff, compileall) et premiers tests de contrat HTTP (T1, T3, T5, T8, T12) | M | Faible | §1 |
| P1-10 | Savepoint autour de `sync_units_for_form` / `sync_stock_for_form`, et compteur d'échecs de synchro exposé dans l'endpoint santé | S | Faible | B4 |
| P1-11 | Restauration : un seul essai atomique (restaurer dans des fichiers temporaires, valider, puis basculer) et retour arrière automatique en cas d'échec sur la seconde base | M | Moyen | M6 |

### P2

| ID | Action | Effort | Risque | Référence |
|---|---|---|---|---|
| P2-1 | PDF Unicode : police TTF embarquée (DejaVu / Noto) dans `fpdf`, supprimer le repli `cp1252 "replace"` | M | Moyen | M1 |
| P2-2 | Endpoints `/healthz` et `/api/admin/health` + job quotidien de santé | M | Faible | §5.1 |
| P2-3 | Tests de propriété (Hypothesis) pour les invariants I1-I4 ; harnais JS (Node + jsdom ou Playwright) pour `get*Data`/`populate*` | L | Faible | §1.3 |
| P2-4 | Hachage du jeton de signature en base ; expiration systématique | S | Faible | S5 |
| P2-5 | Supprimer la table `FIELD_LEGACY_KEYS` / `LEGACY_FIELD_RENAMES` du frontend au profit du seul mécanisme serveur (alias) | S | Moyen | L4 |
| P2-6 | Fermeture explicite des connexions (`contextlib.closing`), `busy_timeout` et `BEGIN IMMEDIATE` sur `persist_form` | M | Moyen | §3.3 |
| P2-7 | Table `schema_version` + test « migrations appliquées deux fois = même schéma » | M | Faible | §3.5 |
| P2-8 | Rétention et export du journal d'audit ; chaînage d'intégrité (hash) pour les actions d'administration | M | Faible | §5 |
| P2-9 | Restreindre `img-src` à `'self' data:` si le logo distant n'est plus nécessaire | S | Faible | S9 |

---

## 7. Ce qui reste à vérifier (supposé)

- Comportement navigateur des `select` / `input[type=number|date]` avec valeur hors liste (L2) et du sélecteur de type sans option correspondante (A1) : à confirmer par un test Selenium avant de corriger.
- Existence en production d'un groupe de portée `masked` disposant de `forms.edit` (S4) : vérifier `groups` dans `users.db` et `seed_default_groups` (les groupes par défaut relevés dans `app.py:210-225` sont tous en `full`).
- Effet réel de la formule CSV dans Excel (S2) et du fichier XML 2003 (S3).
- Fréquence des échecs de synchro parc/stock (B4) : chercher les avertissements « Synchronisation du parc impossible » dans les journaux.
- État de l'assistant de ressource (`admin-resource-wizard.js`) pour les types `list` / `email_with_domain`.

Références des fichiers principaux : `C:\www\dotation\backend\models\forms.py`, `backend\models\catalog.py`, `backend\models\workflow.py`, `backend\models\field_health.py`, `backend\models\inventory.py`, `backend\routes\forms.py`, `backend\routes\admin.py`, `backend\routes\db_backup.py`, `backend\backup.py`, `backend\utils.py`, `backend\app.py`, `frontend\js\app.js`, `frontend\js\admin.js`, `tests\`.
