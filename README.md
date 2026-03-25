# Parcours agents et élu(e)s

Application interne de gestion des dossiers d'attribution et des restitutions pour une collectivité.

## Ce que fait l'application

- créer un dossier pour un agent ou un(e) élu(e)
- enregistrer un dossier en brouillon ou en attribution partielle
- verrouiller un dossier complet une fois signé et validé RGPD
- suivre la restitution des ressources attribuées
- administrer les comptes, les groupes et les ressources attribuables
- consulter un journal des actions pour la traçabilité
- restaurer des suppressions via une corbeille réservée aux admins
- exporter les dossiers en PDF et les données en CSV

## Types de dossier

- `arrivee` : nouvelle arrivée
- `changement_service` : mobilité interne
- `mise_a_jour` : mise à jour de ressources
- `sortie` : sortie ou restitution

## Documents du projet

- `LIVRAISON.md` : vue de remise du projet
- `GUIDE_UTILISATEUR.md` : guide d'usage rapide
- `RECETTE_FONCTIONNELLE.md` : checklist et scénarios de test

## Architecture

- `frontend/` : interface HTML, CSS et JavaScript servie par Flask
- `backend/` : API Flask, authentification et persistance SQLite

## Fichiers principaux

- `frontend/index.html` : tableau de bord des dossiers
- `frontend/form.html` : création et mise à jour d'un dossier
- `frontend/restitution.html` : restitution détaillée
- `frontend/admin.html` : administration des comptes et des ressources
- `frontend/logs.html` : journal des actions
- `frontend/trash.html` : corbeille administrateur
- `frontend/login.html` : connexion
- `frontend/js/storage.js` : accueil, liste, exports et appels API communs
- `frontend/js/app.js` : logique métier du formulaire principal
- `frontend/js/restitution.js` : logique de restitution
- `frontend/js/admin.js` : logique d'administration
- `frontend/js/logs.js` : consultation du journal applicatif
- `frontend/css/style.css` : styles communs
- `backend/app.py` : backend Flask et règles métier principales
- `backend/users.json` : comptes et groupes locaux
- `backend/dotation.db` : base SQLite générée au runtime

## Lancement

Depuis la racine du projet :

```powershell
python backend\app.py
```

Puis ouvrir :

```text
http://127.0.0.1:5000/
```

## Compte initial

- identifiant : `admin`
- mot de passe : `admin123!`

Il est recommandé de modifier ce mot de passe avant tout usage réel.

## Statuts de dossier

- `draft` : brouillon
- `partial_assignment` : attribution partielle, encore modifiable
- `active` : attribution complète signée, verrouillée
- `returned` : restitution terminée
- `partial_return` : restitution partielle
- `cancelled` : dossier annulé

## Règles de sauvegarde

- sans signature ou sans validation RGPD, le dossier reste en brouillon
- avec signature et validation RGPD, l'utilisateur choisit une attribution complète ou partielle
- une attribution complète passe en `active` et devient verrouillée
- une attribution partielle reste modifiable

## Restitution

La restitution se fait depuis l'accueil, sur un dossier `active`.

La page dédiée permet de renseigner :

- la date
- le motif
- les observations
- l'état de chaque ressource

Les informations de restitution restent ensuite visibles en lecture dans le dossier.

## Administration

Les profils autorisés peuvent :

- créer, modifier, désactiver ou supprimer un compte
- changer le mot de passe d'un compte
- affecter un compte à un ou plusieurs groupes
- créer, modifier, désactiver ou supprimer une ressource attribuable
- consulter les groupes et leurs droits
- consulter le journal des actions
- consulter et restaurer les éléments supprimés depuis la corbeille admin

Le journal et la corbeille sont regroupés dans le menu d'administration.

## Groupes standards

- `lecture` : consultation avec données sensibles masquées
- `redaction` : création et modification de dossiers
- `gestion` : rédaction, restitution, suppression
- `admin` : contrôle total et gestion des utilisateurs

## Exports

### PDF

- export unitaire depuis la liste
- export multiple par sélection
- export multiple téléchargé sous forme de ZIP

### CSV

- export global depuis l'accueil
- fichier compatible Excel

## Données et stockage

La base SQLite contient principalement :

- `dotation_forms` : dossier principal et payload JSON complet
- `dotation_items` : vision normalisée par ressource
- `persons` : personnes suivies
- `onboarding_dossiers` : dossiers rattachés aux personnes
- `resource_catalog` : ressources attribuables
- `audit_events` : audit lié aux dossiers
- `app_logs` : journal applicatif global

## Journal applicatif

Le journal est accessible sur `logs.html` pour les profils ayant le droit `users.manage`.

Il trace notamment :

- connexions et déconnexions
- créations, mises à jour et suppressions de dossiers
- restitutions
- actions d'administration sur les comptes
- actions d'administration sur les ressources

## Corbeille administrateur

La corbeille est accessible sur `trash.html` uniquement pour le groupe `admin`.

Elle permet de restaurer :

- un dossier supprimé
- un utilisateur supprimé
- une ressource supprimée

## Recommandations de maintenance

- garder les règles métier centralisées dans `backend/app.py`
- vérifier les droits côté backend et côté interface
- conserver la cohérence des libellés entre frontend et backend
- faire évoluer la documentation à chaque suppression ou ajout de fonctionnalité

## Pistes d'évolution

- remplacer les `alert()` et `confirm()` par de vraies modales
- ajouter des filtres avancés dans le journal
- exporter le journal en CSV
- découper le backend en modules plus fins
- ajouter des tests automatiques backend
