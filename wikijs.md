# Parcours agents et élu(e)s

## Cartouche de version !

| Champ | Valeur |
| --- | --- |
| Version proposée | `2.6.0` |
| Statut | `À valider` |
| Date de mise à jour | `2026-03-25` |
| Périmètre | `Application complète` |
| Référence interne | `wikijs.md` |

> Règle de maintenance : à chaque modification fonctionnelle ou documentaire notable, mettre à jour au minimum la version, la date et, si besoin, le périmètre.

## Présentation

`Parcours agents et élu(e)s` est une application interne destinée à la commune pour suivre :

- l'arrivée d'un nouvel agent ou d'un(e) nouvel(le) élu(e)
- l'attribution de ressources
- les changements de service
- la restitution des ressources
- l'administration des comptes et des référentiels
- la traçabilité des actions

L'application est utilisée depuis un navigateur web et s'appuie sur une base SQLite.

## Accès à l'application

- URL locale habituelle : `http://127.0.0.1:5000/`
- authentification requise
- accès réservé aux utilisateurs habilités

La page de connexion permet de saisir :

- l'identifiant
- le mot de passe

## Tableau de bord

Le tableau de bord centralise les dossiers et permet de :

- rechercher un dossier
- filtrer par état, qualité et service
- ouvrir un dossier
- lancer une restitution
- exporter un PDF
- exporter plusieurs PDF
- supprimer plusieurs dossiers si le profil le permet

## Types de dossier

Les principaux contextes de dossier sont :

- `Nouvelle arrivée`
- `Changement de service`
- `Mise à jour de ressources`
- `Sortie / restitution`

La qualité de la personne reste gérée séparément :

- `Agent`
- `Élu(e)`

## Création d'un dossier

La création ou la mise à jour d'un dossier permet de renseigner :

- l'identité de la personne
- sa qualité
- son service ou son mandat
- son contexte de dossier
- les ressources attribuées par service
- la date et l'heure de remise
- la signature
- la validation RGPD

## Attribution des ressources

Les ressources sont regroupées par service émetteur.

Exemples :

- `DSI`
- `Bâtiment`
- tout autre service créé dans l'administration

Si une nouvelle ressource est créée avec un service émetteur spécifique, une section dédiée peut apparaître automatiquement dans le formulaire.

## Signature et validation

Un dossier peut rester en brouillon tant que :

- la signature n'est pas présente
- ou que la validation RGPD n'est pas cochée

Quand les conditions sont réunies :

- une attribution complète verrouille le dossier
- une attribution partielle laisse le dossier modifiable

## Restitution

La restitution se fait depuis une page dédiée.

Elle permet de renseigner :

- la date de restitution
- le motif
- les observations
- l'état de chaque ressource

Les informations de restitution restent visibles en lecture dans le dossier.

## Administration

Le menu d'administration permet de gérer :

- les utilisateurs
- les groupes
- les ressources attribuables
- le journal applicatif
- la corbeille administrateur

### Comptes utilisateurs

Selon les droits, il est possible de :

- créer un compte
- modifier un compte
- changer un mot de passe
- désactiver un compte
- supprimer un compte

### Ressources

Les ressources peuvent être :

- créées
- modifiées
- désactivées
- supprimées

Chaque ressource peut être liée à un service émetteur.

## Journal applicatif

Le journal des actions dispose d'une page dédiée.

Il permet de retrouver :

- les connexions et déconnexions
- les créations et mises à jour
- les suppressions
- les restaurations depuis la corbeille
- diverses actions système ou utilisateur

Une recherche texte permet de faciliter :

- le diagnostic
- le debug
- le forensic

## Corbeille administrateur

La corbeille est réservée au groupe `admin`.

Elle permet de restaurer certains éléments supprimés par erreur :

- dossiers
- utilisateurs
- ressources

## Rôles standards

- `lecture`
- `redaction`
- `gestion`
- `admin`

## Points d'attention

- le compte `admin` initial doit être sécurisé avant usage réel
- les droits doivent être attribués avec prudence
- la documentation doit être mise à jour à chaque évolution métier
- les suppressions sensibles doivent être vérifiées dans la corbeille

## Recommandations d'usage

- utiliser un navigateur récent
- vérifier les exports PDF avant diffusion
- réserver les suppressions massives aux profils autorisés
- consulter le journal en cas d'anomalie ou de doute sur une action

## Évolutions possibles

- meilleure harmonisation visuelle des pages
- filtres avancés dans le journal
- export du journal
- modularisation plus fine du backend
- renforcement éventuel de la sécurité d'accès selon les besoins de la commune
