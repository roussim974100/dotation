# A quai

## Cartouche de version

| Champ | Valeur |
| --- | --- |
| Version proposee | `2.11.4` |
| Statut | `A valider` |
| Date de mise a jour | `2026-03-29` |
| Perimetre | `stabilisation du chargement des fiches + corrections d encodage et de typographie + ressources personnalisables et ordre par service + historiques dedies + harmonisation des e-mails prepares et PDF + archivage documentaire` |
| Reference interne | `wikijs.md` |

> Regle de maintenance : a chaque modification fonctionnelle ou documentaire notable, mettre a jour au minimum la version, la date et, si besoin, le perimetre.

## Presentation

`A quai` est une application interne destinee a la commune pour suivre :

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

Le tableau de bord centralise les dossiers en cours et permet de :

- rechercher un dossier
- filtrer par etat, qualite, service et pilotage
- ouvrir un dossier
- ouvrir une restitution
- exporter un `PDF dossier`
- exporter un `PDF restitution`
- preparer des e-mails
- supprimer plusieurs dossiers si le profil le permet

Des historiques dedies permettent maintenant de consulter :

- les dossiers termines
- les restitutions terminees

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

## Ressources personnalisables

L'administration des ressources permet de :

- definir une ressource materielle ou immaterielle
- choisir son service emetteur
- ajouter des champs personnalises
- regler son suivi a l'attribution
- la reordonner par service

## Restitution

La restitution est geree dans une page dediee.

Le flux permet de :

- choisir rapidement l'etat de chaque materiel
- saisir une date de restitution
- signer ou documenter l'absence de signature
- exporter un `PDF restitution`

## Exports

### PDF dossier

Le `PDF dossier` contient :

- les informations de la personne
- les ressources attribuees
- la validation RGPD
- la signature de remise

### PDF restitution

Le `PDF restitution` contient :

- les informations de la personne
- la date de restitution
- l'etat de chaque materiel restitue
- la signature de restitution ou le motif d'absence

### E-mails prepares

L'application peut preparer :

- des e-mails d'information
- des e-mails de signature
- des e-mails d'envoi de PDF

## Administration

L'administration permet de :

- gerer les comptes utilisateurs
- gerer les services
- gerer les ressources
- consulter le journal
- acceder a la corbeille
- personnaliser l'application

## Journal

Le journal permet de :

- consulter les actions systeme et utilisateur
- retrouver rapidement un dossier, un acteur ou une ressource
- faciliter le debug et le forensic

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
- signatures masquees dans les PDF

## Points d'attention

- definir une vraie valeur `APP_SECRET_KEY` en environnement de deploiement
- verifier les comportements critiques apres chaque evolution frontend
- maintenir a jour `version/versions/` et les fichiers Markdown racine a chaque release

