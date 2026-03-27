# Parcours agents et elu(e)s

## Cartouche de version

| Champ | Valeur |
| --- | --- |
| Version proposee | `2.9.0` |
| Statut | `A valider` |
| Date de mise a jour | `2026-03-27` |
| Perimetre | `Application complete + restitution avancee + tracabilite de reouverture + protection des signatures PDF + liens de signature remise et restitution + admin en sous-pages + services administrables + archivage documentaire` |
| Reference interne | `wikijs.md` |

> Regle de maintenance : a chaque modification fonctionnelle ou documentaire notable, mettre a jour au minimum la version, la date et, si besoin, le perimetre.

## Presentation

`Parcours agents et elu(e)s` est une application interne destinee a la commune pour suivre :

- l'arrivee d'un nouvel agent ou d'un(e) nouvel(le) elu(e)
- l'attribution de ressources
- les changements de service
- la restitution des ressources
- l'administration des comptes, des services et des referentiels
- la tracabilite des actions

L'application est utilisee depuis un navigateur web et s'appuie sur une base SQLite.

## Acces a l'application

- URL locale habituelle : `http://127.0.0.1:5000/`
- authentification requise
- acces reserve aux utilisateurs habilites

La page de connexion permet de saisir :

- l'identifiant
- le mot de passe

En cas d'erreur :

- un message s'affiche si les identifiants sont incorrects
- un message specifique s'affiche si la session ne peut pas etre conservee

## Tableau de bord

Le tableau de bord centralise les dossiers et permet de :

- rechercher un dossier
- filtrer par etat, qualite et service
- ouvrir un dossier
- lancer une restitution
- exporter un `PDF dossier`
- exporter un `PDF restitution`
- exporter plusieurs `PDF dossier`
- exporter plusieurs `PDF restitution`
- supprimer plusieurs dossiers si le profil le permet

Depuis la fiche, un profil autorise peut aussi generer un lien unique de signature a distance.
Depuis la restitution et le tableau de bord, un profil autorise peut aussi generer un lien unique de signature de restitution.

Les profils en consultation seule peuvent exporter les PDF, mais les signatures y sont masquees.

Un rafraichissement automatique est present, avec :

- signal visuel des nouveaux dossiers
- badge de nouveaux dossiers
- acquittement utilisateur `J'ai vu`
- conservation de la selection pendant le refresh

## Dossiers

Les types de dossier actuellement proposes sont :

- `Nouvelle arrivee`
- `Changement de service`
- `Mise a jour de ressources`
- `Sortie / restitution`

Un dossier peut contenir :

- les informations d'identite
- la qualite `Agent` ou `Elu(e)`
- le service ou le mandat
- les ressources materielles et immaterielles attribuees
- la signature de remise
- la validation RGPD
- un lien de signature a distance

## Tracabilite de reouverture

Quand un dossier encore modifiable est rouvert :

- la reouverture est comptee
- la date de derniere reouverture est memorisee
- l'utilisateur qui a rouvert le dossier est memorise

Ces informations sont visibles dans la fiche et tracees cote backend.

## Signature a distance

Depuis la fiche dossier, un utilisateur autorise peut :

- generer un lien de signature
- copier le lien
- revoquer le lien
- regenerer un lien

Le lien permet a la personne concernee de :

- consulter les ressources remises
- prendre connaissance du RGPD
- signer sans compte applicatif

Regles de base :

- un seul lien actif par dossier
- lien a usage unique
- expiration automatique
- revocation manuelle possible

## Restitution

La restitution est geree dans une page dediee.

Le flux permet de :

- choisir rapidement l'etat de chaque materiel
- utiliser les etats `Conforme`, `Endommage`, `Non restitue`, `Perdu`, `Autre`
- ajouter un commentaire seulement si necessaire
- saisir une date de restitution
- ajouter une signature de restitution
- ou indiquer qu'elle est impossible ou differee avec motif

La restitution reste modifiable tant qu'un materiel est `Non restitue`.

## Exports

### PDF dossier

Le `PDF dossier` sert de document de remise.

Il contient :

- les informations de la personne
- les ressources attribuees
- la validation RGPD
- la signature de remise
- la date de signature

Pour un profil non autorise a consulter les signatures, le PDF reste exportable mais la signature est masquee et remplacee par une mention reservee aux personnes autorisees.

### PDF restitution

Le `PDF restitution` est un document distinct.

Il contient :

- les informations de la personne
- la date de restitution
- l'etat de chaque materiel restitue
- les commentaires d'anomalie
- la signature de restitution ou le motif d'absence

Pour un profil non autorise a consulter les signatures, la signature de restitution est masquee dans le document exporte.

### Export multiple

Les exports multiples produisent des ZIP :

- `PDF dossiers selectionnes`
- `PDF restitutions selectionnees`

Une fenetre de chargement avec progression est affichee pendant la preparation.

## Administration

L'administration permet de :

- gerer les comptes utilisateurs
- modifier les mots de passe
- gerer la liste des services proposes dans les formulaires
- gerer les ressources attribuables
- consulter le journal
- acceder a la corbeille

L'administration est organisee en sous-pages :

- `admin.html` pour la vue d'ensemble
- `admin-comptes.html` pour les comptes et les droits
- `admin-services.html` pour les services
- `admin-ressources.html` pour les ressources

## Archivage documentaire

Les versions documentaires sont archivees dans :

- `administratif/versions/`

Chaque version dispose de son propre dossier avec des fichiers nommes par version.
Les anciennes versions archivees sont distinguees entre :

- `archive reconstituee`
- `snapshot courant`

## Journal

Le journal est disponible dans une page dediee.

Il permet de :

- consulter les actions systeme et utilisateur
- rechercher un element precis
- faciliter le debug ou le forensic

## Corbeille

La corbeille est reservee au groupe `admin`.

Elle permet de restaurer :

- un dossier supprime
- un utilisateur supprime
- une ressource supprimee

## Roles

### Admin

- acces complet
- administration
- journal
- corbeille

### Lecture

- consultation uniquement
- export PDF autorise
- aucune saisie
- aucune restitution
- aucun enregistrement
- aucune suppression
- signatures masquees dans les PDF

## Points d'attention

- definir une vraie valeur `APP_SECRET_KEY` en environnement de deploiement
- verifier le comportement mobile sur les terminaux reels
- effectuer une recette complete apres toute evolution importante

## Evolutions possibles

- regles plus fines sur les ressources par service
- vue personne consolidee
- audit encore plus detaille
- parametrage plus avance des restitutions
