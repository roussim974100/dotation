# Guide Utilisateur

## Objet

L'application permet de gerer :

- les dossiers d'attribution des agent(e)s et elu(e)s
- la signature de remise
- la validation RGPD
- la restitution des ressources materielles
- l'administration des comptes, des services et des ressources
- le journal des actions pour la tracabilite
- la restauration d'elements supprimes via la corbeille admin

## Connexion

1. Ouvrir `http://127.0.0.1:5000/`
2. Saisir l'identifiant et le mot de passe
3. Cliquer sur `Se connecter`

Si les identifiants sont incorrects, un message d'erreur s'affiche sur la page de connexion.

## Tableau de bord

Depuis l'accueil, il est possible de :

- creer un nouveau dossier
- rechercher un dossier existant
- filtrer par etat, qualite ou service
- ouvrir un dossier
- lancer une restitution sur une attribution active ou partielle
- exporter un `PDF dossier`
- exporter un `PDF restitution`
- exporter plusieurs `PDF dossier`
- exporter plusieurs `PDF restitution`
- supprimer plusieurs dossiers si le droit est present
- exporter les donnees en Excel

Le tableau de bord se met a jour automatiquement. Les nouveaux dossiers peuvent etre signales visuellement jusqu'a acquittement.

Les profils en consultation seule peuvent exporter les PDF, mais sans affichage des signatures.

## Creer un dossier

1. Cliquer sur `Nouveau dossier`
2. Renseigner l'identite de la personne
3. Choisir la qualite `Agent` ou `Elu(e)`
4. Choisir le type de dossier
5. Renseigner les ressources attribuees
6. Saisir la signature de remise si necessaire
7. Cocher la validation RGPD
8. Cliquer sur `Enregistrer`

Un dossier incomplet reste modifiable.

## Signature a distance

Depuis la fiche dossier, un gestionnaire peut :

- generer un lien de signature de remise
- generer un lien de signature de restitution
- copier le lien
- revoquer le lien
- regenerer le lien si necessaire

La personne qui ouvre ce lien peut uniquement :

- consulter le dossier
- prendre connaissance des ressources remises
- valider le RGPD
- signer

Le lien devient inutilisable apres validation.

## Reouverture d'un dossier

Quand un dossier encore modifiable est rouvert :

- la reouverture est tracee
- la date de derniere reouverture est conservee
- l'utilisateur ayant rouvert le dossier est memorise

## Restitution

La restitution se fait depuis le bouton `Restitution`.

Pour chaque materiel :

- choisir un etat rapide
- `Conforme`
- `Endommage`
- `Non restitue`
- `Perdu`
- `Autre`

Si l'etat n'est pas `Conforme`, un commentaire peut etre saisi.

La restitution comprend aussi :

- une date de restitution
- une signature de restitution
- ou un motif si la signature est impossible ou differee

Un `PDF restitution` peut etre exporte separement.

## Administration

Les administrateurs peuvent :

- gerer les comptes
- modifier les mots de passe
- gerer les services proposes dans les formulaires
- gerer les ressources attribuables
- consulter le journal
- acceder a la corbeille

L'administration est decoupee en sous-pages :

- `admin.html` pour la vue d'ensemble
- `admin-comptes.html` pour les comptes
- `admin-services.html` pour les services
- `admin-ressources.html` pour les ressources

## Groupe lecture

Le groupe `lecture` peut :

- consulter les dossiers
- exporter un `PDF dossier`
- exporter un `PDF restitution`

Le groupe `lecture` ne peut pas :

- modifier un dossier
- enregistrer une fiche
- saisir une restitution
- supprimer
- administrer l'application

Dans les PDF exportes par un profil `lecture`, les signatures sont masquees et remplacees par une mention reservee aux personnes autorisees.

## Journal

La page `Journal` permet de :

- rechercher dans les actions
- consulter les traces systeme et utilisateur
- faciliter le debug ou le forensic

## Corbeille

La corbeille est reservee aux administrateurs.

Elle permet de restaurer :

- un dossier supprime
- un utilisateur supprime
- une ressource supprimee

## Archives documentaires

Les versions documentaires sont archivees dans `administratif/versions/`.
Chaque version dispose de son propre dossier et de fichiers suffixes par la version.
