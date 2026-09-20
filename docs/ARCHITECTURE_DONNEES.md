# Architecture des données — concepts à connaître

Note de référence (mise à jour à la 3.60.0). Elle explique **pourquoi** le code est fait ainsi, pour éviter de réintroduire les défauts corrigés.

## 1. Un dossier est la source de vérité

Un dossier (`dotation_forms.payload_json`) contient ses ressources dans `resources.additional[]` : chaque entrée porte ses valeurs (`fields`) **et une copie de la description des champs telle qu'elle était à la saisie** (`fieldSchema`). Les autres tables (`dotation_items`, parc `resource_units`, `resource_stock_movements`) sont des **projections** recalculables.

## 2. Un champ a trois identités

| Identité | Rôle | Peut changer ? |
|---|---|---|
| `id` (`fld_…`) | identifiant interne | **jamais** |
| `key` | nom technique des valeurs dans les dossiers | jamais pour un champ existant côté serveur (une clé déjà valide est conservée telle quelle) |
| `label` | texte affiché | oui |

Quand la clé d'un champ change : l'ancienne devient un **alias** (seulement si le libellé est identique, **jamais par position**) et l'`id` est hérité. Les alias survivent aux sauvegardes suivantes.

## 3. Retrouver une valeur saisie sous un ancien nom (ordre de priorité)

1. même `id` de champ dans la description embarquée du dossier (`align_with_embedded_schema`) ;
2. même libellé dans cette description ;
3. alias déclaré au catalogue ;
4. ressemblance de noms (`canonical_key`, dernier recours, affichage seulement).

Toute valeur qui ne correspond à rien est **conservée** : affichée dans « Autres informations enregistrées » (`orphanFieldValues`, `app.js`) et renvoyée telle quelle à l'enregistrement. **Ne jamais reconstruire un dossier uniquement depuis le schéma courant.**

## 4. Rôles de champs

`role` = `identifier` | `quantity` | `variant` (un seul champ par rôle). Ils pilotent le suivi par objet, le stock et la variante. Les drapeaux historiques (`identifier`, `quantity`, `variant`) sont **dérivés** du rôle. Le code ne doit plus dépendre du **nom** d'un champ. La variante d'un article est celle de la **remise** (figée).

## 5. Migrations

`backend/migrations.py` : liste numérotée (`MIGRATIONS`), table `schema_migrations`, `PRAGMA user_version`.
- Chaque migration est **idempotente**, appliquée une fois, dans l'ordre, dans un point de sauvegarde SQLite : en cas d'échec elle est annulée, consignée, retentée au démarrage suivant, et l'application démarre quand même.
- **Copie de sécurité avant** (API de sauvegarde SQLite, fiable en WAL) si la base contient des dossiers ; jamais bloquante ; 5 copies conservées par famille.
- **Base plus récente que le code** : démarrage refusé (`DatabaseTooNewError`).
- Migrations actuelles : 1 baseline, 2 identifiants de champs, 3 rôles de champs, 4 index de performance.
- Les anciennes `migrate_*` de `app.py` restent en place (idempotentes) ; chacune est isolée : l'échec de l'une n'empêche pas le démarrage.
- Pour ajouter une évolution de schéma : ajouter une fonction idempotente et une entrée `MIGRATIONS`, puis mettre à jour les tests qui vérifient le numéro de version (`test_http_endpoints.py`).

## 6. Robustesse : règles à garder

- **Jamais de `json.loads` nu sur une donnée stockée** : utiliser `utils.safe_json` (ou `catalog._schema_list`). Une donnée abîmée ne doit jamais empêcher le démarrage.
- Un dossier abîmé est ignoré et consigné, pas bloquant.
- Démarrage : l'initialisation est verrouillée entre processus (`single_instance_lock`) ; le contrôle de santé quotidien ne tourne que dans un seul processus et **pas au démarrage** (trop lent sur une grosse base).
- Restauration : tout-ou-rien ; refus d'une base d'une version plus récente ou d'une base de comptes vide.

## 7. Santé, erreurs, diagnostic

- **Santé** (`models/health.py`) : intégrité SQLite, références, migrations, valeurs orphelines, écarts dossier / copie à plat, invariants de stock et de parc. Bouton « Contrôle général » et contrôle toutes les 24 h.
- **Erreurs** (`observability.py`) : toute exception inattendue renvoie un code stable `E-XXXXXX` (type d'exception + position dans le code) et un `X-Request-ID`. Le journal fichier n'a **aucune valeur** saisie.
- **Paquet de diagnostic** (`models/diagnostic.py`) : **liste blanche** de collecteurs (agrégats, noms techniques) + verrou `assert_safe` qui refuse de produire le paquet au moindre motif suspect. Testé avec des valeurs « sentinelles ». Ne jamais y ajouter de libellé, de valeur saisie ou de réglage d'identité.

## 8. Personnalisation

- Types de bénéficiaires : `valeur:Libellé` ou `valeur:Libellé|mandat` (type qui porte un mandat ; `elu` sans drapeau garde son mandat pour les anciennes bases).
- Paramétrage exportable/importable (`config_transfer.py`) : **additif**, avec aperçu, une ressource existante n'est jamais modifiée.
- Schémas de champs : 60 champs, 120 caractères de libellé, 200 options au maximum ; un libellé sans lettre latine donne une clé `champ_N`.
