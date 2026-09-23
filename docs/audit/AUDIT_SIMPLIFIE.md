# Audit simplifié — À Quai (20 septembre 2026)

## En une phrase
L'application est saine (base intacte, pas de faille exploitable dans l'affichage des champs personnalisés), mais elle **ne protège pas encore assez les données quand une ressource ou un champ évolue** : c'est ce qui a fait « disparaître » des e-mails et des numéros de série.

## Ce qui s'est passé, expliqué simplement
Chaque champ (par exemple « N° de série ») a un **nom technique** interne. Quand ce nom change, les anciens dossiers gardent l'ancien nom et l'écran ne retrouve plus la valeur : elle est toujours en base, mais invisible. En plus, en réenregistrant le dossier, l'application ne renvoyait que les champs qu'elle connaît : **les valeurs invisibles étaient alors perdues pour de bon**.

## Les chiffres (base locale, copie de la production)
- **43 %** des lignes de ressources de dossiers (31 sur 72) contenaient des noms de champs que le catalogue ne connaît plus, dans **21 dossiers sur 34**.
- La base elle-même est en bon état : contrôle d'intégrité correct, aucune référence cassée.
- Les mêmes valeurs sont **copiées en 3 endroits** (dossier, lignes de suivi, parc) : elles peuvent se contredire.

## Les 5 risques à retenir
1. **Perte de valeurs à l'enregistrement** si le nom du champ a changé (corrigé côté dossier dans nos travaux en cours).
2. **Le filet de sécurité (anciens noms mémorisés) se perd** à la sauvegarde suivante de la ressource : à corriger.
3. **Éditeur de champs de l'administration** : certains types (liste, e-mail avec domaine) repassent en « Texte » à l'enregistrement.
4. **Une ressource désactivée disparaît des dossiers ouverts puis réenregistrés.**
5. **Deux personnes qui modifient le même dossier en même temps** : la dernière écrase l'autre sans avertissement.

## Ce qui est déjà bien
Clé de champ figée dans l'éditeur, masquage plutôt que suppression, protections des codes de ressource, jetons anti-falsification (CSRF), droits d'accès sur l'administration, affichage protégé contre l'injection de code.

## Personnalisation : où l'appli reste rigide
Statuts et types de dossier recopiés dans le code (1 fois en Python, une dizaine en JavaScript), type de bénéficiaire « élu » traité à part dans 10 endroits, tout type personnalisé rétrogradé en « agent » à l'enregistrement, ancien modèle « matériel / immatériel » encore présent à côté des ressources personnalisées, aucune mémoire de version du schéma de la base.

## Ce que nous recommandons (détails dans DECISIONS_COMITE.md)
1. **3.51.0 — Ne plus rien perdre** : conserver les valeurs inconnues, alias fiables, diagnostic et réparation des données existantes.
2. **3.52.0 — Fiabiliser l'édition** : éditeur de champs corrigé, verrou contre les modifications simultanées, ressources hors catalogue conservées, écriture interdite aux profils « masqués ».
3. **3.53.0 — Identifiants de champs immuables + migrations numérotées** : la cause disparaît.
4. **Ensuite** : vocabulaires (statuts, types) pilotés par la configuration, ancien modèle à retirer, tests de bout en bout et contrôle automatique quotidien.
