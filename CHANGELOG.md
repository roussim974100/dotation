# Historique des versions — À Quai

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

#### Sélecteur d'équipement mutualisé dans le formulaire
- Intégration du système de pools partagés dans l'interface de formulaire
- Support multi-sélection pour les ressources partagées
- Synchronisation automatique avec les pools

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
