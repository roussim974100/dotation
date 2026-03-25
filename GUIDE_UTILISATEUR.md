# Guide Utilisateur

## Objet

L'application permet de gérer :

- les dossiers d'attribution des agent(e)s et élu(e)s
- la signature de remise
- la validation RGPD
- la restitution des ressources
- l'administration des comptes et des ressources
- le journal des actions pour la traçabilité
- la restauration d'éléments supprimés via la corbeille admin

## Connexion

1. Ouvrir `http://127.0.0.1:5000/`
2. Saisir l'identifiant et le mot de passe
3. Cliquer sur `Se connecter`

## Tableau de bord

Depuis l'accueil, il est possible de :

- créer un nouveau dossier
- rechercher un dossier existant
- filtrer par état, qualité ou service
- ouvrir un dossier
- lancer une restitution sur une attribution active
- exporter un PDF
- exporter plusieurs PDF
- supprimer plusieurs dossiers si le droit est présent
- exporter les données en CSV

## Créer un dossier

1. Cliquer sur `Nouveau dossier`
2. Choisir le type de dossier
3. Renseigner l'identité de la personne
4. Choisir la qualité `Agent` ou `Élu(e)`
5. Renseigner le service ou le mandat
6. Saisir les ressources attribuées
7. Faire signer la fiche
8. Cocher la validation RGPD
9. Cliquer sur `Enregistrer`

## Statuts

- `Brouillon` : dossier non finalisé, encore modifiable
- `Attribution partielle` : dossier incomplet, encore modifiable
- `Attribution active` : dossier complet signé, verrouillé
- `Restitution terminée` : restitution terminée
- `Restitution partielle` : restitution partielle
- `Dossier annulé` : dossier sans suite

## Restitution

Depuis l'accueil :

1. Repérer un dossier en `Attribution active`
2. Cliquer sur `Restitution`
3. Renseigner la date, le motif et les observations
4. Indiquer l'état de chaque ressource
5. Enregistrer

Les informations de restitution restent ensuite consultables dans le dossier.

## Administration

Les profils autorisés peuvent :

- créer un utilisateur
- modifier un utilisateur
- changer son mot de passe
- activer ou désactiver un compte
- supprimer un compte
- affecter un utilisateur à un ou plusieurs groupes
- créer une ressource attribuable
- modifier une ressource
- désactiver ou supprimer une ressource
- restaurer un élément supprimé depuis la corbeille

Le `Journal` et la `Corbeille` sont accessibles depuis le menu d'administration.

## Journal

La page `logs.html` permet de consulter le journal applicatif.

Elle sert à :

- retrouver qui a fait une action
- vérifier les opérations sur les dossiers
- suivre les actions d'administration
- faciliter le debug ou l'analyse d'un incident

Une recherche texte est disponible sur cette page.

## Corbeille

La page `trash.html` est réservée au groupe `admin`.

Elle permet de restaurer :

- un dossier supprimé
- un utilisateur supprimé
- une ressource supprimée

## Bonnes pratiques

- enregistrer le dossier dès que les informations essentielles sont saisies
- vérifier la date de remise réelle avant validation
- utiliser l'export CSV pour la sauvegarde régulière
- vérifier le journal après une opération sensible ou un incident
- vérifier la corbeille avant de recréer manuellement un élément supprimé
- changer le mot de passe administrateur initial avant déploiement réel
