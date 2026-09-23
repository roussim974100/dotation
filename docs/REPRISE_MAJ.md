# Reprise des mises à jour — À Quai

Document de passage de relais (session du 20 septembre 2026). À lire en premier pour reprendre le travail sans rien redécouvrir.

## 1. Où on en est

| Élément | État |
|---|---|
| Version | **3.60.0** sur `dev` (`README.md`, `frontend/js/branding.js`, `CHANGELOG.md`) |
| PR dev → preprod | **#17** ouverte |
| PR dev → prod | **#18** ouverte, à fusionner **après validation sur preprod** |
| Fusion des PR | par le propriétaire du dépôt (« Create a merge commit », contournement administrateur) |
| Tests | 387 pytest réussis (navigateur inclus) + scénarios `tests/browser/check_*.py` verts |
| Non exécuté sur un vrai serveur | `setup/deploy-common.sh` (validé par syntaxe et tests), migrations sur un LXC Linux multi-workers, CI GitHub |

Historique des versions du chantier : `CHANGELOG.md` (3.50.2 à 3.60.0). Audit et décisions : `docs/audit/`.

## 2. Circuit de mise en production

1. Fusionner la PR #17 (dev → preprod), puis sur le LXC de préprod : `sudo bash deploy.sh` (branche définie par le script de déploiement).
2. Sur preprod : vérifier le démarrage (les **migrations 1 à 4 s'appliquent au démarrage**, copie de sécurité dans `db_backups/`), lancer **Administration > Base de données > Contrôle général de la base**, générer le **paquet de diagnostic**, ouvrir quelques dossiers réels.
3. Fusionner la PR #18 (dev → prod), déployer la production (sauvegarde préalable, retour arrière automatique du script en cas d'échec).
4. Branche de déploiement de la production : **`prod`** (pas `main`).

En cas d'échec : le code d'erreur affiché (`E-XXXXXX`) et le paquet de diagnostic permettent de comprendre sans la base (voir §5).

## 3. Règles de travail

- Développer sur `dev`, **commits en français**, fichiers stagés **explicitement** (jamais `git add -A` : une base de production a déjà été poussée par erreur le 19/09).
- **Demander avant d'incrémenter la version** (dans `README.md`, `frontend/js/branding.js`, `CHANGELOG.md`).
- Le dossier `scripts/` est ignoré par git : les outils versionnés vont dans `tools/`.
- Ne pas nettoyer la base locale (127.0.0.1:5000) : c'est une copie de la production.
- Tests en local sur `http://127.0.0.1:5000` ; les tests en production sont en lecture seule.

## 4. Lancer les tests

```
python -m pytest tests -q                       # ~2 min
RUN_BROWSER_TESTS=1 python -m pytest tests -q   # ~5 à 8 min, à lancer en arrière-plan
python tests/browser/check_field_health.py      # scénarios navigateur isolés (base vierge, port 5055)
python tools/load_test.py 3000                  # charge sur base synthétique
```

Scénarios HTTP : `tests/_http_scenarios.py` (sous-processus, base temporaire) lu par `tests/test_http_endpoints.py`. Après une modification du backend, relancer le serveur local.

## 5. Diagnostiquer chez un client sans sa base

1. Le client communique le **code d'erreur** (`E-XXXXXX`, stable : le même défaut donne le même code) ; le journal fichier est `<DATA_DIR>/logs/aquai.log` (sans valeur personnelle).
2. Il télécharge le **paquet de diagnostic** (Administration > Base de données > Support technique), le relit, vous l'envoie.
3. Vous reconstruisez sa situation : `python tools/build_skeleton.py aquai_diagnostic.zip dossier_de_sortie` (base fictive, mêmes ressources et volumes).

Limite : un bug qui dépend d'une valeur précise ou de la concurrence ne se reproduit pas fidèlement.

## 6. Ce qui reste à faire

| Sujet | Détail |
|---|---|
| Ancien modèle matériel / immatériel | 7 dossiers sur 34 de la copie de production, ~150 références dans le code : projet dédié, sur copie de production |
| PDF Unicode | cyrillique, arabe, chinois sortent en « ? » ; embarquer une police libre (ex. DejaVu Sans) : décision de l'utilisateur |
| Moteur de workflow déclaratif | non commencé |
| Libellés de statut | quelques copies locales restent dans les pages JS (la source unique est `backend/models/vocab.py`) |
| Performance | `/api/forms` ≈ 1,7 ms par dossier (5 s pour 3 000) : pagination à prévoir si un client dépasse quelques centaines de dossiers |
| Réparation des champs | 6 noms rattachables sur la copie de production, bouton « Rattacher les valeurs » non lancé |
| À vérifier | déploiement réel (LXC multi-workers), exécution de la CI GitHub, effet des formules CSV dans Excel |

## 7. Repères dans le code

Voir `docs/ARCHITECTURE_DONNEES.md` pour les concepts (identifiant de champ, rôles, migrations, santé, diagnostic).

| Sujet | Fichiers |
|---|---|
| Migrations numérotées | `backend/migrations.py` |
| Santé de la base | `backend/models/health.py`, `field_health.py`, routes `/api/admin/health`, `/api/admin/field-health` |
| Paquet de diagnostic | `backend/models/diagnostic.py`, `backend/observability.py`, `tools/build_skeleton.py` |
| Schéma de champs | `backend/models/workflow.py` (`normalize_resource_field_schema`), `backend/models/catalog.py` |
| Correspondance des anciens noms | `backend/models/inventory.py` (`align_fields`, `align_with_embedded_schema`, `schema_key_set`) |
| Stock et parc | `backend/models/stock.py`, `units.py` |
| Vocabulaire | `backend/models/vocab.py`, `frontend/js/branding.js` (`isMandateType`) |
| Paramétrage exportable | `backend/models/config_transfer.py` |
| Déploiement | `setup/deploy-common.sh`, `deploy*.sh` |
