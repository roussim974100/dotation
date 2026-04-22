---
name: État du projet — v2.14.0
description: État complet du projet après refactoring et feature UNC
type: project
---

Dernière version poussée : **v2.14.0** (2026-04-01).

**Refactoring backend terminé — app.py : 5221 → 256 lignes**
Modules extraits : config, utils, database, auth, models/(workflow, dossier, audit, signature, settings, catalog, forms), pdf/(attribution, restitution), routes/(admin, forms, pages, signature)

**Feature UNC complète (v2.13.0 → v2.14.0) :**
- Section UNC dans formulaire DSI : chemin, accès (lecture/lecture-écriture/refusé), statut provisioning, commentaire
- Bouton + / − dynamique
- "Copier depuis" un dossier existant (recherche debounce)
- Autocomplétion des chemins depuis l'historique (`GET /api/forms/unc-paths`)
- PDF attribution + export texte
- Export CSV DSI (`GET /api/forms/export-unc`)
- Dashboard provisioning UNC dans admin.html (compteurs + tableau)
- Endpoint `GET /api/admin/unc-stats`
- Sanitisation backend dans `persist_form`

**Sécurité :**
- `/about.html` et `/contact.html` protégées par `@login_required` (oubli corrigé)
- 6 sprints sécurité antérieurs sur app.py

**Prochains sprints identifiés :**
- Colonne UNC dans la liste des dossiers (icône si accès UNC configurés)
- Tests d'intégration pytest

**Why:** Refactoring pour maintenabilité. UNC pour traçabilité des accès réseau DSI.
**How to apply:** Travailler sprint par sprint, tester + commit + push à chaque fois.
